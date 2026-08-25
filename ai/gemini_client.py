"""Gemini vision client for the desktop assistant."""

from __future__ import annotations

import os
from typing import Optional

try:
    import google.generativeai as genai  # type: ignore[import-not-found]
except ImportError:
    genai = None

from dotenv import load_dotenv
load_dotenv()

SYSTEM_PROMPT = """You are a helpful desktop AI assistant that can see the user's current screen through a screenshot.
- Understand the user's request first, then answer it directly.
- Use the screenshot when it is relevant; do not invent details that are not visible.
- Give enough useful information to fully answer the question. Do not artificially limit answers to a fixed sentence count.
- For simple questions, be concise. For troubleshooting, explanations, comparisons, or multi-step requests, give clear detail and numbered steps when useful.
- Prefer practical, actionable answers over generic advice.
- If something is unclear or unreadable on the screen, say exactly what is unclear.
- Never claim that you performed a Windows action unless the local action executor actually performed it.
- Be friendly and direct."""


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY is missing. Copy .env.example to .env and add your free key from https://aistudio.google.com")
        if genai is None:
            raise RuntimeError("google-generativeai is not installed")
        genai.configure(api_key=key)
        model_candidates = ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
        self.model = None
        last_error = None
        for name in model_candidates:
            try:
                self.model = genai.GenerativeModel(model_name=name, system_instruction=SYSTEM_PROMPT)
                break
            except Exception as e:
                last_error = e
        if self.model is None:
            raise RuntimeError(f"Could not initialize any Gemini flash model. Last error: {last_error}")

    def ask_with_screenshot(self, jpeg_bytes: bytes, user_text: str) -> str:
        if not user_text or not user_text.strip():
            user_text = "What is currently on my screen? Give a useful summary."
        image_part = {"mime_type": "image/jpeg", "data": jpeg_bytes}
        prompt = f"User said: {user_text.strip()}"
        try:
            response = self.model.generate_content(
                [image_part, prompt],
                generation_config={"temperature": 0.4, "max_output_tokens": 900},
            )
            if response and response.text:
                return response.text.strip()
            return "I received an empty reply from the model. Please try again."
        except Exception as e:
            return f"Sorry, I hit an error talking to Gemini: {str(e)[:180]}"
