"""Playwright-backed browser primitives used by the generic browser agent.

All Playwright calls run on a single dedicated worker thread so sequential
voice/text commands (each dispatched from a new background thread by the UI)
reliably share one visible BrowserContext and active Page.
"""
from __future__ import annotations

import logging
import os
import queue
import shutil
import threading
import traceback
import urllib.parse
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger("ruby.browser")

try:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover
    Browser = BrowserContext = Page = Playwright = object  # type: ignore
    sync_playwright = None  # type: ignore

_YOUTUBE_SORT_NEWEST = "&sp=CAISAhAB"
_VIDEO_LINK_SELECTORS = (
    "ytd-video-renderer a#video-title",
    "ytd-rich-item-renderer a#video-title",
    "ytd-channel-video-player-renderer a#video-title",
    "a#video-title",
)

T = TypeVar("T")


class BrowserActions:
    """Thread-safe facade over a single persistent Playwright browser session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._jobs: queue.Queue = queue.Queue()
        self._playwright = None
        self._browser = None
        self._context = None
        self._last_error: str | None = None

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._worker_loop, name="ruby-browser-worker", daemon=True)
            self._worker.start()
            logger.info("Browser worker thread started (id=%s)", self._worker.ident)

    def _worker_loop(self) -> None:
        while True:
            item = self._jobs.get()
            if item is None:
                break
            fn, args, kwargs, fut = item
            try:
                result = fn(*args, **kwargs)
                if not fut.cancelled():
                    fut.set_result(result)
            except BaseException as exc:  # noqa: BLE001
                logger.error("Browser worker error in %s: %s\n%s", getattr(fn, "__name__", fn), exc, traceback.format_exc())
                if not fut.cancelled():
                    fut.set_exception(exc)
            finally:
                self._jobs.task_done()

    def _run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        self._ensure_worker()
        fut: Future = Future()
        self._jobs.put((fn, args, kwargs, fut))
        return fut.result(timeout=90)

    def last_error(self) -> str | None:
        return self._last_error

    def _set_error(self, msg: str) -> None:
        self._last_error = msg
        logger.error("BrowserActions: %s", msg)

    def _clear_error(self) -> None:
        self._last_error = None

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
        return shutil.which("chrome.exe") or shutil.which("google-chrome") or shutil.which("chromium")

    def _ensure_context_locked(self):
        if self._context is not None:
            try:
                _ = self._context.pages
                return self._context
            except Exception:
                logger.warning("Existing browser context is stale; recreating")
                self._drop_context_locked()
        if sync_playwright is None:
            raise RuntimeError("playwright is not installed")
        self._playwright = sync_playwright().start()
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Ruby"
        persistent_chrome = root / "browser-profile"
        persistent_chromium = root / "browser-profile-chromium"
        persistent_chrome.mkdir(parents=True, exist_ok=True)
        persistent_chromium.mkdir(parents=True, exist_ok=True)
        chrome = self._chrome_path()
        errors: list[str] = []
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
                logger.info("Browser context started via %s (ctx=%s)", label, id(self._context))
                return self._context
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                logger.warning("Browser start attempt failed (%s): %s", label, exc)
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
                logger.info("Browser context started via %s (ctx=%s)", label, id(self._context))
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
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        raise RuntimeError("Unable to start a visible browser. " + " | ".join(errors[-4:]))

    def _drop_context_locked(self) -> None:
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        self._context = None
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        self._browser = None
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None

    def _page_locked(self, url_hint: str | None = None):
        context = self._ensure_context_locked()
        pages = list(context.pages)
        if url_hint:
            hint = url_hint.lower()
            for page in reversed(pages):
                try:
                    if hint in (page.url or "").lower():
                        return page
                except Exception:
                    continue
        if pages:
            return pages[-1]
        return context.new_page()

    def _bring_to_front_locked(self, page) -> None:
        try:
            page.bring_to_front()
        except Exception:
            pass

    def _describe_state_locked(self) -> str:
        try:
            ctx = self._context
            if ctx is None:
                return "context=None"
            pages = list(ctx.pages)
            urls = []
            for p in pages[-3:]:
                try:
                    urls.append(p.url)
                except Exception:
                    urls.append("<dead>")
            return f"ctx={id(ctx)} pages={len(pages)} urls={urls}"
        except Exception as exc:
            return f"state-error={exc}"

    def open_url(self, url: str) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                self._bring_to_front_locked(page)
                logger.info("open_url url=%s %s", url, self._describe_state_locked())
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                logger.info("open_url done url=%s final=%s", url, page.url)
                return True
            except Exception as exc:
                self._set_error(f"open_url({url!r}) failed: {exc}")
                return False
        return self._run(_op)

    def search(self, query: str, site: str = "youtube", newest: bool = False) -> bool:
        query = (query or "").strip()
        if not query:
            return False
        site = (site or "google").lower()
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
        elif site == "instagram":
            url = "https://www.instagram.com/explore/search/keyword/?q=" + urllib.parse.quote_plus(query)
        elif site == "notion":
            url = "https://www.notion.so/search?query=" + urllib.parse.quote_plus(query)
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"site:{site} {query}" if site else query)
            site = "google"
        logger.info("search query=%r site=%s url=%s", query, site, url)
        return self.open_url(url)

    def search_current_page(self, query: str) -> bool:
        query = (query or "").strip()
        if not query:
            return False

        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                self._bring_to_front_locked(page)
                url = (page.url or "").lower()
                logger.info("search_current_page query=%r url=%s %s", query, url, self._describe_state_locked())
                site = self._site_from_url(url)
                if site:
                    if site in {"youtube", "yt"}:
                        target = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
                    elif site == "google":
                        target = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
                    elif site == "github":
                        target = "https://github.com/search?q=" + urllib.parse.quote_plus(query)
                    elif site == "reddit":
                        target = "https://www.reddit.com/search/?q=" + urllib.parse.quote_plus(query)
                    elif site == "spotify":
                        target = "https://open.spotify.com/search/" + urllib.parse.quote_plus(query)
                    elif site == "linkedin":
                        target = "https://www.linkedin.com/search/results/all/?keywords=" + urllib.parse.quote_plus(query)
                    elif site == "instagram":
                        target = "https://www.instagram.com/explore/search/keyword/?q=" + urllib.parse.quote_plus(query)
                    else:
                        target = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
                    page.goto(target, wait_until="domcontentloaded", timeout=30000)
                    logger.info("search_current_page navigated to %s", page.url)
                    return True
                selectors = (
                    "input[type='search']",
                    "input[name='q']",
                    "input[name='search']",
                    "input[placeholder*='Search' i]",
                    "input[aria-label*='Search' i]",
                    "textarea[placeholder*='Search' i]",
                    "textarea[aria-label*='Search' i]",
                    "[role='searchbox']",
                )
                for selector in selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() and locator.is_visible():
                            locator.fill(query, timeout=5000)
                            locator.press("Enter", timeout=5000)
                            logger.info("search_current_page filled selector=%s", selector)
                            return True
                    except Exception as sel_exc:
                        logger.debug("selector %s failed: %s", selector, sel_exc)
                        continue
                self._set_error(f"search_current_page: no known site and no visible search input on {url!r}")
                return False
            except Exception as exc:
                self._set_error(f"search_current_page({query!r}) failed: {exc}")
                return False
        return self._run(_op)

    def play_latest_youtube_video(self, query: str | None = None) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                if query:
                    if not self._search_locked(query, "youtube", newest=True):
                        return False
                    page = self._page_locked("youtube")
                    page.wait_for_selector(", ".join(_VIDEO_LINK_SELECTORS), timeout=12000)
                else:
                    page = self._page_locked("youtube")
                    if "youtube.com" not in (page.url or "").lower():
                        self._set_error("play_latest_youtube_video: not on youtube")
                        return False
                    page.wait_for_selector(", ".join(_VIDEO_LINK_SELECTORS), timeout=12000)
                return self._click_first_video_locked(page)
            except Exception as exc:
                self._set_error(f"play_latest_youtube_video failed: {exc}")
                return False
        return self._run(_op)

    def _search_locked(self, query: str, site: str, newest: bool = False) -> bool:
        if site in {"youtube", "yt"}:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            if newest:
                url += _YOUTUBE_SORT_NEWEST
        else:
            url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        page = self._page_locked()
        self._bring_to_front_locked(page)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return True

    @staticmethod
    def _click_first_video_locked(page) -> bool:
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
        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                for selector in list(_VIDEO_LINK_SELECTORS) + ["main a[href*='/watch']", "main a[href*='/results/']"]:
                    locator = page.locator(selector).first
                    if locator.count() and locator.is_visible():
                        locator.scroll_into_view_if_needed(timeout=5000)
                        locator.click(timeout=7000)
                        return True
            except Exception as exc:
                self._set_error(f"click_first_result failed: {exc}")
            return False
        return self._run(_op)

    def pause_youtube(self) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked("youtube")
                button = page.locator("button[aria-label*='Pause'], button[title*='Pause']").first
                if button.count() and button.is_visible():
                    button.click(timeout=5000)
                    return True
            except Exception as exc:
                self._set_error(f"pause_youtube failed: {exc}")
            return False
        return self._run(_op)

    def play_spotify_track(self, track: str) -> bool:
        track = (track or "").strip()
        if not track:
            return False

        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                self._bring_to_front_locked(page)
                page.goto("https://open.spotify.com/search/" + urllib.parse.quote(track), wait_until="domcontentloaded", timeout=30000)
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
                self._set_error(f"play_spotify_track: could not start {track!r}")
            except Exception as exc:
                self._set_error(f"play_spotify_track failed: {exc}")
            return False
        return self._run(_op)

    def click_text(self, text: str) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                self._bring_to_front_locked(page)
                for locator in [
                    page.get_by_role("button", name=text, exact=False).first,
                    page.get_by_role("link", name=text, exact=False).first,
                    page.get_by_text(text, exact=False).first,
                ]:
                    try:
                        if locator.count() and locator.is_visible():
                            locator.scroll_into_view_if_needed(timeout=5000)
                            locator.click(timeout=7000)
                            return True
                    except Exception:
                        continue
            except Exception as exc:
                self._set_error(f"click_text({text!r}) failed: {exc}")
            return False
        return self._run(_op)

    def type_text(self, text: str, target: str | None = None) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                page = self._page_locked()
                self._bring_to_front_locked(page)
                if target:
                    for locator in [
                        page.get_by_role("textbox", name=target, exact=False).first,
                        page.get_by_placeholder(target, exact=False).first,
                    ]:
                        try:
                            if locator.count() and locator.is_visible():
                                locator.click(timeout=5000)
                                locator.fill(text)
                                return True
                        except Exception:
                            continue
                page.keyboard.type(text)
                return True
            except Exception as exc:
                self._set_error(f"type_text failed: {exc}")
                return False
        return self._run(_op)

    def scroll(self, direction: str = "down") -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                self._page_locked().mouse.wheel(0, 700 if direction == "down" else -700)
                return True
            except Exception as exc:
                self._set_error(f"scroll failed: {exc}")
                return False
        return self._run(_op)

    def go_back(self) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                self._page_locked().go_back(wait_until="domcontentloaded", timeout=15000)
                return True
            except Exception as exc:
                self._set_error(f"go_back failed: {exc}")
                return False
        return self._run(_op)

    def go_forward(self) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                self._page_locked().go_forward(wait_until="domcontentloaded", timeout=15000)
                return True
            except Exception as exc:
                self._set_error(f"go_forward failed: {exc}")
                return False
        return self._run(_op)

    def refresh(self) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                self._page_locked().reload(wait_until="domcontentloaded", timeout=15000)
                return True
            except Exception as exc:
                self._set_error(f"refresh failed: {exc}")
                return False
        return self._run(_op)

    def close_tab(self) -> bool:
        def _op() -> bool:
            self._clear_error()
            try:
                self._page_locked().close()
                return True
            except Exception as exc:
                self._set_error(f"close_tab failed: {exc}")
                return False
        return self._run(_op)

    def get_current_url(self) -> str:
        def _op() -> str:
            try:
                return self._page_locked().url or ""
            except Exception:
                return ""
        return self._run(_op)

    def get_context_id(self) -> int | None:
        def _op() -> int | None:
            try:
                ctx = self._ensure_context_locked()
                return id(ctx)
            except Exception:
                return None
        return self._run(_op)

    @staticmethod
    def _site_from_url(url: str) -> str | None:
        lower = (url or "").lower()
        if "youtube.com" in lower or "youtu.be" in lower:
            return "youtube"
        if "google.com" in lower and "mail.google" not in lower:
            return "google"
        if "github.com" in lower:
            return "github"
        if "reddit.com" in lower:
            return "reddit"
        if "spotify.com" in lower:
            return "spotify"
        if "linkedin.com" in lower:
            return "linkedin"
        if "instagram.com" in lower:
            return "instagram"
        if "notion.so" in lower or "notion.com" in lower:
            return "notion"
        if "gemini.google.com" in lower:
            return "gemini"
        if "perplexity.ai" in lower:
            return "perplexity"
        return None

    def shutdown(self) -> None:
        def _op() -> None:
            self._drop_context_locked()
        try:
            if self._worker is not None and self._worker.is_alive():
                self._run(_op)
        except Exception:
            pass
        try:
            self._jobs.put(None)
        except Exception:
            pass
        worker = self._worker
        if worker is not None:
            worker.join(timeout=5)
        self._worker = None
