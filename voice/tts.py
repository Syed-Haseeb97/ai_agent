"""
Text-to-speech with free edge-tts (neural voices) and pyttsx3 fallback.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import subprocess


class TTS:
    def __init__(self, voice: str = "en-US-JennyNeural"):
        self.voice = voice
        self._edge_available = self._check_edge()

    def _check_edge(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        text = text.strip()
        if self._edge_available:
            try:
                self._speak_edge(text)
                return
            except Exception:
                pass  # fall through to pyttsx3
        self._speak_pyttsx3(text)

    def _speak_edge(self, text: str) -> None:
        """Generate mp3 with edge-tts and play it via PowerShell MediaPlayer."""
        import edge_tts

        async def _generate(path: str):
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            asyncio.run(_generate(tmp_path))

            # Reliable Windows playback that waits until finished
            cmd = (
                'Add-Type -AssemblyName presentationCore; '
                f'$p = New-Object System.Windows.Media.MediaPlayer; '
                f'$p.Open([System.Uri]::new((Resolve-Path "{tmp_path}").Path)); '
                '$p.Play(); '
                'Start-Sleep -Milliseconds 400; '
                'while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }; '
                'while ($p.Position -lt $p.NaturalDuration.TimeSpan) { Start-Sleep -Milliseconds 200 }; '
                '$p.Close()'
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                check=False,
                capture_output=True,
                timeout=90,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _speak_pyttsx3(self, text: str) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass
