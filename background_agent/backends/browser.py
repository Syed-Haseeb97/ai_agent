"""Level-3 browser automation: headless Chromium in a fresh, throwaway profile.

Why this does not touch the user's desktop: Playwright launches Chromium headless
(no window, no focus, no cursor) with its own ephemeral context, so it shares no
cookies/logins with the user's real browser. `headless` is deliberately not
configurable here.

NOTE on test coverage: BrowserController logic is unit-tested with a fake engine, and
PlaywrightEngine has an integration test (tests/.../test_bg_browser_real.py) that runs a
real headless Chromium against a local HTTP server - it auto-skips when Playwright or
Chromium is missing. It has been run on LINUX only; it has NOT been run on Windows.
Downloads (expect_download) are not covered by any real-browser test yet.
"""
from __future__ import annotations

import abc
import concurrent.futures
import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

from ..actions import Action, ActionErrorCode, ActionFailure, ActionKind, ActionResult
from ..cancellation import CancelToken

INSTALL_HINT = "pip install playwright && python -m playwright install chromium"
MAX_NAV_TIMEOUT_MS = 60_000      # page navigation
MAX_ELEMENT_TIMEOUT_MS = 15_000  # click / fill / extract / download (override with timeout_seconds)


class BrowserUnavailable(Exception):
    pass


class BrowserEngine(abc.ABC):
    @abc.abstractmethod
    def goto(self, url: str, timeout_ms: int) -> str: ...
    @abc.abstractmethod
    def extract_text(self, selector: Optional[str], max_chars: int, timeout_ms: int) -> str: ...
    @abc.abstractmethod
    def click(self, selector: str, timeout_ms: int) -> None: ...
    @abc.abstractmethod
    def fill(self, selector: str, text: str, timeout_ms: int) -> None: ...
    @abc.abstractmethod
    def screenshot(self, path: str) -> None: ...
    @abc.abstractmethod
    def download(self, selector: str, dest: str, timeout_ms: int) -> None: ...
    @abc.abstractmethod
    def close(self) -> None: ...


class PlaywrightEngine(BrowserEngine):
    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(f"Playwright is not installed ({INSTALL_HINT})") from exc
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._context = self._browser.new_context(accept_downloads=True)
            self._page = self._context.new_page()
        except Exception as exc:
            raise BrowserUnavailable(f"Could not launch Chromium: {exc}. Try: {INSTALL_HINT}") from exc

    def goto(self, url: str, timeout_ms: int) -> str:
        self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        return f"{self._page.title()} | {self._page.url}"

    def extract_text(self, selector: Optional[str], max_chars: int, timeout_ms: int) -> str:
        text = self._page.locator(selector or "body").first.inner_text(timeout=timeout_ms)
        return text[:max_chars]

    def click(self, selector: str, timeout_ms: int) -> None:
        self._page.click(selector, timeout=timeout_ms)

    def fill(self, selector: str, text: str, timeout_ms: int) -> None:
        self._page.fill(selector, text, timeout=timeout_ms)

    def screenshot(self, path: str) -> None:
        self._page.screenshot(path=path, full_page=True)

    def download(self, selector: str, dest: str, timeout_ms: int) -> None:
        with self._page.expect_download(timeout=timeout_ms) as info:
            self._page.click(selector, timeout=timeout_ms)
        info.value.save_as(dest)

    def close(self) -> None:
        for step in (lambda: self._context.close(), lambda: self._browser.close(), lambda: self._pw.stop()):
            try:
                step()
            except Exception:
                pass


