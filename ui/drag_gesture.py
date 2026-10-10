"""Small, deterministic helpers for distinguishing orb clicks from drags."""

from PyQt6.QtCore import QPoint


def drag_threshold_exceeded(press_pos: QPoint, current_pos: QPoint, threshold: int) -> bool:
    """Return whether pointer movement should count as a drag, not a click."""
    return (current_pos - press_pos).manhattanLength() >= max(1, threshold)
