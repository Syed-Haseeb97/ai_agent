"""Unit tests for BrowserAgent routing and BrowserActions persistence semantics.

These tests use a fake BrowserActions so they run without launching a real browser.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from actions.browser_agent import BrowserAgent, BrowserTaskResult


@dataclass
class FakeBrowser:
    """Records calls and simulates a persistent context."""

    opens: list[str] = field(default_factory=list)
    searches: list[tuple[str, str]] = field(default_factory=list)
    current_searches: list[str] = field(default_factory=list)
    context_id: int = 42
    current_url: str = "about:blank"
    fail_next: bool = False
    _error: str | None = None

    def last_error(self) -> str | None:
        return self._error

    def open_url(self, url: str) -> bool:
        if self.fail_next:
            self.fail_next = False
            self._error = f"simulated open failure for {url}"
            return False
        self.opens.append(url)
        self.current_url = url
        self._error = None
        return True

    def search(self, query: str, site: str = "youtube", newest: bool = False) -> bool:
        if self.fail_next:
            self.fail_next = False
            self._error = f"simulated search failure for {query} on {site}"
            return False
        self.searches.append((query, site))
        self.current_url = f"https://search/{site}?q={query}"
        self._error = None
        return True

    def search_current_page(self, query: str) -> bool:
        if self.fail_next:
            self.fail_next = False
            self._error = f"simulated current-page search failure for {query}"
            return False
        url = self.current_url.lower()
        site = None
        if "youtube" in url:
            site = "youtube"
        elif "github" in url:
            site = "github"
        elif "spotify" in url:
            site = "spotify"
        elif "instagram" in url:
            site = "instagram"
        elif "notion" in url:
            site = "notion"
        if site:
            return self.search(query, site)
        self.current_searches.append(query)
        self._error = None
        return True

    def play_latest_youtube_video(self, query: str | None = None) -> bool:
        return True

    def play_spotify_track(self, track: str) -> bool:
        return True

    def click_first_result(self) -> bool:
        return True

    def pause_youtube(self) -> bool:
        return True

    def click_text(self, text: str) -> bool:
        return True

    def type_text(self, text: str, target: str | None = None) -> bool:
        return True

    def scroll(self, direction: str = "down") -> bool:
        return True

    def go_back(self) -> bool:
        return True

    def go_forward(self) -> bool:
        return True

    def refresh(self) -> bool:
        return True

    def close_tab(self) -> bool:
        return True

    def get_current_url(self) -> str:
        return self.current_url

    def get_context_id(self) -> int:
        return self.context_id


class BrowserAgentRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.browser = FakeBrowser()
        self.agent = BrowserAgent(self.browser)  # type: ignore[arg-type]

    def test_open_youtube(self):
        r = self.agent.execute("open youtube")
        self.assertTrue(r.recognized)
        self.assertTrue(r.handled)
        self.assertIn("youtube.com", self.browser.opens[-1])

    def test_open_github(self):
        r = self.agent.execute("open github")
        self.assertTrue(r.handled)
        self.assertIn("github.com", self.browser.opens[-1])

    def test_open_spotify(self):
        r = self.agent.execute("open spotify")
        self.assertTrue(r.handled)
        self.assertIn("spotify", self.browser.opens[-1])

    def test_open_instagram(self):
        r = self.agent.execute("open instagram")
        self.assertTrue(r.handled)
        self.assertIn("instagram", self.browser.opens[-1])

    def test_open_notion(self):
        r = self.agent.execute("open notion")
        self.assertTrue(r.handled)
        self.assertIn("notion", self.browser.opens[-1])

    def test_open_gemini(self):
        r = self.agent.execute("open gemini")
        self.assertTrue(r.handled)
        self.assertIn("gemini.google.com", self.browser.opens[-1])

    def test_open_perplexity(self):
        r = self.agent.execute("open perplexity")
        self.assertTrue(r.handled)
        self.assertIn("perplexity", self.browser.opens[-1])

    def test_search_on_youtube(self):
        r = self.agent.execute("search for bbs on youtube")
        self.assertTrue(r.handled)
        self.assertEqual(self.browser.searches[-1], ("bbs", "youtube"))

    def test_open_youtube_and_search(self):
        r = self.agent.execute("open youtube and search for bbs")
        self.assertTrue(r.handled)
        self.assertEqual(self.browser.searches[-1], ("bbs", "youtube"))

    def test_open_instagram_and_search(self):
        r = self.agent.execute("open instagram and search for ronaldo")
        self.assertTrue(r.handled)
        self.assertEqual(self.browser.searches[-1], ("ronaldo", "instagram"))

    def test_sequential_open_then_search_same_context(self):
        """Persistence semantics: open then search must share the same context id."""
        r1 = self.agent.execute("open youtube")
        self.assertTrue(r1.handled)
        ctx1 = self.browser.get_context_id()

        r2 = self.agent.execute("search for mrwhoistheboss")
        self.assertTrue(r2.handled)
        ctx2 = self.browser.get_context_id()
        self.assertEqual(ctx1, ctx2)
        self.assertEqual(self.browser.searches[-1], ("mrwhoistheboss", "youtube"))

    def test_search_without_open_uses_current_page(self):
        self.browser.current_url = "https://www.youtube.com/"
        r = self.agent.execute("search for bbs")
        self.assertTrue(r.handled)
        self.assertEqual(self.browser.searches[-1], ("bbs", "youtube"))

    def test_unknown_site_uses_generic_resolver(self):
        r = self.agent.execute("open someobscuresite")
        self.assertTrue(r.recognized)
        self.assertTrue(r.handled)
        self.assertTrue(
            any("google.com/search" in u for u in self.browser.opens),
            msg=f"expected google lucky search, got {self.browser.opens}",
        )

    def test_failure_surfaces_message(self):
        self.browser.fail_next = True
        r = self.agent.execute("open youtube")
        self.assertTrue(r.recognized)
        self.assertFalse(r.handled)
        self.assertIn("failed", r.message.lower())


class BrowserActionsWorkerImportTests(unittest.TestCase):
    def test_import_and_construct(self):
        from actions.browser_actions import BrowserActions

        ba = BrowserActions()
        self.assertIsNone(ba.last_error())
        ba.shutdown()


if __name__ == "__main__":
    unittest.main()
