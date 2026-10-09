"""A tiny, polished live-state companion pill for Ruby's liquid orb."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QHBoxLayout, QVBoxLayout


class StatusPopup(QWidget):
    """Non-activating status capsule that communicates state without shouting."""

    _STATES = (
        ("listen", "LISTENING", "I'm all ears", "#67e8f9", "◉"),
        ("think", "THINKING", "Putting it together", "#c4b5fd", "✧"),
        ("process", "THINKING", "Putting it together", "#c4b5fd", "✧"),
        ("speak", "SPEAKING", "Tap Ruby to interrupt", "#93c5fd", "♫"),
        ("error", "NEEDS ATTENTION", "Something went wrong", "#fda4af", "!"),
        ("⚠", "NEEDS ATTENTION", "Something went wrong", "#fda4af", "!"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rubyStatus")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(258, 66)

        self._accent = "#a78bfa"
        self._dot_frame = 0
        self.icon = QLabel("✦")
        self.icon.setObjectName("stateIcon")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setFixedSize(38, 38)
        self.icon.setFont(QFont("Segoe UI Symbol", 16, QFont.Weight.DemiBold))

        self.eyebrow = QLabel("R U B Y  ·  READY")
        self.eyebrow.setObjectName("eyebrow")
        self.eyebrow.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))

        self.detail = QLabel("Standing by")
        self.detail.setObjectName("detail")
        self.detail.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.activity = QLabel("")
        self.activity.setObjectName("activity")
        self.activity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.activity.setFixedWidth(24)
        self.activity.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        copy.addWidget(self.eyebrow)
        copy.addWidget(self.detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 9, 12, 9)
        layout.setSpacing(10)
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(copy, 1)
        layout.addWidget(self.activity, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet("""
            QWidget#rubyStatus {
                background: rgba(16, 18, 29, 248);
                border: 1px solid rgba(167, 139, 250, 105);
                border-radius: 19px;
            }
            QLabel { background: transparent; border: none; }
            QLabel#stateIcon {
                color: #c4b5fd;
                background: rgba(167, 139, 250, 22);
                border: 1px solid rgba(167, 139, 250, 75);
                border-radius: 13px;
            }
            QLabel#eyebrow {
                color: #b7b4d1;
                letter-spacing: 1.2px;
            }
            QLabel#detail {
                color: #f4f2ff;
            }
            QLabel#activity {
                color: #c4b5fd;
            }
        """)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_popup)

        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(360)
        self._activity_timer.timeout.connect(self._advance_activity)

    def _advance_activity(self):
        self._dot_frame = (self._dot_frame + 1) % 4
        self.activity.setText("·" * self._dot_frame if self._dot_frame else "•")

    def _set_state_look(self, text: str):
        lowered = text.casefold()
        state = next((item for item in self._STATES if item[0] in lowered), None)
        if state:
            _, title, detail, accent, glyph = state
            if "error" in lowered or "⚠" in text:
                detail = text.strip()[:64] if len(text.strip()) > 2 else detail
        else:
            title, detail, accent, glyph = "RUBY · READY", "Standing by", "#a5f3d0", "✦"

        self._accent = accent
        self.icon.setText(glyph)
        self.eyebrow.setText(f"R U B Y  ·  {title}")
        self.detail.setText(detail)
        self.activity.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        self.icon.setStyleSheet(
            f"color: {accent}; background: rgba(167, 139, 250, 22); "
            f"border: 1px solid {accent}; border-radius: 13px;"
        )
        self.eyebrow.setStyleSheet(f"color: {accent}; background: transparent; border: none;")

    def show_message(self, text: str, near: QPoint, duration_ms: int = 0):
        if not text or not text.strip():
            self.hide_popup()
            return

        self._hide_timer.stop()
        self._set_state_look(text)
        lowered = text.casefold()
        if any(word in lowered for word in ("listen", "think", "process", "speak")):
            self._activity_timer.start()
        else:
            self._activity_timer.stop()
            self.activity.setText("!")

        screen = QApplication.screenAt(near) or QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()
        margin = 10
        x = near.x() - self.width() - 14
        if x < bounds.left() + margin:
            x = near.x() + 92
        x = min(max(bounds.left() + margin, x), bounds.right() - self.width() - margin)
        y = min(max(bounds.top() + margin, near.y() + 82), bounds.bottom() - self.height() - margin)
        self.move(x, y)
        self.show()
        self.raise_()
        if duration_ms > 0:
            self._hide_timer.start(duration_ms)

    def hide_popup(self):
        self._hide_timer.stop()
        self._activity_timer.stop()
        self.hide()
