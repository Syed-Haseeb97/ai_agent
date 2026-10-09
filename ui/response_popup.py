"""Polished, orb-matched conversation surface for Ruby."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
)

from ui.liquid_blob import LiquidBlob, Mood


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
        # This must be an activating window for focus-out dismissal to work.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setMinimumSize(0, 0)
        self.setFixedSize(456, 570)
        self._dismiss_on_deactivate = False

        self.setStyleSheet("""
            QWidget#card {
                background: #11131d;
                border: 1px solid rgba(167, 139, 250, 75);
                border-radius: 24px;
            }
            QLabel { background: transparent; border: none; }
            QLabel#eyebrow {
                color: #9b9db5;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.7px;
            }
            QLabel#title {
                color: #f7f6ff;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#subtitle {
                color: #999bb3;
                font-size: 10px;
            }
            QLabel#online {
                color: #a5f3d0;
                background: rgba(52, 211, 153, 18);
                border: 1px solid rgba(52, 211, 153, 50);
                border-radius: 9px;
                padding: 5px 8px;
                font-size: 9px;
                font-weight: 600;
            }
            QPushButton#iconButton {
                color: #aeb0c7;
                background: rgba(255,255,255,5);
                border: 1px solid rgba(255,255,255,14);
                border-radius: 11px;
                font-size: 17px;
                font-weight: 500;
            }
            QPushButton#iconButton:hover {
                color: #ffffff;
                background: rgba(139, 124, 255, 20);
                border-color: rgba(167, 139, 250, 90);
            }
            QTextEdit#history {
                color: #eff0fb;
                background: transparent;
                border: none;
                padding: 8px 18px;
                selection-background-color: #6554d9;
                font-size: 10pt;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 4px 3px 4px 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(170, 164, 220, 75);
                border-radius: 3px;
                min-height: 26px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(170, 164, 220, 130);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QLineEdit#input {
                color: #f7f7ff;
                background: #1a1c2a;
                border: 1px solid #34364d;
                border-radius: 16px;
                padding: 13px 15px;
                selection-background-color: #6554d9;
                font-size: 10pt;
            }
            QLineEdit#input:focus {
                background: #1d1f30;
                border: 1px solid #8b7cff;
            }
            QPushButton#send {
                color: #ffffff;
                background: #7868ff;
                border: 1px solid rgba(210, 204, 255, 75);
                border-radius: 15px;
                font-size: 21px;
                font-weight: 700;
            }
            QPushButton#send:hover {
                background: #8b7cff;
                border-color: rgba(230, 226, 255, 130);
            }
            QPushButton#send:pressed { background: #5d4bd7; }
        """)

        card = QWidget(self)
        card.setObjectName("card")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.orb = LiquidBlob(card)
        self.orb.setMinimumSize(0, 0)
        self.orb.setFixedSize(38, 38)
        self.orb.set_mood(Mood.IDLE)
        self.orb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(2)

        eyebrow = QLabel("YOUR DESKTOP COMPANION")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Ruby")
        title.setObjectName("title")
        subtitle = QLabel("A little help, right when you need it")
        subtitle.setObjectName("subtitle")
        brand_text.addWidget(eyebrow)
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(12)
        brand_row.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignVCenter)
        brand_row.addLayout(brand_text, 1)

        self.status_badge = QLabel("●  READY")
        self.status_badge.setObjectName("online")
        brand_row.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self.clear_button = QPushButton("⌫")
        self.clear_button.setObjectName("iconButton")
        self.clear_button.setFixedSize(36, 36)
        self.clear_button.setToolTip("Clear conversation")
        self.clear_button.setAccessibleName("Clear conversation")
        self.clear_button.clicked.connect(self.clear_history)

        self.close_button = QPushButton("×")
        self.close_button.setObjectName("iconButton")
        self.close_button.setFixedSize(36, 36)
        self.close_button.setToolTip("Close chat")
        self.close_button.setAccessibleName("Close chat")
        self.close_button.clicked.connect(self.hide_popup)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(7)
        actions.addWidget(self.clear_button)
        actions.addWidget(self.close_button)

        header = QHBoxLayout()
        header.setContentsMargins(20, 18, 16, 17)
        header.setSpacing(12)
        header.addLayout(brand_row, 1)
        header.addLayout(actions)

        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background: rgba(196, 181, 253, 24); border: none;")

        self.history = QTextEdit()
        self.history.setObjectName("history")
        self.history.setReadOnly(True)
        self.history.setAcceptRichText(False)
        self.history.setFont(QFont("Segoe UI", 10))
        self.history.setFrameShape(QTextEdit.Shape.NoFrame)
        self.history.setPlaceholderText(
            "Hey, I'm Ruby.\n\nAsk me about what's on your screen, "
            "or type a question below."
        )

        input_label = QLabel("MESSAGE")
        input_label.setStyleSheet(
            "color: #888ba6; font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
        )
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("input")
        self.input_edit.setPlaceholderText("Message Ruby…")
        self.input_edit.setClearButtonEnabled(False)
        self.input_edit.setMaxLength(8000)
        self.input_edit.returnPressed.connect(self._submit)

        send = QPushButton("↑")
        send.setObjectName("send")
        send.setFixedSize(48, 48)
        send.setToolTip("Send message")
        send.setAccessibleName("Send message")
        send.clicked.connect(self._submit)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(9)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(send)

        footer = QVBoxLayout()
        footer.setContentsMargins(18, 12, 18, 17)
        footer.setSpacing(9)
        footer.addWidget(input_label)
        footer.addLayout(input_row)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(separator)
        layout.addWidget(self.history, 1)
        layout.addLayout(footer)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(card)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def set_status(self, text: str = "") -> None:
        """Keep the chat header synchronized with Ruby's live interaction state."""
        lowered = (text or "").casefold()
        if "listen" in lowered:
            label, accent, tint = "LISTENING", "#67e8f9", "rgba(34, 211, 238, 18)"
        elif "think" in lowered or "process" in lowered:
            label, accent, tint = "THINKING", "#c4b5fd", "rgba(167, 139, 250, 18)"
        elif "speak" in lowered:
            label, accent, tint = "SPEAKING", "#93c5fd", "rgba(96, 165, 250, 18)"
        elif "error" in lowered or "⚠" in lowered:
            label, accent, tint = "ATTENTION", "#fda4af", "rgba(251, 113, 133, 18)"
        else:
            label, accent, tint = "READY", "#a5f3d0", "rgba(52, 211, 153, 18)"
        self.status_badge.setText(f"●  {label}")
        self.status_badge.setStyleSheet(
            f"color: {accent}; background: {tint}; border: 1px solid rgba(167, 139, 250, 85); "
            "border-radius: 9px; padding: 5px 8px; font-size: 9px; font-weight: 600;"
        )

    def _append(self, speaker: str, text: str) -> None:
        text = text.strip()
        if not text:
            return

        cursor = self.history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.history.document().isEmpty():
            cursor.insertBlock()

        safe = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
            .replace("\n", "<br/>")
        )

        if speaker == "user":
            html = (
                '<table width="100%" cellspacing="0" cellpadding="0"><tr><td '
                'align="right"><table cellspacing="0" cellpadding="0"><tr><td '
                'bgcolor="#5144a8" style="padding:11px 14px; color:#ffffff;">'
                f'{safe}</td></tr></table></td></tr></table>'
                '<p style="margin:3px 2px 13px; color:#999bb8; text-align:right; '
                'font-size:8pt;">YOU</p>'
            )
        else:
            html = (
                '<p style="margin:7px 2px 5px; color:#b9aaff; '
                'font-size:8pt; font-weight:700; letter-spacing:1px;">RUBY</p>'
                '<table width="100%" cellspacing="0" cellpadding="0"><tr><td '
                'bgcolor="#1c1f2d" style="padding:12px 14px; color:#f0f0fa;">'
                f'{safe}</td></tr></table>'
                '<p style="margin:0 0 13px; color:#747991; font-size:3pt;"> </p>'
            )

        cursor.insertHtml(html)
        self.history.setTextCursor(cursor)
        bar = self.history.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_user_message(self, text: str, near: QPoint) -> None:
        self._append("user", text)
        self._position(near, activate=False)

    def show_response(self, text: str, near: QPoint, auto_ms: int = 0) -> None:
        self._append("assistant", text)
        self._position(near, activate=False)

    def show_chat(self, near: QPoint) -> None:
        self._dismiss_on_deactivate = True
        self._position(near, activate=True)
        self.input_edit.setFocus(Qt.FocusReason.PopupFocusReason)

    def _position(self, near: QPoint, activate: bool = False) -> None:
        self.adjustSize()
        screen = QApplication.screenAt(near) or QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()
        margin = 12
        left = near.x() - self.width() - 14
        if left < bounds.left() + margin:
            left = near.x() + 78 + 14
        x = min(max(bounds.left() + margin, left), bounds.right() - self.width() - margin)
        y = min(max(bounds.top() + margin, near.y() - 8), bounds.bottom() - self.height() - margin)
        self.move(x, y)
        self.show()
        self.raise_()
        if activate:
            self.activateWindow()

    def _submit(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.submitted.emit(text)
        # Keep the conversation open after sending so the reply is readable.
        self._dismiss_on_deactivate = True
        self.input_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, watched, event):
        if not self.isVisible() or not self._dismiss_on_deactivate:
            return False
        if event.type() == QEvent.Type.MouseButtonPress:
            target = watched
            if isinstance(target, QWidget) and (target is self or self.isAncestorOf(target)):
                return False
            global_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else None
            if global_pos is not None and not self.frameGeometry().contains(global_pos):
                self.hide_popup()
        return False

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and self._dismiss_on_deactivate
            and self.isVisible()
        ):
            QTimer.singleShot(0, self.hide_popup)

    def clear_history(self) -> None:
        self.history.clear()

    def hide_popup(self) -> None:
        self._dismiss_on_deactivate = False
        self.hide()
