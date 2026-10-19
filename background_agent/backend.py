"""Replaceable execution-environment abstraction.

The manager/worker only know these two interfaces. A future WindowsSandboxBackend
or VMBackend implements them; nothing above this layer changes.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional

from .actions import Action, ActionKind, ActionResult
from .cancellation import CancelToken


@dataclass(frozen=True)
class BackendStatus:
    available: bool
    detail: str = ""


class ExecutionEnvironment(abc.ABC):
    """One task's isolated workspace. Created per task, closed when the task ends.

    Contract:
      * execute() is only ever called from one worker thread at a time.
      * abort(), release_inputs() and close() may be called from ANY thread, may be
        called more than once, and must not raise for repeat calls.
      * abort() must make a blocked execute() return promptly.
      * close() must leave nothing running (processes, browsers, VMs).
      * deadline is an absolute time.monotonic() value.
    """

    capabilities: FrozenSet[ActionKind] = frozenset()
    workspace: Optional[Path] = None

    @abc.abstractmethod
    def execute(self, action: Action, *, deadline: float, cancel: CancelToken) -> ActionResult: ...

    @abc.abstractmethod
    def abort(self) -> None: ...

    def release_inputs(self) -> None:
        """Release held keys/mouse buttons. No-op for backends without input devices;
        GUI backends MUST override it."""

    @abc.abstractmethod
    def close(self) -> None: ...


class ExecutionBackend(abc.ABC):
    """Factory for per-task environments."""

    name: str = "backend"
    #: How many environments may be open at once. 1 unless the backend explicitly
    #: guarantees concurrent environments cannot interfere with each other.
    max_concurrency: int = 1

    @abc.abstractmethod
    def check_available(self) -> BackendStatus: ...

    @abc.abstractmethod
    def open_environment(self, task_id: str) -> ExecutionEnvironment: ...
