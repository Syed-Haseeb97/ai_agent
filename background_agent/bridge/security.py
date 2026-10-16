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
import secrets
from pathlib import Path
from typing import Dict, Iterable, Optional

from .protocol import BridgeError, ErrorCode

DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")  # Vite dev server
ALLOWED_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "[::1]"})
ORIGINS_ENV = "RUBY_BRIDGE_ALLOWED_ORIGINS"  # comma-separated


def generate_token() -> str:
    return secrets.token_urlsafe(32)


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

    # -- individual checks (raise BridgeError) --------------------------
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
        """No Origin = non-browser client (still needs the token). A present Origin must be
        allow-listed; the literal 'null' (file://, sandboxed frames) is rejected."""
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

    # -- combined entry points ---------------------------------------------
    def check_http(self, *, host: Optional[str], origin: Optional[str], authorization: Optional[str]) -> None:
        self.check_host(host)
        self.check_origin(origin)
        self.check_bearer_header(authorization)

    def check_ws_upgrade(self, *, host: Optional[str], origin: Optional[str]) -> None:
        """Before accepting the socket. The token arrives in the first frame (browsers cannot
        set headers on WebSocket and query strings end up in logs)."""
        self.check_host(host)
        self.check_origin(origin)


def write_dev_env(path: Path, base_url: str, token: str) -> None:
    """Hand the port/token to the Vite dev app via an env file (e.g. `.env.local`, which
    Vite ignores in git by convention). Merges: other keys in the file are preserved.
    Note: VITE_* values are bundled into the dev client - acceptable for localhost dev only."""
    path = Path(path)
    ours = {"VITE_RUBY_BRIDGE_URL": base_url, "VITE_RUBY_BRIDGE_TOKEN": token}
    kept = []
    if path.exists():
        kept = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.split("=", 1)[0].strip() not in ours]
    text = "\n".join([*kept, *(f"{k}={v}" for k, v in ours.items())]) + "\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner-only on POSIX
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)  # no-op semantics on Windows (inherits the folder's ACL)
    except OSError:
        pass
