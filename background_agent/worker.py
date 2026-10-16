"""BackgroundWorker: runs ONE task inside ONE environment and returns an outcome.

The worker never sets terminal task states itself; it returns a WorkerOutcome and the
manager applies it. That keeps "first terminal transition wins" in one place and means
an abandoned (unresponsive) worker thread can never overwrite a CANCELLED/TIMEOUT task.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

from .actions import Action, ActionErrorCode, ActionKind, ActionResult, GUI_KINDS
from .backend import ExecutionEnvironment
from .cancellation import CancelReason, CancelToken, TaskAborted
from .models import (BackgroundTask, FailureCode, OutputFile, TaskError, TaskResult,
                     TaskStatus)
from .planner import Decision, Finish, PlanContext, Planner, StepRecord
from .policy import (ActionPolicy, ConfirmationHandler, ConfirmationRequest, PolicyVerdict)
from .verification import VerificationContext, Verifier

log = logging.getLogger("background_agent")

_FATAL_TO_FAILURE = {
    ActionErrorCode.GUI_ISOLATION_REQUIRED: FailureCode.GUI_ISOLATION_REQUIRED,
    ActionErrorCode.BROWSER_UNAVAILABLE: FailureCode.BROWSER_UNAVAILABLE,
}


@dataclass(frozen=True)
class WorkerOutcome:
    status: TaskStatus
    message: str = ""
    error: Optional[TaskError] = None
    result: Optional[TaskResult] = None
    outputs: Tuple[OutputFile, ...] = ()


class _Fail(Exception):
    def __init__(self, code: FailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f"... [truncated {len(text) - limit} chars]"


class BackgroundWorker:
    def __init__(self, *, policy: ActionPolicy, verifier: Verifier,
                 confirmation_handler: ConfirmationHandler) -> None:
        self._policy = policy
        self._verifier = verifier
        self._confirm = confirmation_handler

    # ------------------------------------------------------------------
    def run(self, task: BackgroundTask, env: ExecutionEnvironment, planner: Planner,
            cancel: CancelToken, deadline: float) -> WorkerOutcome:
        try:
            return self._run(task, env, planner, cancel, deadline)
        except TaskAborted as aborted:
            if aborted.reason is CancelReason.TIMEOUT:
                return WorkerOutcome(TaskStatus.TIMEOUT, "Task exceeded its time limit",
                                     TaskError(FailureCode.TIMEOUT, "Maximum runtime exceeded"))
            return WorkerOutcome(TaskStatus.CANCELLED, "Cancelled")
        except _Fail as fail:
            return WorkerOutcome(TaskStatus.FAILED, fail.message, TaskError(fail.code, fail.message))
        except Exception as exc:  # worker bugs must never escape into the scheduler
            log.exception("worker crashed for task %s", task.id)
            msg = f"{type(exc).__name__}: {exc}"[:500]
            return WorkerOutcome(TaskStatus.FAILED, "Worker crashed",
                                 TaskError(FailureCode.WORKER_EXCEPTION, msg))

    # ------------------------------------------------------------------
    def _checkpoint(self, cancel: CancelToken, deadline: float) -> None:
        cancel.raise_if_cancelled()
        if time.monotonic() >= deadline:
            raise TaskAborted(CancelReason.TIMEOUT)

    def _run(self, task: BackgroundTask, env: ExecutionEnvironment, planner: Planner,
             cancel: CancelToken, deadline: float) -> WorkerOutcome:
        limits = task.limits
        history: Deque[StepRecord] = deque(maxlen=limits.history_steps)
        produced: Dict[str, None] = {}
        turns = denials = repeat = 0
        last_fp: Optional[str] = None
        finish: Optional[Finish] = None

        while finish is None:
            self._checkpoint(cancel, deadline)
            if turns >= limits.max_turns:
                raise _Fail(FailureCode.TURN_LIMIT, f"Reached the {limits.max_turns}-turn limit")
            turns += 1

            ctx = PlanContext(task.goal, tuple(history), env.capabilities,
                              limits.max_actions - task.action_count,
                              max(0.0, deadline - time.monotonic()))
            try:
                decision: Decision = planner.next_step(ctx)
            except TaskAborted:
                raise
            except Exception as exc:
                raise _Fail(FailureCode.PLANNER_ERROR, f"Planner failed: {type(exc).__name__}: {exc}"[:500])
            self._checkpoint(cancel, deadline)

            if isinstance(decision, Finish):
                finish = decision
                break
            if not isinstance(decision, Action):
                raise _Fail(FailureCode.PLANNER_ERROR, "Planner returned an invalid decision")

            fp = decision.fingerprint()
            repeat = repeat + 1 if fp == last_fp else 1
            last_fp = fp
            if repeat >= limits.max_repeated_actions:
                raise _Fail(FailureCode.REPEATED_ACTION,
                            f"Same action requested {repeat} times in a row: {decision.summary()}")
            if task.action_count >= limits.max_actions:
                raise _Fail(FailureCode.ACTION_LIMIT, f"Reached the {limits.max_actions}-action limit")

            result = self._guarded(task, env, decision, cancel, deadline, count=True)
            self._checkpoint(cancel, deadline)  # a cancelled action must not be recorded as normal

            for path in result.produced_paths:
                produced.setdefault(path, None)
                task.track_output(path)
            code = result.error_code
            if code is not None and code.fatal:
                raise _Fail(_FATAL_TO_FAILURE[code], result.error)
            if code is ActionErrorCode.POLICY_DENIED:
                denials += 1
                if denials >= limits.max_policy_denials:
                    raise _Fail(FailureCode.POLICY_DENIED,
                                f"{denials} actions were blocked by policy; last: {result.error}")
            observation = result.output if result.ok else f"{code.value if code else 'ERROR'}: {result.error}"
            history.append(StepRecord(decision.summary(), result.ok,
                                      _truncate(observation, limits.max_observation_chars), code))
            task.add_progress(f"Step {task.action_count}: {decision.summary()} - "
                              f"{'ok' if result.ok else (code.value if code else 'error')}")

        return self._verify(task, env, cancel, deadline, finish, tuple(produced))

    # ------------------------------------------------------------------
    def _verify(self, task: BackgroundTask, env: ExecutionEnvironment, cancel: CancelToken,
                deadline: float, finish: Finish, produced: Tuple[str, ...]) -> WorkerOutcome:
        if not task.try_transition(TaskStatus.VERIFYING, "Verifying result"):
            raise TaskAborted(cancel.reason or CancelReason.USER)  # already terminal elsewhere
        ctx = VerificationContext(
            task_id=task.id, goal=task.goal, summary=finish.summary,
            claimed_outputs=tuple(finish.claimed_outputs), produced_outputs=produced,
            expectations=tuple(finish.expectations),
            no_artifacts_expected=finish.no_artifacts_expected,
            run_action=lambda a: self._guarded(task, env, a, cancel, deadline, count=False))
        try:
            report = self._verifier.verify(ctx)
        except TaskAborted:
            raise
        except Exception as exc:
            raise _Fail(FailureCode.VERIFICATION_FAILED,
                        f"Verifier error: {type(exc).__name__}: {exc}"[:500])
        self._checkpoint(cancel, deadline)

        verified = tuple(o for o in report.outputs if o.verified)
        if not report.passed:
            detail = "; ".join(f"{c.name} ({c.detail})" for c in report.failed_checks)[:500]
            msg = f"Verification failed: {detail}"
            return WorkerOutcome(TaskStatus.FAILED, msg,
                                 TaskError(FailureCode.VERIFICATION_FAILED, msg),
                                 TaskResult(finish.summary[:2000], verified, report),
                                 report.outputs)
        names = ", ".join(o.path.replace("\\", "/").rsplit("/", 1)[-1] for o in verified)
        message = "Completed" + (f" - verified: {names}" if names else "")
        return WorkerOutcome(TaskStatus.COMPLETED, message, None,
                             TaskResult(finish.summary[:2000], verified, report), report.outputs)

    # ------------------------------------------------------------------
    def _guarded(self, task: BackgroundTask, env: ExecutionEnvironment, action: Action,
                 cancel: CancelToken, deadline: float, *, count: bool) -> ActionResult:
        """Capability check -> policy -> (confirmation) -> execute. Fails closed."""
        if action.kind not in env.capabilities:
            if action.kind in GUI_KINDS:
                return ActionResult.failure(
                    ActionErrorCode.GUI_ISOLATION_REQUIRED,
                    "This task needs GUI interaction, which requires an isolated desktop "
                    "backend (Windows Sandbox/VM). Ruby will not touch your active desktop.")
            return ActionResult.failure(ActionErrorCode.UNSUPPORTED,
                                        f"{action.kind.value} is not supported by this environment")
        try:
            decision = self._policy.evaluate(action, task)
        except Exception as exc:
            log.exception("policy raised")
            raise _Fail(FailureCode.POLICY_ERROR, f"Policy error: {type(exc).__name__}: {exc}"[:500])

        if decision.verdict is PolicyVerdict.DENY:
            return ActionResult.failure(ActionErrorCode.POLICY_DENIED, decision.reason or "Blocked by policy")
        if decision.verdict is PolicyVerdict.CONFIRM:
            task.add_progress(f"Waiting for confirmation: {decision.reason}")
            try:
                approved = bool(self._confirm(
                    ConfirmationRequest(task.id, action.kind, action.summary(), decision.reason,
                                        action.details()), cancel))
            except Exception:
                log.exception("confirmation handler raised; treating as declined")
                approved = False
            self._checkpoint(cancel, deadline)
            if not approved:
                return ActionResult.failure(ActionErrorCode.POLICY_DENIED,
                                            f"Not confirmed: {decision.reason}")
        elif decision.verdict is not PolicyVerdict.ALLOW:
            raise _Fail(FailureCode.POLICY_ERROR, f"Unknown policy verdict {decision.verdict!r}")

        if count:
            task.note_action()
        action_deadline = min(deadline, time.monotonic() + task.limits.per_action_timeout_seconds)
        try:
            result = env.execute(action, deadline=action_deadline, cancel=cancel)
        except TaskAborted:
            raise
        except Exception as exc:
            raise _Fail(FailureCode.BACKEND_FAILURE,
                        f"Execution environment error: {type(exc).__name__}: {exc}"[:500])
        if not isinstance(result, ActionResult):
            raise _Fail(FailureCode.BACKEND_FAILURE, "Environment returned an invalid result")
        return result
