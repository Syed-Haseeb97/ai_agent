"""Browser automation used by the Windows action layer.

The browser layer is intentionally isolated from the rest of the assistant. It
uses a dedicated Playwright-controlled Chrome profile for reliable DOM actions,
while retaining a conservative fallback for an already-open Chrome window.
"""
from __future__ import annotations

import os
import shutil
import time
import urllib.parse
from pathlib import Path

import pyautogui
import pygetwindow as gw
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright


class BrowserActions:
    """Perform explicit browser actions without changing the legacy UI path."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None

    @staticmethod
    def _chrome_path() -> str | None:
        candidates = [
            os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return shutil.which("chrome.exe")

    def _ensure_context(self) -> BrowserContext:
        if self._context is not None:
            return self._context

        self._playwright = sync_playwright().start()
        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Ruby" / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        executable = self._chrome_path()
        kwargs = {
            "user_data_dir": str(profile),
            "headless": False,
            "no_viewport": True,
            "args": ["--start-maximized"],
        }
        if executable:
            kwargs["executable_path"] = executable
        self._context = self._playwright.chromium.launch_persistent_context(**kwargs)
        return self._context

    def _page(self, url_hint: str | None = None) -> Page:
        context = self._ensure_context()
        pages = context.pages
        if url_hint:
            hint = url_hint.lower()
            for page in reversed(pages):
                if hint in page.url.lower():
                    return page
        if pages:
            return pages[-1]
        return context.new_page()

    def open_url(self, url: str) -> bool:
        try:
            page = self._page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return True
        except Exception:
            return False

    def search_current_tab(self, query: str, preferred_title: str | None = None) -> bool:
        """Search an existing YouTube tab; use Playwright when Ruby owns it."""
        query = query.strip()
        if not query:
            return False
        try:
            page = self._page("youtube")
            if "youtube.com" in page.url.lower():
                page.goto(
                    "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                return True
        except Exception:
            pass
        return self._keyboard_search_existing_window(query, preferred_title)

    def search_current_page(self, query: str) -> bool:
        """Search the currently controlled page using its site, without requiring a site name."""
        query = query.strip()
        if not query:
            return False
        try:
            page = self._page()
            current = page.url.lower()
            if "youtube.com" in current:
                return self.search(query, "youtube")
            if "google.com" in current:
                return self.search(query, "google")
        except Exception:
            pass
        return False

    def search(self, query: str, site: str = "youtube") -> bool:
        query = query.strip()
        if not query:
            return False
        site = site.lower()
        if site in {"youtube", "yt"}:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        elif site == "google":
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        return self.open_url(url)

    def play_youtube(self, query: str | None = None) -> bool:
        try:
            page = self._page("youtube")
            if query:
                self.search(query, "youtube")
                page = self._page("youtube")
                page.wait_for_selector("a#video-title", timeout=10000)
            button = page.locator("button[aria-label*='Play'], button[title*='Play']").first
            if button.count():
                button.click(timeout=5000)
                return True
            video = page.locator("a#video-title").first
            if video.count():
                video.click(timeout=5000)
                return True
        except Exception:
            return False
        return False

    def play_latest_youtube_video(self, query: str) -> bool:
        """Open the first current YouTube result for the requested topic."""
        try:
            self.search(query, "youtube")
            page = self._page("youtube")
            page.wait_for_selector("a#video-title", timeout=15000)
            result = page.locator("a#video-title").first
            if result.count():
                result.click(timeout=5000)
                return True
        except Exception:
            return False
        return False

    def pause_youtube(self) -> bool:
        try:
            page = self._page("youtube")
            button = page.locator("button[aria-label*='Pause'], button[title*='Pause']").first
            if button.count():
                button.click(timeout=5000)
                return True
        except Exception:
            return False
        return False

    def click_text(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        try:
            page = self._page()
            locators = [
                page.get_by_role("button", name=text, exact=False).first,
                page.get_by_role("link", name=text, exact=False).first,
                page.get_by_text(text, exact=False).first,
            ]
            for locator in locators:
                if locator.count():
                    locator.click(timeout=5000)
                    return True
        except Exception:
            return False
        return False

    def type_text(self, text: str) -> bool:
        try:
            page = self._page()
            page.keyboard.type(text)
            return True
        except Exception:
            return False

    def go_back(self) -> bool:
        try:
            self._page().go_back(wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception:
            return False

    def go_forward(self) -> bool:
        try:
            self._page().go_forward(wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception:
            return False

    def refresh(self) -> bool:
        try:
            self._page().reload(wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception:
            return False

    def close_tab(self) -> bool:
        try:
            page = self._page()
            page.close()
            return True
        except Exception:
            return False

    @staticmethod
    def _find_browser_window(preferred_title: str | None = None):
        titles = [t for t in gw.getAllTitles() if t]
        preferred = (preferred_title or "").lower()
        if preferred:
            for title in titles:
                if preferred in title.lower() and ("chrome" in title.lower() or "youtube" in title.lower()):
                    windows = gw.getWindowsWithTitle(title)
                    if windows:
                        return windows[0]
        for title in titles:
            lower = title.lower()
            if "chrome" in lower or "youtube" in lower:
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    return windows[0]
        return None

    def _keyboard_search_existing_window(self, query: str, preferred_title: str | None = None) -> bool:
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

    def shutdown(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
