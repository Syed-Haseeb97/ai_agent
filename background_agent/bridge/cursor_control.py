"""Thin bridge adapter for Ruby's existing F16 desktop-control loop.

Nothing in F16 is reimplemented here. ``AutonomousAgent`` is started on a daemon
thread (the same loop ``autonomous_agent.py`` runs) and its progress/result is
projected into the bridge's task snapshot shape so the Control Center can poll
and cancel it like any other task. The cursor companion UI is not attached in
bridge mode; the desktop actions themselves use the existing PyAutoGUI executor.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

from ..models import (BackgroundTask, FailureCode, TaskError, TaskLimits, TaskResult,
                      TaskStatus)
from .execution import EXECUTION_ENVIRONMENTS, ExecutionMode

log = logging.getLogger("background_agent.bridge.cursor_control")

DEFAULT_MAX_TURNS = 120
DEFAULT_MAX_RUNTIME_SECONDS = 4 * 60 * 60
DEFAULT_MAX_HISTORY = 50
CURSOR_CONTROL_MODE = ExecutionMode.CURSOR_CONTROL
CURSOR_CONTROL_ENVIRONMENT = EXECUTION_ENVIRONMENTS[CURSOR_CONTROL_MODE]

AgentFactory = Callable[[str, threading.Event, BackgroundTask], Any]


def action_target(action: Any) -> Optional[Dict[str, int]]:
    """Extract F16's normalized 0-999 pointer target, when the action has one."""
    arguments = getattr(action, "arguments", None)
    if not isinstance(arguments, dict):
        return None
    try:
        x = int(arguments["x"])
        y = int(arguments["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"x": max(0, min(999, x)), "y": max(0, min(999, y))}


class CursorControlTasks:
    """Run F16 tasks and expose bridge-compatible snapshots."""

    def __init__(self, *, agent_factory: Optional[AgentFactory] = None,
                 max_turns: int = DEFAULT_MAX_TURNS,
                 max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS,
                 max_history: int = DEFAULT_MAX_HISTORY) -> None:
        self._agent_factory = agent_factory or self._build_agent
        self._max_turns = max(1, int(max_turns))
        self._max_runtime_seconds = max(1, int(max_runtime_seconds))
        self._max_history = max(1, int(max_history))
        self._lock = threading.Lock()
        self._tasks: "OrderedDict[str, BackgroundTask]" = OrderedDict()
        self._stops: Dict[str, threading.Event] = {}
        self._agents: Dict[str, Any] = {}
        self._threads: Dict[str, threading.Thread] = {}
        self._cursor_targets: Dict[str, Dict[str, int]] = {}
        self._closed = False

    @property
    def limits(self) -> TaskLimits:
        return TaskLimits(max_runtime_seconds=float(self._max_runtime_seconds),
                          max_turns=self._max_turns)

    def _build_agent(self, goal: str, stop_event: threading.Event,
                     task: BackgroundTask) -> Any:
        from agent.autonomous_loop import AutonomousAgent

        def on_action_start(action: Any) -> None:
            target = action_target(action)
            if target is not None:
                with self._lock:
                    self._cursor_targets[task.id] = target
            name = getattr(action, "name", "action")
            detail = f"Desktop action: {name}"
            if target is not None:
                detail += f" at {target['x']}, {target['y']}"
            task.add_progress(detail)

        return AutonomousAgent(
            max_turns=self._max_turns,
            max_runtime_seconds=self._max_runtime_seconds,
            stop_event=stop_event,
            on_action_start=on_action_start,
            on_action_end=lambda _action: task.note_action(),
        )

    def submit(self, goal: str) -> Dict[str, Any]:
        task = BackgroundTask(goal, self.limits)
        stop_event = threading.Event()
        with self._lock:
            if self._closed:
                raise RuntimeError("cursor control is shutting down")
            self._tasks[task.id] = task
            self._stops[task.id] = stop_event
            task.transition(TaskStatus.QUEUED, "Queued for desktop control")
            thread = threading.Thread(target=self._run, args=(task, stop_event),
                                      name=f"cursor-control-{task.id[:8]}", daemon=True)
            self._threads[task.id] = thread
            self._prune_locked()
            thread.start()
        return self._snapshot(task)

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_snapshots(self) -> List[Dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())
        tasks.reverse()
        return [self._snapshot(task) for task in tasks]

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task.is_terminal:
                return False
            stop_event = self._stops.get(task_id)
            agent = self._agents.get(task_id)
        task.flag_cancel_requested()
        if stop_event is not None:
            stop_event.set()
        stop = getattr(agent, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                log.exception("cursor control agent failed to stop")
        if task.status in (TaskStatus.CREATED, TaskStatus.QUEUED):
            return task.try_transition(TaskStatus.CANCELLED, "Cancelled before it started")
        return True

    def shutdown(self, timeout: float = 5.0) -> None:
        with self._lock:
            self._closed = True
            tasks = list(self._tasks.values())
            agents = list(self._agents.values())
            threads = list(self._threads.values())
            stops = list(self._stops.values())
        for stop_event in stops:
            stop_event.set()
        for agent in agents:
            stop = getattr(agent, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    log.exception("cursor control agent failed to stop during shutdown")
        deadline = time.monotonic() + max(0.0, timeout)
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        for task in tasks:
            if not task.is_terminal:
                task.try_transition(TaskStatus.CANCELLED, "Cancelled: Ruby is shutting down")

    # ---- internals -------------------------------------------------------
    def _run(self, task: BackgroundTask, stop_event: threading.Event) -> None:
        try:
            if stop_event.is_set():
                task.try_transition(TaskStatus.CANCELLED, "Cancelled before it started")
                return
            if not task.try_transition(TaskStatus.RUNNING, "Desktop control started"):
                return
            try:
                agent = self._agent_factory(task.goal, stop_event, task)
            except Exception as exc:
                self._fail(task, f"Could not start F16 desktop control: "
                                 f"{type(exc).__name__}: {exc}")
                return
            with self._lock:
                self._agents[task.id] = agent
            if stop_event.is_set():
                task.try_transition(TaskStatus.CANCELLED, "Cancelled")
                return
            result = agent.run(task.goal)
            self._apply_result(task, result)
        except Exception as exc:
            log.exception("cursor control task crashed")
            self._fail(task, f"F16 desktop control failed: {type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._agents.pop(task.id, None)
                self._threads.pop(task.id, None)

    @staticmethod
    def _apply_result(task: BackgroundTask, result: Any) -> None:
        status = str(getattr(result, "status", "error") or "error")
        message = str(getattr(result, "message", "") or "").strip()[:500]
        if status == "completed":
            summary = message or "Desktop task completed."
            # The model requires RUNNING -> VERIFYING -> COMPLETED. F16 already
            # performs its own native verification before reporting completion.
            if task.try_transition(TaskStatus.VERIFYING, summary):
                task.try_transition(TaskStatus.COMPLETED, summary,
                                    result=TaskResult(summary=summary))
        elif status == "stopped":
            task.try_transition(TaskStatus.CANCELLED, message or "Stopped by the user.")
        elif status == "timeout":
            detail = message or "Maximum autonomous runtime reached."
            task.try_transition(TaskStatus.TIMEOUT, detail,
                                error=TaskError(FailureCode.TIMEOUT, detail))
        else:
            detail = message or f"F16 desktop control ended: {status}"
            task.try_transition(TaskStatus.FAILED, detail,
                                error=TaskError(FailureCode.BACKEND_FAILURE, detail))

    @staticmethod
    def _fail(task: BackgroundTask, message: str) -> None:
        detail = message[:500]
        task.try_transition(TaskStatus.FAILED, detail,
                            error=TaskError(FailureCode.BACKEND_FAILURE, detail))

    def _snapshot(self, task: BackgroundTask) -> Dict[str, Any]:
        snapshot = task.snapshot()
        snapshot["execution_mode"] = CURSOR_CONTROL_MODE.value
        snapshot["execution_environment"] = CURSOR_CONTROL_ENVIRONMENT
        target = self._cursor_targets.get(task.id)
        if target is not None:
            snapshot["cursor_target"] = dict(target)
        return snapshot

    def _prune_locked(self) -> None:
        terminal = [task_id for task_id, task in self._tasks.items() if task.is_terminal]
        for task_id in terminal[:max(0, len(terminal) - self._max_history)]:
            self._tasks.pop(task_id, None)
            self._stops.pop(task_id, None)
            self._agents.pop(task_id, None)
            self._threads.pop(task_id, None)
            self._cursor_targets.pop(task_id, None)
