"""Ruby background agent core (UI-independent, Windows-isolation-ready).

See README.md. Nothing here touches the user's active desktop.
"""
from .actions import (Action, ActionErrorCode, ActionKind, ActionResult, BROWSER_KINDS,
                      FS_KINDS, GUI_KINDS, PROCESS_KINDS)
from .backend import BackendStatus, ExecutionBackend, ExecutionEnvironment
from .cancellation import CancelReason, CancelToken, TaskAborted
from .errors import (BackgroundAgentError, InvalidGoalError, InvalidTransitionError,
                     ManagerClosedError, PlannerError, QueueFullError, TaskNotFoundError)
from .manager import BackgroundTaskManager, TaskEvent
from .models import (BackgroundTask, CheckResult, FailureCode, OutputFile, TaskError,
                     TaskLimits, TaskResult, TaskStatus, TERMINAL_STATUSES,
                     VerificationReport)
from .planner import Finish, PlanContext, Planner, ScriptedPlanner, StepRecord
from .policy import (ActionPolicy, ConfirmationRequest, DefaultActionPolicy, PolicyDecision,
                     PolicyVerdict, deny_all_confirmations)
from .verification import (CommandSucceeds, DefaultVerifier, FileContains, FileExists,
                           VerificationContext, Verifier)
from .worker import BackgroundWorker, WorkerOutcome

__all__ = [n for n in dir() if not n.startswith("_")]
