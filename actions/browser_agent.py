"""Generic browser task planner."""
from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

try:
    from actions.browser_actions import BrowserActions
except ModuleNotFoundError:
    from .browser_actions import BrowserActions

logger = logging.getLogger("ruby.browser")


@dataclass(frozen=True)
class BrowserTaskResult:
    handled: bool
    message: str = ""
    recognized: bool = False


class BrowserAgent:
    """General-purpose browser task layer; avoid phrase-specific command hacks."""

    SITE_ALIASES = {
        "youtube": "youtube", "yt": "youtube", "google": "google", "github": "github",
        "reddit": "reddit", "gmail": "gmail", "chatgpt": "chatgpt", "amazon": "amazon",
        "netflix": "netflix", "spotify": "spotify", "linkedin": "linkedin", "linkdin": "linkedin",
        "instagram": "instagram", "insta": "instagram", "notion": "notion", "gemini": "gemini",
        "perplexity": "perplexity", "discord": "discord", "slack": "slack", "canva": "canva",
        "twitter": "twitter", "x": "twitter",
    }

    BROWSER_ALIASES = {
        "chrome": "google", "google chrome": "google", "browser": "google",
        "this browser": "google", "the browser": "google",
    }

    SITE_URLS = {
        "youtube": "https://www.youtube.com", "google": "https://www.google.com",
        "github": "https://github.com", "reddit": "https://www.reddit.com",
        "gmail": "https://mail.google.com", "chatgpt": "https://chatgpt.com",
        "amazon": "https://www.amazon.com", "netflix": "https://www.netflix.com",
        "spotify": "https://open.spotify.com", "linkedin": "https://www.linkedin.com",
        "instagram": "https://www.instagram.com", "notion": "https://www.notion.so",
        "gemini": "https://gemini.google.com", "perplexity": "https://www.perplexity.ai",
        "discord": "https://discord.com/app", "slack": "https://app.slack.com",
        "canva": "https://www.canva.com", "twitter": "https://x.com",
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

        spotify = self._spotify(original)
        if spotify.recognized:
            return spotify

        compound = self._compound(original)
        if compound.recognized:
            return compound

        for handler in (self._open, self._search, self._media, self._navigation, self._interaction):
            result = handler(original if handler is self._interaction else q)
            if result.recognized:
                return result
        return BrowserTaskResult(False)

    def _fail(self, user_message: str) -> BrowserTaskResult:
        detail = None
        try:
            detail = self.browser.last_error()
        except Exception:
            pass
        if detail:
            logger.error("Browser task failed: %s | underlying=%s", user_message, detail)
        else:
            logger.error("Browser task failed: %s", user_message)
        return BrowserTaskResult(False, user_message, recognized=True)

    def _compound(self, original: str) -> BrowserTaskResult:
        parts = [
            p.strip(" .")
            for p in re.split(
                r"\s+and\s+(?=(?:then\s+)?(?:play|watch|open|search|look\s+up|find|click|type|go|navigate|scroll|refresh|reload|close)\b)",
                original,
                flags=re.I,
            )
            if p.strip()
        ]
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

    def _spotify(self, original: str) -> BrowserTaskResult:
        lower = original.lower().strip()
        if lower == "open spotify":
            ok = self.browser.open_url("https://open.spotify.com")
            if ok:
                return BrowserTaskResult(True, "Opening spotify…", recognized=True)
            return self._fail("I tried to open spotify, but the browser action failed.")
        match = re.match(r"^open\s+spotify\s+and\s+play\s+(.+?)\s*$", original, re.I)
        if match:
            track = match.group(1).strip()
            if not self.browser.open_url("https://open.spotify.com"):
                return self._fail("I tried to open Spotify, but the browser action failed.")
            if getattr(self.browser, "play_spotify_track", lambda t: False)(track):
                return BrowserTaskResult(True, f"Playing {track} on Spotify…", recognized=True)
            return self._fail(f"Spotify opened, but I couldn't start {track}.")
        return BrowserTaskResult(False)

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
                    return self._fail(f"I tried to open {site} and search for {term}, but the browser action failed.")
            ok = self.browser.open_url(self._site_url(site))
            if ok:
                return BrowserTaskResult(True, f"Opening {site}…", recognized=True)
            return self._fail(f"I tried to open {site}, but the browser action failed.")
        generic = re.match(
            r"^(?:please\s+)?(?:open|launch|start|visit|go\s+to|take\s+me\s+to|show)\s+(?:me\s+)?(?:the\s+)?(.+?)\s*$",
            q, re.I,
        )
        if not generic:
            return BrowserTaskResult(False)
        target = self._clean_term(generic.group(1))
        if not target or re.search(r"\b(search|look\s+up|find)\b", target):
            return BrowserTaskResult(False)
        ok = self.browser.open_url(self._guess_url(target))
        if ok:
            return BrowserTaskResult(True, f"Opening {target}…", recognized=True)
        return self._fail(f"I tried to open {target}, but the browser action failed.")

    def _search(self, q: str) -> BrowserTaskResult:
        explicit = re.match(
            r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s+(?:on|in)\s+(?:this\s+|my\s+|the\s+)?(.+?)(?:\s+(?:tab|browser|app))?\s*$",
            q, re.I,
        )
        if explicit:
            term = self._clean_term(explicit.group(1))
            destination = explicit.group(2).strip().lower()
            site = self.SITE_ALIASES.get(destination) or self.BROWSER_ALIASES.get(destination)
            if site and term:
                ok = self.browser.search(term, site)
                if ok:
                    return BrowserTaskResult(True, f"Searching {site} for {term}…", recognized=True)
                return self._fail(f"I tried to search {site} for {term}, but the browser action failed.")
        generic = re.match(r"^(?:please\s+)?(?:search|look\s+up|find)\s+(?:for\s+)?(.+?)\s*$", q, re.I)
        if not generic:
            return BrowserTaskResult(False)
        term = self._clean_term(generic.group(1))
        if not term:
            return BrowserTaskResult(False)
        ok = self.browser.search_current_page(term)
        if ok:
            return BrowserTaskResult(True, f"Searching for {term}…", recognized=True)
        return self._fail(
            f"I understood you want to search for {term}, but I couldn't do it in the current browser context."
        )

    def _media(self, q: str) -> BrowserTaskResult:
        if not re.search(r"\b(play|watch|open)\b", q):
            return BrowserTaskResult(False)
        latest = re.search(
            r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(?:(?:video|upload)\s+)?(?:uploaded\s+by|posted\s+by|by|of|from|for)\s+(.+?)(?:\s+video)?\s*(?:on\s+(?:youtube|yt))?\s*$",
            q, re.I,
        )
        if not latest:
            latest = re.search(
                r"\b(?:play|watch|open)\s+(?:the\s+)?(?:latest|newest|most\s+recent)\s+(.+?)\s+video(?:\s+on\s+(?:youtube|yt))?\s*$",
                q, re.I,
            )
        if latest:
            topic = self._clean_term(latest.group(1))
            ok = self.browser.play_latest_youtube_video(topic or None)
            if ok:
                return BrowserTaskResult(
                    True,
                    f"Playing the latest video for {topic}…" if topic else "Playing the latest video…",
                    recognized=True,
                )
            return self._fail(
                f"I tried to play the latest video for {topic}, but the browser action failed."
                if topic
                else "I tried to play the latest video, but the browser action failed."
            )
        if re.search(r"\b(?:its|the|his|her)\s+(?:latest|newest|most\s+recent)\s+(?:uploaded\s+)?(?:video|upload)\b", q):
            ok = self.browser.play_latest_youtube_video()
            if ok:
                return BrowserTaskResult(True, "Playing the latest video…", recognized=True)
            return self._fail("I tried to play the latest video, but the browser action failed.")
        if re.search(r"\b(?:first|top)\s+(?:video|result)\b", q):
            ok = self.browser.click_first_result()
            if ok:
                return BrowserTaskResult(True, "Opening the first result…", recognized=True)
            return self._fail("I tried to open the first result, but the browser action failed.")
        if re.search(r"\b(?:pause|stop)\b(?:\s+the)?\s+(?:current\s+)?video\b|\bpause\s+(?:youtube|yt)\b", q):
            ok = self.browser.pause_youtube()
            if ok:
                return BrowserTaskResult(True, "Pausing the video…", recognized=True)
            return self._fail("I tried to pause the video, but the browser action failed.")
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
                return self._fail(f"I tried to do that ({message.strip('…')}), but it failed.")
        return BrowserTaskResult(False)

    def _interaction(self, original: str) -> BrowserTaskResult:
        q = original.lower()
        click = re.match(r"\s*(?:please\s+)?click\s+(?:on\s+)?(?:the\s+)?(.+?)\s*$", original, re.I)
        if click:
            target = self._clean_term(click.group(1))
            ok = self.browser.click_text(target)
            if ok:
                return BrowserTaskResult(True, f"Clicking {target}…", recognized=True)
            return self._fail(f'I couldn\'t find anything matching "{target}" to click on the current page.')
        type_match = re.match(r"\s*(?:please\s+)?type\s+(.+?)(?:\s+into\s+(?:the\s+)?(.+))?\s*$", original, re.I)
        if type_match:
            text = self._clean_term(type_match.group(1))
            target = self._clean_term(type_match.group(2) or "")
            ok = self.browser.type_text(text, target or None)
            if ok:
                return BrowserTaskResult(True, "Typing…", recognized=True)
            return self._fail("I tried to type that, but the browser action failed.")
        if re.search(r"\bscroll\s+(?:down|up)\b", q):
            direction = "up" if " up" in q else "down"
            ok = self.browser.scroll(direction)
            if ok:
                return BrowserTaskResult(True, f"Scrolling {direction}…", recognized=True)
            return self._fail(f"I tried to scroll {direction}, but the browser action failed.")
        return BrowserTaskResult(False)

    @classmethod
    def _site_in_text(cls, q: str) -> str | None:
        for alias, site in sorted(cls.SITE_ALIASES.items(), key=lambda x: -len(x[0])):
            if re.search(rf"\b{re.escape(alias)}\b", q):
                return site
        return None

    @classmethod
    def _site_url(cls, site: str) -> str:
        return cls.SITE_URLS.get(site, "https://www.google.com")

    @classmethod
    def _mentions_desktop_app(cls, q: str) -> bool:
        return any(re.search(rf"\b{re.escape(kw)}\b", q) for kw in cls.NON_WEB_KEYWORDS)

    @classmethod
    def _guess_url(cls, target: str) -> str:
        """Resolve a spoken website name to a direct destination URL.

        Known aliases use SITE_URLS. Unknown names are resolved via Google's
        Feeling Lucky redirect chain, but we extract the real destination from
        google.com/url?q=... and never hand that interstitial URL to Playwright.
        """
        target = (target or "").strip()
        if not target:
            return "https://www.google.com"

        lowered = target.lower()
        if lowered.startswith("http://") or lowered.startswith("https://"):
            return target
        if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}(/.*)?$", lowered):
            return "https://" + target.lstrip("/")

        key = re.sub(r"[^a-z0-9]+", "", lowered)
        for alias, site in cls.SITE_ALIASES.items():
            if re.sub(r"[^a-z0-9]+", "", alias) == key:
                return cls._site_url(site)

        resolved = cls._resolve_unknown_site(target)
        if resolved:
            return resolved

        slug = key or "google"
        return f"https://www.{slug}.com"

    @classmethod
    def _resolve_unknown_site(cls, target: str) -> str | None:
        """Resolve an unknown spoken site name to a direct http(s) URL."""
        query = urllib.parse.quote_plus(f"{target} official website")
        start = f"https://www.google.com/search?q={query}&btnI=1"
        try:
            class _StopRedirect(Exception):
                def __init__(self, url: str) -> None:
                    self.url = url

            class _CaptureRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
                    raise _StopRedirect(newurl)

            req = urllib.request.Request(
                start,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            opener = urllib.request.build_opener(_CaptureRedirect())
            try:
                with opener.open(req, timeout=12) as resp:
                    final = resp.geturl()
            except _StopRedirect as stop:
                final = stop.url
            except Exception as exc:
                logger.warning("site resolve failed for %r: %s", target, exc)
                return None

            direct = cls._extract_direct_destination(final)
            if direct:
                logger.info("resolved %r -> %s", target, direct)
                return direct
            host = urllib.parse.urlparse(final).netloc.lower()
            if final.startswith("http") and "google." not in host:
                return final
        except Exception as exc:
            logger.warning("site resolve error for %r: %s", target, exc)
        return None

    @staticmethod
    def _extract_direct_destination(url: str) -> str | None:
        """Pull the real destination out of a Google /url redirect, if present."""
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return None
        host = (parsed.netloc or "").lower()
        if "google." not in host:
            return None
        if not (parsed.path or "").startswith("/url"):
            return None
        qs = urllib.parse.parse_qs(parsed.query or "")
        for key in ("q", "url"):
            for value in qs.get(key) or []:
                if isinstance(value, str) and value.startswith("http"):
                    return value
        return None

    @staticmethod
    def _clean_term(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", value).strip(" .?!,\"'")
