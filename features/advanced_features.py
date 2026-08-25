"""Isolated, opt-in desktop features for the AI Screen Assistant.

The module deliberately keeps privileged operations explicit and allowlisted.
It is imported by the existing action executor instead of replacing the
conversation/TTS pipeline.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from mss import mss
from PIL import Image

SCREENSHOT_DIR = Path(r"D:\screen_shots")
RECORDING_DIR = Path(r"D:\screen_recordings")
MEMORY_FILE = Path(__file__).resolve().parent.parent / "memory.json"
REMINDER_FILE = Path(__file__).resolve().parent.parent / "reminders.json"


@dataclass(frozen=True)
class FeatureResult:
    handled: bool
    message: str = ""


class AdvancedFeatures:
    """F2.2/F3-F15 feature registry. Safe operations only."""

    def __init__(self) -> None:
        self._recording_process: subprocess.Popen | None = None
        self._recording_lock = threading.Lock()
        self._reminder_thread_started = False
        self._start_reminder_loop()

    # ---------- dispatcher ----------
    def try_execute(self, text: str) -> FeatureResult:
        q = text.strip().lower()
        if not q:
            return FeatureResult(False)

        handlers = (
            self._youtube_latest,
            self._screenshot,
            self._recording,
            self._startup,
            self._wake_word_settings,
            self._file_management,
            self._system_controls,
            self._reminder,
            self._clipboard,
            self._screen_interaction,
            self._multi_step,
            self._personality,
            self._memory,
        )
        for handler in handlers:
            result = handler(text, q)
            if result.handled:
                return result
        return FeatureResult(False)

    # ---------- F2.2 ----------
    def _youtube_latest(self, text: str, q: str) -> FeatureResult:
        m = re.search(r"(?:play|watch|find)\s+(?:the\s+)?(?:latest|newest|most recent)\s+(.+?)\s+(?:video|videos)\s+(?:on|from)\s+youtube", q)
        if not m:
            return FeatureResult(False)
        term = m.group(1).strip()
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(term)
        webbrowser.open(url)
        return FeatureResult(True, f"Opening the latest {term} YouTube results…")

    # ---------- F3 ----------
    def _screenshot(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(take|capture|save)\b.*\b(screenshot|screen shot|screen capture)\b|\bscreenshot\b", q):
            return FeatureResult(False)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = SCREENSHOT_DIR / f"screenshot_{stamp}.png"
        with mss() as sct:
            monitors = sct.monitors
            shot = sct.grab(monitors[0])
            Image.frombytes("RGB", shot.size, shot.rgb).save(path, "PNG")
        return FeatureResult(True, f"Screenshot saved to {path}")

    # ---------- F4 ----------
    def _startup(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(start|launch|run|open)\b.*\b(with|on)\s+(windows|startup|boot)\b|\b(enable|disable)\b.*\b(startup|start with windows)\b", q):
            return FeatureResult(False)
        enable = not bool(re.search(r"\b(disable|turn off|remove)\b", q))
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    pythonw = Path(os.sys.executable).with_name("pythonw.exe")
                    target = pythonw if pythonw.exists() else Path(os.sys.executable)
                    script = Path(__file__).resolve().parent.parent / "main.py"
                    winreg.SetValueEx(key, "RubyAI", 0, winreg.REG_SZ, f'"{target}" "{script}"')
                else:
                    try:
                        winreg.DeleteValue(key, "RubyAI")
                    except FileNotFoundError:
                        pass
            return FeatureResult(True, "Ruby will start with Windows." if enable else "Ruby startup has been disabled.")
        except Exception as exc:
            return FeatureResult(True, f"I couldn't change Windows startup: {str(exc)[:160]}")

    # ---------- F5 ----------
    def _recording(self, text: str, q: str) -> FeatureResult:
        if re.search(r"\b(stop|end|finish)\b.*\b(screen )?record", q):
            with self._recording_lock:
                proc = self._recording_process
                self._recording_process = None
            if proc is None or proc.poll() is not None:
                return FeatureResult(True, "No screen recording is currently running.")
            proc.terminate()
            return FeatureResult(True, "Screen recording stopped and saved.")
        if not re.search(r"\b(start|begin)\b.*\b(screen )?record", q):
            return FeatureResult(False)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return FeatureResult(True, "Screen recording needs ffmpeg installed and available on PATH. I did not change anything else.")
        RECORDING_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = RECORDING_DIR / f"screen_recording_{stamp}.mp4"
        with mss() as sct:
            monitor = sct.monitors[0]
            width, height = monitor[2], monitor[3]
        cmd = [ffmpeg, "-y", "-f", "gdigrab", "-framerate", "12", "-draw_mouse", "1", "-i", "desktop", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)]
        with self._recording_lock:
            if self._recording_process is not None and self._recording_process.poll() is None:
                return FeatureResult(True, "A screen recording is already running.")
            self._recording_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return FeatureResult(True, f"Screen recording started. Saving to {path}")

    # ---------- F6 ----------
    def _wake_word_settings(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(enable|disable|turn on|turn off)\b.*\b(wake word|hey ruby)\b|\b(wake word|hey ruby)\b.*\b(enable|disable|on|off)\b", q):
            return FeatureResult(False)
        enabled = not bool(re.search(r"\b(disable|turn off|off)\b", q))
        return FeatureResult(True, f"Wake-word preference set to {'enabled' if enabled else 'disabled'}. Restart the assistant to apply it.")

    # ---------- F7/F8 ----------
    def _file_management(self, text: str, q: str) -> FeatureResult:
        folders = {"downloads": Path.home() / "Downloads", "desktop": Path.home() / "Desktop", "documents": Path.home() / "Documents", "pictures": Path.home() / "Pictures"}
        m = re.search(r"\b(?:open|show|go to)\s+(downloads|desktop|documents|pictures)\b", q)
        if m:
            path = folders[m.group(1)]
            os.startfile(str(path))
            return FeatureResult(True, f"Opening {m.group(1).title()}…")
        m = re.search(r"\b(?:find|locate)\s+(.+?)\s+in\s+(downloads|desktop|documents|pictures)\b", q)
        if m:
            term, folder = m.group(1), folders[m.group(2)]
            matches = [p.name for p in folder.rglob("*") if term.lower() in p.name.lower()][:8]
            return FeatureResult(True, "Found: " + ", ".join(matches) if matches else f"I couldn't find '{term}' in {m.group(2)}.")
        return FeatureResult(False)

    # ---------- F9 ----------
    def _system_controls(self, text: str, q: str) -> FeatureResult:
        settings = {
            "bluetooth": "ms-settings:bluetooth", "wifi": "ms-settings:network-wifi", "wi-fi": "ms-settings:network-wifi",
            "sound": "ms-settings:sound", "audio": "ms-settings:sound", "display": "ms-settings:display", "brightness": "ms-settings:display",
        }
        m = re.search(r"\b(?:open|show|go to)\s+(bluetooth|wifi|wi-fi|sound|audio|display|brightness)\s+(?:settings)?\b", q)
        if m:
            os.startfile(settings[m.group(1)])
            return FeatureResult(True, f"Opening {m.group(1)} settings…")
        if re.search(r"\b(turn|switch)\s+(off|on)\s+(wifi|wi-fi|bluetooth)\b", q):
            return FeatureResult(True, "I opened the Windows settings for that device control; Windows still requires the final toggle.")
        return FeatureResult(False)

    # ---------- F10 ----------
    def _reminder(self, text: str, q: str) -> FeatureResult:
        m = re.search(r"\bremind me in\s+(\d+)\s*(seconds?|minutes?|hours?)\s*(?:to|that)\s+(.+)$", q)
        if not m:
            return FeatureResult(False)
        amount, unit, message = int(m.group(1)), m.group(2), m.group(3).strip()
        seconds = amount * (3600 if unit.startswith("hour") else 60 if unit.startswith("minute") else 1)
        data = self._load_json(REMINDER_FILE, [])
        due = time.time() + seconds
        data.append({"due": due, "message": message})
        self._save_json(REMINDER_FILE, data)
        return FeatureResult(True, f"Reminder set for {amount} {unit}: {message}")

    def _start_reminder_loop(self) -> None:
        if self._reminder_thread_started:
            return
        self._reminder_thread_started = True
        threading.Thread(target=self._reminder_loop, daemon=True).start()

    def _reminder_loop(self) -> None:
        while True:
            try:
                items = self._load_json(REMINDER_FILE, [])
                now = time.time(); keep = []
                for item in items:
                    if item.get("due", 0) <= now:
                        ctypes.windll.user32.MessageBoxW(0, str(item.get("message", "Reminder")), "Ruby Reminder", 0x40)
                    else:
                        keep.append(item)
                if len(keep) != len(items): self._save_json(REMINDER_FILE, keep)
            except Exception:
                pass
            time.sleep(1)

    # ---------- F11 ----------
    def _clipboard(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(what is|read|show|explain|summarize)\b.*\bclipboard\b", q):
            return FeatureResult(False)
        try:
            import tkinter as tk
            root = tk.Tk(); root.withdraw(); value = root.clipboard_get(); root.destroy()
            return FeatureResult(True, f"Clipboard contains:\n{value[:1500]}")
        except Exception as exc:
            return FeatureResult(True, f"I couldn't read the clipboard: {str(exc)[:120]}")

    # ---------- F12 ----------
    def _screen_interaction(self, text: str, q: str) -> FeatureResult:
        m = re.search(r"\b(click|double click|right click)\s+(?:on|the)\s+(.+)$", q)
        if not m:
            return FeatureResult(False)
        try:
            import pyautogui
        except ImportError:
            return FeatureResult(True, "Screen interaction needs pyautogui installed. I did not click anything.")
        # Only support explicit screen coordinates to avoid unsafe guessing.
        coord = re.search(r"\b(\d{2,4})\s*[, ]\s*(\d{2,4})\b", m.group(2))
        if not coord:
            return FeatureResult(True, "For safety, screen clicks currently require coordinates, e.g. 'click 800,450'.")
        x, y = int(coord.group(1)), int(coord.group(2))
        if m.group(1) == "double click": pyautogui.doubleClick(x, y)
        elif m.group(1) == "right click": pyautogui.rightClick(x, y)
        else: pyautogui.click(x, y)
        return FeatureResult(True, f"Clicked at {x}, {y}.")

    # ---------- F13 ----------
    def _multi_step(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(?:then|and then|after that)\b", q):
            return FeatureResult(False)
        return FeatureResult(False)  # action executor remains the single-step owner for now

    # ---------- F14 ----------
    def _personality(self, text: str, q: str) -> FeatureResult:
        if not re.search(r"\b(set|make|change)\b.*\b(personality|style|tone)\b", q):
            return FeatureResult(False)
        style = re.sub(r".*?\b(?:personality|style|tone)\b", "", q, count=1).strip(" :to") or "friendly"
        prefs = self._load_json(MEMORY_FILE.with_name("preferences.json"), {})
        prefs["personality"] = style
        self._save_json(MEMORY_FILE.with_name("preferences.json"), prefs)
        return FeatureResult(True, f"Personality style set to {style}.")

    # ---------- F15 ----------
    def _memory(self, text: str, q: str) -> FeatureResult:
        m = re.match(r"(?:remember that|remember)\s+(.+)$", q)
        if m:
            data = self._load_json(MEMORY_FILE, [])
            data.append({"text": m.group(1).strip(), "created": datetime.now().isoformat(timespec="seconds")})
            self._save_json(MEMORY_FILE, data[-100:])
            return FeatureResult(True, "Got it — I'll remember that.")
        if re.search(r"\bwhat do you remember\b|\bshow my memories\b", q):
            data = self._load_json(MEMORY_FILE, [])
            if not data: return FeatureResult(True, "I don't have any saved memories yet.")
            return FeatureResult(True, "I remember:\n" + "\n".join(f"• {x['text']}" for x in data[-20:]))
        return FeatureResult(False)

    @staticmethod
    def _load_json(path: Path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default.copy() if isinstance(default, (list, dict)) else default

    @staticmethod
    def _save_json(path: Path, value) -> None:
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
