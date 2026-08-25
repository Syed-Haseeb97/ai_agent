"""Explicit allowlist of safe Windows desktop actions."""
from __future__ import annotations

import os
import re
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ActionResult:
    handled: bool
    message: str = ""


class WindowsActionExecutor:
    """Execute only known, explicitly registered desktop actions."""

    def try_execute(self, text: str) -> ActionResult:
        q = text.strip().lower()
        if not q:
            return ActionResult(False)
        open_words = r"\b(open|launch|start|show|bring up)\b"
        close_words = r"\b(close|quit|exit)\b"

        if re.search(open_words + r".*\b(chrome|google chrome)\b", q):
            self._launch_app("chrome", ["chrome.exe"]); return ActionResult(True, "Opening Chrome…")
        if re.search(close_words + r".*\b(chrome|google chrome)\b", q):
            self._kill_process("chrome.exe"); return ActionResult(True, "Closing Chrome…")
        if re.search(open_words + r".*\bcamera\b", q):
            os.startfile("microsoft.windows.camera:"); return ActionResult(True, "Opening Camera…")
        if re.search(open_words + r".*\b(vs code|visual studio code|code)\b", q):
            self._launch_app("VS Code", ["code.exe"]); return ActionResult(True, "Opening VS Code…")
        if re.search(open_words + r".*\b(task manager|taskmgr)\b", q):
            subprocess.Popen(["taskmgr.exe"], shell=False); return ActionResult(True, "Opening Task Manager…")
        if re.search(open_words + r".*\b(calculator|calc)\b", q):
            subprocess.Popen(["calc.exe"], shell=False); return ActionResult(True, "Opening Calculator…")
        if re.search(open_words + r".*\b(notepad)\b", q):
            subprocess.Popen(["notepad.exe"], shell=False); return ActionResult(True, "Opening Notepad…")
        if re.search(open_words + r".*\b(file explorer|explorer)\b", q):
            subprocess.Popen(["explorer.exe"], shell=False); return ActionResult(True, "Opening File Explorer…")
        if re.search(open_words + r".*\b(command prompt|cmd)\b", q):
            subprocess.Popen(["cmd.exe"], shell=False); return ActionResult(True, "Opening Command Prompt…")
        if re.search(open_words + r".*\b(powershell|power shell)\b", q):
            subprocess.Popen(["powershell.exe", "-NoProfile"], shell=False); return ActionResult(True, "Opening PowerShell…")

        url_match = re.search(r"\b(?:open|go to|visit)\s+(https?://\S+|www\.\S+)", text, re.I)
        if url_match:
            url = url_match.group(1); url = "https://" + url if url.startswith("www.") else url
            webbrowser.open(url); return ActionResult(True, f"Opening {url}…")

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
