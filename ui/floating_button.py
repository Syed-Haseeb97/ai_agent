"""
Circular always-on-top floating button that owns the full interaction pipeline.
States: idle → listening → thinking → speaking → error
"""

from __future__ import annotations

import threading
from enum import Enum, auto

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QRadialGradient,
    QPainterPath,
    QFont,
)
from PyQt6.QtWidgets import QWidget, QSystemTrayIcon, QMenu, QApplication

from ui.status_popup import StatusPopup
from ui.response_popup import ResponsePopup
from voice.listener import VoiceListener
from voice.tts import TTS
from vision.capture import capture_primary_screen
from ai.gemini_client import GeminiClient


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()


class FloatingButton(QWidget):
    # Signals to talk safely from background thread → UI thread
    sig_status = pyqtSignal(str)
    sig_response = pyqtSignal(str)
    sig_state = pyqtSignal(object)  # State
    sig_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(68, 68)

        self.state = State.IDLE
        self._drag_pos: QPoint | None = None
        self._busy = False

        # Position top-right with small margin
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 90, 40)

        self.status_popup = StatusPopup()
        self.response_popup = ResponsePopup()

        self.sig_status.connect(self._on_status)
        self.sig_response.connect(self._on_response)
        self.sig_state.connect(self._on_state)
        self.sig_error.connect(self._on_error)

        # Breathing animation for idle
        self._breath = 0.0
        self._breath_dir = 1
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(40)

        self._init_tray()

        # Lazy init of heavy objects
        self._listener: VoiceListener | None = None
        self._tts: TTS | None = None
        self._gemini: GeminiClient | None = None

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        # Simple generated icon would be nicer; for MVP we use text fallback
        self.tray.setToolTip("AI Screen Assistant")
        menu = QMenu()
        menu.addAction("Ask (same as click)", self.trigger)
        menu.addAction("Show / Hide button", self._toggle_visible)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _toggle_visible(self):
        self.setVisible(not self.isVisible())

    # ── Painting ──────────────────────────────────────────────
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = {
            State.IDLE: (QColor(40, 40, 48), QColor(90, 90, 110)),
            State.LISTENING: (QColor(20, 90, 50), QColor(40, 200, 100)),
            State.THINKING: (QColor(20, 50, 100), QColor(60, 130, 255)),
            State.SPEAKING: (QColor(70, 30, 100), QColor(180, 90, 255)),
            State.ERROR: (QColor(100, 20, 20), QColor(220, 60, 60)),
        }
        base, accent = colors.get(self.state, colors[State.IDLE])

        # Soft outer glow
        glow_alpha = int(50 + 40 * abs(self._breath)) if self.state == State.IDLE else 90
        glow = QRadialGradient(34, 34, 36)
        glow.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), 0))
        glow.setColorAt(0.85, QColor(accent.red(), accent.green(), accent.blue(), glow_alpha))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 68, 68)

        # Main circle
        grad = QRadialGradient(24, 22, 40)
        grad.setColorAt(0, accent.lighter(130))
        grad.setColorAt(1, base)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.5))
        p.drawEllipse(6, 6, 56, 56)

        # Center label
        p.setPen(QColor(255, 255, 255, 230))
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(QRectF(6, 6, 56, 56), Qt.AlignmentFlag.AlignCenter, "AI")

    def _animate(self):
        if self.state == State.IDLE:
            self._breath += 0.04 * self._breath_dir
            if self._breath > 1.0:
                self._breath = 1.0
                self._breath_dir = -1
            elif self._breath < 0.0:
                self._breath = 0.0
                self._breath_dir = 1
            self.update()

    # ── Mouse ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # If the mouse barely moved, treat as click
            if self._drag_pos is not None:
                delta = (event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos)
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    self.trigger()
            self._drag_pos = None
            event.accept()

    # ── Public trigger (also called by hotkey) ────────────────
    def trigger(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self):
        try:
            # 1. Listen
            self.sig_state.emit(State.LISTENING)
            self.sig_status.emit("Listening…")
            if self._listener is None:
                self._listener = VoiceListener()
            user_text = self._listener.listen()

            if not user_text:
                self.sig_error.emit("I didn’t catch that. Try again?")
                return

            # 2. Capture screen
            self.sig_state.emit(State.THINKING)
            self.sig_status.emit("Thinking…")
            jpeg_bytes, _ = capture_primary_screen()

            # 3. Gemini
            if self._gemini is None:
                self._gemini = GeminiClient()
            answer = self._gemini.ask_with_screenshot(jpeg_bytes, user_text)

            # 4. Show + speak
            self.sig_response.emit(answer)
            self.sig_state.emit(State.SPEAKING)
            self.sig_status.emit("Speaking…")
            if self._tts is None:
                self._tts = TTS()
            self._tts.speak(answer)

        except Exception as e:
            self.sig_error.emit(str(e)[:200])
        finally:
            self.sig_state.emit(State.IDLE)
            self._busy = False

    # ── Signal handlers (UI thread) ───────────────────────────
    def _on_state(self, state: State):
        self.state = state
        self.update()

    def _on_status(self, text: str):
        self.status_popup.show_message(text, self.pos())

    def _on_response(self, text: str):
        self.status_popup.hide_popup()
        self.response_popup.show_response(text, self.pos())

    def _on_error(self, text: str):
        self.status_popup.hide_popup()
        self.sig_state.emit(State.ERROR)
        self.response_popup.show_response(f"⚠️ {text}", self.pos(), auto_ms=8000)
        # Return to idle after a short moment
        QTimer.singleShot(2500, lambda: self.sig_state.emit(State.IDLE))
