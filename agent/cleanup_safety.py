"""Independent path safety checks for the future cleanup executor.

This module never deletes files and never runs shell commands. It only classifies
whether a proposed path is inside a narrowly configured temporary-directory root.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CleanupDisposition(str, Enum):
    ALLOWLISTED = "allowlisted"
    APPROVAL_REQUIRED = "approval_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CleanupDecision:
    disposition: CleanupDisposition
    requested_path: str
    resolved_path: str | None
    reason: str

    @property
    def allowed_without_approval(self) -> bool:
        return self.disposition is CleanupDisposition.ALLOWLISTED


def default_temporary_roots() -> tuple[Path, ...]:
    """Return candidate temp roots; absent/non-Windows roots are filtered by validation."""
    roots = [Path(tempfile.gettempdir())]
    if os.name == "nt":
        windows = os.environ.get("WINDIR", r"C:\Windows")
        roots.append(Path(windows) / "Temp")
    return tuple(roots)


def _is_reparse_or_symlink(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction()) if callable(is_junction) else False
    except OSError:
        return True


def _contains_link_between(path: Path, root: Path) -> bool:
    """Reject symlinks/junctions in the existing lexical path from root to target."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    if _is_reparse_or_symlink(current):
        return True
    for part in relative.parts:
        current = current / part
        if _is_reparse_or_symlink(current):
            return True
    return False


def classify_cleanup_target(
    target: str | os.PathLike[str],
    *,
    allowed_roots: tuple[str | os.PathLike[str], ...] | None = None,
) -> CleanupDecision:
    """Classify a proposed target; never grants permission to run arbitrary commands.

    Autonomous cleanup is restricted to a strict descendant of a configured temp
    root. The root itself is not a valid deletion target. Other paths require
    approval unless they are clearly sensitive/system locations, which are blocked.
    """
    raw = os.fspath(target)
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            return CleanupDecision(
                CleanupDisposition.BLOCKED, raw, None,
                "Relative cleanup paths are blocked; use a fully resolved absolute path.",
            )

        # Hard-block sensitive locations before considering any allowlist. This
        # remains a block even if a caller accidentally configures an unsafe root.
        candidate_abs = Path(os.path.abspath(candidate))
        blocked_components = {
            "system32", "syswow64", "program files", "program files (x86)",
            "desktop", "documents", "pictures", "videos", "music", "downloads",
        }
        if any(part.casefold() in blocked_components for part in candidate_abs.parts):
            return CleanupDecision(
                CleanupDisposition.BLOCKED, raw, None,
                "System or personal-data locations are prohibited from autonomous cleanup.",
            )

        # Resolve for boundary comparisons but separately inspect the lexical path
        # so a symlink/junction cannot disguise an escape from an approved root.
        roots = tuple(Path(os.path.abspath(Path(p).expanduser())) for p in (
            allowed_roots if allowed_roots is not None else default_temporary_roots()
        ))
        for root in roots:
            try:
                root_resolved = root.resolve(strict=False)
                candidate_resolved = candidate_abs.resolve(strict=False)
                relative = candidate_abs.relative_to(root)
            except (ValueError, OSError, RuntimeError):
                continue

            if not relative.parts:
                return CleanupDecision(
                    CleanupDisposition.BLOCKED, raw, str(candidate_resolved),
                    "The temporary root itself is not a cleanup target; select specific children.",
                )
            if _contains_link_between(candidate_abs, root):
                return CleanupDecision(
                    CleanupDisposition.BLOCKED, raw, str(candidate_resolved),
                    "Symlink/junction paths are blocked to prevent escaping the approved directory.",
                )
            try:
                candidate_resolved.relative_to(root_resolved)
            except ValueError:
                return CleanupDecision(
                    CleanupDisposition.BLOCKED, raw, str(candidate_resolved),
                    "Resolved target escapes the approved temporary directory.",
                )
            return CleanupDecision(
                CleanupDisposition.ALLOWLISTED, raw, str(candidate_resolved),
                "Target is a non-root descendant of an approved temporary directory. "
                "The executor must still validate each entry and honor cancellation.",
            )
        return CleanupDecision(
            CleanupDisposition.APPROVAL_REQUIRED, raw, str(candidate_abs.resolve(strict=False)),
            "Target is outside the temporary-directory allowlist and requires explicit user approval.",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return CleanupDecision(
            CleanupDisposition.BLOCKED, raw, None,
            f"Could not safely resolve cleanup target ({type(exc).__name__}); failing closed.",
        )
