"""
Clean response card that shows Gemini's answer and auto-dismisses.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QGraphicsDropShadowEffect,
    QPushButton,
    QHBoxLayout,
)


class ResponsePopup(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setFixedWidth(340)

        container = QWidget()
        container.setObjectName("card")
        container.setStyleSheet(
            """
            #card {
                background-color: rgba(28, 28, 32, 235);
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 25);
            }
            """
        )

        title = QLabel("AI Assistant")
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        title.setStyleSheet("color: #a0a0b0; padding: 10px 14px 0 14px;")

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Segoe UI", 10))
        self.text.setStyleSheet(
            """
            QTextEdit {
                color: #f0f0f5;
                background: transparent;
                border: none;
                padding: 4px 12px 8px 12px;
            }
            """
        )
        self.text.setMaximumHeight(220)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            """
            QPushButton {
                color: #888;
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover { color: #fff; }
            """
        )
        close_btn.clicked.connect(self.hide)

        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch()
        top.addWidget(close_btn)
        top.setContentsMargins(4, 4, 8, 0)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.addLayout(top)
        lay.addWidget(self.text)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_response(self, text: str, near: QPoint, auto_ms: int = 18000):
        self.text.setPlainText(text)
        self.adjustSize()
        # Place to the left of the button so it stays on-screen
        x = max(12, near.x() - self.width() - 12)
        y = max(12, near.y() - 20)
        self.move(x, y)
        self.show()
        self.raise_()
        self._hide_timer.start(auto_ms)

    def hide_popup(self):
        self._hide_timer.stop()
        self.hide()
