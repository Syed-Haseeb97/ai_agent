"""
Global hotkey listener (Ctrl+Alt+Space) using pynput.
Runs in its own thread and emits a callback.
"""

from __future__ import annotations

from typing import Callable, Optional
from pynput import keyboard


class HotkeyManager:
    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self._listener: Optional[keyboard.GlobalHotKeys] = None

    def start(self):
        # Ctrl+Alt+Space
        hotkey = "<ctrl>+<alt>+<space>"
        self._listener = keyboard.GlobalHotKeys({hotkey: self._on_hotkey})
        self._listener.start()

    def _on_hotkey(self):
        try:
            self.callback()
        except Exception:
            pass  # never let hotkey crash the app

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
