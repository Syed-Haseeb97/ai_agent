"""Standalone glossy Liquid Blob playground for Ruby.

Visual prototype only: deliberately isolated from the production assistant.
Requires PyQt6. Run with: python prototypes/liquid_blob/prototype.py
"""
from __future__ import annotations

import math
import sys
import time
from enum import Enum

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QBrush, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)


class Mood(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    HAPPY = "Happy"
    SAD = "Sad"
    ERROR = "Error"


MOOD_COLORS = {
    Mood.IDLE: (QColor("#8b5cf6"), QColor("#2563eb")),
    Mood.LISTENING: (QColor("#22d3ee"), QColor("#2563eb")),
    Mood.THINKING: (QColor("#a78bfa"), QColor("#4f46e5")),
    Mood.SPEAKING: (QColor("#60a5fa"), QColor("#7c3aed")),
    Mood.HAPPY: (QColor("#c084fc"), QColor("#3b82f6")),
    Mood.SAD: (QColor("#60a5fa"), QColor("#60a5fa")),
    Mood.ERROR: (QColor("#ff526b"), QColor("#b91235")),
}


class LiquidBlob(QWidget):
    """Paint a soft, glossy organic character with mood-driven motion."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mood = Mood.IDLE
        self.started_at = time.monotonic()
        self.hovered = False
        self.setMinimumSize(300, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self.update)
        self._timer.start(33)  # ~30 FPS is enough for a desktop companion.

    def set_mood(self, mood: Mood) -> None:
        if self.mood != mood:
            self.mood = mood
            self.update()

    def enterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def _phase(self) -> float:
        return time.monotonic() - self.started_at

    def _body_path(self, cx: float, cy: float, radius: float, t: float) -> QPainterPath:
        path = QPainterPath()
        points: list[QPointF] = []
        count = 120
        mood = self.mood
        energy = 0.025
        if mood == Mood.HAPPY:
            energy = 0.065
        elif mood == Mood.LISTENING:
            energy = 0.038
        elif mood == Mood.THINKING:
            energy = 0.045
        elif mood == Mood.SAD:
            energy = 0.018
        elif mood == Mood.ERROR:
            energy = 0.07

        breathe = math.sin(t * (2.1 if mood != Mood.SAD else 0.9)) * 0.018
        for i in range(count):
            angle = math.tau * i / count
            wave_a = math.sin(3 * angle + t * 1.25) * energy
            wave_b = math.sin(2 * angle - t * 0.85) * energy * 0.42
            wave_c = math.cos(5 * angle + t * 0.7) * energy * 0.22
            deform = 1.0 + wave_a + wave_b + wave_c + breathe
            if mood == Mood.SAD:
                # A subtly heavier lower half gives the body a drooping silhouette.
                deform += max(0.0, math.sin(angle)) * 0.035
            elif mood == Mood.HAPPY:
                deform += math.sin(angle * 2 + t * 2.0) * 0.018
            elif mood == Mood.ERROR:
                deform += math.sin(angle * 7 + t * 9.0) * 0.018
            r = radius * deform
            x = cx + math.cos(angle) * r
            y = cy + math.sin(angle) * r * (1.0 + (0.045 if mood == Mood.SAD else 0.0))
            points.append(QPointF(x, y))

        path.moveTo(points[0])
        # Midpoint quadratic curves create a smooth closed organic outline.
        for i, point in enumerate(points):
            nxt = points[(i + 1) % count]
            mid = QPointF((point.x() + nxt.x()) / 2, (point.y() + nxt.y()) / 2)
            path.quadTo(point, mid)
        path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = float(self.width()), float(self.height())
        t = self._phase()
        cx, cy = w / 2, h / 2 - 6
        radius = min(w * 0.34, h * 0.34, 150.0)
        if self.hovered:
            radius *= 1.025

        breathe = math.sin(t * (1.9 if self.mood != Mood.SAD else 0.8))
        if self.mood == Mood.HAPPY:
            cy -= abs(math.sin(t * 3.2)) * 5
        elif self.mood == Mood.SAD:
            cy += 3 + abs(breathe) * 3
        elif self.mood == Mood.THINKING:
            cx += math.sin(t * 1.2) * 2.8
        elif self.mood == Mood.ERROR:
            cx += math.sin(t * 12.0) * 2.0

        primary, secondary = MOOD_COLORS[self.mood]
        # Error is deliberately clean and flat outside its red body: no floating halo.
        if self.mood != Mood.ERROR:
            halo_alpha = 55 if self.mood != Mood.SAD else 28

            # Ambient halo.
            halo = QRadialGradient(QPointF(cx, cy), radius * 1.55)
            halo.setColorAt(0.0, QColor(primary.red(), primary.green(), primary.blue(), halo_alpha))
            halo.setColorAt(0.52, QColor(secondary.red(), secondary.green(), secondary.blue(), 25))
            halo.setColorAt(1.0, QColor(secondary.red(), secondary.green(), secondary.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(QRectF(cx - radius * 1.55, cy - radius * 1.55, radius * 3.1, radius * 3.1))

        # Preserve the soft grounding shadow for normal moods, but keep Error shade-free.
        if self.mood != Mood.ERROR:
            shadow = QRadialGradient(QPointF(cx, cy + radius * 0.48), radius * 0.95)
            shadow.setColorAt(0.0, QColor(0, 0, 0, 100))
            shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(shadow))
            painter.drawEllipse(QRectF(cx - radius, cy - radius * 0.4, radius * 2, radius * 1.6))

        # Everyday states have two distinct layers: a solid, glass-like face orb,
        # surrounded by the continuously deforming liquid body.
        has_black_core = self.mood in (Mood.IDLE, Mood.LISTENING, Mood.SPEAKING, Mood.SAD)
        core_radius = radius * 0.63

        body = self._body_path(cx, cy, radius, t)
        # A broad, moving highlight gives every mood a living, liquid sheen.
        # Error keeps the same glossy motion, recolored into its warning-red theme.
        highlight_x = cx + math.cos(t * 0.72) * radius * 0.24
        highlight_y = cy + math.sin(t * 0.58) * radius * 0.22
        gradient = QRadialGradient(QPointF(highlight_x, highlight_y), radius * 1.38)
        if self.mood == Mood.SAD:
            # Keep the sad fluid clean blue; no charcoal/navy shading in its body.
            gradient.setColorAt(0.0, QColor("#b9ddff"))
            gradient.setColorAt(0.22, QColor("#80bdff"))
            gradient.setColorAt(0.58, QColor("#60a5fa"))
            gradient.setColorAt(1.0, QColor("#60a5fa"))
        elif self.mood == Mood.ERROR:
            # Glossy warning-red palette: bright moving sheen, saturated red body,
            # and a deeper crimson edge. The ambient halo and cast shadow stay off.
            gradient.setColorAt(0.0, QColor("#ff9aa8"))
            gradient.setColorAt(0.18, QColor("#ff647b"))
            gradient.setColorAt(0.42, QColor("#ff304f"))
            gradient.setColorAt(0.72, QColor("#e7193c"))
            gradient.setColorAt(1.0, QColor("#b91235"))
        else:
            gradient.setColorAt(0.0, primary.lighter(175))
            gradient.setColorAt(0.22, primary.lighter(135))
            gradient.setColorAt(0.52, primary)
            gradient.setColorAt(0.82, secondary)
            gradient.setColorAt(1.0, secondary)
        painter.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 185), 1.4))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(body)

        # Inner edge and reflected light.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.drawPath(self._body_path(cx - 1.5, cy - 2.0, radius * 0.955, t + 0.08))

        # Removed the broad radial shine overlay: it created an unwanted
        # circular blue/pink shade across every liquid body.


        if has_black_core:
            # A clearly separate, opaque black sphere with a restrained charcoal
            # highlight and subtle rim. White eyes remain high-contrast and readable.
            orb = QRadialGradient(
                QPointF(cx - core_radius * 0.32, cy - core_radius * 0.42),
                core_radius * 1.55,
            )
            orb.setColorAt(0.0, QColor("#30313a"))
            orb.setColorAt(0.22, QColor("#17181e"))
            orb.setColorAt(0.68, QColor("#08090d"))
            orb.setColorAt(0.94, QColor("#020305"))
            orb.setColorAt(1.0, QColor("#000000"))
            painter.setPen(QPen(QColor("#555965"), 1.5))
            painter.setBrush(QBrush(orb))
            painter.drawEllipse(QRectF(cx - core_radius, cy - core_radius,
                                       core_radius * 2, core_radius * 2))

            # Keep the black core clean and opaque; no extra highlight overlay.


        face_radius = core_radius * 0.88 if has_black_core else radius
        self._draw_face(painter, cx, cy, face_radius, t)

        # No isolated specular dot: the broad animated gradient supplies the sheen.
        painter.end()

    def _draw_face(self, painter: QPainter, cx: float, cy: float, r: float, t: float) -> None:
        mood = self.mood
        has_black_core = mood in (Mood.IDLE, Mood.LISTENING, Mood.SPEAKING, Mood.SAD)
        gaze_x = 0.0
        gaze_y = 0.0
        if mood == Mood.THINKING:
            gaze_x = math.sin(t * 0.75) * 7.0 + 5.0
            gaze_y = -5.0 + math.sin(t * 1.5) * 2.0
        elif mood == Mood.LISTENING:
            gaze_x = math.sin(t * 2.2) * 2.5
        elif mood == Mood.HAPPY:
            gaze_y = -1.5
        elif mood == Mood.SAD:
            gaze_y = 3.0
        elif mood == Mood.ERROR:
            gaze_x = math.sin(t * 14.0) * 2.0

        eye_y = cy - r * 0.015 + gaze_y
        eye_dx = r * 0.29
        eye_w = r * 0.105
        eye_h = r * 0.245

        # Gentle periodic blink, shared by the white eyes in every non-smile state.
        # A short smooth close/open cycle roughly every 3.5–5 seconds.
        blink_cycle = (t + 0.37) % 4.15
        blink = 1.0
        if blink_cycle < 0.16:
            blink = max(0.06, abs(blink_cycle - 0.08) / 0.08)
        elif 0.16 <= blink_cycle < 0.24:
            blink = max(0.06, (blink_cycle - 0.16) / 0.08)
        if mood != Mood.HAPPY:
            eye_h *= blink

        # Thinking eyes briefly narrow and glance up/sideways like a thinking emoji.
        if mood == Mood.THINKING:
            eye_h *= 0.72 + (math.sin(t * 2.0) + 1.0) * 0.09
        elif mood == Mood.SAD:
            eye_h *= 0.82
        elif mood == Mood.HAPPY:
            eye_h *= 0.52
        elif mood == Mood.ERROR:
            eye_h *= 0.8

        for sign in (-1, 1):
            ex = cx + sign * eye_dx + gaze_x
            ey = eye_y
            this_eye_h = eye_h
            painter.save()
            painter.translate(ex, ey)
            if mood == Mood.HAPPY:
                # Closed smiling eyes with a fine dark outline for definition.
                arc = QPainterPath()
                arc.moveTo(-eye_w * 0.9, this_eye_h * 0.15)
                arc.quadTo(0, -this_eye_h * 0.72, eye_w * 0.9, this_eye_h * 0.15)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#111018"), max(4.8, r * 0.065), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawPath(arc)
                painter.setPen(QPen(QColor("#f7fbff"), max(2.6, r * 0.035), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawPath(arc)
            else:
                eye_rect = QRectF(-eye_w / 2, -this_eye_h / 2, eye_w, this_eye_h)
                eye_gradient = QLinearGradient(-eye_w, -this_eye_h, eye_w, this_eye_h)
                eye_gradient.setColorAt(0.0, QColor("#ffffff"))
                eye_gradient.setColorAt(1.0, QColor("#cfe5ff"))
                # Thin dark outline keeps white eyes visible against bright highlights.
                painter.setPen(QPen(QColor("#111018"), max(1.0, r * 0.018)))
                painter.setBrush(QBrush(eye_gradient))
                painter.drawEllipse(eye_rect)
            painter.restore()

        if mood == Mood.SPEAKING:
            mouth_w = r * (0.08 + (math.sin(t * 11.0) + 1.0) * 0.025)
            mouth_h = r * (0.025 + abs(math.sin(t * 11.0)) * 0.065)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 18, 55, 210))
            painter.drawEllipse(QRectF(cx - mouth_w / 2, cy + r * 0.18, mouth_w, mouth_h))
        elif mood == Mood.LISTENING:
            # Original calm listening face; no eyebrow gimmick or orbiting dots.
            pass
        elif mood == Mood.SAD:
            painter.setPen(QPen(QColor(235, 240, 255, 190), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(QRectF(cx - r * 0.13, cy + r * 0.19, r * 0.26, r * 0.12), 25 * 16, 130 * 16)
        elif mood == Mood.ERROR:
            painter.setPen(QPen(QColor("#ffe4e6"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(cx - r * 0.09, cy + r * 0.22), QPointF(cx + r * 0.09, cy + r * 0.22))


class StateButton(QPushButton):
    def __init__(self, mood: Mood, parent: QWidget | None = None) -> None:
        super().__init__(mood.value, parent)
        self.mood = mood
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setMinimumHeight(36)
        self.setStyleSheet("""
            QPushButton {
                color: #cbd5e1; background: #111827;
                border: 1px solid #293449; border-radius: 10px;
                padding: 7px 12px; font: 600 10pt 'Segoe UI';
            }
            QPushButton:hover { background: #1b2540; border-color: #596b91; color: white; }
            QPushButton:checked { color: #ffffff; background: #3b2b70; border-color: #9b87f5; }
            QPushButton:pressed { background: #31245b; }
        """)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Ruby — Liquid Blob Playground")
        self.resize(560, 680)
        self.setMinimumSize(420, 560)
        self.setStyleSheet("QMainWindow { background: #080b14; } QWidget { color: #e5e7eb; }")

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)

        header = QLabel("R U B Y")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #d9d4ff; font: 700 11pt 'Segoe UI'; letter-spacing: 5px;")
        subtitle = QLabel("LIQUID COMPANION  /  MOTION PLAYGROUND")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #77829a; font: 9pt 'Segoe UI'; letter-spacing: 1px;")

        self.blob = LiquidBlob()
        self.state_label = QLabel("IDLE  ·  calm breathing")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setStyleSheet("color: #a5b4fc; font: 600 10pt 'Segoe UI';")

        card = QFrame()
        card.setStyleSheet("QFrame { background: #0c1120; border: 1px solid #202942; border-radius: 24px; }")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 8)
        card_layout.addWidget(self.blob, 1)

        state_grid = QHBoxLayout()
        state_grid.setSpacing(8)
        self.buttons: list[StateButton] = []
        moods = [Mood.IDLE, Mood.LISTENING, Mood.THINKING, Mood.SPEAKING]
        for mood in moods:
            button = StateButton(mood)
            button.clicked.connect(lambda checked=False, m=mood: self.choose_mood(m))
            state_grid.addWidget(button)
            self.buttons.append(button)

        emotion_grid = QHBoxLayout()
        emotion_grid.setSpacing(8)
        for mood in [Mood.HAPPY, Mood.SAD, Mood.ERROR]:
            button = StateButton(mood)
            button.clicked.connect(lambda checked=False, m=mood: self.choose_mood(m))
            emotion_grid.addWidget(button)
            self.buttons.append(button)

        footer = QLabel("Choose a state to preview the character's expression and motion.")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        footer.setStyleSheet("color: #7e8aa4; font: 9pt 'Segoe UI'; padding-top: 2px;")

        layout.addWidget(header)
        layout.addWidget(subtitle)
        layout.addSpacing(2)
        layout.addWidget(card, 1)
        layout.addWidget(self.state_label)
        layout.addLayout(state_grid)
        layout.addLayout(emotion_grid)
        layout.addWidget(footer)

        self.setCentralWidget(root)
        self.choose_mood(Mood.IDLE)

    def choose_mood(self, mood: Mood) -> None:
        self.blob.set_mood(mood)
        descriptions = {
            Mood.IDLE: "IDLE  ·  calm breathing",
            Mood.LISTENING: "LISTENING  ·  calm, attentive breathing",
            Mood.THINKING: "THINKING  ·  shifting gaze and focused eyes",
            Mood.SPEAKING: "SPEAKING  ·  rhythmic mouth and body pulse",
            Mood.HAPPY: "HAPPY  ·  bright eyes and buoyant movement",
            Mood.SAD: "EMPATHETIC  ·  softer gaze and slower movement",
            Mood.ERROR: "ERROR  ·  alert wobble and glossy warning-red sheen",
        }
        self.state_label.setText(descriptions[mood])
        for button in self.buttons:
            button.setChecked(button.mood == mood)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Ruby Liquid Blob Playground")
    app.setFont(QFont("Segoe UI", 10))
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
