"""BridgeService: the transport-independent surface the UI talks to.

Pure Python (stdlib only). Every method is thread-safe, quick, and returns JSON-safe data
or raises BridgeError. Transports (FastAPI today, anything later) are thin adapters.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..backend import ExecutionBackend
from ai.chat_service import ChatService
from ..errors import InvalidGoalError, ManagerClosedError, QueueFullError, TaskNotFoundError
from ..manager import BackgroundTaskManager, PlannerFactory, TaskEvent
from ..models import TERMINAL_STATUSES, TaskLimits, TaskStatus
from ..policy import ActionPolicy
from ..verification import Verifier
from .confirmations import ConfirmationBroker
from .cursor_control import CursorControlTasks
from .events import EventHub, Frame, Subscription
from .execution import (EXECUTION_ENVIRONMENTS, ExecutionMode, Submission, TaskDispatcher)
from .protocol import MAX_WS_CONNECTIONS, PROTOCOL_VERSION, BridgeError, ErrorCode
from .security import BridgeAuth

log = logging.getLogger("background_agent.bridge")
PROGRESS_MIN_INTERVAL_SECONDS = 0.25
MAX_LIST_LIMIT = 500
MAX_TRACKED_MODES = 500


class BridgeService:
    def __init__(self, manager: BackgroundTaskManager, broker: ConfirmationBroker, hub: EventHub,
                 auth: BridgeAuth, backend_name: str = "", *,
                 cursor_control: Optional[CursorControlTasks] = None,
                 chat_service: Optional[ChatService] = None) -> None:
        self.manager, self.broker, self.hub, self.auth = manager, broker, hub, auth
        self._backend_name = backend_name
        self.chat_service = chat_service
        self.cursor_control = cursor_control or CursorControlTasks()
        self.dispatcher = TaskDispatcher({
            ExecutionMode.TASK_DOING: self._submit_managed,
            ExecutionMode.BACKGROUND_TASK: self._submit_managed,
            ExecutionMode.CURSOR_CONTROL: self._submit_cursor_control,
        })
        self._lock = threading.Lock()
        self._last_progress: Dict[str, float] = {}
        self._last_activity: Optional[Dict[str, Any]] = None
        self._connections = 0
        self._closed = False
        self._task_modes: Dict[str, ExecutionMode] = {}
        broker.on_event = self._on_confirmation_event
        manager.subscribe(self._on_task_event)

    @classmethod
    def create(cls, backend: ExecutionBackend, planner_factory: PlannerFactory, *,
               policy: Optional[ActionPolicy] = None, verifier: Optional[Verifier] = None,
               default_limits: Optional[TaskLimits] = None, max_queued: int = 20, max_history: int = 200,
               confirmation_timeout: float = 120.0, token: Optional[str] = None,
               allowed_origins: Optional[Iterable[str]] = None, hub_buffer: int = 1000,
               cursor_control: Optional[CursorControlTasks] = None,
               chat_service: Optional[ChatService] = None) -> "BridgeService":
        hub = EventHub(hub_buffer)
        broker = ConfirmationBroker(timeout_seconds=confirmation_timeout)
        manager = BackgroundTaskManager(backend, planner_factory, policy=policy, verifier=verifier,
                                        confirmation_handler=broker, default_limits=default_limits,
                                        max_queued=max_queued, max_history=max_history)
        return cls(manager, broker, hub, BridgeAuth(token, allowed_origins),
                   getattr(backend, "name", ""), cursor_control=cursor_control, chat_service=chat_service)

    def start(self) -> None:
        self.manager.start()

    def shutdown(self, timeout: float = 10.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.hub.publish("shutdown", {})
        # Order matters: cancel tasks FIRST. A blocked worker notices its cancelled token within
        # one poll interval and the broker dismisses the prompt as "cancelled". Declining prompts
        # first would let a task carry on, finish and end COMPLETED instead of CANCELLED.
        self.manager.shutdown(timeout=timeout)
        self.cursor_control.shutdown(timeout=timeout)
        self.broker.shutdown()                      # sweep: refuse new prompts, decline leftovers
        self.hub.close()

    # ---- commands --------------------------------------------------------
    def submit(self, goal: Any, execution_mode: Any = None) -> Submission:
        submission = self.dispatcher.dispatch(goal, execution_mode)
        self._remember_mode(submission.task.get("id"), submission.execution_mode)
        return submission

    def submit_task(self, goal: Any, execution_mode: Any = None) -> Dict[str, Any]:
        return self.submit(goal, execution_mode).task

    def chat(self, conversation_id: Any, message: Any) -> Dict[str, str]:
        """Send a chat turn without invoking the task planner or desktop operator."""
        if self.chat_service is None:
            raise BridgeError(ErrorCode.SERVICE_UNAVAILABLE, "Ruby chat is not configured.")
        try:
            return self.chat_service.send(conversation_id, message)
        except ValueError as exc:
            raise BridgeError(ErrorCode.BAD_REQUEST, str(exc)) from None
        except Exception:
            log.exception("Ruby conversational request failed")
            raise BridgeError(ErrorCode.SERVICE_UNAVAILABLE,
                              "Ruby could not answer right now. Check Gemini configuration and try again.") from None

    def _submit_managed(self, goal: str) -> Dict[str, Any]:
        try:
            return self.manager.submit(goal).snapshot()
        except InvalidGoalError as exc:
            raise BridgeError(ErrorCode.INVALID_GOAL, str(exc)) from None
        except QueueFullError as exc:
            raise BridgeError(ErrorCode.QUEUE_FULL, str(exc)) from None
        except ManagerClosedError:
            raise BridgeError(ErrorCode.SHUTTING_DOWN, "Ruby is shutting down") from None

    def _submit_cursor_control(self, goal: str) -> Dict[str, Any]:
        try:
            return self.cursor_control.submit(goal)
        except RuntimeError:
            raise BridgeError(ErrorCode.SHUTTING_DOWN, "Ruby is shutting down") from None

    def list_tasks(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        wanted = None
        if status:
            try:
                wanted = TaskStatus(status).value
            except ValueError:
                raise BridgeError(ErrorCode.BAD_REQUEST, f"unknown status {status!r}") from None
        limit = max(1, min(int(limit), MAX_LIST_LIMIT))
        tasks = self._snapshots()
        if wanted is not None:
            tasks = [task for task in tasks if task.get("status") == wanted]
        return tasks[:limit]

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._with_mode(self._task(task_id).snapshot())

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        try:
            task = self.manager.get(task_id)
        except TaskNotFoundError:
            accepted = self.cursor_control.cancel(task_id)
            task = self.cursor_control.get(task_id)
            if task is None:
                raise BridgeError(ErrorCode.NOT_FOUND, "no such task") from None
        else:
            accepted = self.manager.cancel(task_id)
        return {"accepted": accepted, "task": self._with_mode(task.snapshot())}

    def respond_confirmation(self, confirmation_id: str, approved: Any) -> Dict[str, Any]:
        if not isinstance(approved, bool):
            raise BridgeError(ErrorCode.BAD_REQUEST, "'approved' must be true or false")
        out = self.broker.respond(confirmation_id, approved)
        return {"id": out.id, "applied": out.applied, "resolution": out.resolution}

    def pending_confirmations(self) -> List[Dict[str, Any]]:
        return self.broker.pending()

    def reset_backend_quarantine(self) -> Dict[str, Any]:
        self.manager.reset_quarantine()
        self._publish_activity_if_changed(force=True)
        return {"quarantine": self.manager.quarantine_reason}

    # ---- state / stream ----------------------------------------------------
    def activity(self) -> Dict[str, Any]:
        tasks = self._snapshots()
        queued = sum(task.get("status") == TaskStatus.QUEUED.value for task in tasks)
        running = sum(task.get("status") in (TaskStatus.RUNNING.value, TaskStatus.VERIFYING.value)
                      for task in tasks)
        awaiting = len(self.broker.pending())
        state = ("needs_confirmation" if awaiting else "running" if running else
                 "queued" if queued else "idle")
        return {"state": state, "queued": queued, "running": running, "awaiting_confirmation": awaiting}

    def state(self) -> Dict[str, Any]:
        """Full snapshot used for initial sync and resync."""
        return {"tasks": self.list_tasks(limit=MAX_LIST_LIMIT), "confirmations": self.broker.pending(),
                "activity": self.activity(),
                "backend": {"name": self._backend_name, "quarantine": self.manager.quarantine_reason},
                "server": {"protocol": PROTOCOL_VERSION, "epoch": self.hub.epoch, "seq": self.hub.last_seq}}

    def open_event_stream(self, epoch: Optional[str] = None, last_seq: Optional[int] = None, *,
                          on_ready: Optional[Callable[[], None]] = None, maxsize: int = 256
                          ) -> Tuple[Subscription, List[Frame]]:
        """Returns (live subscription, frames to send first). Events are absolute states, so a
        client may safely apply them in order even if hello's snapshot is slightly newer."""
        sub, replay, seq = self.hub.subscribe(epoch=epoch, last_seq=last_seq, maxsize=maxsize, on_ready=on_ready)
        resync = replay is None
        hello: Frame = {"v": PROTOCOL_VERSION, "type": "hello", "seq": seq, "epoch": self.hub.epoch,
                        "resync": resync, "data": self.state() if resync else None}
        return sub, [hello, *(replay or [])]

    def try_acquire_connection(self) -> bool:
        with self._lock:
            if self._connections >= MAX_WS_CONNECTIONS or self._closed:
                return False
            self._connections += 1
            return True

    def release_connection(self) -> None:
        with self._lock:
            self._connections = max(0, self._connections - 1)

    # ---- internals -----------------------------------------------------------
    def _snapshots(self) -> List[Dict[str, Any]]:
        """All tasks (managed + cursor control), newest first."""
        snapshots = [self._with_mode(task.snapshot()) for task in self.manager.list_tasks()]
        snapshots.extend(self.cursor_control.list_snapshots())
        snapshots.sort(key=lambda task: task.get("created_at") or "", reverse=True)
        return snapshots

    def _with_mode(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        mode = self._task_modes.get(snapshot.get("id"))
        if mode is None:
            return snapshot
        decorated = dict(snapshot)
        decorated["execution_mode"] = mode.value
        decorated["execution_environment"] = EXECUTION_ENVIRONMENTS[mode]
        return decorated

    def _remember_mode(self, task_id: Any, mode: ExecutionMode) -> None:
        if not isinstance(task_id, str) or not task_id:
            return
        with self._lock:
            self._task_modes[task_id] = mode
            while len(self._task_modes) > MAX_TRACKED_MODES:
                self._task_modes.pop(next(iter(self._task_modes)))

    def _task(self, task_id: str):
        try:
            return self.manager.get(task_id)
        except TaskNotFoundError:
            task = self.cursor_control.get(task_id)
            if task is None:
                raise BridgeError(ErrorCode.NOT_FOUND, "no such task") from None
            return task

    def _on_task_event(self, ev: TaskEvent) -> None:  # manager dispatcher thread
        if ev.type == "progress":
            now = time.monotonic()
            with self._lock:
                if now - self._last_progress.get(ev.task_id, 0.0) < PROGRESS_MIN_INTERVAL_SECONDS:
                    return
                self._last_progress[ev.task_id] = now
        self.hub.publish("task", {"change": ev.type, "task": self._with_mode(ev.snapshot)},
                         droppable=(ev.type == "progress"))
        if ev.status in TERMINAL_STATUSES and ev.type == "status":
            with self._lock:
                self._last_progress.pop(ev.task_id, None)
        if ev.type == "status":
            self._publish_activity_if_changed()

    def _on_confirmation_event(self, event_type: str, payload: Dict[str, Any]) -> None:  # worker thread
        self.hub.publish(event_type, payload)
        self._publish_activity_if_changed()

    def _publish_activity_if_changed(self, force: bool = False) -> None:
        current = self.activity()
        with self._lock:
            if not force and current == self._last_activity:
                return
            self._last_activity = current
        self.hub.publish("activity", current)
