"""Glossy liquid-orb widget used by Ruby's production floating assistant."""
from __future__ import annotations

import math
import time
from enum import Enum

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QColor, QBrush, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QSizePolicy, QWidget


class Mood(str, Enum):
    IDLE = "Idle"
    LISTENING = "Listening"
    THINKING = "Thinking"
    SPEAKING = "Speaking"
    HAPPY = "Happy"
    EXCITED = "Excited"
    SAD = "Sad"
    EMPATHETIC = "Empathetic"
    CURIOUS = "Curious"
    SURPRISED = "Surprised"
    ERROR = "Error"


MOOD_COLORS = {
    Mood.IDLE: (QColor("#8b5cf6"), QColor("#2563eb")),
    Mood.LISTENING: (QColor("#22d3ee"), QColor("#2563eb")),
    Mood.THINKING: (QColor("#a78bfa"), QColor("#4f46e5")),
    Mood.SPEAKING: (QColor("#60a5fa"), QColor("#7c3aed")),
    Mood.HAPPY: (QColor("#c084fc"), QColor("#3b82f6")),
    Mood.EXCITED: (QColor("#fb7185"), QColor("#7c3aed")),
    Mood.SAD: (QColor("#60a5fa"), QColor("#60a5fa")),
    Mood.EMPATHETIC: (QColor("#7dd3fc"), QColor("#818cf8")),
    Mood.CURIOUS: (QColor("#67e8f9"), QColor("#8b5cf6")),
    Mood.SURPRISED: (QColor("#a5b4fc"), QColor("#ec4899")),
    Mood.ERROR: (QColor("#ff526b"), QColor("#b91235")),
}


