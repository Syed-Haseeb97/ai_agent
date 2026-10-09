"""Compact glass status pill styled to complement Ruby's liquid orb."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QHBoxLayout


class StatusPopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.dot = QLabel("●")
        self.dot.setObjectName("dot")
        self.dot.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.label = QLabel("")
        self.label.setObjectName("message")
        self.label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.label.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

        self.setStyleSheet("""
            QWidget {
                background: rgba(17, 19, 30, 246);
                border: 1px solid rgba(167, 139, 250, 85);
                border-radius: 14px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QLabel#dot {
                color: #a78bfa;
                padding-left: 1px;
            }
            QLabel#message {
                color: #f4f2ff;
                padding-right: 2px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 13, 8)
        layout.setSpacing(8)
        layout.addWidget(self.dot)
        layout.addWidget(self.label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, near: QPoint, duration_ms: int = 0):
        if not text or not text.strip():
            self.hide_popup()
            return

        self._hide_timer.stop()
        lowered = text.casefold()
        if "listen" in lowered:
            accent = "#67e8f9"
        elif "think" in lowered or "process" in lowered:
            accent = "#c4b5fd"
        elif "speak" in lowered:
            accent = "#93c5fd"
        elif "error" in lowered or "⚠" in text:
            accent = "#fb7185"
        else:
            accent = "#a78bfa"

        self.dot.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        self.label.setText(text)
        self.adjustSize()

        screen = QApplication.screenAt(near) or QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()
        margin = 10
        x = near.x() - self.width() + 28
        y = near.y() + 82
        x = min(max(bounds.left() + margin, x), bounds.right() - self.width() - margin)
        y = min(max(bounds.top() + margin, y), bounds.bottom() - self.height() - margin)
        self.move(x, y)
        self.show()
        self.raise_()
        if duration_ms > 0:
            self._hide_timer.start(duration_ms)

    def hide_popup(self):
        self._hide_timer.stop()
        self.hide()
