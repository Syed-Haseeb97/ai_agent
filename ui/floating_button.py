"""
Animated circular always-on-top AI button and interaction pipeline.
States: idle -> listening -> thinking -> speaking -> error.

Each interaction has a monotonically increasing run id. Old queued UI events
are ignored so an earlier answer can never overwrite the current one.
"""

from __future__ import annotations

import math
import threading
from enum import Enum, auto

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QRadialGradient, QFont
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
    sig_status = pyqtSignal(int, str)
    sig_response = pyqtSignal(int, str)
    sig_state = pyqtSignal(int, object)
    sig_error = pyqtSignal(int, str)
    sig_finished = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(78, 78)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.state = State.IDLE
        self._drag_pos: QPoint | None = None
        self._busy = False
        self._run_id = 0
        self._phase = 0.0
        self._hover = False

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 100, 34)

        self.status_popup = StatusPopup()
        self.response_popup = ResponsePopup()

        self.sig_status.connect(self._on_status)
        self.sig_response.connect(self._on_response)
        self.sig_state.connect(self._on_state)
        self.sig_error.connect(self._on_error)
        self.sig_finished.connect(self._on_finished)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(16)

        self._init_tray()

        self._listener: VoiceListener | None = None
        self._tts: TTS | None = None
        self._gemini: GeminiClient | None = None

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("AI Screen Assistant")
        menu = QMenu()
        menu.addAction("Ask / Interrupt (same as click)", self.trigger)
        menu.addAction("Show / Hide button", self._toggle_visible)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _toggle_visible(self):
        self.setVisible(not self.isVisible())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = cy = 39.0
        pulse = (math.sin(self._phase * 2.0) + 1.0) / 2.0
        palettes = {
            State.IDLE: ((35, 38, 52), (120, 92, 255)),
            State.LISTENING: ((15, 65, 52), (45, 230, 145)),
            State.THINKING: ((20, 45, 85), (70, 150, 255)),
            State.SPEAKING: ((72, 30, 100), (205, 100, 255)),
            State.ERROR: ((100, 22, 28), (255, 75, 90)),
        }
        base_rgb, accent_rgb = palettes[self.state]
        accent = QColor(*accent_rgb)
        base = QColor(*base_rgb)

        aura = 4.0 + pulse * 5.0 + (3.0 if self.state != State.IDLE else 0.0)
        glow = QRadialGradient(cx, cy, 39 + aura)
        glow.setColorAt(0.48, QColor(accent.red(), accent.green(), accent.blue(), 0))
        glow.setColorAt(0.72, QColor(accent.red(), accent.green(), accent.blue(), 35 + int(45 * pulse)))
        glow.setColorAt(0.92, QColor(accent.red(), accent.green(), accent.blue(), 8))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(0, 0, 78, 78))

        speed = 0.8 if self.state == State.IDLE else 2.4
        for i, radius in enumerate((31.5, 35.0)):
            alpha = 42 if i == 0 else 22
            angle = self._phase * speed * (1 if i == 0 else -1)
            offset = math.sin(angle + i) * 1.5
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha), 1.4))
            p.drawEllipse(QRectF(cx - radius - offset, cy - radius + offset, (radius + offset) * 2, (radius - offset) * 2))

        r = 29.5 if self._hover else 28.0
        grad = QRadialGradient(cx - 9, cy - 11, 43)
        grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 245))
        grad.setColorAt(0.42, QColor(min(255, accent.red() + 20), min(255, accent.green() + 20), min(255, accent.blue() + 20), 235))
        grad.setColorAt(1.0, base)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 75), 1.2))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 115), 2.0))
        p.drawArc(QRectF(cx - r + 3, cy - r + 3, (r - 3) * 2, (r - 3) * 2), int((-self._phase * 35) * 16), 80 * 16)

        dot_count = {State.IDLE: 1, State.LISTENING: 3, State.THINKING: 4, State.SPEAKING: 5, State.ERROR: 2}[self.state]
        for i in range(dot_count):
            a = self._phase * (1.5 if self.state != State.IDLE else 0.5) + (2 * math.pi * i / dot_count)
            dx = cx + math.cos(a) * 31.5
            dy = cy + math.sin(a) * 31.5
            p.setBrush(QBrush(QColor(255, 255, 255, 120 + int(80 * pulse))))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(dx - 2, dy - 2, 4, 4))

        p.setPen(QColor(255, 255, 255, 245))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.drawText(QRectF(cx - r, cy - r, r * 2, r * 2), Qt.AlignmentFlag.AlignCenter, "AI")

    def _animate(self):
        self._phase += 0.055
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

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
            if self._drag_pos is not None:
                delta = event.globalPosition().toPoint() - self.frameGeometry().topLeft() - self._drag_pos
                if abs(delta.x()) < 5 and abs(delta.y()) < 5:
                    self.trigger()
            self._drag_pos = None
            event.accept()

    def _next_run(self) -> int:
        self._run_id += 1
        return self._run_id

    def trigger(self):
        # Barge-in: clicking or pressing the hotkey while speaking stops the
        # current audio and immediately starts listening for a new question.
        if self._busy and self.state == State.SPEAKING:
            if self._tts is not None:
                self._tts.stop()
            self._next_run()  # invalidate the old pipeline
            self._busy = False
            self.status_popup.hide_popup()
            self.response_popup.hide_popup()

        # Do not start a second microphone/Gemini pipeline while one is still
        # listening/thinking. A second microphone worker cannot be safely
        # cancelled with SpeechRecognition. Speaking is the explicit interrupt
        # point.
        if self._busy:
            return

        run_id = self._next_run()
        self._busy = True
        self.status_popup.hide_popup()
        self.response_popup.hide_popup()
        self.update()
        threading.Thread(target=self._pipeline, args=(run_id,), daemon=True).start()

    def _is_current(self, run_id: int) -> bool:
        return run_id == self._run_id

    def _pipeline(self, run_id: int):
        try:
            self.sig_state.emit(run_id, State.LISTENING)
            self.sig_status.emit(run_id, "Listening…")
            if self._listener is None:
                self._listener = VoiceListener()
            user_text = self._listener.listen()

            if not self._is_current(run_id):
                return
            if not user_text:
                self.sig_error.emit(run_id, "I didn’t catch that. Try again?")
                return

            self.sig_state.emit(run_id, State.THINKING)
            self.sig_status.emit(run_id, "Thinking…")
            jpeg_bytes, _ = capture_primary_screen()

            if not self._is_current(run_id):
                return
            if self._gemini is None:
                self._gemini = GeminiClient()
            answer = self._gemini.ask_with_screenshot(jpeg_bytes, user_text)

            if not self._is_current(run_id):
                return

            # IMPORTANT: update the card immediately when the current answer
            # arrives, before TTS starts. The user should never see answer N-1
            # while answer N is being spoken.
            self.sig_response.emit(run_id, answer)

            self.sig_state.emit(run_id, State.SPEAKING)
            self.sig_status.emit(run_id, "Speaking…  •  click to interrupt")
            if self._tts is None:
                self._tts = TTS()
            spoke = self._tts.speak(answer)

            if not self._is_current(run_id):
                return
            if not spoke:
                return

        except Exception as e:
            if self._is_current(run_id):
                self.sig_error.emit(run_id, str(e)[:200])
        finally:
            if self._is_current(run_id):
                self.sig_finished.emit(run_id)

    def _on_state(self, run_id: int, state: State):
        if not self._is_current(run_id):
            return
        self.state = state
        self.update()

    def _on_status(self, run_id: int, text: str):
        if not self._is_current(run_id):
            return
        if text:
            self.status_popup.show_message(text, self.pos())
        else:
            self.status_popup.hide_popup()

    def _on_response(self, run_id: int, text: str):
        if not self._is_current(run_id):
            return
        self.response_popup.hide_popup()
        self.response_popup.show_response(text, self.pos())

    def _on_error(self, run_id: int, text: str):
        if not self._is_current(run_id):
            return
        self.status_popup.hide_popup()
        self.state = State.ERROR
        self.update()
        self.response_popup.hide_popup()
        self.response_popup.show_response(f"⚠️ {text}", self.pos(), auto_ms=8000)
        QTimer.singleShot(2500, lambda rid=run_id: self._return_idle(rid))

    def _return_idle(self, run_id: int):
        if self._is_current(run_id):
            self.state = State.IDLE
            self.update()

    def _on_finished(self, run_id: int):
        if not self._is_current(run_id):
            return
        self.status_popup.hide_popup()
        if self.state != State.ERROR:
            self.state = State.IDLE
            self.update()
        self._busy = False
