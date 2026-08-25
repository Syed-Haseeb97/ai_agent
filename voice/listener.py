"""
Voice listener using the free Google Web Speech API via SpeechRecognition.
No API key required for basic usage.
"""

from __future__ import annotations

import speech_recognition as sr


class VoiceListener:
    def __init__(self, timeout: float = 6.0, phrase_time_limit: float = 10.0):
        self.recognizer = sr.Recognizer()
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        # Adjust for ambient noise once at start if possible
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
        except Exception:
            pass  # mic may not be ready yet; ignore

    def listen(self) -> str:
        """
        Listen on the default microphone and return the transcribed text.
        Returns empty string on failure / silence / timeout.
        """
        try:
            with sr.Microphone() as source:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )
            # Google Web Speech is free and requires no key for reasonable volume
            text = self.recognizer.recognize_google(audio)
            return text.strip() if text else ""
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            # Network / Google service issue
            raise RuntimeError(f"Speech recognition service error: {e}") from e
        except OSError as e:
            # No microphone or permission denied
            raise RuntimeError(
                "Microphone not available or permission denied. "
                "Check Windows privacy settings → Microphone."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Unexpected listening error: {e}") from e
