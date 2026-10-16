"""ConfirmationBroker: turns ActionPolicy CONFIRM verdicts into UI prompts.

The broker IS the manager's ConfirmationHandler. It runs on the task's worker thread and
blocks (polling) until a human answers, the request expires, the task is cancelled, or the
bridge shuts down. Everything except an explicit approval is a decline: fail closed.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from ..cancellation import CancelToken
from ..policy import ConfirmationRequest
from .protocol import BridgeError, ErrorCode

log = logging.getLogger("background_agent.bridge")

APPROVED, DENIED, TIMEOUT, CANCELLED, SHUTDOWN, OVERLOADED = (
    "approved", "denied", "timeout", "cancelled", "shutdown", "overloaded")
EventSink = Callable[[str, Dict[str, Any]], None]


@dataclass
class _Pending:
    id: str
    request: ConfirmationRequest
    created_at: datetime
    expires_at: datetime
    expires_monotonic: float
    done: threading.Event = field(default_factory=threading.Event)
    resolution: Optional[str] = None

    def payload(self) -> Dict[str, Any]:
        r = self.request
        return {"id": self.id, "task_id": r.task_id, "kind": r.kind.value, "summary": r.summary,
                "reason": r.reason, "details": r.details,
                "created_at": self.created_at.isoformat(), "expires_at": self.expires_at.isoformat()}


@dataclass(frozen=True)
class ConfirmationOutcome:
    id: str
    applied: bool       # False => it had already been resolved; your answer changed nothing
    resolution: str


class ConfirmationBroker:
    def __init__(self, on_event: Optional[EventSink] = None, *, timeout_seconds: float = 120.0,
                 max_pending: int = 10, poll_interval: float = 0.1) -> None:
        self.on_event = on_event
        self._timeout = timeout_seconds
        self._max_pending = max_pending
        self._poll = poll_interval
        self._lock = threading.Lock()
        self._pending: Dict[str, _Pending] = {}
        self._recent: Deque[tuple] = collections.deque(maxlen=200)  # (id, resolution)
        self._shutdown = False

    # ---- ConfirmationHandler interface (worker thread) -------------------
    def __call__(self, request: ConfirmationRequest, cancel: CancelToken) -> bool:
        now = datetime.now(timezone.utc)
        pending = _Pending(uuid.uuid4().hex, request, now, now + timedelta(seconds=self._timeout),
                           time.monotonic() + self._timeout)
        with self._lock:
            if self._shutdown or len(self._pending) >= self._max_pending:
                return False
            self._pending[pending.id] = pending
        self._emit("confirmation_requested", pending.payload())
        while not pending.done.wait(self._poll):
            if cancel.is_cancelled:
                self._resolve(pending, CANCELLED)
            elif time.monotonic() >= pending.expires_monotonic:
                self._resolve(pending, TIMEOUT)
        return pending.resolution == APPROVED

    # ---- UI side -----------------------------------------------------------
    def respond(self, confirmation_id: str, approved: bool) -> ConfirmationOutcome:
        with self._lock:
            pending = self._pending.get(confirmation_id)
            if pending is None:
                for rid, resolution in self._recent:
                    if rid == confirmation_id:
                        return ConfirmationOutcome(rid, False, resolution)
                raise BridgeError(ErrorCode.NOT_FOUND, "no such confirmation")
        applied = self._resolve(pending, APPROVED if approved else DENIED)
        return ConfirmationOutcome(confirmation_id, applied, pending.resolution or DENIED)

    def pending(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [p.payload() for p in self._pending.values()]

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown = True
            everything = list(self._pending.values())
        for p in everything:
            self._resolve(p, SHUTDOWN)

    # ---- internals -----------------------------------------------------------
    def _resolve(self, pending: _Pending, resolution: str) -> bool:
        """First resolution wins. Returns True if this call decided it."""
        with self._lock:
            if pending.resolution is not None:
                return False
            pending.resolution = resolution
            self._pending.pop(pending.id, None)
            self._recent.append((pending.id, resolution))
            pending.done.set()
        self._emit("confirmation_resolved", {"id": pending.id, "task_id": pending.request.task_id,
                                             "resolution": resolution})
        return True

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        sink = self.on_event
        if sink is None:
            return
        try:
            sink(event_type, payload)
        except Exception:
            log.exception("confirmation event sink failed")
