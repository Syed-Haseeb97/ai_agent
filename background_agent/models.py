"""Task lifecycle / state model.

Deliberately separate from Ruby's emotion enum: task status describes *work*,
not Ruby's mood.
"""
from __future__ import annotations

import enum
import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from .errors import InvalidTransitionError

log = logging.getLogger("background_agent")

MAX_PROGRESS_EVENTS = 200
SNAPSHOT_PROGRESS_EVENTS = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class TaskStatus(str, enum.Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT}
)

_S = TaskStatus
ALLOWED_TRANSITIONS: Dict[TaskStatus, frozenset] = {
    _S.CREATED: frozenset({_S.QUEUED, _S.CANCELLED}),
    _S.QUEUED: frozenset({_S.RUNNING, _S.CANCELLED, _S.FAILED}),
    _S.RUNNING: frozenset({_S.VERIFYING, _S.FAILED, _S.CANCELLED, _S.TIMEOUT}),
    _S.VERIFYING: frozenset({_S.COMPLETED, _S.FAILED, _S.CANCELLED, _S.TIMEOUT}),
    _S.COMPLETED: frozenset(),
    _S.FAILED: frozenset(),
    _S.CANCELLED: frozenset(),
    _S.TIMEOUT: frozenset(),
}


class FailureCode(str, enum.Enum):
    GUI_ISOLATION_REQUIRED = "GUI_ISOLATION_REQUIRED"
    BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_FAILURE = "BACKEND_FAILURE"
    PLANNER_ERROR = "PLANNER_ERROR"
    POLICY_DENIED = "POLICY_DENIED"
    POLICY_ERROR = "POLICY_ERROR"
    ACTION_LIMIT = "ACTION_LIMIT"
    TURN_LIMIT = "TURN_LIMIT"
    REPEATED_ACTION = "REPEATED_ACTION"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    WORKER_EXCEPTION = "WORKER_EXCEPTION"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class TaskLimits:
    """Bounds applied to every task."""

    max_runtime_seconds: float = 900.0
    max_actions: int = 50
    max_turns: int = 75
    max_policy_denials: int = 3
    max_repeated_actions: int = 3
    per_action_timeout_seconds: float = 120.0
    cancel_grace_seconds: float = 5.0
    cleanup_timeout_seconds: float = 15.0
    max_observation_chars: int = 4000
    history_steps: int = 40

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if value <= 0:
                raise ValueError(f"TaskLimits.{name} must be positive, got {value!r}")
        if self.max_repeated_actions < 2:
            raise ValueError("TaskLimits.max_repeated_actions must be >= 2")


@dataclass(frozen=True)
class TaskError:
    code: FailureCode
    message: str


@dataclass(frozen=True)
class OutputFile:
    path: str
    size_bytes: Optional[int] = None
    verified: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class VerificationReport:
    passed: bool
    checks: Tuple[CheckResult, ...] = ()
    outputs: Tuple[OutputFile, ...] = ()
    note: str = ""

    @property
    def failed_checks(self) -> Tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.passed)


@dataclass(frozen=True)
class TaskResult:
    summary: str
    outputs: Tuple[OutputFile, ...] = ()  # verified outputs only
    verification: Optional[VerificationReport] = None


@dataclass(frozen=True)
class ProgressEvent:
    timestamp: datetime
    message: str


Observer = Callable[[str, str, Dict[str, Any]], None]  # (task_id, event_type, snapshot)


