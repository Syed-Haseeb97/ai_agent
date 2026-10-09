"""CLI entry point for Ruby F16 — Autonomous Computer Use Mode."""
from __future__ import annotations

import argparse
import logging
import threading

from pynput import keyboard
from agent.autonomous_loop import AutonomousAgent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Ruby continuously on a desktop task.")
    parser.add_argument("goal", nargs="+", help="Natural-language objective for Ruby")
    parser.add_argument("--max-turns", type=int, default=120)
    parser.add_argument("--max-hours", type=float, default=4.0)
    args = parser.parse_args()

    logging.basicConfig(
        filename="autonomous_agent.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    stop_event = threading.Event()

    def emergency_stop() -> None:
        logging.critical("Emergency stop hotkey pressed; requesting cooperative stop.")
        stop_event.set()

    # pynput owns an independent listener thread. Prefer cooperative cancellation
    # over os._exit(), which can leave the desktop in a partially completed state.
    hotkey = keyboard.GlobalHotKeys({"<ctrl>+<alt>+<shift>+q": emergency_stop})
    hotkey.start()
    try:
        goal = " ".join(args.goal)
        logging.info("Autonomous run started: %s", goal)
        result = AutonomousAgent(
            max_turns=max(1, args.max_turns),
            max_runtime_seconds=max(1, int(args.max_hours * 3600)),
            stop_event=stop_event,
        ).run(goal)
        logging.info("Autonomous run finished: %s", result)
        print(f"Ruby autonomous mode: {result.status} — {result.message}")
        return 0 if result.status == "completed" else 2
    finally:
        stop_event.set()
        hotkey.stop()


if __name__ == "__main__":
    raise SystemExit(main())
