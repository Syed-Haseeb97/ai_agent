"""
Small non-modal status popup that appears near the floating button.
Shows "Listening…", "Thinking…", etc.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor


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

        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                background-color: rgba(30, 30, 35, 220);
                border-radius: 12px;
                padding: 8px 16px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text: str, near: QPoint, duration_ms: int = 0):
        self.label.setText(text)
        self.adjustSize()
        # Position just below-left of the button
        x = near.x() - self.width() + 20
        y = near.y() + 70
        self.move(max(8, x), y)
        self.show()
        self.raise_()
        if duration_ms > 0:
            self._hide_timer.start(duration_ms)

    def hide_popup(self):
        self._hide_timer.stop()
        self.hide()
