"""Compact keyboard-input popup for the assistant."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout


class InputPopup(QFrame):
    submitted = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedWidth(360)
        self.setStyleSheet(
            "QFrame { background: #171923; border: 1px solid #555b78; border-radius: 14px; }"
            "QLabel { color: #f5f7ff; }"
            "QLineEdit { color: #ffffff; background: #25283a; border: 1px solid #454b69; border-radius: 9px; padding: 9px; }"
            "QPushButton { color: #ffffff; background: #6857ff; border: 0; border-radius: 9px; padding: 9px 13px; }"
            "QPushButton:hover { background: #7969ff; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(9)

        title = QLabel("🤖  Type a question")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(7)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Ask about your screen or tell me what to do…")
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self._submit)
        row.addWidget(self.edit, 1)

        send = QPushButton("Send")
        send.clicked.connect(self._submit)
        row.addWidget(send)
        layout.addLayout(row)

        hint = QLabel("Enter to send  •  Esc to cancel")
        hint.setStyleSheet("color: #9da3bd; font-size: 11px; border: 0;")
        layout.addWidget(hint)

    def open_near(self, button_pos):
        self.adjustSize()
        x = button_pos.x() - self.width() + 78
        y = button_pos.y() + 86
        self.move(max(8, x), max(8, y))
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()

    def _submit(self):
        text = self.edit.text().strip()
        if not text:
            return
        # Keep the input surface open so it can be reused for the next question.
        self.edit.clear()
        self.submitted.emit(text)
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)
