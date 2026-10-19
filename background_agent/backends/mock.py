"""In-memory mock backend for testing orchestration without any real OS access.

Special action params understood by MockEnvironment.execute:
  mock_sleep: seconds to block, but wake immediately on abort/cancel (cooperative)
  mock_hang:  seconds to block IGNORING abort/cancel (simulates a wedged environment)
  mock_raise: message; raises RuntimeError from execute()
"""
from __future__ import annotations

import threading
import time
from pathlib import PurePosixPath
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional

from ..actions import Action, ActionErrorCode, ActionKind, ActionResult
from ..backend import BackendStatus, ExecutionBackend, ExecutionEnvironment
from ..cancellation import CancelToken

Handler = Callable[[Action, "MockEnvironment"], Optional[ActionResult]]
DEFAULT_KINDS = frozenset(k for k in ActionKind if k.value.split(".")[0] in ("fs", "process", "browser"))


class MockEnvironment(ExecutionEnvironment):
    def __init__(self, backend: "MockBackend", task_id: str) -> None:
        self.backend = backend
        self.task_id = task_id
        self.capabilities: FrozenSet[ActionKind] = backend.capabilities
        self.files: Dict[str, str] = dict(backend.initial_files)
        self._abort = threading.Event()
        self._closed = False

    def _full(self, path: str) -> str:
        p = PurePosixPath(path)
        return str(p if p.is_absolute() else PurePosixPath("/mock") / self.task_id / p)

    def execute(self, action: Action, *, deadline: float, cancel: CancelToken) -> ActionResult:
        self.backend.record(f"exec:{action.kind.value}")
        p = action.params
        if p.get("mock_raise"):
            raise RuntimeError(str(p["mock_raise"]))
        if p.get("mock_hang"):
            time.sleep(float(p["mock_hang"]))
            return ActionResult.success("hung")
        if p.get("mock_sleep"):
            end = time.monotonic() + float(p["mock_sleep"])
            while time.monotonic() < end:
                if self._abort.is_set() or cancel.is_cancelled:
                    return ActionResult.failure(ActionErrorCode.CANCELLED, "aborted")
                time.sleep(0.01)
        if self.backend.handler is not None:
            custom = self.backend.handler(action, self)
            if custom is not None:
                return custom
        if action.kind is ActionKind.FS_WRITE:
            path = self._full(str(p["path"]))
            self.files[path] = str(p.get("content", ""))
            return ActionResult.success("written", produced_paths=(path,))
        if action.kind is ActionKind.FS_STAT:
            path = self._full(str(p["path"]))
            exists = path in self.files
            return ActionResult.success("", data={"path": path, "exists": exists, "is_file": exists,
                                                  "is_dir": False, "size": len(self.files[path].encode()) if exists else 0})
        if action.kind is ActionKind.FS_READ:
            path = self._full(str(p["path"]))
            if path not in self.files:
                return ActionResult.failure(ActionErrorCode.NOT_FOUND, "no such file")
            return ActionResult.success(self.files[path])
        return ActionResult.success("ok")

    def abort(self) -> None:
        self.backend.record("abort")
        self._abort.set()

    def release_inputs(self) -> None:
        self.backend.record("release_inputs")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.backend.record("close")
        if self.backend.close_delay:
            time.sleep(self.backend.close_delay)
        self.backend._env_closed()
        if self.backend.fail_close:
            raise RuntimeError("mock close failure")


class MockBackend(ExecutionBackend):
    name = "mock"

    def __init__(self, *, max_concurrency: int = 1, available: bool = True,
                 fail_open: Optional[Exception] = None, open_delay: float = 0.0,
                 handler: Optional[Handler] = None,
                 capabilities: Optional[FrozenSet[ActionKind]] = None,
                 initial_files: Optional[Mapping[str, str]] = None,
                 fail_close: bool = False, close_delay: float = 0.0) -> None:
        self.max_concurrency = max_concurrency
        self.available = available
        self.fail_open = fail_open
        self.open_delay = open_delay
        self.handler = handler
        self.capabilities = capabilities if capabilities is not None else DEFAULT_KINDS
        self.initial_files = dict(initial_files or {})
        self.fail_close = fail_close
        self.close_delay = close_delay
        self.events: List[str] = []
        self.environments: List[MockEnvironment] = []
        self._lock = threading.Lock()
        self.active_environments = 0
        self.max_observed_concurrency = 0

    def record(self, event: str) -> None:
        with self._lock:
            self.events.append(event)

    def _env_closed(self) -> None:
        with self._lock:
            self.active_environments -= 1

    def check_available(self) -> BackendStatus:
        return BackendStatus(self.available, "" if self.available else "mock backend marked unavailable")

    def open_environment(self, task_id: str) -> MockEnvironment:
        if self.fail_open is not None:
            raise self.fail_open
        if self.open_delay:
            time.sleep(self.open_delay)
        env = MockEnvironment(self, task_id)
        with self._lock:
            self.events.append(f"open:{task_id[:8]}")
            self.active_environments += 1
            self.max_observed_concurrency = max(self.max_observed_concurrency, self.active_environments)
            self.environments.append(env)
        return env
