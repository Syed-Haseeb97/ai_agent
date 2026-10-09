"""Native, deterministic checks for Ruby's autonomous desktop agent."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import psutil


def collect_process_identities() -> set[tuple[int, str]]:
    """Return current (PID, executable name) pairs for launch-baseline comparisons."""
    identities: set[tuple[int, str]] = set()
    try:
        for process in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = process.info.get("name") or Path(process.info.get("exe") or "").name
                pid = process.info.get("pid")
                if name and pid is not None:
                    identities.add((int(pid), Path(name).name.casefold()))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
                continue
    except (psutil.Error, OSError):
        pass
    return identities


def verify_process(process_name: str) -> bool:
    """Return whether a process with this executable name is currently running."""
    wanted = Path(process_name.strip().strip('"')).name.casefold()
    if not wanted:
        return False
    try:
        for process in psutil.process_iter(["name", "exe"]):
            try:
                name = process.info.get("name") or Path(process.info.get("exe") or "").name
                if name and Path(name).name.casefold() == wanted:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except (psutil.Error, OSError):
        return False
    return False


def verify_file_content(filepath: str | Path, expected_text: str | None = None) -> bool:
    """Verify a non-empty regular file and, optionally, its exact UTF-8 text."""
    path = Path(filepath).expanduser()
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        if expected_text is not None:
            return path.read_text(encoding="utf-8-sig") == expected_text
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def get_active_window_title() -> str:
    """Return the foreground window title on Windows, or an empty string elsewhere."""
    if os.name != "nt":
        return ""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        if not handle:
            return ""
        buffer = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(handle, buffer, len(buffer))
        return buffer.value.strip()
    except (AttributeError, OSError, ValueError):
        try:
            import pygetwindow

            window = pygetwindow.getActiveWindow()
            return (window.title or "").strip() if window else ""
        except Exception:
            return ""


def collect_os_context(filesystem_paths: list[str | Path] | None = None) -> dict[str, Any]:
    """Collect a small prompt-safe snapshot of process names, focus, and requested paths."""
    process_names: set[str] = set()
    try:
        for process in psutil.process_iter(["name"]):
            try:
                name = process.info.get("name")
                if name:
                    process_names.add(Path(name).name)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except (psutil.Error, OSError):
        pass

    paths: dict[str, dict[str, Any]] = {}
    for raw_path in filesystem_paths or []:
        path = Path(raw_path).expanduser()
        try:
            exists = path.exists()
            paths[str(path)] = {
                "exists": exists,
                "is_file": path.is_file() if exists else False,
                "size_bytes": path.stat().st_size if exists and path.is_file() else None,
            }
        except OSError:
            paths[str(path)] = {"exists": False, "is_file": False, "size_bytes": None}

    return {
        "running_processes": sorted(process_names, key=str.casefold)[:30],
        "active_window_title": get_active_window_title(),
        "filesystem_status": paths,
    }


def verify_goal_app_launch(
    goal: str,
    processes_before: set[tuple[int, str]] | None = None,
) -> tuple[bool, str] | None:
    """Verify a foreground app window or a process newly launched for this task.

    A pre-existing background process alone is not proof that the requested app
    was opened. Callers may supply the pre-task (PID, name) snapshot.
    """
    if not re.search(r"\b(open|launch|start|show|bring up)\b", goal, re.I):
        return None
    lowered = goal.casefold()
    apps = {
        "calculator": (("calculatorapp.exe", "calculator.exe", "calc.exe"), "calculator"),
        "notepad": (("notepad.exe",), "notepad"),
        "chrome": (("chrome.exe",), "chrome"),
        "file explorer": (("explorer.exe",), "file explorer"),
        "task manager": (("taskmgr.exe",), "task manager"),
        "command prompt": (("cmd.exe",), "command prompt"),
    }
    for label, (processes, title_hint) in apps.items():
        if re.search(rf"\b{re.escape(label)}\b", lowered):
            title = get_active_window_title()
            if title_hint in title.casefold():
                return True, f"Native verification passed: {label.title()} window is foregrounded."
            current = collect_process_identities()
            baseline = processes_before
            target_names = {name.casefold() for name in processes}
            if baseline is not None and any(
                name in target_names and (pid, name) not in baseline for pid, name in current
            ):
                return True, f"Native verification passed: a new {label.title()} process was launched."
            return False, (
                f"Native verification failed: {label.title()} is not foregrounded and no new "
                "matching process was detected for this task."
            )
    return None


def _expected_file_candidates(goal: str, filename: str) -> list[Path]:
    raw = Path(filename)
    if raw.is_absolute() or "/" in filename or "\\" in filename:
        if raw.is_absolute():
            return [raw]
        normalized = filename.replace("\\", os.sep).replace("/", os.sep)
        return [Path.home() / normalized, Path.cwd() / normalized]

    home = Path.home()
    candidates: list[Path] = []
    lowered = goal.casefold()
    if "document" in lowered:
        candidates.extend([home / "Documents" / filename, home / "OneDrive" / "Documents" / filename])
        for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "Documents" / filename)
    elif "desktop" in lowered:
        candidates.append(home / "Desktop" / filename)
    candidates.extend([Path.cwd() / filename, home / "Documents" / filename,
                       home / "OneDrive" / "Documents" / filename])
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def goal_file_paths(goal: str) -> list[Path]:
    """Resolve candidate locations for explicitly named files in a save/write goal."""
    if not re.search(r"\b(save|write|create|export|store|file|document)\b", goal, re.I):
        return []
    filenames = re.findall(r"(?<![\w])([\w.-]+\.(?:txt|md|csv|json|log|ya?ml))\b", goal, re.I)
    return list(dict.fromkeys(
        path for filename in filenames for path in _expected_file_candidates(goal, filename)
    ))


def verify_goal_file_outputs(goal: str) -> tuple[bool, str] | None:
    """Verify explicitly named output files; return None for non-file goals."""
    if not re.search(r"\b(save|write|create|export|store|file|document)\b", goal, re.I):
        return None
    filenames = list(dict.fromkeys(re.findall(
        r"(?<![\w])([\w.-]+\.(?:txt|md|csv|json|log|ya?ml))\b", goal, re.I
    )))
    if not filenames:
        return None

    quoted_text = None
    match = re.search(
        r"\b(?:type|write|enter|contain|contents? of)\b.{0,60}['\"]([^'\"]{1,200})['\"]",
        goal, re.I | re.S,
    )
    if match:
        quoted_text = match.group(1)

    for filename in filenames:
        candidates = _expected_file_candidates(goal, filename)
        valid = [path for path in candidates if verify_file_content(path, quoted_text)]
        if not valid:
            expectation = f" with exact text {quoted_text!r}" if quoted_text is not None else ""
            checked = ", ".join(str(path) for path in candidates[:4])
            return False, f"Native verification failed: {filename!r} was not found as a non-empty file{expectation}. Checked: {checked}"
    return True, f"Native verification passed for: {', '.join(filenames)}"
