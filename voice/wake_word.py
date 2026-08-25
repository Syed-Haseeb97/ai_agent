"""Optional local wake-word listener for Ruby."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path


class WakeWordService:
    def __init__(self, callback):
        self.callback = callback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        if os.getenv("RUBY_WAKE_WORD", "0").strip() == "1": return True
        try:
            prefs = json.loads((Path(__file__).resolve().parent.parent / "preferences.json").read_text(encoding="utf-8"))
            return bool(prefs.get("wake_word_enabled", False))
        except Exception:
            return False

    def start(self) -> bool:
        if not self.enabled or (self._thread and self._thread.is_alive()): return False
        self._stop.clear(); self._thread = threading.Thread(target=self._run, daemon=True, name="RubyWakeWord"); self._thread.start(); return True

    def stop(self) -> None: self._stop.set()

    def _run(self) -> None:
        try:
            import numpy as np
            import pyaudiowpatch as pyaudio
            from openwakeword.model import Model
        except ImportError:
            return
        model_path = os.getenv("RUBY_WAKE_MODEL", "").strip()
        try:
            model = Model(wakeword_models=[model_path] if model_path else ["hey_jarvis"])
        except Exception:
            # openWakeWord does not ship a stock "Hey Ruby" model. Set
            # RUBY_WAKE_MODEL to a compatible custom Hey Ruby model file.
            return
        pa = pyaudio.PyAudio(); stream = None
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1280)
            while not self._stop.is_set():
                data = stream.read(1280, exception_on_overflow=False)
                scores = model.predict(np.frombuffer(data, dtype=np.int16))
                if any(float(v) > 0.65 for v in scores.values()):
                    self.callback(); self._stop.wait(1.0)
        except Exception:
            pass
        finally:
            try:
                if stream: stream.stop_stream(); stream.close()
            except Exception: pass
            pa.terminate()
