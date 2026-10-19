"""EventHub: sequence numbers, replay buffer and bounded per-client queues.

Thread-safe and framework-free. Producers (manager/broker threads) call publish();
consumers (the WebSocket adapter) drain a Subscription and get woken via on_ready.

Delivery guarantees:
  * frames carry a strictly increasing `seq` (per hub `epoch`)
  * subscribe() atomically returns the replay for (epoch, last_seq) and registers the
    queue, so there is no gap and no duplicate between replay and live frames
  * a client that cannot keep up is cut off (overflow) and must resync; only frames
    marked droppable (progress ticks) are ever silently discarded
"""
from __future__ import annotations

import collections
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

from .protocol import PROTOCOL_VERSION

log = logging.getLogger("background_agent.bridge")
Frame = Dict[str, Any]


class Subscription:
    def __init__(self, hub: "EventHub", maxsize: int, on_ready: Optional[Callable[[], None]]) -> None:
        self._hub = hub
        self._maxsize = maxsize
        self._on_ready = on_ready
        self._q: Deque[Frame] = collections.deque()
        self._cond = threading.Condition()
        self._closed = False
        self.overflowed = False
        self.dropped = 0

    # -- producer side ---------------------------------------------------
    def _offer(self, frame: Frame, droppable: bool) -> None:
        with self._cond:
            if self._closed:
                return
            if len(self._q) >= self._maxsize:
                if droppable:
                    self.dropped += 1
                    return
                self.overflowed = True
                self._closed = True
            else:
                self._q.append(frame)
            self._cond.notify_all()
        self._wake()

    def _wake(self) -> None:
        if self._on_ready is not None:
            try:
                self._on_ready()
            except Exception:  # e.g. event loop already closed
                log.debug("subscription wake callback failed", exc_info=True)

    # -- consumer side ---------------------------------------------------
    def get_nowait(self) -> Optional[Frame]:
        with self._cond:
            return self._q.popleft() if self._q else None

    def get(self, timeout: Optional[float] = None) -> Optional[Frame]:
        """Blocking read for non-async consumers/tests. None on timeout or when closed+empty."""
        with self._cond:
            self._cond.wait_for(lambda: self._q or self._closed, timeout)
            return self._q.popleft() if self._q else None

    @property
    def has_items(self) -> bool:
        with self._cond:
            return bool(self._q)

    @property
    def closed(self) -> bool:
        with self._cond:
            return self._closed

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        self._hub._remove(self)
        self._wake()


class EventHub:
    def __init__(self, buffer_size: int = 1000) -> None:
        self.epoch = uuid.uuid4().hex[:12]  # changes on every server start
        self._lock = threading.Lock()
        self._seq = 0
        self._ring: Deque[Frame] = collections.deque(maxlen=buffer_size)
        self._subs: Set[Subscription] = set()

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def publish(self, type: str, data: Dict[str, Any], *, droppable: bool = False) -> int:
        with self._lock:
            self._seq += 1
            frame: Frame = {"v": PROTOCOL_VERSION, "seq": self._seq, "type": type,
                            "ts": datetime.now(timezone.utc).isoformat(), "data": data}
            self._ring.append(frame)
            subs = list(self._subs)
            for sub in subs:
                sub._offer(frame, droppable)  # non-blocking by construction
            return self._seq

    def subscribe(self, *, epoch: Optional[str] = None, last_seq: Optional[int] = None,
                  maxsize: int = 256, on_ready: Optional[Callable[[], None]] = None
                  ) -> Tuple[Subscription, Optional[List[Frame]], int]:
        """Returns (subscription, replay, seq_at_subscribe).
        replay is a list of missed frames, or None when the client must do a full resync
        (first connect, different epoch, or its position fell out of the buffer)."""
        sub = Subscription(self, maxsize, on_ready)
        with self._lock:
            current = self._seq
            replay: Optional[List[Frame]] = None
            if epoch == self.epoch and isinstance(last_seq, int) and not isinstance(last_seq, bool):
                if last_seq == current:
                    replay = []
                elif last_seq < current and self._ring and self._ring[0]["seq"] <= last_seq + 1:
                    replay = [f for f in self._ring if f["seq"] > last_seq]
            self._subs.add(sub)
            return sub, replay, current

    def _remove(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    def close(self) -> None:
        with self._lock:
            subs = list(self._subs)
            self._subs.clear()
        for sub in subs:
            sub.close()
