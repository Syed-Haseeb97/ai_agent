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
    Mood.SAD: (QColor("#60a5fa"), QColor("#334155")),
    Mood.ERROR: (QColor("#fb7185"), QColor("#991b1b")),
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
        halo_alpha = 55 if self.mood != Mood.SAD else 28
        if self.mood == Mood.ERROR:
            halo_alpha = 45

        # Ambient halo.
        halo = QRadialGradient(QPointF(cx, cy), radius * 1.55)
        halo.setColorAt(0.0, QColor(primary.red(), primary.green(), primary.blue(), halo_alpha))
        halo.setColorAt(0.52, QColor(secondary.red(), secondary.green(), secondary.blue(), 25))
        halo.setColorAt(1.0, QColor(secondary.red(), secondary.green(), secondary.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QRectF(cx - radius * 1.55, cy - radius * 1.55, radius * 3.1, radius * 3.1))

        # Soft cast shadow under the body.
        shadow = QRadialGradient(QPointF(cx, cy + radius * 0.48), radius * 0.95)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 100))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(cx - radius, cy - radius * 0.4, radius * 2, radius * 1.6))

        # Everyday states have two distinct layers: a solid, glass-like face orb,
        # surrounded by the continuously deforming liquid body.
        has_rigid_core = self.mood in (Mood.IDLE, Mood.LISTENING, Mood.SPEAKING)
        core_radius = radius * 0.63

        body = self._body_path(cx, cy, radius, t)
        # Rich cool gradient gives the flat shape a glossy, rounded 3D feel.
        gradient = QRadialGradient(QPointF(cx - radius * 0.32, cy - radius * 0.42), radius * 1.75)
        gradient.setColorAt(0.0, QColor("#a5c8ff"))
        gradient.setColorAt(0.18, QColor("#587ff5"))
        gradient.setColorAt(0.48, primary)
        gradient.setColorAt(0.78, secondary)
        gradient.setColorAt(1.0, QColor("#11142f"))
        painter.setPen(QPen(QColor(primary.red(), primary.green(), primary.blue(), 185), 1.4))
        painter.setBrush(QBrush(gradient))
        painter.drawPath(body)

        # Inner edge and reflected light.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.drawPath(self._body_path(cx - 1.5, cy - 2.0, radius * 0.955, t + 0.08))

        shine = QRadialGradient(QPointF(cx - radius * 0.36, cy - radius * 0.58), radius * 0.8)
        shine.setColorAt(0.0, QColor(255, 255, 255, 85))
        shine.setColorAt(0.38, QColor(210, 230, 255, 28))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shine))
        painter.drawEllipse(QRectF(cx - radius * 0.92, cy - radius * 0.98, radius * 1.2, radius * 0.92))

        # Listening uses orbiting droplets as a clear "hearing" cue—no mouth
        # waveform. The dots travel around the liquid perimeter at staggered phases.
        if self.mood == Mood.LISTENING:
            for i, dot_size in enumerate((5.0, 3.8, 4.5)):
                angle = -math.pi / 2 + t * 1.35 + i * math.tau / 3
                orbit = radius * (1.13 + 0.025 * math.sin(t * 2.2 + i))
                dx = cx + math.cos(angle) * orbit
                dy = cy + math.sin(angle) * orbit
                alpha = int(135 + 90 * (0.5 + 0.5 * math.sin(t * 3.0 + i)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(175, 248, 255, alpha))
                painter.drawEllipse(QRectF(dx - dot_size / 2, dy - dot_size / 2,
                                           dot_size, dot_size))

        if has_rigid_core:
            # A genuinely separate inner orb: its own opaque pearl-blue material,
            # highlight, darker lower rim, and crisp edge. This is drawn OVER the
            # liquid shell so the two materials remain visibly distinct.
            orb = QRadialGradient(QPointF(cx - core_radius * 0.32,
                                          cy - core_radius * 0.42),
                                  core_radius * 1.55)
            orb.setColorAt(0.0, QColor("#f0fbff"))
            orb.setColorAt(0.18, QColor("#b6dcff"))
            orb.setColorAt(0.48, QColor("#668cf0"))
            orb.setColorAt(0.78, QColor("#394eb1"))
            orb.setColorAt(0.96, QColor("#222b68"))
            orb.setColorAt(1.0, QColor("#171d49"))
            painter.setPen(QPen(QColor("#d5edff"), 1.8))
            painter.setBrush(QBrush(orb))
            painter.drawEllipse(QRectF(cx - core_radius, cy - core_radius,
                                       core_radius * 2, core_radius * 2))

            # Crisp inner specular highlight makes the orb read as a separate object.
            core_shine = QRadialGradient(
                QPointF(cx - core_radius * 0.38, cy - core_radius * 0.55),
                core_radius * 0.78,
            )
            core_shine.setColorAt(0.0, QColor(255, 255, 255, 115))
            core_shine.setColorAt(0.45, QColor(225, 244, 255, 34))
            core_shine.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(core_shine))
            painter.drawEllipse(QRectF(cx - core_radius * 0.92,
                                       cy - core_radius * 0.96,
                                       core_radius * 1.15, core_radius * 0.78))

        face_radius = core_radius * 0.88 if has_rigid_core else radius
        self._draw_face(painter, cx, cy, face_radius, t)

        # A tiny specular glint reinforces the glassy material.
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.drawEllipse(QRectF(cx - radius * 0.53, cy - radius * 0.67, 4.0, 4.0))
        painter.end()

    def _draw_face(self, painter: QPainter, cx: float, cy: float, r: float, t: float) -> None:
        mood = self.mood
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
            painter.save()
            painter.translate(ex, ey)
            if mood == Mood.HAPPY:
                # Closed smiling eyes as soft upward arcs.
                painter.setPen(QPen(QColor("#f7fbff"), max(3.0, r * 0.045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                arc = QPainterPath()
                arc.moveTo(-eye_w * 0.9, eye_h * 0.15)
                arc.quadTo(0, -eye_h * 0.72, eye_w * 0.9, eye_h * 0.15)
                painter.drawPath(arc)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                eye_gradient = QLinearGradient(-eye_w, -eye_h, eye_w, eye_h)
                eye_gradient.setColorAt(0.0, QColor("#ffffff"))
                eye_gradient.setColorAt(1.0, QColor("#cfe5ff"))
                painter.setBrush(QBrush(eye_gradient))
                painter.drawEllipse(QRectF(-eye_w / 2, -eye_h / 2, eye_w, eye_h))
            painter.restore()

        if mood == Mood.SPEAKING:
            mouth_w = r * (0.08 + (math.sin(t * 11.0) + 1.0) * 0.025)
            mouth_h = r * (0.025 + abs(math.sin(t * 11.0)) * 0.065)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(20, 18, 55, 210))
            painter.drawEllipse(QRectF(cx - mouth_w / 2, cy + r * 0.18, mouth_w, mouth_h))
        elif mood == Mood.LISTENING:
            # Keep the face relaxed while the orbiting droplets around the shell
            # provide the listening motion cue.
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
            Mood.LISTENING: "LISTENING  ·  attentive gaze and audio pulse",
            Mood.THINKING: "THINKING  ·  shifting gaze and focused eyes",
            Mood.SPEAKING: "SPEAKING  ·  rhythmic mouth and body pulse",
            Mood.HAPPY: "HAPPY  ·  bright eyes and buoyant movement",
            Mood.SAD: "EMPATHETIC  ·  softer gaze and slower movement",
            Mood.ERROR: "ERROR  ·  alert wobble and warm warning glow",
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
