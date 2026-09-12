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
        self._generation_lock = threading.Lock()
        self._generation = 0
        self._process: subprocess.Popen | None = None

    @staticmethod
    def _load_voice() -> str | None:
        try:
            data = json.loads((Path(__file__).resolve().parent.parent / "preferences.json").read_text(encoding="utf-8"))
            return data.get("voice")
        except Exception:
            return None

    def set_voice(self, voice: str) -> None:
        self.voice = voice

    @staticmethod
    def _check_edge() -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def _begin_generation(self) -> int:
        """Start a new speech generation and invalidate any older generation."""
        with self._generation_lock:
            self._generation += 1
            generation = self._generation
        self._stop_event.clear()
        return generation

    def _is_generation_current(self, generation: int) -> bool:
        with self._generation_lock:
            return generation == self._generation

    def stop(self) -> None:
        """Cancel only the currently active speech generation.

        A new speak() call gets a fresh generation, so an interrupted speech
        cannot accidentally resume when the next interaction clears the shared
        stop event.
        """
        with self._generation_lock:
            self._generation += 1
        self._stop_event.set()
        with self._process_lock:
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

    def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return True
        generation = self._begin_generation()
        text = text.strip()
        if self._edge_available:
            try:
                # ffplay can consume edge-tts audio chunks immediately instead
                # of waiting for the complete MP3 file to be synthesized.
                if shutil.which("ffplay"):
                    return self._speak_edge_stream(text, generation)
                return self._speak_edge_file(text, generation)
            except Exception:
                if self._stop_event.is_set() or not self._is_generation_current(generation):
                    return False
        return self._speak_pyttsx3(text, generation)

    def _speak_edge_stream(self, text: str, generation: int) -> bool:
        import edge_tts

        process = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with self._process_lock:
            self._process = process

        async def feed() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            async for chunk in communicate.stream():
                if self._stop_event.is_set() or not self._is_generation_current(generation):
                    break
                if chunk.get("type") == "audio" and chunk.get("data") and process.stdin:
                    process.stdin.write(chunk["data"])
                    process.stdin.flush()
            if process.stdin:
                try:
                    process.stdin.close()
                except Exception:
                    pass

        try:
            asyncio.run(feed())
            while process.poll() is None:
                if self._stop_event.wait(0.05) or not self._is_generation_current(generation):
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    return False
            return not self._stop_event.is_set() and self._is_generation_current(generation)
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None
            if process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass

    def _speak_edge_file(self, text: str, generation: int) -> bool:
        import edge_tts

        async def _generate(path: str):
            await edge_tts.Communicate(text, self.voice).save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
        try:
            asyncio.run(_generate(tmp_path))
            if self._stop_event.is_set() or not self._is_generation_current(generation):
                return False
            cmd = (
                'Add-Type -AssemblyName presentationCore; '
                '$p=New-Object System.Windows.Media.MediaPlayer; '
                f'$p.Open([System.Uri]::new((Resolve-Path "{tmp_path}").Path)); '
                '$p.Play(); Start-Sleep -Milliseconds 400; '
                'while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }; '
                'while ($p.Position -lt $p.NaturalDuration.TimeSpan) { Start-Sleep -Milliseconds 100 }; $p.Close()'
            )
            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._process_lock:
                self._process = process
            while process.poll() is None:
                if self._stop_event.wait(0.1) or not self._is_generation_current(generation):
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    return False
            return not self._stop_event.is_set() and self._is_generation_current(generation)
        finally:
            with self._process_lock:
                if self._process is process if 'process' in locals() else False:
                    self._process = None
            if 'process' in locals() and process.poll() is None:
                try:
                    process.terminate()
                except Exception:
                    pass
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _speak_pyttsx3(self, text: str, generation: int) -> bool:
        try:
            import pyttsx3
            if self._stop_event.is_set() or not self._is_generation_current(generation):
                return False
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            return not self._stop_event.is_set() and self._is_generation_current(generation)
        except Exception:
            return False
