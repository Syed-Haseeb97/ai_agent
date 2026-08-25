"""
Text-to-speech with free edge-tts (neural voices) and pyttsx3 fallback.
Supports interrupting the current speech so a new question can barge in.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
import threading


class TTS:
    def __init__(self, voice: str = "en-US-JennyNeural"):
        self.voice = voice
        self._edge_available = self._check_edge()
        self._stop_event = threading.Event()
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    def _check_edge(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def stop(self) -> None:
        """Interrupt current speech playback as quickly as possible."""
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
        """Speak text. Returns False when speech was interrupted."""
        if not text or not text.strip():
            return True

        self._stop_event.clear()
        text = text.strip()

        if self._edge_available:
            try:
                return self._speak_edge(text)
            except InterruptedError:
                return False
            except Exception:
                if self._stop_event.is_set():
                    return False

        return self._speak_pyttsx3(text)

    def _speak_edge(self, text: str) -> bool:
        import edge_tts

        async def _generate(path: str):
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(path)

        if self._stop_event.is_set():
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            asyncio.run(_generate(tmp_path))

            if self._stop_event.is_set():
                return False

            # Windows playback. The process is kept so stop() can terminate it.
            cmd = (
                'Add-Type -AssemblyName presentationCore; '
                '$p = New-Object System.Windows.Media.MediaPlayer; '
                f'$p.Open([System.Uri]::new((Resolve-Path "{tmp_path}").Path)); '
                '$p.Play(); '
                'Start-Sleep -Milliseconds 400; '
                'while ($p.NaturalDuration.HasTimeSpan -eq $false) { '
                'Start-Sleep -Milliseconds 100 }; '
                'while ($p.Position -lt $p.NaturalDuration.TimeSpan) { '
                'Start-Sleep -Milliseconds 100 }; '
                '$p.Close()'
            )

            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with self._process_lock:
                self._process = process

            try:
                while process.poll() is None:
                    if self._stop_event.wait(0.1):
                        try:
                            process.terminate()
                        except Exception:
                            pass
                        return False
                return not self._stop_event.is_set()
            finally:
                with self._process_lock:
                    if self._process is process:
                        self._process = None
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _speak_pyttsx3(self, text: str) -> bool:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            return not self._stop_event.is_set()
        except Exception:
            return False
