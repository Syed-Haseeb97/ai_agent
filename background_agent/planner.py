"""Planner interface: the "brain" that picks the next action.

This PR ships the interface plus ScriptedPlanner (for tests/demos). A Gemini-backed
planner plugs in later by implementing Planner; nothing else changes.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Callable, FrozenSet, Iterable, List, Optional, Sequence, Tuple, Union

from .actions import Action, ActionErrorCode, ActionKind
from .errors import PlannerError
from .verification import Expectation


@dataclass(frozen=True)
class StepRecord:
    action_summary: str
    ok: bool
    observation: str  # truncated by the worker
    error_code: Optional[ActionErrorCode] = None


@dataclass(frozen=True)
class PlanContext:
    goal: str
    history: Tuple[StepRecord, ...]
    capabilities: FrozenSet[ActionKind]
    actions_remaining: int
    seconds_remaining: float


@dataclass(frozen=True)
class Finish:
    """The planner believes the goal is met. The worker will verify, not trust."""

    summary: str
    claimed_outputs: Tuple[str, ...] = ()
    expectations: Tuple[Expectation, ...] = ()
    no_artifacts_expected: bool = False


Decision = Union[Action, Finish]


class Planner(abc.ABC):
    @abc.abstractmethod
    def next_step(self, ctx: PlanContext) -> Decision: ...


PlannerStep = Union[Action, Finish, Exception, Callable[[PlanContext], Decision]]


class ScriptedPlanner(Planner):
    """Replays a fixed script. Items may be Actions, Finish, exceptions to raise, or
    callables receiving the PlanContext."""

    def __init__(self, steps: Iterable[PlannerStep]) -> None:
        self._steps: List[PlannerStep] = list(steps)
        self._index = 0
        self.contexts: List[PlanContext] = []

    def next_step(self, ctx: PlanContext) -> Decision:
        self.contexts.append(ctx)
        if self._index >= len(self._steps):
            raise PlannerError("scripted planner exhausted")
        step = self._steps[self._index]
        self._index += 1
        if isinstance(step, Exception):
            raise step
        if callable(step) and not isinstance(step, (Action, Finish)):
            return step(ctx)
        return step  # type: ignore[return-value]
