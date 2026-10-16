"""Safety policy hooks.

DefaultActionPolicy is conservative defense-in-depth. It is NOT a sandbox: a
determined command can still do anything the Windows user could. Real containment
comes from the execution backend. Replace/extend this to reuse Ruby's existing
autonomous-agent policy (implement ActionPolicy and pass it to the manager).
"""
from __future__ import annotations

import abc
import enum
import ipaddress
import re
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, TYPE_CHECKING
from urllib.parse import urlsplit

from .actions import Action, ActionKind, GUI_KINDS
from .cancellation import CancelToken

if TYPE_CHECKING:  # pragma: no cover
    from .models import BackgroundTask


class PolicyVerdict(str, enum.Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    verdict: PolicyVerdict
    reason: str = ""

    @classmethod
    def allow(cls) -> "PolicyDecision":
        return cls(PolicyVerdict.ALLOW)

    @classmethod
    def confirm(cls, reason: str) -> "PolicyDecision":
        return cls(PolicyVerdict.CONFIRM, reason)

    @classmethod
    def deny(cls, reason: str) -> "PolicyDecision":
        return cls(PolicyVerdict.DENY, reason)


@dataclass(frozen=True)
class ConfirmationRequest:
    task_id: str
    kind: ActionKind
    summary: str  # redacted; safe for logs/progress
    reason: str
    details: str = ""  # full sanitized description; for the approval prompt ONLY


#: (request, cancel_token) -> approved. Must return promptly once cancel is set.
ConfirmationHandler = Callable[[ConfirmationRequest, CancelToken], bool]


def deny_all_confirmations(request: ConfirmationRequest, cancel: CancelToken) -> bool:
    """Default: nobody is available to confirm, so risky actions are refused."""
    return False


class ActionPolicy(abc.ABC):
    @abc.abstractmethod
    def evaluate(self, action: Action, task: "BackgroundTask") -> PolicyDecision: ...


DEFAULT_ALLOWED_EXECUTABLES = frozenset(
    {"python", "python3", "py", "pip", "pip3", "git", "node", "npm", "ffmpeg", "ffprobe"}
)
# GUI launchers (would appear on the user's real desktop), shells (go through
# PROCESS_SHELL policy instead) and system-damaging tools.
DEFAULT_DENIED_EXECUTABLES = frozenset({
    "explorer", "notepad", "mspaint", "calc", "chrome", "msedge", "firefox", "code",
    "start", "cmd", "powershell", "pwsh", "wscript", "cscript", "mshta", "regsvr32",
    "rundll32", "format", "diskpart", "shutdown", "reg", "bcdedit", "taskkill", "takeown",
    "icacls", "cipher", "schtasks", "net",
})
DEFAULT_DENIED_SHELL_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bformat\s+[a-z]:", r"\bdiskpart\b", r"\bshutdown\b", r"\brm\s+-[a-z]*r[a-z]*f?\s+/",
    r"\bdel\s+/[sfq]", r"\brd\s+/s", r"\brmdir\s+/s", r"\breg\s+(delete|add)\b",
    r"\bbcdedit\b", r"\bcipher\s+/w", r"remove-item\b.*-recurse", r"\b(stop|restart)-computer\b",
    r"\btakeown\b", r"\bicacls\b", r"\bnet\s+user\b", r"\bschtasks\b",
    r"\bpowershell\b.*\s-enc", r"\bmkfs\b", r"\bdd\s+if=",
))


def _exe_name(raw: str) -> str:
    name = re.split(r"[\\/]", str(raw))[-1].lower()
    for suffix in (".exe", ".bat", ".cmd", ".com"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


class DefaultActionPolicy(ActionPolicy):
    def __init__(self, *, allow_gui: bool = False,
                 allowed_executables: Iterable[str] = DEFAULT_ALLOWED_EXECUTABLES,
                 denied_executables: Iterable[str] = DEFAULT_DENIED_EXECUTABLES) -> None:
        self.allow_gui = allow_gui
        self.allowed_executables = frozenset(e.lower() for e in allowed_executables)
        self.denied_executables = frozenset(e.lower() for e in denied_executables)

    def evaluate(self, action: Action, task: "BackgroundTask") -> PolicyDecision:
        kind, p = action.kind, action.params
        if kind in GUI_KINDS:
            return PolicyDecision.allow() if self.allow_gui else PolicyDecision.deny(
                "GUI actions are disabled by policy")
        if kind is ActionKind.FS_DELETE:
            return PolicyDecision.confirm("Deleting files or folders is destructive")
        if kind in (ActionKind.FS_WRITE, ActionKind.FS_MOVE, ActionKind.FS_COPY) and p.get("overwrite"):
            return PolicyDecision.confirm("Overwriting an existing file")
        if kind is ActionKind.PROCESS_SHELL:
            command = str(p.get("command", ""))
            if not command.strip():
                return PolicyDecision.deny("Empty shell command")
            for pattern in DEFAULT_DENIED_SHELL_PATTERNS:
                if pattern.search(command):
                    return PolicyDecision.deny("Shell command matches a blocked pattern")
            return PolicyDecision.confirm("Running a shell command")
        if kind is ActionKind.PROCESS_RUN:
            argv = p.get("argv")
            if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(a, str) for a in argv):
                return PolicyDecision.deny("process.run needs a non-empty argv list of strings")
            exe = _exe_name(argv[0])
            if exe in self.denied_executables:
                return PolicyDecision.deny(f"Executable '{exe}' is blocked")
            if exe in self.allowed_executables:
                return PolicyDecision.allow()
            return PolicyDecision.confirm(f"Running unlisted executable '{exe}'")
        if kind is ActionKind.BROWSER_GOTO:
            return self._check_url(str(p.get("url", "")))
        return PolicyDecision.allow()

    @staticmethod
    def _check_url(url: str) -> PolicyDecision:
        try:
            parts = urlsplit(url)
        except ValueError:
            return PolicyDecision.deny("Malformed URL")
        if parts.scheme.lower() not in ("http", "https"):
            return PolicyDecision.deny("Only http/https URLs are allowed")
        host: Optional[str] = parts.hostname
        if not host:
            return PolicyDecision.deny("URL has no host")
        if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
            return PolicyDecision.confirm("URL points at a local/internal host")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return PolicyDecision.allow()
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return PolicyDecision.confirm("URL points at a private/local address")
        return PolicyDecision.allow()
