"""Authentication and request-origin checks.

Threat model: this socket can start command execution, and any web page the user visits
can *try* to reach 127.0.0.1. Defenses (all required, none sufficient alone):
  1. bind to loopback only (ensure_loopback)
  2. 256-bit random bearer token per launch, compared in constant time
  3. Origin allow-list (browsers always send Origin; a hostile page cannot forge it)
  4. Host allow-list (defeats DNS-rebinding, where Origin is the attacker's own site)
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Dict, Iterable, Optional

from .protocol import BridgeError, ErrorCode

DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "[::1]"})
ORIGINS_ENV = "RUBY_BRIDGE_ALLOWED_ORIGINS"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,}$")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def _valid_token(token: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(token.strip()))


def read_token_file(path: Path) -> Optional[str]:
    """Read a persisted dev token, returning None for missing/corrupt/short values."""
    path = Path(path)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return token if _valid_token(token) else None


def write_token_file(path: Path, token: str) -> None:
    """Write a dev token with owner-only POSIX permissions where supported."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _valid_token(token):
        raise ValueError("bridge token is invalid or too short")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_or_create_token(path: Path) -> str:
    """Reuse a valid persisted token; replace a missing/corrupt/short token."""
    existing = read_token_file(path)
    if existing:
        return existing
    token = generate_token()
    write_token_file(path, token)
    return token


def ensure_loopback(host: str) -> str:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"bridge may only bind to loopback, refusing {host!r}")
    return host


def origins_from_env(environ: Optional[Dict[str, str]] = None) -> tuple:
    raw = (environ if environ is not None else os.environ).get(ORIGINS_ENV, "")
    extra = tuple(o.strip().rstrip("/") for o in raw.split(",") if o.strip())
    return tuple(dict.fromkeys((*DEFAULT_ALLOWED_ORIGINS, *extra)))


class BridgeAuth:
    def __init__(self, token: Optional[str] = None, allowed_origins: Optional[Iterable[str]] = None) -> None:
        self.token = token or generate_token()
        if len(self.token) < 16:
            raise ValueError("bridge token is too short")
        self.allowed_origins = frozenset(o.rstrip("/") for o in (allowed_origins or origins_from_env()))
        if "*" in self.allowed_origins:
            raise ValueError("wildcard origins are not allowed")

    def check_token(self, presented: Optional[str]) -> None:
        if not isinstance(presented, str) or not presented:
            raise BridgeError(ErrorCode.UNAUTHORIZED, "missing credentials")
        if not hmac.compare_digest(presented.encode("utf-8"), self.token.encode("utf-8")):
            raise BridgeError(ErrorCode.UNAUTHORIZED, "invalid credentials")

    def check_bearer_header(self, header: Optional[str]) -> None:
        if not header or not header.lower().startswith("bearer "):
            raise BridgeError(ErrorCode.UNAUTHORIZED, "missing bearer token")
        self.check_token(header[7:].strip())

    def check_origin(self, origin: Optional[str]) -> None:
        if origin is None:
            return
        if origin.rstrip("/") not in self.allowed_origins:
            raise BridgeError(ErrorCode.FORBIDDEN, "origin not allowed")

    def check_host(self, host: Optional[str]) -> None:
        if not host:
            raise BridgeError(ErrorCode.FORBIDDEN, "missing Host header")
        name = host.rsplit(":", 1)[0] if not host.endswith("]") and ":" in host else host
        if name.lower() not in ALLOWED_HOSTNAMES:
            raise BridgeError(ErrorCode.FORBIDDEN, "host not allowed")

    def check_http(self, *, host: Optional[str], origin: Optional[str], authorization: Optional[str]) -> None:
        self.check_host(host)
        self.check_origin(origin)
        self.check_bearer_header(authorization)

    def check_ws_upgrade(self, *, host: Optional[str], origin: Optional[str]) -> None:
        self.check_host(host)
        self.check_origin(origin)


def write_dev_env(path: Path, base_url: str, token: str) -> bool:
    """Write bridge URL/token while preserving unrelated keys.

    Returns True only when the file contents changed. This lets a restart reuse the
    same token without touching `.env.local`, avoiding unnecessary Vite reloads.
    """
    path = Path(path)
    ours = {"VITE_RUBY_BRIDGE_URL": base_url, "VITE_RUBY_BRIDGE_TOKEN": token}
    kept = []
    if path.exists():
        kept = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.split("=", 1)[0].strip() not in ours]
    text = "\n".join([*kept, *(f"{k}={v}" for k, v in ours.items())]) + "\n"
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else None
    except (OSError, UnicodeError):
        current = None
    if current == text:
        return False
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return True
