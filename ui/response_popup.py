"""Refined glass conversation panel for Ruby, the liquid-blob desktop companion."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QLineEdit
)


class ResponsePopup(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(432, 540)

        card = QWidget()
        card.setObjectName("card")
        card.setStyleSheet("""
            QWidget#card {
                background: rgba(19, 20, 27, 248);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 22px;
            }
            QLabel#eyebrow {
                color: #a5a7ba;
                background: transparent;
                border: none;
                padding: 0;
                letter-spacing: 1px;
            }
            QLabel#title {
                color: #f7f7fc;
                background: transparent;
                border: none;
                padding: 0;
            }
            QLabel#status {
                color: #9295a8;
                background: transparent;
                border: none;
                padding: 0;
            }
            QPushButton#iconButton {
                color: #a3a5b6;
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,13);
                border-radius: 10px;
                font-size: 15px;
            }
            QPushButton#iconButton:hover {
                color: #ffffff;
                background: rgba(255,255,255,12);
                border-color: rgba(255,255,255,28);
            }
            QTextEdit#history {
                color: #e9eaf2;
                background: transparent;
                border: none;
                padding: 8px 4px;
                selection-background-color: #5546c8;
            }
            QLineEdit#input {
                color: #f7f7fc;
                background: rgba(38, 39, 51, 230);
                border: 1px solid rgba(255,255,255,18);
                border-radius: 15px;
                padding: 13px 15px;
                selection-background-color: #6857ff;
            }
            QLineEdit#input:focus {
                background: rgba(42, 42, 58, 245);
                border: 1px solid rgba(139, 124, 255, 170);
            }
            QPushButton#send {
                color: white;
                background: #7464ff;
                border: none;
                border-radius: 14px;
                font-size: 19px;
                font-weight: 600;
            }
            QPushButton#send:hover { background: #8476ff; }
            QPushButton#send:pressed { background: #5c4de0; }
        """)

        eyebrow = QLabel("YOUR AI COMPANION")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))

        title = QLabel("Ruby")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI Variable Display", 17, QFont.Weight.DemiBold))

        subtitle = QLabel("Ready when you are")
        subtitle.setObjectName("status")
        subtitle.setFont(QFont("Segoe UI", 9))

        brand = QVBoxLayout()
        brand.setSpacing(3)
        brand.addWidget(eyebrow)
        brand.addWidget(title)
        brand.addWidget(subtitle)

        close_btn = QPushButton("×")
        close_btn.setObjectName("iconButton")
        close_btn.setFixedSize(34, 34)
        close_btn.setToolTip("Hide Ruby")
        close_btn.clicked.connect(self.hide)

        clear_btn = QPushButton("⌫")
        clear_btn.setObjectName("iconButton")
        clear_btn.setFixedSize(34, 34)
        clear_btn.setToolTip("Clear conversation")
        clear_btn.clicked.connect(self.clear_history)

        top = QHBoxLayout()
        top.setContentsMargins(20, 18, 16, 14)
        top.setSpacing(8)
        top.addLayout(brand)
        top.addStretch()
        top.addWidget(clear_btn)
        top.addWidget(close_btn)

        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background: rgba(255,255,255,13); border: none;")

        self.history = QTextEdit()
        self.history.setObjectName("history")
        self.history.setReadOnly(True)
        self.history.setFont(QFont("Segoe UI", 10))
        self.history.setFrameShape(QTextEdit.Shape.NoFrame)
        self.history.setPlaceholderText(
            "Hey, I'm Ruby.\n\nAsk me about what's on your screen, "
            "or type a question below."
        )

        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("input")
        self.input_edit.setPlaceholderText("Message Ruby…")
        self.input_edit.setClearButtonEnabled(False)
        self.input_edit.returnPressed.connect(self._submit)

        send = QPushButton("↑")
        send.setObjectName("send")
        send.setFixedSize(48, 48)
        send.setToolTip("Send message")
        send.clicked.connect(self._submit)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(16, 12, 16, 16)
        input_row.setSpacing(9)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(send)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(top)
        lay.addWidget(separator)
        lay.addWidget(self.history, 1)
        lay.addLayout(input_row)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

    def _append(self, speaker: str, text: str) -> None:
        if not text.strip():
            return
        label = "YOU" if speaker == "user" else "RUBY"
        safe = (
            text.strip()
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace(chr(10), "<br>")
        )
        label_color = "#aaa0ff" if speaker == "user" else "#a5a7ba"
        self.history.append(
            f'<p style="margin:14px 0 5px; color:{label_color}; '
            f'font-size:8pt; letter-spacing:1px;"><b>{label}</b></p>'
            f'<p style="margin:0 0 12px; color:#f0f0f7; '
            f'font-size:10pt; line-height:1.5;">{safe}</p>'
        )
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

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
        self.move(x, y)
        self.show()
        self.raise_()

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
