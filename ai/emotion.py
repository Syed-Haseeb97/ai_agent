"""Parse and validate the emotion metadata returned with Ruby's AI responses."""
from __future__ import annotations

import json
import re

EMOTIONS = frozenset({
    "neutral",
    "happy",
    "excited",
    "sad",
    "empathetic",
    "curious",
    "surprised",
})

# The model can misread ordinary disclosures of distress as Sad or Neutral.
# These patterns are intentionally limited to first-person/support contexts so
# negative words in unrelated questions do not automatically change the mood.
_SUPPORT_PATTERNS = (
    r"\bi (?:am|'m|feel|am feeling) (?:having )?(?:a )?(?:really )?(?:bad|rough|hard|terrible|awful|tough) day\b",
    r"\bi(?:'m| am) (?:feeling )?(?:sad|upset|down|lonely|overwhelmed|stressed|anxious|hurt|heartbroken|exhausted)\b",
    r"\bi feel (?:like a failure|disappointed in myself|hopeless|alone|overwhelmed|stressed|anxious|hurt|sad|down)\b",
    r"\bi(?:'m| am) struggling\b",
    r"\bi need (?:some )?(?:support|comfort|someone to talk to)\b",
    r"\bi(?:'ve| have) had (?:a )?(?:really )?(?:bad|rough|hard|terrible|awful|tough) day\b",
    r"\bthings have been (?:really )?(?:hard|rough|difficult) for me\b",
)


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


def infer_support_emotion(user_text: str) -> str | None:
    """Return empathetic for clear first-person distress, otherwise defer to the model."""
    text = re.sub(r"\s+", " ", (user_text or "").strip().casefold())
    if text and any(re.search(pattern, text) for pattern in _SUPPORT_PATTERNS):
        return "empathetic"
    return None


def parse_emotion_response(raw_text: str, user_text: str = "") -> tuple[str, str]:
    """Parse Gemini's JSON into (answer, emotion), prioritizing clear distress cues.

    Plain-text model replies remain usable and default to neutral if JSON formatting
    is unavailable or malformed. Clear first-person distress in the user's message
    overrides an unreliable model emotion label, without altering the answer text.
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
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(candidate[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                return raw_text, infer_support_emotion(user_text) or "neutral"
        else:
            return raw_text, infer_support_emotion(user_text) or "neutral"

    if not isinstance(payload, dict):
        return raw_text, infer_support_emotion(user_text) or "neutral"

    answer = payload.get("response", payload.get("answer", payload.get("text", "")))
    emotion = normalize_emotion(payload.get("emotion", "neutral"))
    if not isinstance(answer, str) or not answer.strip():
        return raw_text, infer_support_emotion(user_text) or "neutral"
    emotion = infer_support_emotion(user_text) or emotion
    return answer.strip(), emotion
