"""Persistent conversation panel with an always-available chat input."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QGraphicsDropShadowEffect,
    QPushButton, QHBoxLayout, QLineEdit
)


class ResponsePopup(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(410, 560)

        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet("""
            #card { background-color: rgba(22, 23, 30, 245); border-radius: 18px; border: 1px solid rgba(255,255,255,28); }
            QLabel#title { color: #f4f4fb; padding: 12px 14px 4px; }
            QLabel#subtitle { color: #858899; padding: 0 14px 10px; }
            QPushButton { color: #999baa; background: transparent; border: none; font-size: 16px; }
            QPushButton:hover { color: white; }
            QTextEdit#history { color: #f1f1f6; background: transparent; border: none; padding: 8px 12px; }
            QLineEdit#input { color: #ffffff; background: #25283a; border: 1px solid #454b69; border-radius: 12px; padding: 10px 12px; }
            QLineEdit#input:focus { border: 1px solid #6857ff; }
            QPushButton#send { color: #ffffff; background: #6857ff; border: none; border-radius: 11px; padding: 9px 13px; font-weight: 600; }
            QPushButton#send:hover { background: #7969ff; }
        """)

        title = QLabel("🤖  AI Screen Assistant")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        subtitle = QLabel("Conversation history")
        subtitle.setObjectName("subtitle")
        subtitle.setFont(QFont("Segoe UI", 8))

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.hide)
        clear_btn = QPushButton("⌫")
        clear_btn.setFixedSize(28, 28)
        clear_btn.setToolTip("Clear conversation")
        clear_btn.clicked.connect(self.clear_history)

        top = QHBoxLayout()
        labels = QVBoxLayout(); labels.setSpacing(0)
        labels.addWidget(title); labels.addWidget(subtitle)
        top.addLayout(labels); top.addStretch(); top.addWidget(clear_btn); top.addWidget(close_btn)
        top.setContentsMargins(8, 5, 8, 0)

        self.history = QTextEdit()
        self.history.setObjectName("history")
        self.history.setReadOnly(True)
        self.history.setFont(QFont("Segoe UI", 10))
        self.history.setPlaceholderText("Your conversation will appear here…")

        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("input")
        self.input_edit.setPlaceholderText("Type a message…")
        self.input_edit.setClearButtonEnabled(True)
        self.input_edit.returnPressed.connect(self._submit)

        send = QPushButton("➤")
        send.setObjectName("send")
        send.setFixedWidth(48)
        send.setToolTip("Send")
        send.clicked.connect(self._submit)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(10, 4, 10, 4)
        input_row.setSpacing(7)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(send)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.addLayout(top)
        lay.addWidget(self.history, 1)
        lay.addLayout(input_row)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.addWidget(card)

        shadow = QGraphicsDropShadowEffect(self); shadow.setBlurRadius(30); shadow.setColor(QColor(0,0,0,190)); shadow.setOffset(0,8); self.setGraphicsEffect(shadow)

    def _append(self, speaker: str, text: str) -> None:
        if not text.strip(): return
        label = "You" if speaker == "user" else "🤖 Assistant"
        safe = (text.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(chr(10), "<br>"))
        self.history.append(f'<p style="margin:8px 0 3px; color:#8f91a3; font-size:9pt;"><b>{label}</b></p><p style="margin:0 0 10px; color:#f1f1f6;">{safe}</p>')
        self.history.verticalScrollBar().setValue(self.history.verticalScrollBar().maximum())

    def add_user_message(self, text: str, near: QPoint) -> None:
        self._append("user", text)
        self._position(near)

    def show_response(self, text: str, near: QPoint, auto_ms: int = 0) -> None:
        self._append("assistant", text)
        self._position(near)

    def show_chat(self, near: QPoint) -> None:
        self._position(near)
        self.raise_()
        self.activateWindow()
        self.input_edit.setFocus()

    def _position(self, near: QPoint) -> None:
        x = max(12, near.x() - self.width() - 12)
        y = max(12, near.y() + 10)
        self.move(x, y); self.show(); self.raise_()

    def _submit(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.input_edit.setFocus()
        self.submitted.emit(text)

    def clear_history(self) -> None:
        self.history.clear()

    def hide_popup(self) -> None:
        self.hide()
