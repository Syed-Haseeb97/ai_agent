"""Small, explicit browser UI actions used by the Windows action layer."""
from __future__ import annotations

import time
import urllib.parse

import pyautogui
import pygetwindow as gw


class BrowserActions:
    """Perform conservative actions against an already-open browser window."""

    @staticmethod
    def _find_browser_window(preferred_title: str | None = None):
        titles = [t for t in gw.getAllTitles() if t]
        preferred = (preferred_title or "").lower()
        if preferred:
            for title in titles:
                if preferred in title.lower() and ("chrome" in title.lower() or "youtube" in title.lower()):
                    return gw.getWindowsWithTitle(title)[0]
        for title in titles:
            lower = title.lower()
            if "chrome" in lower or "youtube" in lower:
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    return windows[0]
        return None

    def search_current_tab(self, query: str, preferred_title: str | None = None) -> bool:
        query = query.strip()
        if not query:
            return False
        window = self._find_browser_window(preferred_title)
        if window is None:
            return False
        try:
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.15)
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            pyautogui.hotkey("ctrl", "l")
            pyautogui.write(url, interval=0.005)
            pyautogui.press("enter")
            return True
        except Exception:
            return False
