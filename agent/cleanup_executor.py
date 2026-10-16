"""Non-destructive dry-run planner for Ruby's temporary-file cleanup.

This module only enumerates and sizes candidates. It never unlinks files, invokes
shell commands, or treats a tutorial/model suggestion as authorization.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from agent.cleanup_safety import (
    CleanupDisposition,
    classify_cleanup_target,
)


@dataclass(frozen=True)
class CleanupCandidate:
    path: str
    size_bytes: int
    disposition: str
    reason: str


@dataclass(frozen=True)
class CleanupDryRun:
    root: str
    candidates: tuple[CleanupCandidate, ...]
    skipped_paths: tuple[str, ...]
    total_candidate_bytes: int
    allowlisted_bytes: int
    approval_required_bytes: int
    blocked_bytes: int
    truncated: bool = False
    cancelled: bool = False

    def to_dict(self) -> dict:
        result = asdict(self)
        result["candidates"] = [asdict(candidate) for candidate in self.candidates]
        return result


def _is_link_or_junction(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if callable(is_junction) else False
    except OSError:
        return True


def build_cleanup_dry_run(
    root: str | os.PathLike[str],
    *,
    max_entries: int = 10_000,
    stop_requested: Callable[[], bool] | None = None,
) -> CleanupDryRun:
    """Enumerate regular-file candidates without following links or deleting data.

    Each candidate is independently passed through the cleanup safety classifier.
    The root itself must be an allowlisted temp root; callers should not use this
    function to explore arbitrary paths. Entry count is capped to bound work/memory.
    """
    if max_entries < 1:
        raise ValueError("max_entries must be at least 1")

    raw_root = os.fspath(root)
    base = Path(raw_root).expanduser()
    if not base.is_absolute():
        raise ValueError("Cleanup root must be an absolute path")
    if _is_link_or_junction(base):
        raise ValueError("Refusing to enumerate a symlink/junction cleanup root")
    if not base.exists() or not base.is_dir():
        raise NotADirectoryError(str(base))

    root_decision = classify_cleanup_target(base)
    # A configured root is a special boundary, not a deletion target. Confirm it
    # matches a configured temp root by checking one harmless child-shaped path.
    probe = base / ".ruby-cleanup-root-validation-probe"
    probe_decision = classify_cleanup_target(probe)
    if probe_decision.disposition is not CleanupDisposition.ALLOWLISTED:
        raise PermissionError(
            "Cleanup root is not inside the configured temporary-directory allowlist"
        )

    candidates: list[CleanupCandidate] = []
    skipped: list[str] = []
    totals = {
        CleanupDisposition.ALLOWLISTED.value: 0,
        CleanupDisposition.APPROVAL_REQUIRED.value: 0,
        CleanupDisposition.BLOCKED.value: 0,
    }
    stack = [base]
    truncated = False
    cancelled = False

    while stack:
        if stop_requested is not None and stop_requested():
            cancelled = True
            break
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if stop_requested is not None and stop_requested():
                        cancelled = True
                        break
                    path = Path(entry.path)
                    try:
                        if entry.is_symlink() or _is_link_or_junction(path):
                            skipped.append(str(path))
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            skipped.append(str(path))
                            continue
                        stat = entry.stat(follow_symlinks=False)
                        decision = classify_cleanup_target(path)
                        disposition = decision.disposition.value
                        size = max(0, int(stat.st_size))
                        if len(candidates) >= max_entries:
                            truncated = True
                            break
                        candidates.append(CleanupCandidate(
                            path=str(path),
                            size_bytes=size,
                            disposition=disposition,
                            reason=decision.reason,
                        ))
                        totals[disposition] += size
                    except (FileNotFoundError, PermissionError, OSError) as exc:
                        skipped.append(f"{path} ({type(exc).__name__})")
                if cancelled or truncated:
                    break
        except (FileNotFoundError, PermissionError, OSError) as exc:
            skipped.append(f"{current} ({type(exc).__name__})")

        if cancelled or truncated:
            break

    return CleanupDryRun(
        root=str(base),
        candidates=tuple(candidates),
        skipped_paths=tuple(skipped),
        total_candidate_bytes=sum(totals.values()),
        allowlisted_bytes=totals[CleanupDisposition.ALLOWLISTED.value],
        approval_required_bytes=totals[CleanupDisposition.APPROVAL_REQUIRED.value],
        blocked_bytes=totals[CleanupDisposition.BLOCKED.value],
        truncated=truncated,
        cancelled=cancelled,
    )
