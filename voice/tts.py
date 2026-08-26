"""Text-to-speech with free edge-tts and pyttsx3 fallback."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


class TTS:
    def __init__(self, voice: str | None = None):
        self.voice = voice or self._load_voice() or "en-US-JennyNeural"
        self._edge_available = self._check_edge()
        self._stop_event = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    @staticmethod
    def _load_voice() -> str | None:
        try:
            data = json.loads((Path(__file__).resolve().parent.parent / "preferences.json").read_text(encoding="utf-8"))
            return data.get("voice")
        except Exception:
            return None

    def set_voice(self, voice: str) -> None: self.voice = voice

    @staticmethod
    def _check_edge() -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def stop(self) -> None:
        self._stop_event.set()
        with self._process_lock:
            process = self._process; self._process = None
        if process is not None and process.poll() is None:
            try: process.terminate()
            except Exception: pass

    def speak(self, text: str) -> bool:
        if not text or not text.strip(): return True
        self._stop_event.clear(); text = text.strip()
        if self._edge_available:
            try:
                if shutil.which("ffplay"):
                    return self._speak_edge_stream(text)
                return self._speak_edge_file(text)
            except Exception:
                if self._stop_event.is_set(): return False
        return self._speak_pyttsx3(text)

    def _speak_edge_stream(self, text: str) -> bool:
        import edge_tts

        process = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with self._process_lock: self._process = process

        async def feed() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            async for chunk in communicate.stream():
                if self._stop_event.is_set(): break
                if chunk.get("type") == "audio" and chunk.get("data") and process.stdin:
                    try:
                        process.stdin.write(chunk["data"]); process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        break
            if process.stdin:
                try: process.stdin.close()
                except (BrokenPipeError, OSError): pass

        worker_error: list[BaseException] = []

        def runner() -> None:
            try:
                asyncio.run(feed())
            except BaseException as exc:
                worker_error.append(exc)

        worker = threading.Thread(target=runner, name="edge-tts-stream", daemon=True)
        worker.start()
        try:
            while worker.is_alive():
                if self._stop_event.wait(0.05):
                    if process.poll() is None:
                        try: process.terminate()
                        except Exception: pass
                    break
            worker.join(timeout=2.0)
            if worker_error and not self._stop_event.is_set():
                raise worker_error[0]
            return not self._stop_event.is_set()
        finally:
            with self._process_lock:
                if self._process is process: self._process = None
            if process.poll() is None:
                try: process.terminate()
                except Exception: pass

    def _speak_edge_file(self, text: str) -> bool:
        import edge_tts
        async def _generate(path: str): await edge_tts.Communicate(text, self.voice).save(path)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f: tmp_path = f.name
        try:
            asyncio.run(_generate(tmp_path))
            if self._stop_event.is_set(): return False
            cmd=('Add-Type -AssemblyName presentationCore; $p=New-Object System.Windows.Media.MediaPlayer; '
                 f'$p.Open([System.Uri]::new((Resolve-Path "{tmp_path}").Path)); $p.Play(); Start-Sleep -Milliseconds 400; '
                 'while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }; '
                 'while ($p.Position -lt $p.NaturalDuration.TimeSpan) { Start-Sleep -Milliseconds 100 }; $p.Close()')
            process=subprocess.Popen(["powershell","-NoProfile","-Command",cmd],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            with self._process_lock: self._process=process
            while process.poll() is None:
                if self._stop_event.wait(0.1):
                    try: process.terminate()
                    except Exception: pass
                    return False
            return not self._stop_event.is_set()
        finally:
            with self._process_lock: self._process=None
            try: os.unlink(tmp_path)
            except OSError: pass

    def _speak_pyttsx3(self, text: str) -> bool:
        try:
            import pyttsx3
            engine=pyttsx3.init(); engine.setProperty("rate",185); engine.say(text); engine.runAndWait(); engine.stop(); return not self._stop_event.is_set()
        except Exception: return False
