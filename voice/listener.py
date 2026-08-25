"""
Voice listener using the free Google Web Speech API via SpeechRecognition.
No API key required for basic usage.
"""

from __future__ import annotations

import threading

import speech_recognition as sr


class VoiceListener:
    def __init__(
        self,
        timeout: float = 6.0,
        phrase_time_limit: float = 10.0,
        recognition_timeout: float = 15.0,
    ):
        self.recognizer = sr.Recognizer()
        self.timeout = timeout
        self.phrase_time_limit = phrase_time_limit
        self.recognition_timeout = recognition_timeout

        # Adjust for ambient noise once at start if possible. Keep this short so
        # a microphone/driver problem cannot leave the assistant stuck here.
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.6)
        except Exception:
            pass

    def listen(self) -> str:
        """
        Listen on the default microphone and return the transcribed text.

        There are two separate time limits:
        - timeout: maximum time waiting for the user to start speaking
        - phrase_time_limit: maximum length of the spoken phrase

        Google Web Speech recognition itself does not expose a reliable timeout
        in SpeechRecognition, so it runs in a daemon worker and is bounded by
        recognition_timeout as well. This prevents the UI from staying in
        "Listening…" forever when the network/service hangs.
        """
        try:
            with sr.Microphone() as source:
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit,
                )

            result: dict[str, object] = {}
            done = threading.Event()

            def recognize() -> None:
                try:
                    result["text"] = self.recognizer.recognize_google(audio)
                except Exception as exc:
                    result["error"] = exc
                finally:
                    done.set()

            worker = threading.Thread(target=recognize, daemon=True)
            worker.start()

            if not done.wait(self.recognition_timeout):
                raise RuntimeError(
                    "Speech recognition timed out. Check your internet connection "
                    "and try again."
                )

            error = result.get("error")
            if error is not None:
                if isinstance(error, sr.UnknownValueError):
                    return ""
                if isinstance(error, sr.RequestError):
                    raise RuntimeError(
                        f"Speech recognition service error: {error}"
                    ) from error
                raise RuntimeError(f"Speech recognition error: {error}") from error

            text = result.get("text", "")
            return text.strip() if isinstance(text, str) else ""

        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            raise RuntimeError(f"Speech recognition service error: {e}") from e
        except OSError as e:
            raise RuntimeError(
                "Microphone not available or permission denied. "
                "Check Windows privacy settings → Microphone."
            ) from e
        except Exception as e:
            raise RuntimeError(f"Unexpected listening error: {e}") from e
