"""Shared test helpers. Puts the repo root on sys.path so `import background_agent` works
no matter how the tests are launched."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Callable, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from background_agent import (Action, ActionKind, BackgroundTaskManager, Finish,  # noqa: E402
                              ScriptedPlanner, TaskLimits)
from background_agent.backends.mock import MockBackend  # noqa: E402


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.01) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def write(path: str, content: str = "data") -> Action:
    return Action(ActionKind.FS_WRITE, {"path": path, "content": content})


def sleep_action(seconds: float, **extra) -> Action:
    return Action(ActionKind.FS_STAT, {"path": "x", "mock_sleep": seconds, **extra})


def planner_for(*steps) -> Callable:
    """Planner factory handing every task a fresh copy of the same script."""
    return lambda task: ScriptedPlanner(list(steps))


FAST = TaskLimits(max_runtime_seconds=10, cancel_grace_seconds=0.5, cleanup_timeout_seconds=1.0)


def make_manager(backend=None, factory=None, **kwargs) -> BackgroundTaskManager:
    kwargs.setdefault("default_limits", FAST)
    manager = BackgroundTaskManager(backend or MockBackend(),
                                    factory or planner_for(write("out.txt"), Finish("done", ("out.txt",))),
                                    **kwargs)
    return manager


class EventLog:
    """Collects status transitions for one manager."""

    def __init__(self, manager: BackgroundTaskManager) -> None:
        self.events: List = []
        self._lock = threading.Lock()
        manager.subscribe(self._on)

    def _on(self, event) -> None:
        with self._lock:
            self.events.append(event)

    def statuses(self, task_id: str) -> List[str]:
        with self._lock:
            return [e.status.value for e in self.events if e.task_id == task_id and e.type == "status"]
