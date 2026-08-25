"""Small, explicit allowlist of Windows actions.

The assistant never executes arbitrary model-generated shell commands.  Natural
language is matched to one of these known actions and everything else remains a
normal Gemini question.
"""

from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ActionResult:
    handled: bool
    message: str = ""


class WindowsActionExecutor:
    """Recognize and execute a deliberately small set of safe desktop actions."""

    def try_execute(self, text: str) -> ActionResult:
        q = text.strip().lower()
        if not q:
            return ActionResult(False)

        # Websites / browser.
        if re.search(r"\b(open|launch|start)\b.*\b(chrome|google chrome)\b", q):
            self._launch_app("chrome", ["chrome.exe"])
            return ActionResult(True, "Opening Chrome…")
        if re.search(r"\b(close|quit|exit)\b.*\b(chrome|google chrome)\b", q):
            self._kill_process("chrome.exe")
            return ActionResult(True, "Closing Chrome…")
        if re.search(r"\b(open|launch|start)\b.*\bcamera\b", q):
            os.startfile("microsoft.windows.camera:")
            return ActionResult(True, "Opening Camera…")
        if re.search(r"\b(open|launch|start)\b.*\b(vs code|visual studio code|code)\b", q):
            self._launch_app("VS Code", ["code.exe"])
            return ActionResult(True, "Opening VS Code…")

        url_match = re.search(r"\b(?:open|go to|visit)\s+(https?://\S+|www\.\S+)", text, re.I)
        if url_match:
            url = url_match.group(1)
            if url.startswith("www."):
                url = "https://" + url
            webbrowser.open(url)
            return ActionResult(True, f"Opening {url}…")

        # Windows settings pages.  We intentionally open the official Settings UI
        # instead of running privileged device-management commands silently.
        if re.search(r"\b(bluetooth)\b.*\b(on|enable|turn on)\b", q) or re.search(r"\b(turn on|enable)\b.*\bbluetooth\b", q):
            os.startfile("ms-settings:bluetooth")
            return ActionResult(True, "Opening Bluetooth settings…")
        if re.search(r"\b(bluetooth)\b.*\b(off|disable|turn off)\b", q) or re.search(r"\b(turn off|disable)\b.*\bbluetooth\b", q):
            os.startfile("ms-settings:bluetooth")
            return ActionResult(True, "Opening Bluetooth settings so you can turn Bluetooth off…")

        if re.search(r"\b(open|show)\b.*\b(wifi|wi-fi|network)\b", q):
            os.startfile("ms-settings:network")
            return ActionResult(True, "Opening network settings…")
        if re.search(r"\b(open|show)\b.*\b(sound|audio|volume)\b", q):
            os.startfile("ms-settings:sound")
            return ActionResult(True, "Opening sound settings…")
        if re.search(r"\b(open|show)\b.*\b(bluetooth)\b", q):
            os.startfile("ms-settings:bluetooth")
            return ActionResult(True, "Opening Bluetooth settings…")

        # Windows Alarms & Clock.  The exact alarm time is deliberately left to
        # the user in the system UI rather than silently creating a scheduled task.
        if re.search(r"\b(set|create|open|show)\b.*\b(alarm|alarms|clock)\b", q) or re.search(r"\balarm\b.*\b\d{1,2}(:\d{2})?\b", q):
            os.startfile("ms-clock:alarms")
            return ActionResult(True, "Opening Windows Alarms & Clock…")

        # Common folders.
        if re.search(r"\b(open|show)\b.*\b(downloads)\b", q):
            os.startfile(str(Path.home() / "Downloads"))
            return ActionResult(True, "Opening Downloads…")
        if re.search(r"\b(open|show)\b.*\b(desktop)\b", q):
            os.startfile(str(Path.home() / "Desktop"))
            return ActionResult(True, "Opening Desktop…")

        return ActionResult(False)

    @staticmethod
    def _launch_app(label: str, commands: list[str]) -> None:
        for command in commands:
            try:
                subprocess.Popen([command], shell=False)
                return
            except FileNotFoundError:
                continue
        # Fallback to Windows' app resolution through the shell for known app names.
        subprocess.Popen(f'start "" "{label}"', shell=True)

    @staticmethod
    def _kill_process(executable: str) -> None:
        subprocess.run(
            ["taskkill", "/IM", executable, "/F"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
