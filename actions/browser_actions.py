"""Playwright-backed browser primitives used by Ruby's generic browser agent."""
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
    """Low-level browser operations. No user/site/channel names are hard-coded."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._current_site: str | None = None

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
        kwargs = {"user_data_dir": str(profile), "headless": False, "no_viewport": True, "args": ["--start-maximized"]}
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
        """Open a URL in the user's existing Chrome when possible.

        The previous implementation always created a separate Playwright
        profile. That meant the assistant could open YouTube in one Chrome
        instance while the user was looking at another, and later browser
        commands operated on the wrong context. Prefer the visible existing
        Chrome window and fall back to Playwright only when no Chrome window
        exists.
        """
        try:
            window = self._find_browser_window()
            if window is not None:
                if window.isMinimized:
                    window.restore()
                window.activate()
                time.sleep(0.15)
                pyautogui.hotkey("ctrl", "l")
                pyautogui.write(url, interval=0.003)
                pyautogui.press("enter")
                self._remember_site(url)
                return True
        except Exception:
            pass

        try:
            page = self._page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._remember_site(page.url)
            return True
        except Exception:
            return False

    def search(self, query: str, site: str = "youtube") -> bool:
        query = query.strip()
        if not query:
            return False
        site = site.lower()
        if site in {"youtube", "yt"}:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            site = "youtube"
        elif site == "google":
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        elif site == "github":
            url = "https://github.com/search?q=" + urllib.parse.quote_plus(query)
        elif site == "reddit":
            url = "https://www.reddit.com/search/?q=" + urllib.parse.quote_plus(query)
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            site = "google"

        # Search in the same visible browser window the user is already using.
        if self._keyboard_search_existing_window(query, preferred_title=site):
            self._current_site = site
            return True

        ok = self.open_url(url)
        if ok:
            self._current_site = site
        return ok

    def search_current_page(self, query: str) -> bool:
        """Search the current visible browser page, not a hidden/separate profile."""
        query = query.strip()
        if not query:
            return False

        # First use the visible Chrome window. This is the user's actual tab.
        site = self._current_site or self._site_from_window_title()
        if site in {"youtube", "google", "github", "reddit"}:
            return self.search(query, site)

        # If Playwright already owns a useful page, use its URL as a fallback.
        try:
            page = self._page()
            current = page.url.lower()
            site = self._site_from_url(current) or self._current_site
            if site in {"youtube", "google", "github", "reddit"}:
                return self.search(query, site)
        except Exception:
            pass

        return False

    def play_youtube(self, query: str | None = None) -> bool:
        try:
            page = self._page("youtube")
            if query:
                self.search(query, "youtube")
                page = self._page("youtube")
                page.wait_for_selector("a#video-title", timeout=12000)
            return self._click_first_video(page)
        except Exception:
            return False

    def play_latest_youtube_video(self, query: str | None = None) -> bool:
        """Search optionally, request newest-first results, then inspect the DOM and open the first video."""
        try:
            # When a query is supplied, navigate/search in the visible Chrome
            # first. Playwright is then used only if it can see that same page.
            if query:
                if not self.search(query, "youtube"):
                    return False
            page = self._page("youtube")
            page.wait_for_selector("a#video-title", timeout=15000)
            return self._click_first_video(page)
        except Exception:
            # Last-resort keyboard path for the user's visible Chrome.
            if query and self._keyboard_search_existing_window(query, "youtube"):
                time.sleep(1.5)
                return self._keyboard_click_first_youtube_video()
            return False

    @staticmethod
    def _click_first_video(page: Page) -> bool:
        candidates = [
            page.locator("ytd-video-renderer a#video-title").first,
            page.locator("ytd-rich-item-renderer a#video-title").first,
            page.locator("a#video-title").first,
        ]
        for locator in candidates:
            try:
                if locator.count() and locator.is_visible():
                    locator.click(timeout=7000)
                    return True
            except Exception:
                continue
        return False

    def _keyboard_click_first_youtube_video(self) -> bool:
        """Use keyboard navigation as a last-resort fallback in visible Chrome."""
        window = self._find_browser_window("youtube")
        if window is None:
            return False
        try:
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(0.2)
            pyautogui.press("tab", presses=8, interval=0.05)
            pyautogui.press("enter")
            return True
        except Exception:
            return False

    def click_first_result(self) -> bool:
        try:
            page = self._page()
            selectors = [
                "ytd-video-renderer a#video-title",
                "ytd-rich-item-renderer a#video-title",
                "main a[href*='/watch']",
                "main a[href*='/results/']",
            ]
            for selector in selectors:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.click(timeout=7000)
                    return True
        except Exception:
            pass
        return False

    def pause_youtube(self) -> bool:
        try:
            page = self._page("youtube")
            button = page.locator("button[aria-label*='Pause'], button[title*='Pause']").first
            if button.count() and button.is_visible():
                button.click(timeout=5000)
                return True
        except Exception:
            pass
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
                try:
                    if locator.count() and locator.is_visible():
                        locator.click(timeout=7000)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def type_text(self, text: str, target: str | None = None) -> bool:
        try:
            page = self._page()
            if target:
                locators = [
                    page.get_by_role("textbox", name=target, exact=False).first,
                    page.get_by_placeholder(target, exact=False).first,
                    page.get_by_text(target, exact=False).first,
                ]
                for locator in locators:
                    try:
                        if locator.count() and locator.is_visible():
                            locator.click(timeout=5000)
                            locator.fill(text)
                            return True
                    except Exception:
                        continue
            page.keyboard.type(text)
            return True
        except Exception:
            return False

    def scroll(self, direction: str = "down") -> bool:
        try:
            page = self._page()
            delta = 700 if direction == "down" else -700
            page.mouse.wheel(0, delta)
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
            self._page().close()
            return True
        except Exception:
            return False

    @staticmethod
    def _site_from_url(url: str) -> str | None:
        lower = url.lower()
        if "youtube.com" in lower or "youtu.be" in lower:
            return "youtube"
        if "google.com" in lower:
            return "google"
        if "github.com" in lower:
            return "github"
        if "reddit.com" in lower:
            return "reddit"
        return None

    @staticmethod
    def _site_from_window_title() -> str | None:
        try:
            titles = [t.lower() for t in gw.getAllTitles() if t]
            for title in titles:
                if "youtube" in title:
                    return "youtube"
                if "google" in title:
                    return "google"
                if "github" in title:
                    return "github"
                if "reddit" in title:
                    return "reddit"
        except Exception:
            pass
        return None

    def _remember_site(self, url: str) -> None:
        site = self._site_from_url(url)
        if site:
            self._current_site = site

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
            site = (preferred_title or self._site_from_window_title() or "youtube").lower()
            if site in {"youtube", "yt"}:
                url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            elif site == "google":
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            elif site == "github":
                url = "https://github.com/search?q=" + urllib.parse.quote_plus(query)
            elif site == "reddit":
                url = "https://www.reddit.com/search/?q=" + urllib.parse.quote_plus(query)
            else:
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
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
