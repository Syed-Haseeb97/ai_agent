"""Small compatibility extensions for the generic browser agent.

Core browser lifecycle and generic search live in browser_actions.py. This
module only adds capabilities that genuinely need site-specific interaction.
"""
from __future__ import annotations

import re
import urllib.parse

from .browser_actions import BrowserActions
from .browser_agent import BrowserAgent, BrowserTaskResult

_ORIGINAL_EXECUTE = BrowserAgent.execute


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
        for selector in ("[data-testid='tracklist-row']", "div[data-testid='tracklist-row']", "a[href*='/track/']"):
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
    except Exception:
        pass
    return False


def _execute(self: BrowserAgent, text: str) -> BrowserTaskResult:
    normalized = text.strip()
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


def _generic_destination_url(target: str) -> str:
    """Resolve arbitrary spoken website names without a growing site whitelist."""
    target = re.sub(r"\s+", " ", target).strip()
    query = urllib.parse.quote_plus(f"{target} official website")
    return f"https://www.google.com/search?q={query}&btnI=1"


BrowserActions.play_spotify_track = _play_spotify_track
BrowserAgent._guess_url = staticmethod(_generic_destination_url)
BrowserAgent.execute = _execute
