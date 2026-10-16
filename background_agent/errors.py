"""Exception types for the background agent package."""
from __future__ import annotations


class BackgroundAgentError(Exception):
    """Base class for all errors raised by this package."""


class InvalidGoalError(BackgroundAgentError, ValueError):
    """The user-supplied goal is empty, too long, or contains control characters."""


class QueueFullError(BackgroundAgentError):
    """The pending-task queue is at capacity."""


class TaskNotFoundError(BackgroundAgentError, KeyError):
    """No task with the given id is known to the manager."""


class InvalidTransitionError(BackgroundAgentError):
    """A task status change that the lifecycle state machine does not allow."""


class ManagerClosedError(BackgroundAgentError):
    """The manager has been shut down and accepts no new tasks."""


class PlannerError(BackgroundAgentError):
    """The planner could not produce a valid next step."""
