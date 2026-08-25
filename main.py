"""AI Screen Assistant – free MVP for Windows 11."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.floating_button import FloatingButton
from hotkey_manager import HotkeyManager
from voice.wake_word import WakeWordService


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("AI Screen Assistant")
    app.setFont(QFont("Segoe UI", 10))

    button = FloatingButton()
    button.show()

    hotkey = HotkeyManager(callback=button.request_trigger)
    hotkey.start()

    wake_word = WakeWordService(callback=button.request_trigger)
    wake_word.start()

    app.aboutToQuit.connect(hotkey.stop)
    app.aboutToQuit.connect(wake_word.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
