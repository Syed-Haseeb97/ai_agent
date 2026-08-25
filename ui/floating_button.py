"""
Animated circular always-on-top AI button and interaction pipeline.
States: idle -> listening -> thinking -> speaking -> error
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
    # Every signal carries a run id. UI handlers ignore events from an older
    # interaction, which prevents an old answer from replacing a new answer.
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

        # Smooth 60-ish FPS animation. The button always has subtle motion;
        # each state changes the motion style.
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
        menu.addAction("Ask (same as click)", self.trigger)
        menu.addAction("Show / Hide button", self._toggle_visible)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def _toggle_visible(self):
        self.setVisible(not self.isVisible())

    # ── Animated painting ─────────────────────────────────────
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

        # Animated outer aura.
        aura = 4.0 + pulse * 5.0
        if self.state != State.IDLE:
            aura += 3.0
        glow = QRadialGradient(cx, cy, 39 + aura)
        glow.setColorAt(0.48, QColor(accent.red(), accent.green(), accent.blue(), 0))
        glow.setColorAt(0.72, QColor(accent.red(), accent.green(), accent.blue(), 35 + int(45 * pulse)))
        glow.setColorAt(0.92, QColor(accent.red(), accent.green(), accent.blue(), 8))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QRectF(0, 0, 78, 78))

        # Two soft animated rings make the idle button feel alive. Active
        # states rotate them faster.
        speed = 0.8 if self.state == State.IDLE else 2.4
        for i, radius in enumerate((31.5, 35.0)):
            alpha = 42 if i == 0 else 22
            angle = self._phase * speed * (1 if i == 0 else -1)
            offset = math.sin(angle + i) * 1.5
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha), 1.4))
            p.drawEllipse(QRectF(cx - radius - offset, cy - radius + offset, (radius + offset) * 2, (radius - offset) * 2))

        # Main glass-like sphere.
        hover_scale = 1.5 if self._hover else 0.0
        r = 28.0 + hover_scale
        grad = QRadialGradient(cx - 9, cy - 11, 43)
        grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 245))
        grad.setColorAt(0.42, QColor(min(255, accent.red() + 20), min(255, accent.green() + 20), min(255, accent.blue() + 20), 235))
        grad.setColorAt(1.0, base)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 75), 1.2))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Moving highlight arc.
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 115), 2.0))
        p.drawArc(QRectF(cx - r + 3, cy - r + 3, (r - 3) * 2, (r - 3) * 2), int((-self._phase * 35) * 16), 80 * 16)

        # State-specific orbit dots.
        dot_count = {State.IDLE: 1, State.LISTENING: 3, State.THINKING: 4, State.SPEAKING: 5, State.ERROR: 2}[self.state]
        dot_radius = 2.0
        orbit = 31.5
        for i in range(dot_count):
            a = self._phase * (1.5 if self.state != State.IDLE else 0.5) + (2 * math.pi * i / dot_count)
            dx = cx + math.cos(a) * orbit
            dy = cy + math.sin(a) * orbit
            p.setBrush(QBrush(QColor(255, 255, 255, 120 + int(80 * pulse))))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(dx - dot_radius, dy - dot_radius, dot_radius * 2, dot_radius * 2))

        # Clean AI mark.
        p.setPen(QColor(255, 255, 255, 245))
        p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        p.drawText(QRectF(cx - r, cy - r, r * 2, r * 2), Qt.AlignmentFlag.AlignCenter, "AI")

    def _animate(self):
        self._phase += 0.055
        self.update()

    # ── Hover ─────────────────────────────────────────────────
    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # ── Mouse / drag ──────────────────────────────────────────
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

    # ── Interaction ───────────────────────────────────────────
    def trigger(self):
        if self._busy:
            return

        self._busy = True
        self._run_id += 1
        run_id = self._run_id

        # Clear the previous card immediately in the UI thread.
        self.status_popup.hide_popup()
        self.response_popup.hide_popup()
        self.update()

        threading.Thread(target=self._pipeline, args=(run_id,), daemon=True).start()

    def _pipeline(self, run_id: int):
        try:
            self.sig_state.emit(run_id, State.LISTENING)
            self.sig_status.emit(run_id, "Listening…")
            if self._listener is None:
                self._listener = VoiceListener()
            user_text = self._listener.listen()

            if not user_text:
                self.sig_error.emit(run_id, "I didn’t catch that. Try again?")
                return

            self.sig_state.emit(run_id, State.THINKING)
            self.sig_status.emit(run_id, "Thinking…")
            jpeg_bytes, _ = capture_primary_screen()

            if self._gemini is None:
                self._gemini = GeminiClient()
            answer = self._gemini.ask_with_screenshot(jpeg_bytes, user_text)

            self.sig_state.emit(run_id, State.SPEAKING)
            self.sig_status.emit(run_id, "Speaking…")
            if self._tts is None:
                self._tts = TTS()
            self._tts.speak(answer)

            # Only this run can publish this answer.
            self.sig_response.emit(run_id, answer)

        except Exception as e:
            self.sig_error.emit(run_id, str(e)[:200])
        finally:
            self.sig_finished.emit(run_id)

    # ── UI-thread handlers ────────────────────────────────────
    def _is_current(self, run_id: int) -> bool:
        return run_id == self._run_id

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
        # Replace, never append, and only accept the newest interaction.
        self.response_popup.hide_popup()
        self.response_popup.show_response(text, self.pos())

    def _on_error(self, run_id: int, text: str):
        if not self._is_current(run_id):
            return
        self.status_popup.hide_popup()
        self.state = State.ERROR
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
