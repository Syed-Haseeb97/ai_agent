"""Deterministic disk measurements for Ruby's cleanup workflow.

This module observes disk and directory usage only. It does not delete files.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class DiskSnapshot:
    drive: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    measured_at: float


@dataclass(frozen=True)
class CleanupMeasurement:
    target: str
    bytes_before: int
    bytes_after: int
    target_bytes_delta: int
    drive_free_before: int
    drive_free_after: int
    drive_free_delta: int
    skipped_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def measure_disk(drive: str | os.PathLike[str] = "C:\\") -> DiskSnapshot:
    """Return exact byte counts reported by the operating system."""
    path = os.fspath(drive)
    usage = __import__("shutil").disk_usage(path)
    return DiskSnapshot(
        drive=path,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        measured_at=time.time(),
    )


def directory_size_bytes(
    root: str | os.PathLike[str],
    *,
    stop_requested: Callable[[], bool] | None = None,
) -> int:
    """Measure regular-file sizes without following symlinks; fail on unsafe ambiguity.

    A directory that vanishes or becomes inaccessible during traversal is skipped.
    Symlinks are never traversed. The result is an estimate of bytes represented by
    accessible regular files, not a promise of reclaimable disk clusters.
    """
    base = Path(root)
    if base.is_symlink():
        raise ValueError(f"Refusing to measure a symlink root: {base}")
    if not base.exists():
        return 0
    if not base.is_dir():
        raise NotADirectoryError(str(base))

    total = 0
    stack = [base]
    while stack:
        if stop_requested is not None and stop_requested():
            raise InterruptedError("Directory measurement cancelled.")
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if stop_requested is not None and stop_requested():
                        raise InterruptedError("Directory measurement cancelled.")
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except (FileNotFoundError, PermissionError, OSError):
                        # Concurrently removed or inaccessible entries cannot be measured.
                        continue
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return total


def build_measurement(
    target: str | os.PathLike[str],
    bytes_before: int,
    bytes_after: int,
    drive_free_before: int,
    drive_free_after: int,
    skipped_paths: tuple[str, ...] = (),
) -> CleanupMeasurement:
    """Build a report from measured values; positive delta means more free space."""
    return CleanupMeasurement(
        target=str(target),
        bytes_before=max(0, int(bytes_before)),
        bytes_after=max(0, int(bytes_after)),
        target_bytes_delta=int(bytes_before) - int(bytes_after),
        drive_free_before=max(0, int(drive_free_before)),
        drive_free_after=max(0, int(drive_free_after)),
        drive_free_delta=int(drive_free_after) - int(drive_free_before),
        skipped_paths=tuple(skipped_paths),
    )
