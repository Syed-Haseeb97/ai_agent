"""
AI Screen Assistant – free MVP for Windows 11
Click the floating circle (or press Ctrl+Alt+Space) → speak → it sees your screen + answers.
"""

from __future__ import annotations

import sys
import os

# Ensure project root is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.floating_button import FloatingButton
from hotkey_manager import HotkeyManager


def main():
    # High-DPI awareness
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running when button is hidden
    app.setApplicationName("AI Screen Assistant")
    app.setFont(QFont("Segoe UI", 10))

    button = FloatingButton()
    button.show()

    # Global hotkey
    hotkey = HotkeyManager(callback=button.trigger)
    hotkey.start()

    # Clean shutdown
    app.aboutToQuit.connect(hotkey.stop)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
