"""Small, local-only IPC channel for sharing Ruby's current visual state.

Only a bounded state label and emotion are written; no prompts, transcripts, or
screen content are persisted. The timestamp makes abandoned state expire.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_STATES = {"idle", "listening", "thinking", "speaking", "error"}
_EMOTIONS = {"neutral", "happy", "excited", "sad", "empathetic", "curious", "surprised"}
_DEFAULT_PATH = Path(tempfile.gettempdir()) / "ruby_assistant_mood_state.json"


def _state_path(path: str | os.PathLike[str] | None = None) -> Path:
    override = os.environ.get("RUBY_MOOD_STATE_PATH")
    return Path(path or override or _DEFAULT_PATH)


def write_mood_state(
    state: str,
    emotion: str = "neutral",
    *,
    path: str | os.PathLike[str] | None = None,
    timestamp: float | None = None,
) -> bool:
    """Atomically publish only the assistant's bounded operational/emotion state."""
    normalized_state = str(state).strip().casefold()
    normalized_emotion = str(emotion).strip().casefold()
    if normalized_state not in _STATES:
        normalized_state = "idle"
    if normalized_emotion not in _EMOTIONS:
        normalized_emotion = "neutral"

    destination = _state_path(path)
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state": normalized_state,
            "emotion": normalized_emotion,
            "timestamp": float(time.time() if timestamp is None else timestamp),
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        return True
    except (OSError, TypeError, ValueError):
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def read_mood_state(
    *,
    path: str | os.PathLike[str] | None = None,
    max_age_seconds: float = 15.0,
    now: float | None = None,
) -> dict[str, Any] | None:
    """Read a fresh, validated state snapshot; stale or malformed data is ignored."""
    if max_age_seconds <= 0:
        return None
    try:
        payload = json.loads(_state_path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        state = str(payload.get("state", "")).strip().casefold()
        emotion = str(payload.get("emotion", "neutral")).strip().casefold()
        timestamp = float(payload["timestamp"])
        age = (time.time() if now is None else float(now)) - timestamp
        if state not in _STATES or emotion not in _EMOTIONS:
            return None
        if age < -2 or age > max_age_seconds:
            return None
        return {"state": state, "emotion": emotion, "timestamp": timestamp}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
