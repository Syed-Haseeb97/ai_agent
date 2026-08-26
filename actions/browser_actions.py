"""Playwright-backed browser primitives used by Ruby's generic browser agent.

Design note (read before touching this file)
----------------------------------------------
Earlier versions of this module drove the browser in two completely
different, uncoordinated ways:

1. ``open_url``/``search`` tried ``pyautogui`` window-activation + keystrokes
   aimed at whatever window Windows reported as "Chrome" (``pygetwindow``).
2. Every other action (clicking a video, typing, scrolling, going back...)
   used a Playwright ``Page`` from a *separate*, dedicated automation
   browser context (``launch_persistent_context``).

Those are two different browser windows. A search performed via keystrokes
in the user's real Chrome window left the Playwright-controlled window
untouched (often still on ``about:blank``), so any later DOM-based action
(click the first video, etc.) ran against the wrong page and silently did
nothing useful. The "play the latest video" path made this worse by not
using Playwright at all: it blindly pressed Tab ~12 times and Enter,
*always* reporting success regardless of what was actually focused -- which
is why the assistant would say "Playing the latest video for X..." while
the browser did nothing.

The fix is architectural, not cosmetic: every single action in this class
now goes through the *same* Playwright-controlled, visible (non-headless)
persistent browser context, using real DOM locators. There is exactly one
browser, one context, and one notion of "the current page." No pyautogui,
no window-title guessing, no blind keystroke sequences.
"""
from __future__ import annotations

import os
import shutil
import urllib.parse
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

# YouTube's "sort by upload date" search filter. This is what makes
# "play the latest video by X" actually mean *latest*, instead of just
# "most relevant", which is YouTube's default search ordering.
_YOUTUBE_SORT_NEWEST = "&sp=CAISAhAB"

_VIDEO_LINK_SELECTORS = (
    "ytd-video-renderer a#video-title",
    "ytd-rich-item-renderer a#video-title",
    "ytd-channel-video-player-renderer a#video-title",
    "a#video-title",
)


class BrowserActions:
    """Low-level browser operations. No user/site/channel names are hard-coded."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._current_site: str | None = None

    # ------------------------------------------------------------------
    # Context / page plumbing
    # ------------------------------------------------------------------
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
        """Start (once) the single, visible, persistent browser context that
        every action in this class operates on. ``headless=False`` means
        this is a real, on-screen browser window -- not a hidden one."""
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
        """Return the page the user is looking at. If ``url_hint`` is given,
        prefer an already-open tab whose URL matches it (e.g. "youtube"),
        so we keep acting on the same tab instead of accumulating new ones.
        """
        context = self._ensure_context()
        pages = context.pages
        if url_hint:
            hint = url_hint.lower()
            for page in reversed(pages):
                try:
                    if hint in page.url.lower():
                        return page
                except Exception:
                    continue
        if pages:
            return pages[-1]
        return context.new_page()

    def _bring_to_front(self, page: Page) -> None:
        try:
            page.bring_to_front()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def open_url(self, url: str) -> bool:
        """Navigate the visible Playwright-controlled browser to ``url``."""
        try:
            page = self._page()
            self._bring_to_front(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._remember_site(page.url)
            return True
        except Exception:
            return False

    def search(self, query: str, site: str = "youtube", newest: bool = False) -> bool:
        """Build a search-results URL for ``site`` and navigate to it.

        ``newest`` (YouTube only) sorts by upload date so "latest video"
        requests actually land on the most recently uploaded video, not
        just the most "relevant" one.
        """
        query = query.strip()
        if not query:
            return False
        site = site.lower()
        if site in {"youtube", "yt"}:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            if newest:
                url += _YOUTUBE_SORT_NEWEST
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
        ok = self.open_url(url)
        if ok:
            self._current_site = site
        return ok

    def search_current_page(self, query: str) -> bool:
        """Search using whatever site the user was last on, without letting
        an explicit destination elsewhere override it (that logic lives in
        BrowserAgent -- by the time we get here, the caller has already
        decided this should reuse the current context)."""
        query = query.strip()
        if not query:
            return False
        site = self._current_site
        if site not in {"youtube", "google", "github", "reddit"}:
            try:
                site = self._site_from_url(self._page().url)
            except Exception:
                site = None
        if site in {"youtube", "google", "github", "reddit"}:
            return self.search(query, site)
        return False

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------
    def play_latest_youtube_video(self, query: str | None = None) -> bool:
        """Find and click a video on YouTube using real DOM locators.

        If ``query`` is given, this performs a fresh "sorted by upload
        date" search for it first (so "the latest video by X" means the
        actual newest upload, for an arbitrary, user-supplied ``X`` --
        never a hardcoded name). Either way, the click itself is delegated
        to :meth:`click_first_result`-equivalent logic, which waits for and
        clicks the real first result element instead of guessing with Tab
        presses.
        """
        try:
            if query:
                if not self.search(query, "youtube", newest=True):
                    return False
                page = self._page("youtube")
                page.wait_for_selector(", ".join(_VIDEO_LINK_SELECTORS), timeout=12000)
            else:
                page = self._page("youtube")
                if "youtube.com" not in page.url.lower():
                    return False
                page.wait_for_selector(", ".join(_VIDEO_LINK_SELECTORS), timeout=12000)
            return self._click_first_video(page)
        except Exception:
            return False

    @staticmethod
    def _click_first_video(page: Page) -> bool:
        for selector in _VIDEO_LINK_SELECTORS:
            try:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.scroll_into_view_if_needed(timeout=5000)
                    locator.click(timeout=7000)
                    return True
            except Exception:
                continue
        return False

    def click_first_result(self) -> bool:
        """Click the first visible result on the current page (YouTube
        search results / channel video grid, or a generic results list)."""
        try:
            page = self._page()
            selectors = list(_VIDEO_LINK_SELECTORS) + [
                "main a[href*='/watch']",
                "main a[href*='/results/']",
            ]
            for selector in selectors:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.scroll_into_view_if_needed(timeout=5000)
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

    # ------------------------------------------------------------------
    # Generic interaction
    # ------------------------------------------------------------------
    def click_text(self, text: str) -> bool:
        text = text.strip()
        if not text:
            return False
        try:
            page = self._page()
            self._bring_to_front(page)
            locators = [
                page.get_by_role("button", name=text, exact=False).first,
                page.get_by_role("link", name=text, exact=False).first,
                page.get_by_text(text, exact=False).first,
            ]
            for locator in locators:
                try:
                    if locator.count() and locator.is_visible():
                        locator.scroll_into_view_if_needed(timeout=5000)
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
            self._bring_to_front(page)
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

    def _remember_site(self, url: str) -> None:
        site = self._site_from_url(url)
        if site:
            self._current_site = site

    def shutdown(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
