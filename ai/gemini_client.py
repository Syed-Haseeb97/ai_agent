"""
Gemini client – free tier, vision-capable.
Uses gemini-1.5-flash (or the latest flash model available on free tier).
"""

from __future__ import annotations

import os
from typing import Optional

try:
    import google.generativeai as genai  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled at runtime
    genai = None

from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """You are a helpful, concise desktop AI assistant that can see the user’s current screen via the provided screenshot and can hear the user’s voice command.
- First understand what is visible on the screen.
- Answer the user’s spoken request helpfully and practically.
- If the request requires up-to-date information or web knowledge, use your knowledge and reasoning.
- Keep answers short (2–6 sentences) unless the user clearly asks for more detail.
- If you cannot see something clearly on the screenshot, say so politely.
- Be friendly and direct."""


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is missing. Copy .env.example to .env and add your free key from https://aistudio.google.com"
            )
        genai.configure(api_key=key)

        # Prefer the latest flash model that supports vision on free tier.
        # Fallbacks keep the MVP working if model names change.
        model_candidates = [
                     "gemini-3.5-flash-lite",   # fastest free model right now
                     "gemini-3.6-flash",
                     "gemini-3.5-flash",
                     "gemini-flash-latest",
        ]
        self.model = None
        last_error = None
        for name in model_candidates:
            try:
                self.model = genai.GenerativeModel(
                    model_name=name,
                    system_instruction=SYSTEM_PROMPT,
                )
                # quick sanity check
                break
            except Exception as e:
                last_error = e
                continue
        if self.model is None:
            raise RuntimeError(f"Could not initialize any Gemini flash model. Last error: {last_error}")

    def ask_with_screenshot(
        self,
        jpeg_bytes: bytes,
        user_text: str,
    ) -> str:
        """
        Send screenshot + user speech transcript to Gemini and return the text reply.
        """
        if not user_text or not user_text.strip():
            user_text = "What is currently on my screen? Give a short helpful summary."

        image_part = {
            "mime_type": "image/jpeg",
            "data": jpeg_bytes,
        }

        prompt = f"User said: {user_text.strip()}"

        try:
            response = self.model.generate_content(
                [image_part, prompt],
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 512,
                },
            )
            if response and response.text:
                return response.text.strip()
            return "I received an empty reply from the model. Please try again."
        except Exception as e:
            return f"Sorry, I hit an error talking to Gemini: {str(e)[:180]}"
