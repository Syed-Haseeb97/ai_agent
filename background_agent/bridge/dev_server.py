"""Development server for building the React UI WITHOUT a real planner.

    python -m background_agent.bridge.dev_server --env-file desktop_app/.env.local

Goals containing certain words trigger demo behaviour:
    (anything)  write a file, run a short process, finish           -> COMPLETED
    "confirm"   overwrite the file                                    -> approval prompt
    "delete"    delete the file                                       -> approval prompt (destructive)
    "gui"       tries a GUI click                                     -> FAILED GUI_ISOLATION_REQUIRED
    "slow"      runs a 60s process so you can test Stop               -> use Stop
    "fail"      claims a file it never created                        -> FAILED VERIFICATION_FAILED
This is NOT an AI planner. Dev only.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from ..actions import Action, ActionKind
from ..backends.local_tools import LocalToolBackend
from ..planner import Finish, PlanContext, Planner
from ..models import TaskLimits
from .security import write_dev_env
from .service import BridgeService


class DemoPlanner(Planner):
    def __init__(self, goal: str) -> None:
        g = goal.lower()
        py = sys.executable
        steps = [Action(ActionKind.FS_WRITE, {"path": "demo.md", "content": f"# Demo\n\nGoal: {goal[:200]}\n"})]
        steps.append(Action(ActionKind.PROCESS_RUN, {"argv": [py, "-c", "import time; time.sleep(60 if 'slow' in %r else 2)" % g]}))
        if "confirm" in g:
            steps.append(Action(ActionKind.FS_WRITE, {"path": "demo.md", "content": "# Overwritten\n", "overwrite": True}))
        if "delete" in g:
            steps.append(Action(ActionKind.FS_DELETE, {"path": "demo.md"}))
        if "gui" in g:
            steps.append(Action(ActionKind.GUI_CLICK, {"x": 1, "y": 1}))
        claimed = ("ghost.xlsx",) if "fail" in g else ("demo.md",)
        steps.append(Finish("Demo task finished.", claimed, no_artifacts_expected=False))
        self._steps = steps
        self._i = 0

    def next_step(self, ctx: PlanContext):
        step = self._steps[min(self._i, len(self._steps) - 1)]
        self._i += 1
        return step


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--env-file", type=Path, help="write VITE_RUBY_BRIDGE_URL/TOKEN here (e.g. desktop_app/.env.local)")
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        from .server import BridgeServer
        import uvicorn  # noqa: F401
    except ImportError:
        print('FastAPI/uvicorn are required: pip install fastapi "uvicorn[standard]"', file=sys.stderr)
        return 2

    workspace = args.workspace or Path(tempfile.mkdtemp(prefix="ruby-bridge-dev-"))
    service = BridgeService.create(
        LocalToolBackend(workspace), lambda task: DemoPlanner(task.goal),
        default_limits=TaskLimits(max_runtime_seconds=120, cleanup_timeout_seconds=5))
    server = BridgeServer(service, port=args.port)
    service.start()
    server.start()
    if args.env_file:
        write_dev_env(args.env_file, server.base_url, service.auth.token)
        print(f"wrote bridge URL + token to {args.env_file}")
    else:
        print(f"bridge listening on {server.base_url} (use --env-file to hand the token to the Vite app)")
    print(f"workspace: {workspace}\nCtrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        service.shutdown()
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
