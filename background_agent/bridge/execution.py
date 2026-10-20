"""Execution-environment routing for task submissions.

The desktop UI chooses an execution mode per task. This module is deliberately a
thin traffic cop: it validates the requested mode, calls the matching handler,
and stamps the response with the environment that accepted the work. Execution
semantics stay inside the existing handlers (the managed background pipeline and
Ruby's F16 desktop-control loop).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from .protocol import BridgeError, ErrorCode

DEFAULT_EXECUTION_MODE = "task_doing"
MAX_GOAL_LENGTH = 4000


class ExecutionMode(str, enum.Enum):
    CURSOR_CONTROL = "cursor_control"
    TASK_DOING = "task_doing"
    BACKGROUND_TASK = "background_task"


EXECUTION_ENVIRONMENTS: Dict[ExecutionMode, str] = {
    ExecutionMode.CURSOR_CONTROL: "desktop",
    ExecutionMode.TASK_DOING: "foreground",
    ExecutionMode.BACKGROUND_TASK: "background",
}

# 201 = a managed task was created; 202 = work was accepted by an asynchronous
# execution environment (desktop control or the background queue).
SUBMISSION_STATUS: Dict[ExecutionMode, int] = {
    ExecutionMode.CURSOR_CONTROL: 202,
    ExecutionMode.TASK_DOING: 201,
    ExecutionMode.BACKGROUND_TASK: 202,
}

TaskSnapshot = Dict[str, Any]
ExecutionHandler = Callable[[str], TaskSnapshot]


def parse_execution_mode(value: Any) -> ExecutionMode:
    """Return the mode selected by the UI, defaulting to task_doing."""
    if value is None:
        return ExecutionMode(DEFAULT_EXECUTION_MODE)
    if isinstance(value, ExecutionMode):
        return value
    if not isinstance(value, str):
        raise BridgeError(ErrorCode.BAD_REQUEST, "executionMode must be a string")
    try:
        return ExecutionMode(value.strip())
    except ValueError:
        allowed = ", ".join(mode.value for mode in ExecutionMode)
        raise BridgeError(ErrorCode.BAD_REQUEST,
                          f"unknown executionMode {value!r}; expected one of: {allowed}") from None


def validate_goal(goal: Any) -> str:
    if not isinstance(goal, str):
        raise BridgeError(ErrorCode.INVALID_GOAL, "goal must be a string")
    if not goal.strip():
        raise BridgeError(ErrorCode.INVALID_GOAL, "goal must not be empty")
    if len(goal) > MAX_GOAL_LENGTH:
        raise BridgeError(ErrorCode.INVALID_GOAL,
                          f"goal is longer than {MAX_GOAL_LENGTH} characters")
    return goal


@dataclass(frozen=True)
class Submission:
    task: TaskSnapshot
    execution_mode: ExecutionMode
    execution_environment: str
    http_status: int


class TaskDispatcher:
    """Delegate a goal to the handler registered for its execution mode."""

    def __init__(self, handlers: Mapping[ExecutionMode, ExecutionHandler]) -> None:
        missing = [mode.value for mode in ExecutionMode if mode not in handlers]
        if missing:
            raise ValueError(f"missing execution handlers for: {', '.join(missing)}")
        self._handlers: Dict[ExecutionMode, ExecutionHandler] = dict(handlers)

    def dispatch(self, goal: Any, execution_mode: Any = None) -> Submission:
        goal = validate_goal(goal)
        mode = parse_execution_mode(execution_mode)
        snapshot = dict(self._handlers[mode](goal))
        environment = EXECUTION_ENVIRONMENTS[mode]
        snapshot["execution_mode"] = mode.value
        snapshot["execution_environment"] = environment
        return Submission(task=snapshot, execution_mode=mode, execution_environment=environment,
                          http_status=SUBMISSION_STATUS[mode])
