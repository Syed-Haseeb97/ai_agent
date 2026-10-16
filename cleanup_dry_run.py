"""CLI for inspecting a temporary directory without deleting anything.

Example:
    python cleanup_dry_run.py
    python cleanup_dry_run.py --root "%TEMP%" --max-entries 2000
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import tempfile
import threading

from agent.cleanup_executor import build_cleanup_dry_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview Ruby's temporary-file cleanup candidates; no files are deleted."
    )
    parser.add_argument(
        "--root",
        default=tempfile.gettempdir(),
        help="Absolute temporary directory to inspect (default: current OS temp directory).",
    )
    parser.add_argument("--max-entries", type=int, default=10_000)
    args = parser.parse_args(argv)

    stop_event = threading.Event()
    previous_sigint = signal.getsignal(signal.SIGINT)

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    try:
        plan = build_cleanup_dry_run(
            args.root,
            max_entries=args.max_entries,
            stop_requested=stop_event.is_set,
        )
        print(json.dumps(plan.to_dict(), indent=2))
        if plan.cancelled:
            return 130
        return 0
    except (OSError, ValueError, PermissionError) as exc:
        print(
            json.dumps({"error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    finally:
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
