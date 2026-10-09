"""Parse and validate the emotion metadata returned with Ruby's AI responses."""
from __future__ import annotations

import json

EMOTIONS = frozenset({
    "neutral",
    "happy",
    "excited",
    "sad",
    "empathetic",
    "curious",
    "surprised",
})


def normalize_emotion(value: object) -> str:
    """Return a supported lower-case emotion label, falling back safely to neutral."""
    if not isinstance(value, str):
        return "neutral"
    label = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "joyful": "happy",
        "enthusiastic": "excited",
        "sympathetic": "empathetic",
        "interested": "curious",
        "astonished": "surprised",
        "none": "neutral",
        "calm": "neutral",
    }
    label = aliases.get(label, label)
    return label if label in EMOTIONS else "neutral"


def parse_emotion_response(raw_text: str) -> tuple[str, str]:
    """Parse Gemini's JSON response into (user-facing answer, validated emotion).

    Plain-text model replies remain usable and default to neutral if JSON formatting
    is unavailable or malformed.
    """
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return "I received an empty reply from the model. Please try again.", "neutral"

    candidate = raw_text
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        # Some model versions may add a short preamble around the JSON object.
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(candidate[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                return raw_text, "neutral"
        else:
            return raw_text, "neutral"

    if not isinstance(payload, dict):
        return raw_text, "neutral"

    answer = payload.get("response", payload.get("answer", payload.get("text", "")))
    emotion = normalize_emotion(payload.get("emotion", "neutral"))
    if not isinstance(answer, str) or not answer.strip():
        return raw_text, "neutral"
    return answer.strip(), emotion
