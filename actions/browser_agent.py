"""Generic browser task planner.

This module deliberately contains no site/channel/video names. It turns natural
language browser tasks into reusable browser primitives and lets Playwright
inspect the current DOM before acting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from actions.browser_actions import BrowserActions


@dataclass(frozen=True)
class BrowserTaskResult:
    handled: bool
    message: str = ""


class BrowserAgent:
    """General-purpose browser task layer; avoid phrase-specific command hacks."""

    SITE_ALIASES = {
        "youtube": "youtube", "yt": "youtube", "google": "google", "github": "github",
        "reddit": "reddit", "gmail": "gmail", "chatgpt": "chatgpt", "amazon": "amazon", "netflix": "netflix",
    }

    def __init__(self, browser: BrowserActions):
        self.browser = browser

    def execute(self, text: str) -> BrowserTaskResult:
        original = text.strip()
        q = original.lower()
        if not q:
            return BrowserTaskResult(False)
        compound = self._compound(original)
        if compound.handled:
            return compound
        for handler in (self._open, self._search, self._media, self._navigation, self._interaction):
            result = handler(original if handler is self._interaction else q)
            if result.handled:
                return result
        return BrowserTaskResult(False)

    def _compound(self, original: str) -> BrowserTaskResult:
        parts = [p.strip(" .") for p in re.split(
            r"\s+and\s+(?=(?:then\s+)?(?:play|watch|open|search|look\s+up|find|click|type|go|navigate|scroll|refresh|reload|close)\b)",
            original,
            flags=re.I,
        ) if p.strip()]
        if len(parts) < 2:
            return BrowserTaskResult(False)
        messages: list[str] = []
        for part in parts:
            result = self.execute(part)
            if not result.handled:
                return BrowserTaskResult(False)
            if result.message:
                messages.append(result.message)
        return BrowserTaskResult(True, " ".join(messages))

    def _open(self, q: str) -> BrowserTaskResult:
        site = self._site_in_text(q)
        if not site or not re.search(r"\b(open|launch|start|visit|go to|take me to|show)\b", q):
            return BrowserTaskResult(False)
        search_match = re.search(r"\b(?:and\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s*$", q)
        if search_match:
            term = self._clean_term(search_match.group(1))
            if term and self.browser.search(term, site):
                return BrowserTaskResult(True, f"Opening {site} and searching for {term}…")
        if self.browser.open_url(self._site_url(site)):
            return BrowserTaskResult(True, f"Opening {site}…")
        return BrowserTaskResult(False)

    def _search(self, q: str) -> BrowserTaskResult:
        explicit = re.match(
            r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+(?:this\s+|my\s+)?(youtube|yt|google|github|reddit)(?:\s+tab)?\s*$",
            q,
            re.I,
        )
        if explicit:
            term = self._clean_term(explicit.group(1))
            site = self.SITE_ALIASES[explicit.group(2).lower()]
            ok = self.browser.search(term, site)
            return BrowserTaskResult(ok, f"Searching {site} for {term}…" if ok else "")
        generic = re.match(r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s*$", q, re.I)
        if not generic:
            return BrowserTaskResult(False)
        term = self._clean_term(generic.group(1))
        if not term:
            return BrowserTaskResult(False)
        ok = self.browser.search_current_page(term)
        return BrowserTaskResult(ok, f"Searching for {term}…" if ok else "")

    def _media(self, q: str) -> BrowserTaskResult:
        if not re.search(r"\b(play|watch|open)\b", q):
            return BrowserTaskResult(False)
        latest = re.search(
            r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+"
            r"(?:(?:video)\s+)?(?:of|from|for)\s+(.+?)(?:\s+(?:video))?\s*(?:on\s+(?:youtube|yt))?\s*$",
            q,
            re.I,
        )
        if not latest:
            latest = re.search(
                r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(.+?)\s+video"
                r"(?:\s+on\s+(?:youtube|yt))?\s*$",
                q,
                re.I,
            )
        if latest:
            topic = self._clean_term(latest.group(1))
            ok = self.browser.play_latest_youtube_video(topic or None)
            return BrowserTaskResult(ok, f"Playing the latest video for {topic}…" if ok and topic else "Playing the latest video…" if ok else "")
        if re.search(r"\b(?:its|the)\s+(?:latest|newest|most\s+recent)\s+video\b", q):
            ok = self.browser.play_latest_youtube_video()
            return BrowserTaskResult(ok, "Playing the latest video…" if ok else "")
        if re.search(r"\b(?:first|top)\s+(?:video|result)\b", q):
            ok = self.browser.click_first_result()
            return BrowserTaskResult(ok, "Opening the first result…" if ok else "")
        if re.search(r"\b(?:pause|stop)\b(?:\s+the)?\s+(?:current\s+)?video\b|\bpause\s+(?:youtube|yt)\b", q):
            ok = self.browser.pause_youtube()
            return BrowserTaskResult(ok, "Pausing the video…" if ok else "")
        return BrowserTaskResult(False)

    def _navigation(self, q: str) -> BrowserTaskResult:
        checks = (
            (r"\b(?:go|navigate)\s+back\b", self.browser.go_back, "Going back…"),
            (r"\b(?:go|navigate)\s+forward\b", self.browser.go_forward, "Going forward…"),
            (r"\b(?:refresh|reload)\s+(?:the\s+)?(?:page|tab|browser)\b", self.browser.refresh, "Refreshing…"),
            (r"\bclose\s+(?:this\s+)?(?:browser\s+)?tab\b", self.browser.close_tab, "Closing the tab…"),
        )
        for pattern, action, message in checks:
            if re.search(pattern, q):
                ok = action()
                return BrowserTaskResult(ok, message if ok else "")
        return BrowserTaskResult(False)

    def _interaction(self, original: str) -> BrowserTaskResult:
        q = original.lower()
        click = re.match(r"\s*(?:please\s+)?click\s+(?:on\s+)?(?:the\s+)?(.+?)\s*$", original, re.I)
        if click:
            target = self._clean_term(click.group(1))
            ok = self.browser.click_text(target)
            return BrowserTaskResult(ok, f"Clicking {target}…" if ok else "")
        type_match = re.match(r"\s*(?:please\s+)?type\s+(.+?)(?:\s+into\s+(?:the\s+)?(.+))?\s*$", original, re.I)
        if type_match:
            text = self._clean_term(type_match.group(1))
            target = self._clean_term(type_match.group(2) or "")
            ok = self.browser.type_text(text, target or None)
            return BrowserTaskResult(ok, "Typing…" if ok else "")
        if re.search(r"\bscroll\s+(?:down|up)\b", q):
            direction = "up" if " up" in q else "down"
            ok = self.browser.scroll(direction)
            return BrowserTaskResult(ok, f"Scrolling {direction}…" if ok else "")
        return BrowserTaskResult(False)

    @classmethod
    def _site_in_text(cls, q: str) -> str | None:
        for alias, site in sorted(cls.SITE_ALIASES.items(), key=lambda x: -len(x[0])):
            if re.search(rf"\b{re.escape(alias)}\b", q):
                return site
        return None

    @staticmethod
    def _site_url(site: str) -> str:
        return {
            "youtube": "https://www.youtube.com", "google": "https://www.google.com", "github": "https://github.com",
            "reddit": "https://www.reddit.com", "gmail": "https://mail.google.com", "chatgpt": "https://chatgpt.com",
            "amazon": "https://www.amazon.com", "netflix": "https://www.netflix.com",
        }.get(site, "https://www.google.com")

    @staticmethod
    def _clean_term(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip(" .?!,\"")
