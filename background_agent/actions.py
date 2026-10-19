"""Action vocabulary shared by planners, policies, workers and backends."""
from __future__ import annotations

import enum
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple
from urllib.parse import urlsplit


class ActionKind(str, enum.Enum):
    # Level 1: filesystem
    FS_STAT = "fs.stat"
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_LIST = "fs.list"
    FS_MKDIR = "fs.mkdir"
    FS_MOVE = "fs.move"
    FS_COPY = "fs.copy"
    FS_DELETE = "fs.delete"
    # Level 1: processes
    PROCESS_RUN = "process.run"
    PROCESS_SHELL = "process.shell"
    # Level 3: browser (headless, own profile)
    BROWSER_GOTO = "browser.goto"
    BROWSER_EXTRACT_TEXT = "browser.extract_text"
    BROWSER_CLICK = "browser.click"
    BROWSER_FILL = "browser.fill"
    BROWSER_SCREENSHOT = "browser.screenshot"
    BROWSER_DOWNLOAD = "browser.download"
    # Level 4: GUI. Only an isolated backend (Sandbox/VM) may ever implement these.
    GUI_SCREENSHOT = "gui.screenshot"
    GUI_CLICK = "gui.click"
    GUI_TYPE = "gui.type"
    GUI_KEY = "gui.key"
    GUI_LAUNCH_APP = "gui.launch_app"


FS_KINDS = frozenset(k for k in ActionKind if k.value.startswith("fs."))
PROCESS_KINDS = frozenset(k for k in ActionKind if k.value.startswith("process."))
BROWSER_KINDS = frozenset(k for k in ActionKind if k.value.startswith("browser."))
GUI_KINDS = frozenset(k for k in ActionKind if k.value.startswith("gui."))


class ActionErrorCode(str, enum.Enum):
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    OUTSIDE_WORKSPACE = "OUTSIDE_WORKSPACE"
    INVALID_PARAMS = "INVALID_PARAMS"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    NONZERO_EXIT = "NONZERO_EXIT"
    UNSUPPORTED = "UNSUPPORTED"
    POLICY_DENIED = "POLICY_DENIED"
    GUI_ISOLATION_REQUIRED = "GUI_ISOLATION_REQUIRED"
    BROWSER_UNAVAILABLE = "BROWSER_UNAVAILABLE"
    BROWSER_ERROR = "BROWSER_ERROR"
    IO_ERROR = "IO_ERROR"

    @property
    def fatal(self) -> bool:
        """Fatal codes end the task: retrying with another action cannot help."""
        return self in (ActionErrorCode.GUI_ISOLATION_REQUIRED, ActionErrorCode.BROWSER_UNAVAILABLE)


# Characters that could make an approval prompt lie about what will run: C0/C1 controls,
# line/paragraph separators and bidirectional overrides/isolates ("Trojan Source").
_SPOOFING = {*range(0, 32), *range(0x7F, 0xA0), 0x2028, 0x2029,
             *range(0x202A, 0x202F), *range(0x2066, 0x206A), 0x200E, 0x200F, 0x061C}


def sanitize_for_display(text: str, max_chars: int) -> str:
    out = "".join(f"\\u{ord(c):04x}" if ord(c) in _SPOOFING else c for c in str(text))
    return out if len(out) <= max_chars else out[: max_chars - 1] + "\u2026"


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    params: Mapping[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        blob = json.dumps([self.kind.value, self.params], sort_keys=True, default=str)
        return hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()

    def details(self, max_chars: int = 500) -> str:
        """Human-readable, UNREDACTED description of what this action will do.

        For confirmation prompts ONLY. Never put this in progress lines, snapshots or logs.
        File contents and typed text are deliberately not included (only sizes).
        """
        p, k = self.params, self.kind
        if k is ActionKind.PROCESS_SHELL:
            text = str(p.get("command", ""))
        elif k is ActionKind.PROCESS_RUN:
            argv = p.get("argv")
            text = subprocess.list2cmdline([str(a) for a in argv]) if isinstance(argv, (list, tuple)) else ""
        elif k in (ActionKind.FS_MOVE, ActionKind.FS_COPY):
            text = f"{p.get('src', '')} -> {p.get('dst', '')}" + (" (will overwrite)" if p.get("overwrite") else "")
        elif k is ActionKind.FS_DELETE:
            text = f"{p.get('path', '')}" + (" (recursive)" if p.get("recursive") else "")
        elif k is ActionKind.FS_WRITE:
            content = p.get("content", "")
            size = len(content.encode("utf-8", "replace")) if isinstance(content, str) else 0
            text = f"{p.get('path', '')} ({size} bytes)" + (" (will overwrite)" if p.get("overwrite") else "")
        elif p.get("url"):
            text = str(p["url"])
        else:
            text = str(p.get("path") or p.get("selector") or "")
        if p.get("cwd") and k in (ActionKind.PROCESS_RUN, ActionKind.PROCESS_SHELL):
            text += f"  [in {p['cwd']}]"
        return sanitize_for_display(text, max_chars)

    def summary(self) -> str:
        """Short, redacted description for progress messages (never includes content,
        typed text, command arguments or URL query strings)."""
        p = self.params
        target = ""
        for key in ("path", "src", "selector"):
            if p.get(key):
                target = str(p[key])
                break
        else:
            if p.get("url"):
                parts = urlsplit(str(p["url"]))
                target = f"{parts.scheme}://{parts.netloc}{parts.path}"
            elif isinstance(p.get("argv"), (list, tuple)) and p["argv"]:
                target = str(p["argv"][0])
            elif p.get("command"):
                target = str(p["command"]).split()[0] if str(p["command"]).split() else ""
        return f"{self.kind.value} {target}".strip()[:120]


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    output: str = ""
    error_code: Optional[ActionErrorCode] = None
    error: str = ""
    produced_paths: Tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def success(cls, output: str = "", *, produced_paths: Tuple[str, ...] = (),
                data: Optional[Mapping[str, Any]] = None) -> "ActionResult":
        return cls(True, output=output, produced_paths=tuple(produced_paths), data=data or {})

    @classmethod
    def failure(cls, code: ActionErrorCode, error: str, *, output: str = "",
                data: Optional[Mapping[str, Any]] = None) -> "ActionResult":
        return cls(False, output=output, error_code=code, error=error, data=data or {})


class ActionFailure(Exception):
    """Raised by tool handlers; converted into a failed ActionResult."""

    def __init__(self, code: ActionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
