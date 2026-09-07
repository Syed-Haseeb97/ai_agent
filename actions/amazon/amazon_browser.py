"""Persistent, user-authenticated Amazon.in browser session.

This module deliberately does not automate login, CAPTCHA, OTP, or MFA.
The user signs in manually in the dedicated browser profile.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright


class AmazonBrowser:
    BASE_URL = "https://www.amazon.in"
    ORDERS_URL = "https://www.amazon.in/gp/css/order-history"

    def __init__(
        self,
        profile_dir: str | Path = "data/amazon/browser-profile",
        headless: bool = False,
    ) -> None:
        self.profile_dir = Path(profile_dir).resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self._playwright = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self) -> Page:
        if self.page is not None:
            return self.page

        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport={"width": 1400, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def stop(self) -> None:
        if self.context is not None:
            self.context.close()
        if self._playwright is not None:
            self._playwright.stop()
        self.context = None
        self.page = None
        self._playwright = None

    def open(self, url: str) -> Page:
        page = self.start()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        return page

    def is_logged_in(self) -> bool:
        page = self.open(self.BASE_URL)
        body = page.locator("body").inner_text(timeout=10_000)
        # This is only a coarse health check. The order parser will validate
        # access to the actual orders page.
        return "Hello," in body or "Account & Lists" in body

    def require_login(self) -> None:
        if not self.is_logged_in():
            raise RuntimeError(
                "Amazon.in is not logged in. Run the connector login flow "
                "and sign in manually in the dedicated browser profile."
            )
