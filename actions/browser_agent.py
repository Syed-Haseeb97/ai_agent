
"""Generic browser task planner.

This module deliberately contains no site/channel/video names. It turns natural
language browser tasks into reusable browser primitives and lets Playwright
inspect the current DOM before acting.

Result contract
----------------
Every handler returns a BrowserTaskResult with two independent signals:

* ``recognized`` - True the moment we're confident the text describes a
  browser task, regardless of whether the underlying Playwright action
  actually succeeded. Once a handler recognizes the command, ``execute()``
  commits to that interpretation and returns immediately.
* ``handled``    - True only if the browser action actually succeeded.

This separation matters: previously, if a *recognized* browser command's
Playwright execution failed for any reason (page not loaded, DOM selector
changed, no active context yet, timeout, etc.), the handler simply returned
``handled=False`` with no way to distinguish "this wasn't a browser command"
from "this was a browser command that failed to execute". The caller
(WindowsActionExecutor) treated both cases identically and fell through to
the conversational Gemini path -- which then hallucinated instructions like
"click the search bar and type...". That silent-failure-looks-like-no-match
behavior was the real routing bug: it had nothing to do with which channel
or search term was named.

Now, any recognized-but-failed command gets an honest in-character error
message instead of being silently handed to Gemini.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from actions.browser_actions import BrowserActions
except ModuleNotFoundError:  # pragma: no cover - supports direct module execution
    from .browser_actions import BrowserActions
class BrowserTaskResult:
    handled: bool
    message: str = ""
    recognized: bool = False


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
        if compound.recognized:
            return compound
        for handler in (self._open, self._search, self._media, self._navigation, self._interaction):
            result = handler(original if handler is self._interaction else q)
            if result.recognized:
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
            if not result.recognized:
                return BrowserTaskResult(False)
            if not result.handled:
                return BrowserTaskResult(False, result.message or f"I got partway through that but couldn't finish: {part!r} failed.", recognized=True)
            if result.message:
                messages.append(result.message)
        return BrowserTaskResult(True, " ".join(messages), recognized=True)

    def _open(self, q: str) -> BrowserTaskResult:
        site = self._site_in_text(q)
        if not site or not re.search(r"\b(open|launch|start|visit|go to|take me to|show)\b", q):
            return BrowserTaskResult(False)
        search_match = re.search(r"\b(?:and\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s*$", q)
        if search_match:
            term = self._clean_term(search_match.group(1))
            if term:
                ok = self.browser.search(term, site)
                if ok:
                    return BrowserTaskResult(True, f"Opening {site} and searching for {term}…", recognized=True)
                return BrowserTaskResult(False, f"I tried to open {site} and search for {term}, but the browser action failed.", recognized=True)
        ok = self.browser.open_url(self._site_url(site))
        if ok:
            return BrowserTaskResult(True, f"Opening {site}…", recognized=True)
        return BrowserTaskResult(False, f"I tried to open {site}, but the browser action failed.", recognized=True)

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
            if ok:
                return BrowserTaskResult(True, f"Searching {site} for {term}…", recognized=True)
            return BrowserTaskResult(False, f"I tried to search {site} for {term}, but the browser action failed.", recognized=True)
        generic = re.match(r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s*$", q, re.I)
        if not generic:
            return BrowserTaskResult(False)
        term = self._clean_term(generic.group(1))
        if not term:
            return BrowserTaskResult(False)
        ok = self.browser.search_current_page(term)
        if ok:
            return BrowserTaskResult(True, f"Searching for {term}…", recognized=True)
        return BrowserTaskResult(
            False,
            f"I understood you want to search for {term}, but I couldn't do it in the current browser "
            f"context. Try 'open youtube and search for {term}' to be explicit.",
            recognized=True,
        )

    def _media(self, q: str) -> BrowserTaskResult:
        if not re.search(r"\b(play|watch|open)\b", q):
            return BrowserTaskResult(False)
        # "play/watch/open [the] latest/newest video [uploaded by|posted by|by|of|from|for] X"
        # Accepts "uploaded by" / "posted by" / "by" in addition to "of/from/for" so the
        # channel or topic name is never silently dropped.
        latest = re.search(
            r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+"
            r"(?:(?:video|upload)\s+)?(?:uploaded\s+by|posted\s+by|by|of|from|for)\s+(.+?)"
            r"(?:\s+video)?\s*(?:on\s+(?:youtube|yt))?\s*$",
            q,
            re.I,
        )
        if not latest:
            # "play/watch/open the latest X video" (topic stated before the word "video")
            latest = re.search(
                r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(.+?)\s+video"
                r"(?:\s+on\s+(?:youtube|yt))?\s*$",
                q,
                re.I,
            )
        if latest:
            topic = self._clean_term(latest.group(1))
            ok = self.browser.play_latest_youtube_video(topic or None)
            if ok:
                return BrowserTaskResult(True, f"Playing the latest video for {topic}…" if topic else "Playing the latest video…", recognized=True)
            return BrowserTaskResult(
                False,
                f"I tried to play the latest video for {topic}, but the browser action failed." if topic else
                "I tried to play the latest video, but the browser action failed.",
                recognized=True,
            )
        if re.search(r"\b(?:its|the)\s+(?:latest|newest|most\s+recent)\s+video\b", q):
            ok = self.browser.play_latest_youtube_video()
            if ok:
                return BrowserTaskResult(True, "Playing the latest video…", recognized=True)
            return BrowserTaskResult(False, "I tried to play the latest video, but the browser action failed.", recognized=True)
        if re.search(r"\b(?:first|top)\s+(?:video|result)\b", q):
            ok = self.browser.click_first_result()
            if ok:
                return BrowserTaskResult(True, "Opening the first result…", recognized=True)
            return BrowserTaskResult(False, "I tried to open the first result, but the browser action failed.", recognized=True)
        if re.search(r"\b(?:pause|stop)\b(?:\s+the)?\s+(?:current\s+)?video\b|\bpause\s+(?:youtube|yt)\b", q):
            ok = self.browser.pause_youtube()
            if ok:
                return BrowserTaskResult(True, "Pausing the video…", recognized=True)
            return BrowserTaskResult(False, "I tried to pause the video, but the browser action failed.", recognized=True)
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
                if ok:
                    return BrowserTaskResult(True, message, recognized=True)
                return BrowserTaskResult(False, f"I tried to do that ({message.strip('…')}), but it failed.", recognized=True)
        return BrowserTaskResult(False)

    def _interaction(self, original: str) -> BrowserTaskResult:
        q = original.lower()
        click = re.match(r"\s*(?:please\s+)?click\s+(?:on\s+)?(?:the\s+)?(.+?)\s*$", original, re.I)
        if click:
            target = self._clean_term(click.group(1))
            ok = self.browser.click_text(target)
            if ok:
                return BrowserTaskResult(True, f"Clicking {target}…", recognized=True)
            return BrowserTaskResult(False, f"I couldn't find anything matching \"{target}\" to click on the current page.", recognized=True)
        type_match = re.match(r"\s*(?:please\s+)?type\s+(.+?)(?:\s+into\s+(?:the\s+)?(.+))?\s*$", original, re.I)
        if type_match:
            text = self._clean_term(type_match.group(1))
            target = self._clean_term(type_match.group(2) or "")
            ok = self.browser.type_text(text, target or None)
            if ok:
                return BrowserTaskResult(True, "Typing…", recognized=True)
            return BrowserTaskResult(False, "I tried to type that, but the browser action failed.", recognized=True)
        if re.search(r"\bscroll\s+(?:down|up)\b", q):
            direction = "up" if " up" in q else "down"
            ok = self.browser.scroll(direction)
            if ok:
                return BrowserTaskResult(True, f"Scrolling {direction}…", recognized=True)
            return BrowserTaskResult(False, f"I tried to scroll {direction}, but the browser action failed.", recognized=True)
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
