"""
Screen capture helper using mss + Pillow.
Captures the primary monitor, resizes to max 1280 px width,
and returns JPEG bytes (quality 72) ready for Gemini.
"""

from __future__ import annotations

import io
from typing import Optional, Tuple

import mss
from PIL import Image


def capture_primary_screen(
    max_width: int = 1280,
    jpeg_quality: int = 72,
) -> Tuple[bytes, Tuple[int, int]]:
    """
    Capture the primary monitor and return (jpeg_bytes, (width, height)).
    """
    with mss.mss() as sct:
        # monitors[0] is the virtual combined desktop; [1] is the primary
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)

        # Convert BGRA → RGB
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        # Resize while preserving aspect ratio
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            new_size = (max_width, int(h * ratio))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        return buffer.getvalue(), img.size


def capture_active_window_fallback(
    max_width: int = 1280,
    jpeg_quality: int = 72,
) -> Optional[Tuple[bytes, Tuple[int, int]]]:
    """
    Optional helper – currently just falls back to primary screen.
    Can be extended later with win32gui if needed.
    """
    return capture_primary_screen(max_width, jpeg_quality)
