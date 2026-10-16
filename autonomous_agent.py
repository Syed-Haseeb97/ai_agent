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
    parser.add_argument("--no-orb", action="store_true", help="Run without the visual cursor-following orb.")
    args = parser.parse_args()

    logging.basicConfig(filename="autonomous_agent.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop_event = threading.Event()
    hotkey = keyboard.GlobalHotKeys({"<ctrl>+<alt>+<shift>+r": stop_event.set})
    hotkey.start()
    try:
        goal = " ".join(args.goal)
        logging.info("Autonomous run started: %s", goal)
        if args.no_orb:
            result = AutonomousAgent(
                max_turns=max(1, args.max_turns),
                max_runtime_seconds=max(1, int(args.max_hours * 3600)),
                stop_event=stop_event,
            ).run(goal)
            logging.info("Autonomous run finished: %s", result)
            print(f"Ruby autonomous mode: {result.status} — {result.message}")
            return 0 if result.status == "completed" else 2

        from PyQt6.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
        from PyQt6.QtWidgets import QApplication
        from ui.cursor_companion import CursorCompanion

        class RunSignals(QObject):
            action_started = pyqtSignal(object)
            action_finished = pyqtSignal(object)
            finished = pyqtSignal(object)

        class RunController(QObject):
            def __init__(self, app, companion):
                super().__init__()
                self.app = app
                self.companion = companion
                self.exit_code = 2

            @pyqtSlot(object)
            def finish(self, result):
                logging.info("Autonomous run finished: %s", result)
                print(f"Ruby autonomous mode: {result.status} — {result.message}")
                self.exit_code = 0 if result.status == "completed" else 2
                self.companion.return_home()
                QTimer.singleShot(800, self.app.quit)

        app = QApplication.instance() or QApplication([])
        app.setQuitOnLastWindowClosed(False)
        companion = CursorCompanion()
        companion.show()
        signals = RunSignals()
        controller = RunController(app, companion)
        signals.action_started.connect(companion.follow_cursor)
        signals.action_finished.connect(companion.release_cursor)
        signals.finished.connect(controller.finish)

        def run_agent():
            result = AutonomousAgent(
                max_turns=max(1, args.max_turns),
                max_runtime_seconds=max(1, int(args.max_hours * 3600)),
                stop_event=stop_event,
                on_action_start=signals.action_started.emit,
                on_action_end=signals.action_finished.emit,
            ).run(goal)
            signals.finished.emit(result)

        worker = threading.Thread(target=run_agent, name="ruby-autonomous-agent", daemon=True)
        worker.start()
        app.exec()
        worker.join(timeout=1.0)
        return controller.exit_code
    finally:
        hotkey.stop()


if __name__ == "__main__":
    raise SystemExit(main())
