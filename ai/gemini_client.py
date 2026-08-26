"""Gemini vision client for the desktop assistant."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT / "memory.json"
PREFS_FILE = ROOT / "preferences.json"

BASE_PROMPT = """You are Ruby, a helpful desktop AI assistant that can see the user's current screen through a screenshot.
- Understand the user's request first, then answer it directly.
- Use the screenshot when it is relevant; do not invent details that are not visible.
- Give enough useful information to fully answer the question. Do not artificially limit answers to a fixed sentence count.
- For simple questions, be concise. For troubleshooting, explanations, comparisons, or multi-step requests, give clear detail and numbered steps when useful.
- Prefer practical, actionable answers over generic advice.
- If something is unclear or unreadable on the screen, say exactly what is unclear.
- Never claim that you performed a Windows action unless the local action executor actually performed it.
- Be friendly and direct.
"""


def _load_context() -> str:
    parts = [BASE_PROMPT]
    try:
        memories = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if memories:
            parts.append("Useful user memories (only use when relevant):\n" + "\n".join(f"- {m.get('text','')}" for m in memories[-20:]))
    except Exception:
        pass
    try:
        prefs = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
        personality = prefs.get("personality")
        if personality:
            parts.append(f"Preferred response style: {personality}.")
    except Exception:
        pass
    return "\n".join(parts)


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY is missing. Copy .env.example to .env and add your free key from https://aistudio.google.com")
        if genai is None or types is None:
            raise RuntimeError("google-genai is not installed")

        self.client = genai.Client(api_key=key)
        # Use a current stable Flash model rather than legacy/imaginary model names.
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.system_instruction = _load_context()

    def ask_with_screenshot(self, jpeg_bytes: bytes, user_text: str) -> str:
        if not user_text or not user_text.strip():
            user_text = "What is currently on my screen? Give a useful summary."
        prompt = f"User said: {user_text.strip()}"
        try:
            image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            response = self.client.models.generate_content(
                model=self.model,
                contents=[image_part, prompt],
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.4,
                    max_output_tokens=900,
                ),
            )
            if response and getattr(response, "text", None):
                return response.text.strip()
            return "I received an empty reply from the model. Please try again."
        except Exception as e:
            return f"Sorry, I hit an error talking to Gemini: {str(e)[:180]}"
