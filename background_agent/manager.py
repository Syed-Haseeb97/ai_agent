"""BackgroundTaskManager: queue, scheduling, supervision, cancellation, cleanup.

Threads:
  * scheduler   - starts queued tasks while the backend's concurrency budget allows
  * run thread  - one per active task; supervises a worker thread, then cleans up
  * worker      - runs BackgroundWorker.run (daemon so a wedged worker cannot block exit)
  * dispatcher  - delivers task events to subscribers in order (listeners never run
                  under task/manager locks)
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

from .backend import ExecutionBackend, ExecutionEnvironment
from .cancellation import CancelReason, CancelToken
from .errors import (InvalidGoalError, ManagerClosedError, QueueFullError, TaskNotFoundError)
from .models import (BackgroundTask, FailureCode, TERMINAL_STATUSES, TaskError, TaskLimits,
                     TaskStatus)
from .planner import Planner
from .policy import ActionPolicy, ConfirmationHandler, DefaultActionPolicy, deny_all_confirmations
from .verification import DefaultVerifier, Verifier
from .worker import BackgroundWorker, WorkerOutcome

log = logging.getLogger("background_agent")

MAX_GOAL_LENGTH = 4000
PlannerFactory = Callable[[BackgroundTask], Planner]


@dataclass(frozen=True)
class TaskEvent:
    type: str  # "status" | "progress" | "cancel_requested"
    task_id: str
    status: TaskStatus
    snapshot: Dict[str, Any]


Listener = Callable[[TaskEvent], None]


class BackgroundTaskManager:
    def __init__(self, backend: ExecutionBackend, planner_factory: PlannerFactory, *,
                 policy: Optional[ActionPolicy] = None, verifier: Optional[Verifier] = None,
                 confirmation_handler: ConfirmationHandler = deny_all_confirmations,
                 default_limits: Optional[TaskLimits] = None, max_queued: int = 20,
                 max_history: int = 200) -> None:
        self._backend = backend
        self._planner_factory = planner_factory
        self._default_limits = default_limits or TaskLimits()
        self._max_queued = max_queued
        self._max_history = max_history
        self._worker = BackgroundWorker(policy=policy or DefaultActionPolicy(),
                                        verifier=verifier or DefaultVerifier(),
                                        confirmation_handler=confirmation_handler)
        self._cond = threading.Condition()
        self._tasks: "OrderedDict[str, BackgroundTask]" = OrderedDict()
        self._queue: Deque[BackgroundTask] = deque()
        self._tokens: Dict[str, CancelToken] = {}
        self._run_threads: Dict[str, threading.Thread] = {}
        self._active = 0
        self._closing = False
        self._scheduler: Optional[threading.Thread] = None
        self._quarantine: Optional[str] = None
        self._listeners: List[Listener] = []
        self._events: "queue.Queue[Optional[TaskEvent]]" = queue.Queue()
        self._dispatcher = threading.Thread(target=self._dispatch_loop, name="bg-dispatch", daemon=True)
        self._dispatcher.start()

    def start(self) -> None:
        with self._cond:
            if self._closing:
                raise ManagerClosedError("manager is shut down")
            if self._scheduler is None:
                self._scheduler = threading.Thread(target=self._scheduler_loop, name="bg-scheduler", daemon=True)
                self._scheduler.start()

    def __enter__(self) -> "BackgroundTaskManager":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.shutdown()

    def shutdown(self, timeout: float = 10.0) -> None:
        with self._cond:
            if self._closing:
                return
            self._closing = True
            queued = list(self._queue)
            self._queue.clear()
            tokens = list(self._tokens.values())
            self._cond.notify_all()
        for task in queued:
            task.try_transition(TaskStatus.CANCELLED, "Cancelled: Ruby is shutting down")
        for token in tokens:
            token.cancel(CancelReason.SHUTDOWN)
        deadline = time.monotonic() + timeout
        if self._scheduler is not None:
            self._scheduler.join(max(0.0, deadline - time.monotonic()))
        for thread in list(self._run_threads.values()):
            thread.join(max(0.0, deadline - time.monotonic()))
        self._events.put(None)
        self._dispatcher.join(max(0.0, deadline - time.monotonic()))

    def submit(self, goal: str, limits: Optional[TaskLimits] = None) -> BackgroundTask:
        goal = self._validate_goal(goal)
        with self._cond:
            if self._closing:
                raise ManagerClosedError("manager is shut down")
            if len(self._queue) >= self._max_queued:
                raise QueueFullError(f"queue is full ({self._max_queued} pending tasks)")
            task = BackgroundTask(goal, limits or self._default_limits, observer=self._on_task_event)
            self._tasks[task.id] = task
            self._tokens[task.id] = CancelToken()
            task.transition(TaskStatus.QUEUED, "Queued")
            self._queue.append(task)
            self._cond.notify_all()
        return task

    def get(self, task_id: str) -> BackgroundTask:
        with self._cond:
            try:
                return self._tasks[task_id]
            except KeyError:
                raise TaskNotFoundError(task_id) from None

    def list_tasks(self, statuses: Optional[Iterable[TaskStatus]] = None) -> List[BackgroundTask]:
        wanted = set(statuses) if statuses is not None else None
        with self._cond:
            tasks = list(self._tasks.values())
        tasks.reverse()
        return [t for t in tasks if wanted is None or t.status in wanted]

    def wait(self, task_id: str, timeout: Optional[float] = None) -> bool:
        return self.get(task_id).wait(timeout)

    def cancel(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task.is_terminal:
            return False
        with self._cond:
            token = self._tokens.get(task_id)
            was_queued = task in self._queue
            if was_queued:
                self._queue.remove(task)
        accepted = token.cancel(CancelReason.USER) if token else False
        task.flag_cancel_requested()
        if task.status in (TaskStatus.CREATED, TaskStatus.QUEUED):
            if task.try_transition(TaskStatus.CANCELLED, "Cancelled before it started"):
                self._forget(task_id)
                return True
            return False
        return accepted

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._cond:
            self._listeners.append(listener)
        def unsubscribe() -> None:
            with self._cond:
                if listener in self._listeners:
                    self._listeners.remove(listener)
        return unsubscribe

    @property
    def quarantine_reason(self) -> Optional[str]:
        return self._quarantine

    def reset_quarantine(self) -> None:
        with self._cond:
            self._quarantine = None
            self._cond.notify_all()

    @staticmethod
    def _validate_goal(goal: Any) -> str:
        if not isinstance(goal, str):
            raise InvalidGoalError("goal must be a string")
        goal = goal.strip()
        if not goal:
            raise InvalidGoalError("goal must not be empty")
        if len(goal) > MAX_GOAL_LENGTH:
            raise InvalidGoalError(f"goal is longer than {MAX_GOAL_LENGTH} characters")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in goal):
            raise InvalidGoalError("goal contains control characters")
        return goal

    def _on_task_event(self, task_id: str, event_type: str, snapshot: Dict[str, Any]) -> None:
        self._events.put(TaskEvent(event_type, task_id, TaskStatus(snapshot["status"]), snapshot))

    def _dispatch_loop(self) -> None:
        while True:
            event = self._events.get()
            if event is None:
                return
            with self._cond:
                listeners = list(self._listeners)
            for listener in listeners:
                try:
                    listener(event)
                except Exception:
                    log.exception("task listener failed")

    def _scheduler_loop(self) -> None:
        with self._cond:
            while True:
                if self._closing:
                    return
                limit = max(1, int(getattr(self._backend, "max_concurrency", 1) or 1))
                if self._queue and self._active < limit:
                    task = self._queue.popleft()
                    token = self._tokens.get(task.id)
                    if task.status is not TaskStatus.QUEUED or token is None:
                        continue
                    self._active += 1
                    thread = threading.Thread(target=self._run_task, args=(task, token),
                                              name=f"bg-task-{task.id[:8]}", daemon=True)
                    self._run_threads[task.id] = thread
                    thread.start()
                    continue
                self._cond.wait()

    def _forget(self, task_id: str) -> None:
        with self._cond:
            self._tokens.pop(task_id, None)
            terminal = [tid for tid, t in self._tasks.items() if t.status in TERMINAL_STATUSES]
            for tid in terminal[: max(0, len(terminal) - self._max_history)]:
                del self._tasks[tid]

    def _run_task(self, task: BackgroundTask, token: CancelToken) -> None:
        env: Optional[ExecutionEnvironment] = None
        try:
            try:
                outcome, env = self._execute_task(task, token)
            except Exception as exc:
                log.exception("task runner crashed")
                outcome = WorkerOutcome(TaskStatus.FAILED, "Internal error",
                                        TaskError(FailureCode.WORKER_EXCEPTION,
                                                  f"{type(exc).__name__}: {exc}"[:500]))
            if env is not None and not self._cleanup_environment(env, task):
                reason = f"environment for task {task.id} could not be cleaned up"
                with self._cond:
                    self._quarantine = reason
                log.error("backend quarantined: %s", reason)
            if outcome is not None:
                task.set_outputs(outcome.outputs)
                task.try_transition(outcome.status, outcome.message,
                                    error=outcome.error, result=outcome.result)
        finally:
            self._forget(task.id)
            with self._cond:
                self._run_threads.pop(task.id, None)
                self._active -= 1
                self._cond.notify_all()

    def _execute_task(self, task: BackgroundTask, token: CancelToken):
        if task.status is not TaskStatus.QUEUED:
            return None, None
        if token.is_cancelled:
            return WorkerOutcome(TaskStatus.CANCELLED, "Cancelled before it started"), None
        if self._quarantine:
            return self._unavailable(f"Backend is quarantined: {self._quarantine}"), None
        try:
            status = self._backend.check_available()
        except Exception as exc:
            return self._unavailable(f"Backend check failed: {type(exc).__name__}: {exc}"), None
        if not status.available:
            return self._unavailable(status.detail or "Execution backend is unavailable"), None
        if not task.try_transition(TaskStatus.RUNNING, "Starting"):
            return None, None
        try:
            env = self._backend.open_environment(task.id)
        except Exception as exc:
            msg = f"Could not open execution environment: {type(exc).__name__}: {exc}"[:500]
            return WorkerOutcome(TaskStatus.FAILED, msg, TaskError(FailureCode.BACKEND_FAILURE, msg)), None
        try:
            planner = self._planner_factory(task)
        except Exception as exc:
            msg = f"Could not create planner: {type(exc).__name__}: {exc}"[:500]
            return WorkerOutcome(TaskStatus.FAILED, msg, TaskError(FailureCode.PLANNER_ERROR, msg)), env
        return self._supervise(task, env, planner, token), env

    @staticmethod
    def _unavailable(message: str) -> WorkerOutcome:
        return WorkerOutcome(TaskStatus.FAILED, message[:500],
                             TaskError(FailureCode.BACKEND_UNAVAILABLE, message[:500]))

    def _supervise(self, task: BackgroundTask, env: ExecutionEnvironment, planner: Planner,
                   token: CancelToken) -> WorkerOutcome:
        limits = task.limits
        deadline = time.monotonic() + limits.max_runtime_seconds
        box: Dict[str, WorkerOutcome] = {}
        def target() -> None:
            box["outcome"] = self._worker.run(task, env, planner, token, deadline)
        worker = threading.Thread(target=target, name=f"bg-worker-{task.id[:8]}", daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(0.05)
            if token.is_cancelled:
                break
            if time.monotonic() >= deadline:
                token.cancel(CancelReason.TIMEOUT)
                break
        if token.is_cancelled and worker.is_alive():
            self._safe(env.release_inputs, "release_inputs")
            self._safe(env.abort, "abort")
            worker.join(limits.cancel_grace_seconds)
            if worker.is_alive():
                log.warning("worker for task %s ignored cancellation; environment will be force-closed", task.id)
        if token.is_cancelled:
            if token.reason is CancelReason.TIMEOUT:
                msg = f"Timed out after {limits.max_runtime_seconds:g}s"
                return WorkerOutcome(TaskStatus.TIMEOUT, msg, TaskError(FailureCode.TIMEOUT, msg))
            return WorkerOutcome(TaskStatus.CANCELLED,
                                 "Cancelled" if token.reason is CancelReason.USER else "Cancelled: Ruby is shutting down")
        outcome = box.get("outcome")
        if outcome is None:
            msg = "Worker ended without a result"
            return WorkerOutcome(TaskStatus.FAILED, msg, TaskError(FailureCode.WORKER_EXCEPTION, msg))
        return outcome

    @staticmethod
    def _safe(fn: Callable[[], None], label: str) -> bool:
        try:
            fn()
            return True
        except Exception:
            log.exception("environment %s failed", label)
            return False

    def _cleanup_environment(self, env: ExecutionEnvironment, task: BackgroundTask) -> bool:
        result = {"closed": False}
        def target() -> None:
            self._safe(env.release_inputs, "release_inputs")
            self._safe(env.abort, "abort")
            result["closed"] = self._safe(env.close, "close")
        thread = threading.Thread(target=target, name=f"bg-cleanup-{task.id[:8]}", daemon=True)
        thread.start()
        thread.join(task.limits.cleanup_timeout_seconds)
        return result["closed"] and not thread.is_alive()
