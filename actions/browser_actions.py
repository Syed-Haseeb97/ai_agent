"""Playwright-backed browser primitives used by Ruby's generic browser agent."""
from __future__ import annotations

import os
import shutil
import urllib.parse
from pathlib import Path
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

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
        self._browser: Browser | None = None
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
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Ruby"
        persistent_chrome = root / "browser-profile"
        persistent_chromium = root / "browser-profile-chromium"
        persistent_chrome.mkdir(parents=True, exist_ok=True)
        persistent_chromium.mkdir(parents=True, exist_ok=True)
        chrome = self._chrome_path()
        errors: list[str] = []

        # Prefer a dedicated persistent Chrome profile so normal browser logins
        # survive restarts, but never let a locked profile take down all actions.
        attempts = []
        if chrome:
            attempts.append(("Chrome persistent", lambda: self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(persistent_chrome), headless=False, no_viewport=True,
                args=["--start-maximized"], executable_path=chrome)))
        attempts.append(("Chromium persistent", lambda: self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(persistent_chromium), headless=False, no_viewport=True,
            args=["--start-maximized"])))

        for label, starter in attempts:
            try:
                self._context = starter()
                return self._context
            except Exception as exc:
                errors.append(f"{label}: {exc}")

        # Last-resort non-persistent browser. This is intentionally separate
        # from the persistent profile path, so a stale/locked profile cannot
        # make even simple `open <site>` commands fail.
        launch_attempts = []
        if chrome:
            launch_attempts.append(("Chrome temporary", lambda: self._playwright.chromium.launch(
                headless=False, executable_path=chrome, args=["--start-maximized"])))
        launch_attempts.append(("Chromium temporary", lambda: self._playwright.chromium.launch(
            headless=False, args=["--start-maximized"])))

        for label, starter in launch_attempts:
            try:
                self._browser = starter()
                self._context = self._browser.new_context(no_viewport=True)
                return self._context
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                if self._browser is not None:
                    try:
                        self._browser.close()
                    except Exception:
                        pass
                    self._browser = None

        try:
            self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        raise RuntimeError("Unable to start a visible browser. " + " | ".join(errors[-4:]))

    def _page(self, url_hint: str | None = None) -> Page:
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
        return pages[-1] if pages else context.new_page()

    def _bring_to_front(self, page: Page) -> None:
        try:
            page.bring_to_front()
        except Exception:
            pass

    def open_url(self, url: str) -> bool:
        try:
            page = self._page()
            self._bring_to_front(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._remember_site(page.url)
            return True
        except Exception:
            return False

    def search(self, query: str, site: str = "youtube", newest: bool = False) -> bool:
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
        elif site == "spotify":
            url = "https://open.spotify.com/search/" + urllib.parse.quote_plus(query)
        elif site == "linkedin":
            url = "https://www.linkedin.com/search/results/all/?keywords=" + urllib.parse.quote_plus(query)
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
            site = "google"
        ok = self.open_url(url)
        if ok:
            self._current_site = site
        return ok

    def search_current_page(self, query: str) -> bool:
        query = query.strip()
        if not query:
            return False
        site = self._current_site
        if site in {"youtube", "google", "github", "reddit", "spotify", "linkedin"}:
            return self.search(query, site)

        # Generic fallback: use the current page's search field when possible.
        # This works for arbitrary sites without maintaining a site whitelist.
        try:
            page = self._page()
            self._bring_to_front(page)
            selectors = (
                "input[type='search']",
                "input[placeholder*='Search' i]",
                "input[aria-label*='Search' i]",
                "textarea[placeholder*='Search' i]",
            )
            for selector in selectors:
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.fill(query, timeout=5000)
                    locator.press("Enter", timeout=5000)
                    return True
        except Exception:
            pass
        return False

    def play_latest_youtube_video(self, query: str | None = None) -> bool:
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
        try:
            page = self._page()
            for selector in list(_VIDEO_LINK_SELECTORS) + ["main a[href*='/watch']", "main a[href*='/results/']"]:
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

    def click_text(self, text: str) -> bool:
        try:
            page = self._page()
            self._bring_to_front(page)
            for locator in [page.get_by_role("button", name=text, exact=False).first, page.get_by_role("link", name=text, exact=False).first, page.get_by_text(text, exact=False).first]:
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
                for locator in [page.get_by_role("textbox", name=target, exact=False).first, page.get_by_placeholder(target, exact=False).first]:
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
            self._page().mouse.wheel(0, 700 if direction == "down" else -700)
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
        if "youtube.com" in lower or "youtu.be" in lower: return "youtube"
        if "google.com" in lower: return "google"
        if "github.com" in lower: return "github"
        if "reddit.com" in lower: return "reddit"
        if "spotify.com" in lower: return "spotify"
        if "linkedin.com" in lower: return "linkedin"
        return None

    def _remember_site(self, url: str) -> None:
        site = self._site_from_url(url)
        self._current_site = site

    def shutdown(self) -> None:
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