class BackgroundTask:
    """One unit of background work. All mutation is lock-protected and idempotent
    at terminal states: the first terminal transition wins."""

    def __init__(self, goal: str, limits: TaskLimits, *, observer: Optional[Observer] = None,
                 task_id: Optional[str] = None) -> None:
        self.id = task_id or uuid.uuid4().hex
        self.goal = goal
        self.limits = limits
        self.created_at = _now()
        self._lock = threading.RLock()
        self._status = TaskStatus.CREATED
        self._message = "Created"
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None
        self._result: Optional[TaskResult] = None
        self._error: Optional[TaskError] = None
        self._cancel_requested = False
        self._action_count = 0
        self._outputs: List[OutputFile] = []
        self._progress: Deque[ProgressEvent] = deque(maxlen=MAX_PROGRESS_EVENTS)
        self._done = threading.Event()
        self._observer = observer

    # ---- read access -------------------------------------------------
    @property
    def status(self) -> TaskStatus:
        with self._lock:
            return self._status

    @property
    def message(self) -> str:
        with self._lock:
            return self._message

    @property
    def result(self) -> Optional[TaskResult]:
        with self._lock:
            return self._result

    @property
    def error(self) -> Optional[TaskError]:
        with self._lock:
            return self._error

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    @property
    def action_count(self) -> int:
        with self._lock:
            return self._action_count

    @property
    def outputs(self) -> Tuple[OutputFile, ...]:
        with self._lock:
            return tuple(self._outputs)

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def completed_at(self) -> Optional[datetime]:
        return self._completed_at

    @property
    def progress(self) -> Tuple[ProgressEvent, ...]:
        with self._lock:
            return tuple(self._progress)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the task reaches a terminal state."""
        return self._done.wait(timeout)

    # ---- mutation (package-internal) ---------------------------------
    def try_transition(self, new: TaskStatus, message: Optional[str] = None, *,
                       error: Optional[TaskError] = None,
                       result: Optional[TaskResult] = None) -> bool:
        with self._lock:
            if new not in ALLOWED_TRANSITIONS[self._status]:
                return False
            self._status = new
            self._message = message or new.value.capitalize()
            if new is TaskStatus.RUNNING:
                self._started_at = _now()
            if new in TERMINAL_STATUSES:
                self._completed_at = _now()
                self._error = error
                self._result = result
            self._emit("status")
            if new in TERMINAL_STATUSES:
                self._done.set()
            return True

    def transition(self, new: TaskStatus, message: Optional[str] = None, **kwargs: Any) -> None:
        with self._lock:
            current = self._status
            if not self.try_transition(new, message, **kwargs):
                raise InvalidTransitionError(f"{current.value} -> {new.value} is not allowed")

    def add_progress(self, message: str) -> None:
        with self._lock:
            if self._status in TERMINAL_STATUSES:
                return
            self._progress.append(ProgressEvent(_now(), message[:300]))
            self._message = message[:300]
            self._emit("progress")

    def note_action(self) -> int:
        with self._lock:
            self._action_count += 1
            return self._action_count

    def track_output(self, path: str) -> None:
        with self._lock:
            if all(o.path != path for o in self._outputs):
                self._outputs.append(OutputFile(path=path))

    def set_outputs(self, outputs: Tuple[OutputFile, ...]) -> None:
        with self._lock:
            if outputs:
                self._outputs = list(outputs)

    def flag_cancel_requested(self) -> None:
        with self._lock:
            if self._status not in TERMINAL_STATUSES:
                self._cancel_requested = True
                self._emit("cancel_requested")

    # ---- serialisation -------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """JSON-safe view for the UI bridge. Contains no screen data or observations."""
        with self._lock:
            result = None
            if self._result is not None:
                v = self._result.verification
                result = {
                    "summary": self._result.summary,
                    "outputs": [_out(o) for o in self._result.outputs],
                    "verified": bool(v and v.passed and v.outputs),
                    "checks": [
                        {"name": c.name, "passed": c.passed, "detail": c.detail}
                        for c in (v.checks if v else ())
                    ],
                    "note": v.note if v else "",
                }
            return {
                "id": self.id,
                "goal": self.goal,
                "status": self._status.value,
                "message": self._message,
                "created_at": _iso(self.created_at),
                "started_at": _iso(self._started_at),
                "completed_at": _iso(self._completed_at),
                "cancel_requested": self._cancel_requested,
                "action_count": self._action_count,
                "progress": [
                    {"timestamp": _iso(p.timestamp), "message": p.message}
                    for p in list(self._progress)[-SNAPSHOT_PROGRESS_EVENTS:]
                ],
                "outputs": [_out(o) for o in self._outputs],
                "result": result,
                "error": (
                    {"code": self._error.code.value, "message": self._error.message}
                    if self._error else None
                ),
            }

    def _emit(self, event_type: str) -> None:
        if self._observer is None:
            return
        try:
            self._observer(self.id, event_type, self.snapshot())
        except Exception:  # observers must never break task state handling
            log.exception("task observer failed")


def _out(o: OutputFile) -> Dict[str, Any]:
    return {"path": o.path, "size_bytes": o.size_bytes, "verified": o.verified}
