"""Optional local 'Hey Ruby' wake-word listener.

Enabled only when RUBY_WAKE_WORD=1 and openwakeword is installed. Keeping it
optional prevents a new background microphone loop from changing the stable
MVP by default.
"""
from __future__ import annotations

import os
import threading


class WakeWordService:
    def __init__(self, callback):
        self.callback = callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return os.getenv("RUBY_WAKE_WORD", "0").strip() == "1"

    def start(self) -> bool:
        if not self.enabled or self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="RubyWakeWord")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            import numpy as np
            import pyaudiowpatch as pyaudio
            from openwakeword.model import Model
        except ImportError:
            return

        try:
            model = Model(wakeword_models=["hey_ruby"])
        except Exception:
            # The model is optional; do not crash the assistant if a custom
            # 'hey_ruby' model is not installed. A user can later configure a
            # supported openWakeWord model and keep the same service.
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                             input=True, frames_per_buffer=1280)
            while not self._stop.is_set():
                data = stream.read(1280, exception_on_overflow=False)
                audio = np.frombuffer(data, dtype=np.int16)
                scores = model.predict(audio)
                if any(float(v) > 0.65 for v in scores.values()):
                    self.callback()
                    self._stop.wait(1.0)
        except Exception:
            pass
        finally:
            try: stream.stop_stream(); stream.close()
            except Exception: pass
            pa.terminate()