class LiquidBlob(QWidget):
    """Paint a soft, glossy organic character with mood-driven motion."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mood = Mood.IDLE
        self.started_at = time.monotonic()
        self.hovered = False
        self._spin_active = False
        self._spin_angle = 0.0
        self._speaking_active = False
        self.setMinimumSize(300, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        # Rotation is a lightweight 2D-painted approximation of a glossy sphere.
        self._last_tick = time.monotonic()

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 FPS is enough for a desktop companion.

    def _tick(self) -> None:
        """Advance the orb animation and Thinking rotation."""
        now = time.monotonic()
        dt = min(0.05, max(0.0, now - self._last_tick))
        self._last_tick = now

        if self.mood == Mood.THINKING and self._spin_active and dt > 0.0:
            # A readable, continuous yaw: fast enough to see the whole body turn,
            # but slow enough for the front/back transition to register.
            self._spin_angle = (self._spin_angle + 300.0 * dt) % 360.0


        self.update()

    def set_thinking_spin_active(self, active: bool) -> None:
        """Start/stop Thinking rotation from prompt-lifecycle events."""
        active = bool(active)
        if self._spin_active != active:
            self._spin_active = active
            self._last_tick = time.monotonic()
            self.update()

    def set_mood(self, mood: Mood) -> None:
        if self.mood != mood:
            self.mood = mood
            # The production state synchronizer explicitly enables Thinking spin.
            self._spin_active = False
            self.update()

    def set_speaking_active(self, active: bool) -> None:
        """Animate the mouth independently from the selected emotional expression."""
        active = bool(active)
        if self._speaking_active != active:
            self._speaking_active = active
            self.update()

    @staticmethod
    def uses_black_core(mood: Mood) -> bool:
        """Only the approved neutral/listening/speaking expressions use the dark face core."""
        return mood in (Mood.IDLE, Mood.LISTENING, Mood.SPEAKING)

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
        elif mood == Mood.EXCITED:
            energy = 0.085
        elif mood == Mood.CURIOUS:
            energy = 0.035
        elif mood == Mood.SURPRISED:
            energy = 0.055
        elif mood == Mood.EMPATHETIC:
            energy = 0.022
        elif mood == Mood.LISTENING:
            energy = 0.038
        elif mood == Mood.THINKING:
            # Keep the silhouette steady so the 3D yaw, not fluid wobble,
            # reads as Ruby turning in place.
            energy = 0.012
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
            flow_x = flow_y = 0.0
            if mood == Mood.SAD:
                # A subtly heavier lower half gives the body a drooping silhouette.
                deform += max(0.0, math.sin(angle)) * 0.035
            elif mood in (Mood.HAPPY, Mood.EXCITED):
                deform += math.sin(angle * 2 + t * (2.8 if mood == Mood.EXCITED else 2.0)) * (0.026 if mood == Mood.EXCITED else 0.018)
            elif mood == Mood.ERROR:
                deform += math.sin(angle * 7 + t * 9.0) * 0.018
            r = radius * deform
            x_scale = 1.0
            y_scale = 1.0
            x = cx + math.cos(angle) * r * x_scale
            y = cy + math.sin(angle) * r * y_scale * (1.0 + (0.045 if mood == Mood.SAD else 0.0))
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

        breathe = math.sin(t * (1.9 if self.mood not in (Mood.SAD, Mood.EMPATHETIC) else 0.8))
        if self.mood in (Mood.HAPPY, Mood.EXCITED):
            cy -= abs(math.sin(t * (4.2 if self.mood == Mood.EXCITED else 3.2)) * (7 if self.mood == Mood.EXCITED else 5))
        elif self.mood == Mood.SAD:
            cy += 3 + abs(breathe) * 3
        elif self.mood == Mood.THINKING:
            # Thinking stays anchored at the center; the whole character spins.
            # Rotation is applied to the painter below, not to its screen position.
            pass
        elif self.mood == Mood.ERROR:
            cx += math.sin(t * 12.0) * 2.0

        thinking_front_facing = True
        if self.mood == Mood.THINKING:
            # Fake a rotating *sphere*, not a flat coin: retain a round silhouette
            # and move a curved, shaded meridian across its surface. A sphere
            # remains circular while its surface markings and lighting rotate.
            painter.save()
            yaw = math.radians(self._spin_angle)
            thinking_front_facing = math.cos(yaw) > 0.0

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
        has_black_core = self.uses_black_core(self.mood)
        core_radius = radius * 0.63

        body = self._body_path(cx, cy, radius, t)
        # A broad, moving highlight gives every mood a living, liquid sheen.
        # Error keeps the same glossy motion, recolored into its warning-red theme.
        if self.mood == Mood.THINKING:
            # A smaller traveling specular reflection keeps the silhouette round.
            yaw_for_shine = math.radians(self._spin_angle)
            highlight_x = cx + math.sin(yaw_for_shine) * radius * 0.24
            highlight_y = cy - radius * 0.28
        else:
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

        if self.mood == Mood.THINKING:
            # Rotating meridian / limb shading sells spherical volume without
            # crushing the silhouette into a coin. The dark crescent shifts as
            # the sphere turns; a soft bright band travels opposite it.
            yaw = math.radians(self._spin_angle)
            facing = math.cos(yaw)
            side = math.sin(yaw)
            band_x = cx + side * radius * 0.50
            band = QRadialGradient(QPointF(band_x, cy - radius * 0.05), radius * 0.95)
            band.setColorAt(0.0, QColor(255, 255, 255, 62))
            band.setColorAt(0.42, QColor(210, 205, 255, 24))
            band.setColorAt(1.0, QColor(10, 8, 35, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(band))
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

            # A curved terminator creates the sense of a sphere turning in depth.
            shade_x = cx - side * radius * 0.42
            shade = QRadialGradient(QPointF(shade_x, cy), radius * 1.05)
            shade.setColorAt(0.0, QColor(18, 12, 55, 0))
            shade.setColorAt(0.58, QColor(18, 12, 55, 10))
            shade.setColorAt(0.84, QColor(8, 6, 30, int(80 + 65 * abs(side))))
            shade.setColorAt(1.0, QColor(5, 4, 20, int(115 + 70 * abs(side))))
            painter.setBrush(QBrush(shade))
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        # Thinking intentionally has no face, particles, or internal trail.

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
        if self.mood != Mood.THINKING:
            # Thinking is intentionally faceless: keep the spinning glossy sphere
            # and all of its shading/motion exactly as-is, with no eyes or mouth.
            self._draw_face(painter, cx, cy, face_radius, t)

        # No isolated specular dot: the broad animated gradient supplies the sheen.
        if self.mood == Mood.THINKING:
            painter.restore()
        painter.end()

    def _draw_face(self, painter: QPainter, cx: float, cy: float, r: float, t: float) -> None:
        mood = self.mood
        has_black_core = self.uses_black_core(mood)
        gaze_x = 0.0
        gaze_y = 0.0
        if mood == Mood.THINKING:
            # Keep the face fixed relative to the front surface; yaw itself
            # carries it out of view and back, so the eyes do not wander.
            gaze_x = 0.0
            gaze_y = -2.0
        elif mood == Mood.LISTENING:
            gaze_x = math.sin(t * 2.2) * 2.5
        elif mood in (Mood.HAPPY, Mood.EXCITED):
            gaze_y = -1.5
        elif mood == Mood.CURIOUS:
            gaze_x = r * 0.055
            gaze_y = -r * 0.035
        elif mood == Mood.SURPRISED:
            gaze_y = -r * 0.015
        elif mood in (Mood.SAD, Mood.EMPATHETIC):
            gaze_y = 3.0 if mood == Mood.SAD else 1.5
        elif mood == Mood.ERROR:
            gaze_x = math.sin(t * 14.0) * 2.0

        eye_y = cy - r * 0.015 + gaze_y
        eye_dx = r * 0.29
        eye_w = r * (0.115 if mood == Mood.SURPRISED else 0.105)
        eye_h = r * (0.29 if mood == Mood.SURPRISED else 0.245)

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

        if mood == Mood.SAD:
            eye_h *= 0.82
        elif mood == Mood.EMPATHETIC:
            eye_h *= 0.9
        elif mood in (Mood.HAPPY, Mood.EXCITED):
            eye_h *= 0.52
        elif mood == Mood.CURIOUS:
            eye_h *= 1.08
        elif mood == Mood.ERROR:
            eye_h *= 0.8

        for sign in (-1, 1):
            ex = cx + sign * eye_dx + gaze_x
            ey = eye_y
            this_eye_h = eye_h
            painter.save()
            painter.translate(ex, ey)
            if mood in (Mood.HAPPY, Mood.EXCITED):
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

        if mood == Mood.SPEAKING or self._speaking_active:
            # A readable, softly animated rose-lilac mouth: larger than a dot,
            # but still restrained, with a dark plum edge against the black core.
            voice = (math.sin(t * 11.0) + 1.0) / 2.0
            mouth_w = r * (0.19 + voice * 0.035)
            mouth_h = r * (0.055 + abs(math.sin(t * 11.0)) * 0.075)
            mouth_rect = QRectF(cx - mouth_w / 2, cy + r * 0.17, mouth_w, mouth_h)
            mouth_gradient = QLinearGradient(
                mouth_rect.left(), mouth_rect.top(), mouth_rect.right(), mouth_rect.bottom()
            )
            mouth_gradient.setColorAt(0.0, QColor("#ffb4d0"))
            mouth_gradient.setColorAt(0.52, QColor("#f472b6"))
            mouth_gradient.setColorAt(1.0, QColor("#c75aab"))
            painter.setPen(QPen(QColor("#3a1738"), max(1.0, r * 0.018)))
            painter.setBrush(QBrush(mouth_gradient))
            painter.drawEllipse(mouth_rect)
        elif mood == Mood.EXCITED:
            # A small open smile makes Excited distinct from calm Happy.
            mouth_w = r * 0.22
            mouth_h = r * (0.095 + abs(math.sin(t * 4.0)) * 0.035)
            mouth_rect = QRectF(cx - mouth_w / 2, cy + r * 0.17, mouth_w, mouth_h)
            painter.setPen(QPen(QColor("#4a174d"), max(1.0, r * 0.018)))
            painter.setBrush(QBrush(QColor("#5b174e")))
            painter.drawEllipse(mouth_rect)
        elif mood == Mood.SURPRISED:
            mouth_w, mouth_h = r * 0.095, r * 0.13
            mouth_rect = QRectF(cx - mouth_w / 2, cy + r * 0.17, mouth_w, mouth_h)
            painter.setPen(QPen(QColor("#4a174d"), max(1.0, r * 0.018)))
            painter.setBrush(QBrush(QColor("#3b1747")))
            painter.drawEllipse(mouth_rect)
        elif mood == Mood.CURIOUS:
            mouth_w, mouth_h = r * 0.13, r * 0.035
            mouth_rect = QRectF(cx - mouth_w / 2, cy + r * 0.20, mouth_w, mouth_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#3f255d")))
            painter.drawEllipse(mouth_rect)
        elif mood == Mood.EMPATHETIC:
            # A quiet, reassuring expression; distinct from the downturned Sad mood.
            comfort_arc = QPainterPath()
            comfort_arc.moveTo(cx - r * 0.11, cy + r * 0.23)
            comfort_arc.quadTo(cx, cy + r * 0.30, cx + r * 0.11, cy + r * 0.23)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#eff6ff"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(comfort_arc)
        elif mood == Mood.LISTENING:
            # Original calm listening face; no eyebrow gimmick or orbiting dots.
            pass
        elif mood == Mood.SAD:
            painter.setPen(QPen(QColor(235, 240, 255, 190), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(QRectF(cx - r * 0.13, cy + r * 0.19, r * 0.26, r * 0.12), 25 * 16, 130 * 16)
        elif mood == Mood.ERROR:
            painter.setPen(QPen(QColor("#ffe4e6"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(cx - r * 0.09, cy + r * 0.22), QPointF(cx + r * 0.09, cy + r * 0.22))
