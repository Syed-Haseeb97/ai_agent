"""Explicit allowlist of safe Windows desktop and browser actions."""
from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ActionResult:
    handled: bool
    message: str = ""


class WindowsActionExecutor:
    """Execute only known, explicitly registered desktop/browser actions."""

    SITE_ALIASES = {
        "youtube": "https://www.youtube.com",
        "youtube.com": "https://www.youtube.com",
        "github": "https://github.com",
        "github.com": "https://github.com",
        "google": "https://www.google.com",
        "google.com": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "gmail.com": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "chatgpt.com": "https://chatgpt.com",
        "reddit": "https://www.reddit.com",
        "reddit.com": "https://www.reddit.com",
        "amazon": "https://www.amazon.com",
        "amazon.com": "https://www.amazon.com",
        "netflix": "https://www.netflix.com",
        "netflix.com": "https://www.netflix.com",
    }

    APP_PROCESSES = {
        "google chrome": "chrome.exe", "chrome": "chrome.exe",
        "command prompt": "cmd.exe", "cmd": "cmd.exe",
        "powershell": "powershell.exe", "power shell": "powershell.exe",
        "notepad": "notepad.exe", "calculator": "calculatorapp.exe", "calc": "calculatorapp.exe",
        "task manager": "taskmgr.exe", "taskmgr": "taskmgr.exe",
        "visual studio code": "code.exe", "vs code": "code.exe", "code": "code.exe",
    }

    def try_execute(self, text: str) -> ActionResult:
        original = text.strip()
        q = original.lower()
        if not q:
            return ActionResult(False)

        open_words = r"\b(open|launch|start|show|bring up|go to|visit|take me to)\b"
        close_words = r"\b(close|quit|exit|shut down|shut)\b"

        result = self._handle_close_command(q, close_words)
        if result.handled:
            return result

        result = self._handle_site_command(q)
        if result.handled:
            return result

        if re.search(open_words + r".*\b(chrome|google chrome)\b", q):
            self._launch_app("Chrome", ["chrome.exe"]); return ActionResult(True, "Opening Chrome…")
        if re.search(open_words + r".*\bcamera\b", q):
            os.startfile("microsoft.windows.camera:"); return ActionResult(True, "Opening Camera…")
        if re.search(open_words + r".*\b(vs code|visual studio code|code)\b", q):
            self._launch_app("VS Code", ["code.exe"]); return ActionResult(True, "Opening VS Code…")
        if re.search(open_words + r".*\b(task manager|taskmgr)\b", q):
            subprocess.Popen(["taskmgr.exe"], shell=False); return ActionResult(True, "Opening Task Manager…")
        if re.search(open_words + r".*\b(calculator|calc)\b", q):
            subprocess.Popen(["calc.exe"], shell=False); return ActionResult(True, "Opening Calculator…")
        if re.search(open_words + r".*\bnotepad\b", q):
            subprocess.Popen(["notepad.exe"], shell=False); return ActionResult(True, "Opening Notepad…")
        if re.search(open_words + r".*\b(file explorer|explorer)\b", q):
            subprocess.Popen(["explorer.exe"], shell=False); return ActionResult(True, "Opening File Explorer…")
        if re.search(open_words + r".*\b(command prompt|cmd)\b", q):
            subprocess.Popen(["cmd.exe"], shell=False); return ActionResult(True, "Opening Command Prompt…")
        if re.search(open_words + r".*\b(powershell|power shell)\b", q):
            subprocess.Popen(["powershell.exe", "-NoProfile"], shell=False); return ActionResult(True, "Opening PowerShell…")

        url_match = re.search(r"\b(?:open|go to|visit)\s+(https?://\S+|www\.\S+)", original, re.I)
        if url_match:
            url = url_match.group(1)
            url = "https://" + url if url.startswith("www.") else url
            self._open_url(url)
            return ActionResult(True, f"Opening {url}…")

        if re.search(r"\b(bluetooth)\b.*\b(on|enable|turn on)\b|\b(turn on|enable)\b.*\bbluetooth\b", q):
            os.startfile("ms-settings:bluetooth"); return ActionResult(True, "Opening Bluetooth settings…")
        if re.search(r"\b(bluetooth)\b.*\b(off|disable|turn off)\b|\b(turn off|disable)\b.*\bbluetooth\b", q):
            os.startfile("ms-settings:bluetooth"); return ActionResult(True, "Opening Bluetooth settings so you can turn Bluetooth off…")
        if re.search(open_words + r".*\b(wifi|wi-fi|network)\b", q):
            os.startfile("ms-settings:network"); return ActionResult(True, "Opening network settings…")
        if re.search(open_words + r".*\b(sound|audio|volume)\b", q):
            os.startfile("ms-settings:sound"); return ActionResult(True, "Opening sound settings…")
        if re.search(open_words + r".*\bbluetooth\b", q):
            os.startfile("ms-settings:bluetooth"); return ActionResult(True, "Opening Bluetooth settings…")
        if re.search(r"\b(set|create|open|show)\b.*\b(alarm|alarms|clock)\b|\balarm\b.*\b\d{1,2}(:\d{2})?\b", q):
            os.startfile("ms-clock:alarms"); return ActionResult(True, "Opening Windows Alarms & Clock…")
        if re.search(open_words + r".*\bdownloads\b", q):
            os.startfile(str(Path.home() / "Downloads")); return ActionResult(True, "Opening Downloads…")
        if re.search(open_words + r".*\bdesktop\b", q):
            os.startfile(str(Path.home() / "Desktop")); return ActionResult(True, "Opening Desktop…")
        return ActionResult(False)

    def _handle_close_command(self, q: str, close_words: str) -> ActionResult:
        for label, executable in sorted(self.APP_PROCESSES.items(), key=lambda item: -len(item[0])):
            if re.search(close_words + rf".*\b{re.escape(label)}\b", q):
                self._kill_process(executable)
                return ActionResult(True, f"Closing {label.title()}…")
        return ActionResult(False)

    def _handle_site_command(self, q: str) -> ActionResult:
        """Open a known site by name, optionally with a search term."""
        aliases = sorted(self.SITE_ALIASES, key=len, reverse=True)
        site_pattern = "|".join(re.escape(a) for a in aliases)
        match = re.search(r"\b(?:open|launch|start|show|go to|visit|take me to)\b\s+(?:google\s+chrome\s+and\s+)?(?:.*?\s+)?(" + site_pattern + r")\b", q)
        if not match:
            return ActionResult(False)

        alias = match.group(1).lower()
        url = self.SITE_ALIASES[alias]
        search_match = re.search(r"\b(?:search|look\s+up|find)\s+(?:for\s+)?(.+)$", q, re.I)
        if search_match:
            term = search_match.group(1).strip(" .?!")
            if term and term not in {alias, alias.removesuffix(".com")}:
                if "youtube.com" in url:
                    search_url = url + "/results?search_query=" + urllib.parse.quote_plus(term)
                else:
                    search_url = url + "/search?q=" + urllib.parse.quote_plus(term)
                self._open_url(search_url)
                return ActionResult(True, f"Opening {alias} and searching for {term}…")

        self._open_url(url)
        return ActionResult(True, f"Opening {alias}…")

    @staticmethod
    def _open_url(url: str) -> None:
        # os.startfile delegates the URL to Windows' default browser reliably,
        # including when this action is invoked from the assistant's worker thread.
        os.startfile(url)

    @staticmethod
    def _launch_app(label: str, commands: list[str]) -> None:
        for command in commands:
            try:
                subprocess.Popen([command], shell=False); return
            except FileNotFoundError:
                continue
        subprocess.Popen(f'start "" "{label}"', shell=True)

    @staticmethod
    def _kill_process(executable: str) -> None:
        subprocess.run(["taskkill", "/IM", executable, "/F"], capture_output=True, text=True, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
