"""Runtime hardening for browser automation."""
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright

from .browser_actions import BrowserActions
from .browser_agent import BrowserAgent, BrowserTaskResult


def _ensure_context(self: BrowserActions) -> BrowserContext:
    if self._context is not None:
        return self._context
    self._playwright = sync_playwright().start()
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Ruby"
    chrome_profile = base / "browser-profile"
    chromium_profile = base / "browser-profile-chromium"
    chrome_profile.mkdir(parents=True, exist_ok=True)
    chromium_profile.mkdir(parents=True, exist_ok=True)
    attempts = []
    chrome = self._chrome_path()
    if chrome:
        attempts.append({"user_data_dir": str(chrome_profile), "headless": False, "no_viewport": True, "args": ["--start-maximized"], "executable_path": chrome})
    attempts.append({"user_data_dir": str(chromium_profile), "headless": False, "no_viewport": True, "args": ["--start-maximized"]})
    last_error = None
    for kwargs in attempts:
        try:
            self._context = self._playwright.chromium.launch_persistent_context(**kwargs)
            return self._context
        except Exception as exc:
            last_error = exc
            self._context = None
    try:
        self._playwright.stop()
    except Exception:
        pass
    self._playwright = None
    raise RuntimeError(f"Unable to start a visible browser: {last_error}")


def _search_current_page(self: BrowserActions, query: str) -> bool:
    query = query.strip()
    if not query:
        return False
    site = self._current_site
    try:
        if site == "linkedin":
            page = self._page()
            self._bring_to_front(page)
            page.goto("https://www.linkedin.com/search/results/all/?keywords=" + urllib.parse.quote(query), wait_until="domcontentloaded", timeout=30000)
            return True
        if site == "spotify":
            page = self._page()
            self._bring_to_front(page)
            page.goto("https://open.spotify.com/search/" + urllib.parse.quote(query), wait_until="domcontentloaded", timeout=30000)
            return True
    except Exception:
        return False
    return _ORIGINAL_SEARCH_CURRENT_PAGE(self, query)


def _play_spotify_track(self: BrowserActions, track: str) -> bool:
    track = track.strip()
    if not track:
        return False
    try:
        page = self._page()
        self._bring_to_front(page)
        page.goto("https://open.spotify.com/search/" + urllib.parse.quote(track), wait_until="domcontentloaded", timeout=30000)
        self._current_site = "spotify"
        page.wait_for_timeout(1500)
        selectors = ("[data-testid='tracklist-row']", "div[data-testid='tracklist-row']", "a[href*='/track/']")
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.scroll_into_view_if_needed(timeout=5000)
                    locator.click(timeout=8000)
                    page.wait_for_timeout(1200)
                    return True
            except Exception:
                continue
        try:
            locator = page.get_by_text(track, exact=False).first
            if locator.count() and locator.is_visible():
                locator.click(timeout=8000)
                page.wait_for_timeout(1200)
                return True
        except Exception:
            pass
        return False
    except Exception:
        return False


_ORIGINAL_EXECUTE = BrowserAgent.execute
_ORIGINAL_SEARCH_CURRENT_PAGE = BrowserActions.search_current_page


def _execute(self: BrowserAgent, text: str) -> BrowserTaskResult:
    normalized = text.strip().replace("linkdin", "linkedin")
    lower = normalized.lower()
    if lower == "open spotify":
        ok = self.browser.open_url("https://open.spotify.com")
        return BrowserTaskResult(ok, "Opening spotify…" if ok else "I tried to open spotify, but the browser action failed.", recognized=True)
    match = re.match(r"^open\s+spotify\s+and\s+play\s+(.+?)\s*$", normalized, re.I)
    if match:
        track = match.group(1).strip()
        if not self.browser.open_url("https://open.spotify.com"):
            return BrowserTaskResult(False, "I tried to open Spotify, but the browser action failed.", recognized=True)
        if self.browser.play_spotify_track(track):
            return BrowserTaskResult(True, f"Playing {track} on Spotify…", recognized=True)
        return BrowserTaskResult(False, f"Spotify opened, but I couldn't start {track}.", recognized=True)
    return _ORIGINAL_EXECUTE(self, normalized)


BrowserActions._ensure_context = _ensure_context
BrowserActions.search_current_page = _search_current_page
BrowserActions.play_spotify_track = _play_spotify_track
BrowserAgent.execute = _execute
