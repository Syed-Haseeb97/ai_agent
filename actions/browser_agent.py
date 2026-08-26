"""Generic browser task planner."""
from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from actions.browser_actions import BrowserActions
except ModuleNotFoundError:
    from .browser_actions import BrowserActions


@dataclass(frozen=True)
class BrowserTaskResult:
    handled: bool
    message: str = ""
    recognized: bool = False


class BrowserAgent:
    """General-purpose browser task layer; avoid phrase-specific command hacks."""

    SITE_ALIASES = {
        "youtube": "youtube", "yt": "youtube", "google": "google", "github": "github",
        "reddit": "reddit", "gmail": "gmail", "chatgpt": "chatgpt", "amazon": "amazon", "netflix": "netflix",
        "spotify": "spotify", "linkedin": "linkedin", "linkdin": "linkedin",
    }

    BROWSER_ALIASES = {
        "chrome": "google", "google chrome": "google", "browser": "google",
        "this browser": "google", "the browser": "google",
    }

    NON_WEB_KEYWORDS = (
        "chrome", "notepad", "calculator", "calc", "task manager", "taskmgr",
        "visual studio code", "vs code", "code", "command prompt", "cmd",
        "powershell", "power shell", "camera", "file explorer", "explorer",
        "downloads", "desktop", "bluetooth", "wifi", "wi-fi", "network",
        "sound", "audio", "volume", "alarm", "alarms", "clock", "settings",
        "control panel", "recycle bin", "this pc", "task bar", "taskbar",
    )

    def __init__(self, browser: BrowserActions):
        self.browser = browser

    def execute(self, text: str) -> BrowserTaskResult:
        original = text.strip().replace("linkdin", "linkedin").replace("plat his", "play his")
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
            original, flags=re.I
        ) if p.strip()]
        if len(parts) < 2:
            return BrowserTaskResult(False)
        messages = []
        for part in parts:
            result = self.execute(part)
            if not result.recognized:
                return BrowserTaskResult(False)
            if not result.handled:
                return BrowserTaskResult(False, result.message or f"I couldn't complete {part!r}.", recognized=True)
            if result.message:
                messages.append(result.message)
        return BrowserTaskResult(True, " ".join(messages), recognized=True)

    def _open(self, q: str) -> BrowserTaskResult:
        if not re.search(r"\b(open|launch|start|visit|go to|take me to|show)\b", q):
            return BrowserTaskResult(False)
        if self._mentions_desktop_app(q):
            return BrowserTaskResult(False)
        site = self._site_in_text(q)
        if site:
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
        generic = re.match(r"^(?:please\s+)?(?:open|launch|start|visit|go\s+to|take\s+me\s+to|show)\s+(?:me\s+)?(?:the\s+)?(.+?)\s*$", q, re.I)
        if not generic:
            return BrowserTaskResult(False)
        target = self._clean_term(generic.group(1))
        if not target or re.search(r"\b(search|look\s+up|find)\b", target):
            return BrowserTaskResult(False)
        ok = self.browser.open_url(self._guess_url(target))
        if ok:
            return BrowserTaskResult(True, f"Opening {target}…", recognized=True)
        return BrowserTaskResult(False, f"I tried to open {target}, but the browser action failed.", recognized=True)

    def _search(self, q: str) -> BrowserTaskResult:
        explicit = re.match(
            r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+(?:this\s+|my\s+|the\s+)?(.+?)(?:\s+(?:tab|browser|app))?\s*$",
            q, re.I
        )
        if explicit:
            term = self._clean_term(explicit.group(1))
            destination = explicit.group(2).strip().lower()
            site = self.SITE_ALIASES.get(destination) or self.BROWSER_ALIASES.get(destination)
            if site and term:
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
        return BrowserTaskResult(False, f"I understood you want to search for {term}, but I couldn't do it in the current browser context.", recognized=True)

    def _media(self, q: str) -> BrowserTaskResult:
        if not re.search(r"\b(play|watch|open)\b", q):
            return BrowserTaskResult(False)
        latest = re.search(
            r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(?:(?:video|upload)\s+)?(?:uploaded\s+by|posted\s+by|by|of|from|for)\s+(.+?)(?:\s+video)?\s*(?:on\s+(?:youtube|yt))?\s*$",
            q, re.I
        )
        if not latest:
            latest = re.search(
                r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(.+?)\s+video(?:\s+on\s+(?:youtube|yt))?\s*$",
                q, re.I
            )
        if latest:
            topic = self._clean_term(latest.group(1))
            ok = self.browser.play_latest_youtube_video(topic or None)
            if ok:
                return BrowserTaskResult(True, f"Playing the latest video for {topic}…" if topic else "Playing the latest video…", recognized=True)
            return BrowserTaskResult(False, f"I tried to play the latest video for {topic}, but the browser action failed." if topic else "I tried to play the latest video, but the browser action failed.", recognized=True)
        if re.search(r"\b(?:its|the|his|her)\s+(?:latest|newest|most\s+recent)\s+(?:uploaded\s+)?(?:video|upload)\b", q):
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
            "amazon": "https://www.amazon.com", "netflix": "https://www.netflix.com", "spotify": "https://open.spotify.com",
            "linkedin": "https://www.linkedin.com",
        }.get(site, "https://www.google.com")

    @classmethod
    def _mentions_desktop_app(cls, q: str) -> bool:
        return any(re.search(rf"\b{re.escape(kw)}\b", q) for kw in cls.NON_WEB_KEYWORDS)

    @staticmethod
    def _guess_url(target: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "", target.lower())
        return f"https://www.{slug}.com" if slug else "https://www.google.com"

    @staticmethod
    def _clean_term(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip(" .?!,\"")
