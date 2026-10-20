"""Production bridge host using Ruby's configured Gemini client.

Development and tests should use ``dev_server``/``DemoPlanner``. This launcher
supports only workspace-confined filesystem actions; process, browser, and GUI
actions are not enabled in production until they have a separately reviewed,
contained execution backend.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from ai.chat_service import ChatService
from ..actions import FS_KINDS
from ..backends.local_tools import LocalToolBackend
from ..gemini_planner import GeminiPlanner
from ..models import TaskLimits
from ..policy import DefaultActionPolicy
from .security import write_bridge_env
from .service import BridgeService

ROOT = Path(__file__).resolve().parents[2]


def default_workspace(environ=None) -> Path:
    env = os.environ if environ is None else environ
    base = Path(env.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "Ruby" / "BackgroundWorkspace"


def build_production_service(*, api_key: Optional[str] = None,
                             workspace: Optional[Path] = None,
                             token: Optional[str] = None,
                             gemini_client_factory: Optional[Callable] = None,
                             backend_factory: Optional[Callable] = None) -> BridgeService:
    key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY")
    if not isinstance(key, str) or not key.strip() or key.strip() == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY is required. Set it in the repository .env file or the process environment.")
    key = key.strip()
    if gemini_client_factory is None:
        from ai.gemini_client import GeminiClient
        gemini_client_factory = GeminiClient
    if backend_factory is None:
        backend_factory = LocalToolBackend
    try:
        client = gemini_client_factory(api_key=key)
    except Exception as exc:
        raise RuntimeError(f"Could not initialize Ruby's Gemini client: {type(exc).__name__}: {exc}") from None

    root = Path(workspace or default_workspace()).expanduser().resolve()
    backend = backend_factory(root, enable_browser=False, allowed_kinds=FS_KINDS)
    bridge_token = token if token is not None else os.getenv("RUBY_BRIDGE_TOKEN")
    return BridgeService.create(
        backend,
        lambda _task: GeminiPlanner(client),
        chat_service=ChatService(client),
        policy=DefaultActionPolicy(),
        default_limits=TaskLimits(max_runtime_seconds=900, max_actions=50, max_turns=75,
                                 cancel_grace_seconds=2, cleanup_timeout_seconds=10),
        token=bridge_token,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="loopback interface only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", type=Path, default=None,
                        help="root for per-task workspaces (default: %%LOCALAPPDATA%%/Ruby/BackgroundWorkspace)")
    parser.add_argument("--bridge-env-file", type=Path, default=ROOT / "desktop_app" / ".env.local",
                        help="host-only URL/token file read by Electron (default: desktop_app/.env.local)")
    parser.add_argument("--managed", action="store_true",
                        help="Electron owns this process; report readiness on stdout without writing credentials to disk")
    parser.add_argument("--validate-gemini", action="store_true",
                        help="validate GEMINI_API_KEY with a small Gemini request, then exit")
    parser.add_argument("--shutdown-file", type=Path, default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.validate_gemini:
        try:
            from ai.gemini_client import GeminiClient
            GeminiClient().generate_text("Reply with the single word OK.", max_output_tokens=8, timeout_seconds=15)
            return 0
        except Exception:
            print("Gemini could not validate this key. Check the key and network connection.", file=sys.stderr)
            return 3
    try:
        service = build_production_service(workspace=args.workspace)
        from .server import BridgeServer
        server = BridgeServer(service, host=args.host, port=args.port)
    except (ImportError, ValueError, RuntimeError) as exc:
        print(f"Ruby production bridge could not start: {exc}", file=sys.stderr)
        return 2

    started = False
    try:
        service.start()
        server.start()
        if args.managed:
            print(f"RUBY_BRIDGE_READY={server.base_url}", flush=True)
        else:
            write_bridge_env(args.bridge_env_file, server.base_url, service.auth.token)
            print(f"Ruby Gemini bridge listening at {server.base_url}")
            print(f"Workspace: {args.workspace or default_workspace()}")
            print(f"Electron host config: {args.bridge_env_file}")
            print("The bearer token was written to the host-only config file; it is not printed.")
        started = True
        while True:
            if args.shutdown_file and args.shutdown_file.exists():
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Ruby production bridge stopped after startup error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if started or service is not None:
            service.shutdown()
            if "server" in locals():
                server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
