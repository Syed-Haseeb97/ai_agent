"""Verification: "I did the action" is not "the task succeeded".

All verification reads go through the same guarded action path as normal actions
(capability check + policy), against the SAME environment the task ran in.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Union

from .actions import Action, ActionKind, ActionResult
from .models import CheckResult, OutputFile, VerificationReport

MAX_EXPECTATIONS = 20
MAX_VERIFY_READ_BYTES = 1_000_000


@dataclass(frozen=True)
class FileExists:
    path: str
    min_size: int = 1


@dataclass(frozen=True)
class FileContains:
    path: str
    text: str
    case_sensitive: bool = True


@dataclass(frozen=True)
class CommandSucceeds:
    argv: Tuple[str, ...]
    stdout_contains: Optional[str] = None


Expectation = Union[FileExists, FileContains, CommandSucceeds]
RunAction = Callable[[Action], ActionResult]


@dataclass
class VerificationContext:
    task_id: str
    goal: str
    summary: str
    claimed_outputs: Tuple[str, ...]
    produced_outputs: Tuple[str, ...]
    expectations: Tuple[Expectation, ...]
    no_artifacts_expected: bool
    run_action: RunAction


class Verifier(abc.ABC):
    @abc.abstractmethod
    def verify(self, ctx: VerificationContext) -> VerificationReport: ...


class DefaultVerifier(Verifier):
    def __init__(self, *, allow_empty_outputs: bool = False) -> None:
        self.allow_empty_outputs = allow_empty_outputs

    def verify(self, ctx: VerificationContext) -> VerificationReport:
        checks: List[CheckResult] = []
        outputs: Dict[str, OutputFile] = {}

        for raw in dict.fromkeys([*ctx.claimed_outputs, *ctx.produced_outputs]):
            res = ctx.run_action(Action(ActionKind.FS_STAT, {"path": raw}))
            if not res.ok:
                checks.append(CheckResult(f"output: {raw}", False, res.error))
                outputs.setdefault(raw, OutputFile(raw, None, False))
                continue
            d = res.data
            path = str(d.get("path", raw))
            size = d.get("size")
            minimum = 0 if self.allow_empty_outputs else 1
            ok = bool(d.get("exists")) and bool(d.get("is_file")) and (size or 0) >= minimum
            detail = (f"{size} bytes" if ok else
                      "does not exist" if not d.get("exists") else
                      "not a regular file" if not d.get("is_file") else "file is empty")
            previous = outputs.get(path)
            if previous is None:
                checks.append(CheckResult(f"output: {path}", ok, detail))
            outputs[path] = OutputFile(path, size if d.get("exists") else None,
                                       ok and (previous.verified if previous else True))

        for exp in ctx.expectations[:MAX_EXPECTATIONS]:
            checks.append(self._check_expectation(exp, ctx.run_action))
        if len(ctx.expectations) > MAX_EXPECTATIONS:
            checks.append(CheckResult("expectations", False,
                                      f"more than {MAX_EXPECTATIONS} expectations supplied"))

        note = ""
        if not checks:
            if ctx.no_artifacts_expected:
                checks.append(CheckResult("no artifacts expected", True,
                                          "nothing to verify by design"))
                note = ("No artifacts were expected; the summary is the planner's own "
                        "statement and was not independently verified.")
            else:
                checks.append(CheckResult(
                    "evidence", False,
                    "Task finished with no outputs or expectations to verify; the model's "
                    "claim of success is not accepted without evidence."))
        passed = all(c.passed for c in checks)
        return VerificationReport(passed, tuple(checks), tuple(outputs.values()), note)

    @staticmethod
    def _check_expectation(exp: Expectation, run: RunAction) -> CheckResult:
        if isinstance(exp, FileExists):
            r = run(Action(ActionKind.FS_STAT, {"path": exp.path}))
            if not r.ok:
                return CheckResult(f"exists: {exp.path}", False, r.error)
            size = r.data.get("size") or 0
            ok = bool(r.data.get("exists")) and bool(r.data.get("is_file")) and size >= exp.min_size
            return CheckResult(f"exists: {exp.path}", ok, f"{size} bytes" if ok else "missing or too small")
        if isinstance(exp, FileContains):
            r = run(Action(ActionKind.FS_READ, {"path": exp.path, "max_bytes": MAX_VERIFY_READ_BYTES}))
            if not r.ok:
                return CheckResult(f"contains: {exp.path}", False, r.error)
            hay, needle = (r.output, exp.text) if exp.case_sensitive else (r.output.casefold(), exp.text.casefold())
            ok = needle in hay
            return CheckResult(f"contains: {exp.path}", ok, "found" if ok else "expected text not found")
        if isinstance(exp, CommandSucceeds):
            r = run(Action(ActionKind.PROCESS_RUN, {"argv": list(exp.argv)}))
            name = f"command: {exp.argv[0] if exp.argv else '?'}"
            if not r.ok:
                return CheckResult(name, False, r.error)
            if exp.stdout_contains is not None and exp.stdout_contains not in r.output:
                return CheckResult(name, False, "expected output not found")
            return CheckResult(name, True, "exit code 0")
        return CheckResult("expectation", False, f"unknown expectation type {type(exp).__name__}")
