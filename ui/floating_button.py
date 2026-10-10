"""Animated floating assistant button and voice/text interaction pipeline."""

from __future__ import annotations

import threading
from enum import Enum, auto

from PyQt6.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QSystemTrayIcon, QMenu, QApplication, QPushButton

from actions.windows_actions import WindowsActionExecutor
from ui.status_popup import StatusPopup
from ui.liquid_blob import LiquidBlob, Mood
from ui.response_popup import ResponsePopup
from ui.drag_gesture import drag_threshold_exceeded
from voice.listener import VoiceListener
from voice.tts import TTS
from vision.capture import capture_primary_screen
from ai.gemini_client import GeminiClient
from ai.mood_sync import write_mood_state


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    THINKING = auto()
    SPEAKING = auto()
    ERROR = auto()


class FloatingButton(QWidget):
    sig_trigger_requested = pyqtSignal()
    sig_text_requested = pyqtSignal(str)
    sig_status = pyqtSignal(int, str)
    sig_user = pyqtSignal(int, str)
    sig_response = pyqtSignal(int, str)
    sig_state = pyqtSignal(int, object)
    sig_emotion = pyqtSignal(int, str)
    sig_error = pyqtSignal(int, str)
    sig_finished = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(78, 112)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.state = State.IDLE
        self.blob = LiquidBlob(self)
        self.blob.setFixedSize(78, 78)
        self.blob.move(0, 0)
        self.blob.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.blob.set_mood(Mood.IDLE)
        self._drag_pos: QPoint | None = None
        self._press_global_pos: QPoint | None = None
        self._dragged = False
        self._busy = False
        self._run_id = 0
        self._response_ready: dict[int, threading.Event] = {}
        self._continuous_mode = False
        self._response_emotion = "neutral"
        self._mood_sync_timer = QTimer(self)
        self._mood_sync_timer.setInterval(2000)
        self._mood_sync_timer.timeout.connect(
            lambda: write_mood_state(self.state.name.lower(), self._response_emotion)
        )
        self._mood_sync_timer.start()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - 100, 34)
        self.status_popup = StatusPopup()
        self.response_popup = ResponsePopup()
        self.action_executor = WindowsActionExecutor()

        self.stop_listening_button = QPushButton("●  Stop", self)
        self.stop_listening_button.setFixedSize(68, 25)
        self.stop_listening_button.move(5, 83)
        self.stop_listening_button.setToolTip("Stop listening and return Ruby to idle")
        self.stop_listening_button.setAccessibleName("Stop listening")
        self.stop_listening_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_listening_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stop_listening_button.setStyleSheet("""
            QPushButton {
                background: rgba(17, 19, 30, 246);
                color: #fda4af;
                border: 1px solid rgba(167, 139, 250, 105);
                border-radius: 12px;
                padding: 2px 8px;
                font: 600 9px 'Segoe UI';
            }
            QPushButton:hover {
                background: rgba(91, 35, 55, 248);
                color: #ffe4e6;
                border-color: rgba(251, 113, 133, 210);
            }
            QPushButton:pressed {
                background: rgba(127, 29, 50, 255);
                border-color: rgba(251, 113, 133, 235);
            }
        """)
        self.stop_listening_button.hide()
        self.stop_listening_button.clicked.connect(self.stop_continuous_listening)

        self.sig_trigger_requested.connect(self.trigger)
        self.sig_text_requested.connect(self.submit_text)
        self.sig_status.connect(self._on_status)
        self.sig_user.connect(self._on_user)
        self.sig_response.connect(self._on_response)
        self.sig_state.connect(self._on_state)
        self.sig_emotion.connect(self._on_emotion)
        self.sig_error.connect(self._on_error)
        self.sig_finished.connect(self._on_finished)
        self.response_popup.submitted.connect(self.submit_text)

        self._init_tray()
        self._listener: VoiceListener | None = None
        self._tts: TTS | None = None
        self._gemini: GeminiClient | None = None

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self); self.tray.setToolTip("AI Screen Assistant")
        menu = QMenu()
        menu.addAction("Ask by voice / Interrupt", self.trigger)
        menu.addAction("Type a question", self.show_text_input)
        menu.addAction("Show / Hide button", self._toggle_visible)
        menu.addSeparator(); menu.addAction("Quit", QApplication.instance().quit)
        self.tray.setContextMenu(menu); self.tray.show()

    def _toggle_visible(self): self.setVisible(not self.isVisible())

    def _set_continuous_ui(self, enabled: bool):
        self._continuous_mode = enabled
        self.stop_listening_button.setVisible(enabled)
        if enabled:
            self.stop_listening_button.raise_()
        self.update()


    def enterEvent(self, event):
        self.blob.hovered = True
        self.blob.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.blob.hovered = False
        self.blob.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global_pos = event.globalPosition().toPoint()
            self._dragged = False
            self._drag_pos = self._press_global_pos - self.frameGeometry().topLeft()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.show_text_input()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current_global_pos = event.globalPosition().toPoint()
            if self._press_global_pos is not None and drag_threshold_exceeded(
                self._press_global_pos, current_global_pos, QApplication.startDragDistance()
            ):
                self._dragged = True
            self.move(current_global_pos - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._press_global_pos is not None and drag_threshold_exceeded(
                self._press_global_pos,
                event.globalPosition().toPoint(),
                QApplication.startDragDistance(),
            ):
                self._dragged = True

            # A release after moving Ruby is a reposition gesture, never a
            # click-to-listen. Compare global press/release coordinates: using
            # frameGeometry() here is incorrect because the window has already
            # moved with the pointer by the time the release arrives.
            should_trigger = self._press_global_pos is not None and not self._dragged
            self._drag_pos = None
            self._press_global_pos = None
            self._dragged = False
            if should_trigger:
                self.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _set_state(self, state: State):
        """Synchronize the production state machine with Ruby's visual mood."""
        self.state = state
        mood_map = {
            State.IDLE: Mood.IDLE,
            State.LISTENING: Mood.LISTENING,
            State.THINKING: Mood.THINKING,
            State.SPEAKING: {
                "neutral": Mood.SPEAKING,
                "happy": Mood.HAPPY,
                "excited": Mood.EXCITED,
                "sad": Mood.SAD,
                "empathetic": Mood.EMPATHETIC,
                "curious": Mood.CURIOUS,
                "surprised": Mood.SURPRISED,
            }.get(self._response_emotion, Mood.SPEAKING),
            State.ERROR: Mood.ERROR,
        }
        if state != State.SPEAKING:
            self._response_emotion = "neutral"
        self.blob.set_mood(mood_map[state])
        self.blob.set_speaking_active(state == State.SPEAKING)
        self.blob.set_thinking_spin_active(state == State.THINKING)
        write_mood_state(state.name.lower(), self._response_emotion)
        self.blob.update()

    def _next_run(self): self._run_id += 1; return self._run_id
    def trigger(self):
        if self._busy and self.state==State.SPEAKING:
            self._interrupt_current()
            if self._continuous_mode:
                self._start_run(None)
            return
        if self._busy:
            return
        self._set_continuous_ui(True)
        self._start_run(None)

    def stop_continuous_listening(self):
        self._set_continuous_ui(False)
        if self._busy:
            self._interrupt_current()
        else:
            self.status_popup.hide_popup()
            self._set_state(State.IDLE)

    def request_trigger(self): self.sig_trigger_requested.emit()

    def show_text_input(self):
        if self._busy:
            if self.state==State.SPEAKING: self._interrupt_current()
            else: return
        self.response_popup.show_chat(self.pos())

    def submit_text(self,text):
        if not text.strip() or self._busy: return
        self._start_run(text.strip())

    def _start_run(self,user_text):
        run_id=self._next_run(); self._busy=True; self._response_ready[run_id] = threading.Event(); self.status_popup.hide_popup(); self.update()
        if user_text:
            self.response_popup.add_user_message(user_text, self.pos())
        threading.Thread(target=self._pipeline,args=(run_id,user_text),daemon=True).start()

    def _interrupt_current(self):
        if self._tts is not None: self._tts.stop()
        self._next_run(); self._busy=False; self.status_popup.hide_popup(); self._set_state(State.IDLE)
        self._response_ready.clear()

    def _is_current(self,run_id): return run_id==self._run_id

    def _wait_for_response_ui(self, run_id):
        ready = self._response_ready.get(run_id)
        if ready is not None: ready.wait(timeout=2.0)

    def _pipeline(self,run_id,typed_text):
        try:
            if typed_text is None:
                self.sig_state.emit(run_id,State.LISTENING); self.sig_status.emit(run_id,"Listening…")
                if self._listener is None: self._listener=VoiceListener()
                user_text=self._listener.listen()
                if not self._is_current(run_id): return
                if not user_text:
                    self.sig_error.emit(run_id,"I didn’t catch that. Try again?"); return
                self.sig_user.emit(run_id,user_text)
            else: user_text=typed_text
            if not self._is_current(run_id): return

            action=self.action_executor.try_execute(user_text)
            if action.handled:
                self.sig_emotion.emit(run_id, "neutral")
                self.sig_response.emit(run_id,action.message)
                self._wait_for_response_ui(run_id)
                if not self._is_current(run_id): return
                self.sig_state.emit(run_id,State.SPEAKING); self.sig_status.emit(run_id,"Speaking…  •  click to interrupt")
                if self._tts is None: self._tts=TTS()
                spoke=self._tts.speak(action.message)
                if not self._is_current(run_id) or not spoke: return
                return

            self.sig_state.emit(run_id,State.THINKING); self.sig_status.emit(run_id,"Thinking…")
            jpeg_bytes,_=capture_primary_screen()
            if not self._is_current(run_id): return
            if self._gemini is None: self._gemini=GeminiClient()
            answer, emotion = self._gemini.ask_with_screenshot_and_emotion(jpeg_bytes,user_text)
            if not self._is_current(run_id): return
            self.sig_emotion.emit(run_id, emotion)
            self.sig_response.emit(run_id,answer)
            self._wait_for_response_ui(run_id)
            if not self._is_current(run_id): return
            self.sig_state.emit(run_id,State.SPEAKING); self.sig_status.emit(run_id,"Speaking…  •  click to interrupt")
            if self._tts is None: self._tts=TTS()
            spoke=self._tts.speak(answer)
            if not self._is_current(run_id) or not spoke: return
        except Exception as e:
            if self._is_current(run_id): self.sig_error.emit(run_id,str(e)[:200])
        finally:
            if self._is_current(run_id): self.sig_finished.emit(run_id)
            self._response_ready.pop(run_id, None)

    def _on_state(self,run_id,state):
        if self._is_current(run_id): self._set_state(state)

    def _on_emotion(self, run_id, emotion):
        if not self._is_current(run_id):
            return
        from ai.emotion import normalize_emotion
        self._response_emotion = normalize_emotion(emotion)
        write_mood_state(self.state.name.lower(), self._response_emotion)

    def _on_status(self,run_id,text):
        if not self._is_current(run_id): return
        self.response_popup.set_status(text or "")
        if text: self.status_popup.show_message(text,self.pos())
        else: self.status_popup.hide_popup()
    def _on_user(self,run_id,text):
        if self._is_current(run_id): self.response_popup.add_user_message(text,self.pos())
    def _on_response(self,run_id,text):
        if self._is_current(run_id):
            self.response_popup.show_response(text,self.pos())
            ready=self._response_ready.get(run_id)
            if ready is not None: ready.set()
    def _on_error(self,run_id,text):
        if not self._is_current(run_id): return
        # An error must stop continuous listening; otherwise an empty/failed
        # listen immediately starts another run and oscillates ERROR/LISTENING.
        self._set_continuous_ui(False)
        self.response_popup.set_status(f"⚠️ {text}")
        self.status_popup.show_message(f"⚠️ {text}",self.pos(),duration_ms=3500)
        self._set_state(State.ERROR)
        QTimer.singleShot(2500, lambda rid=run_id: self._return_idle(rid))
    def _return_idle(self,run_id):
        if self._is_current(run_id): self._set_state(State.IDLE)
    def _on_finished(self,run_id):
        if not self._is_current(run_id): return
        # Keep the error message visible for its configured duration.
        if self.state != State.ERROR:
            self.status_popup.hide_popup()
            self.response_popup.set_status("")
            self._set_state(State.IDLE)
        self._busy=False
        if self._continuous_mode:
            QTimer.singleShot(250, self._continue_listening)

    def _continue_listening(self):
        if self._continuous_mode and not self._busy:
            self._start_run(None)