class BrowserController:
    """Runs all engine calls on ONE dedicated thread (Playwright's sync API is bound to
    the thread that created it) while keeping execute() cancellable from the caller."""

    def __init__(self, engine_factory: Callable[[], BrowserEngine],
                 resolve_path: Callable[[str], Any], max_text_chars: int = 20_000) -> None:
        self._factory = engine_factory
        self._resolve = resolve_path
        self._max_text = max_text_chars
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg-browser")
        self._engine: Optional[BrowserEngine] = None

    def _get_engine(self) -> BrowserEngine:  # runs on the browser thread
        if self._engine is None:
            self._engine = self._factory()
        return self._engine

    def execute(self, action: Action, deadline: float, cancel: CancelToken) -> ActionResult:
        try:
            call, produced = self._prepare(action, deadline)
        except ActionFailure as f:
            return ActionResult.failure(f.code, f.message)

        def guarded() -> Any:
            try:
                return ("ok", call(self._get_engine()))
            except Exception as exc:  # noqa: BLE001
                return ("err", exc)

        future = self._executor.submit(guarded)
        while True:
            try:
                kind, value = future.result(timeout=0.1)
                break
            except concurrent.futures.TimeoutError:
                if cancel.is_cancelled:
                    return ActionResult.failure(ActionErrorCode.CANCELLED, "browser action cancelled")
                if time.monotonic() >= deadline:
                    return ActionResult.failure(ActionErrorCode.TIMEOUT, "browser action timed out")
        if kind == "err":
            if isinstance(value, BrowserUnavailable):
                return ActionResult.failure(ActionErrorCode.BROWSER_UNAVAILABLE, str(value))
            return ActionResult.failure(ActionErrorCode.BROWSER_ERROR, f"{type(value).__name__}: {value}"[:500])
        return ActionResult.success(str(value or ""), produced_paths=produced)

    def _dest(self, raw: str) -> str:
        """Resolve (confined) and make sure the parent folder exists."""
        path = self._resolve(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _prepare(self, action: Action, deadline: float):
        p = action.params
        remaining_ms = (deadline - time.monotonic()) * 1000
        cap = MAX_NAV_TIMEOUT_MS if action.kind is ActionKind.BROWSER_GOTO else MAX_ELEMENT_TIMEOUT_MS
        if p.get("timeout_seconds"):
            cap = min(MAX_NAV_TIMEOUT_MS, float(p["timeout_seconds"]) * 1000)
        timeout_ms = int(max(500, min(cap, remaining_ms)))

        def need(key: str) -> str:
            value = p.get(key)
            if not isinstance(value, str) or not value:
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, f"'{key}' is required")
            return value

        k = action.kind
        if k is ActionKind.BROWSER_GOTO:
            url = need("url")
            if urlsplit(url).scheme.lower() not in ("http", "https"):
                raise ActionFailure(ActionErrorCode.INVALID_PARAMS, "only http/https URLs are allowed")
            return (lambda e: e.goto(url, timeout_ms)), ()
        if k is ActionKind.BROWSER_EXTRACT_TEXT:
            sel = p.get("selector") or None
            limit = min(int(p.get("max_chars") or self._max_text), self._max_text)
            return (lambda e: e.extract_text(sel, limit, timeout_ms)), ()
        if k is ActionKind.BROWSER_CLICK:
            sel = need("selector")
            return (lambda e: (e.click(sel, timeout_ms), "clicked")[1]), ()
        if k is ActionKind.BROWSER_FILL:
            sel, text = need("selector"), str(p.get("text", ""))
            return (lambda e: (e.fill(sel, text, timeout_ms), "filled")[1]), ()
        if k is ActionKind.BROWSER_SCREENSHOT:
            dest = self._dest(need("path"))
            return (lambda e: (e.screenshot(dest), "saved")[1]), (dest,)
        if k is ActionKind.BROWSER_DOWNLOAD:
            sel, dest = need("selector"), self._dest(need("path"))
            return (lambda e: (e.download(sel, dest, timeout_ms), "downloaded")[1]), (dest,)
        raise ActionFailure(ActionErrorCode.UNSUPPORTED, f"{k.value} is not a browser action")

    def close(self, timeout: float) -> None:
        """Close the browser on its own thread. Raises if it cannot finish in time."""
        def shutdown() -> None:
            if self._engine is not None:
                self._engine.close()
        try:
            self._executor.submit(shutdown).result(timeout=timeout)
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)
