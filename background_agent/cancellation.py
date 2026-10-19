"""Cooperative cancellation primitives."""
from __future__ import annotations

import enum
import threading
from typing import Optional

from .errors import BackgroundAgentError


class CancelReason(str, enum.Enum):
    USER = "user"
    TIMEOUT = "timeout"
    SHUTDOWN = "shutdown"


class TaskAborted(BackgroundAgentError):
    """Raised inside the worker when its task must stop (cancel / timeout / shutdown)."""

    def __init__(self, reason: CancelReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class CancelToken:
    """Thread-safe, first-reason-wins cancellation flag."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason: Optional[CancelReason] = None

    def cancel(self, reason: CancelReason = CancelReason.USER) -> bool:
        """Request cancellation. Returns True only for the call that set the flag."""
        with self._lock:
            if self._event.is_set():
                return False
            self._reason = reason
            self._event.set()
            return True

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[CancelReason]:
        return self._reason

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise TaskAborted(self._reason or CancelReason.USER)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until cancelled or timeout; returns True if cancelled."""
        return self._event.wait(timeout)
