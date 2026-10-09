"""Click-through liquid orb that trails Ruby's real Windows cursor."""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QWidget

from ui.liquid_blob import LiquidBlob, Mood


class CursorCompanion(QWidget):
    """Keep the existing orb renderer intact while smoothly following the cursor."""

    ORB_SIZE = 78
    CURSOR_GAP = 30
    FOLLOW_ALPHA = 0.28
    RELEASE_GRACE_MS = 520
    WALL_HIT_HOLD_MS = 720
    WALL_RECOIL_PX = 18

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedSize(self.ORB_SIZE, self.ORB_SIZE)

        self.blob = LiquidBlob(self)
        self.blob.setFixedSize(self.ORB_SIZE, self.ORB_SIZE)
        self.blob.move(0, 0)
        self.blob.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.blob.set_mood(Mood.IDLE)

        screen = QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()
        self._home = QPoint(
            max(bounds.left(), bounds.right() - self.ORB_SIZE - 18),
            max(bounds.top() + 18, 18),
        )
        self._wall_x = max(bounds.left(), bounds.right() - self.ORB_SIZE + 1)
        self.move(self._home)
        self._following = False
        self._return_phase = "idle"
        self._wall_hit_timer = QTimer(self)
        self._wall_hit_timer.setSingleShot(True)
        self._wall_hit_timer.setInterval(self.WALL_HIT_HOLD_MS)
        self._wall_hit_timer.timeout.connect(self._start_wall_recoil)

        self._release_timer = QTimer(self)
        self._release_timer.setSingleShot(True)
        self._release_timer.setInterval(self.RELEASE_GRACE_MS)
        self._release_timer.timeout.connect(self.return_home)

        self._motion_timer = QTimer(self)
        self._motion_timer.setInterval(16)
        self._motion_timer.timeout.connect(self._animate_position)
        self._motion_timer.start()

    @property
    def following_cursor(self) -> bool:
        return self._following

    @property
    def return_phase(self) -> str:
        """Current end-of-task animation phase, exposed for tests and diagnostics."""
        return self._return_phase

    @pyqtSlot(object)
    def follow_cursor(self, _action=None) -> None:
        """Begin following before an action; cancel any pending return animation."""
        self._release_timer.stop()
        self._wall_hit_timer.stop()
        self._following = True
        self._return_phase = "following"
        self.blob.set_mood(Mood.IDLE)

    @pyqtSlot(object)
    def release_cursor(self, _action=None) -> None:
        """Keep following briefly after fast clicks/moves so the motion is visible."""
        if self._following:
            self._release_timer.start()

    def return_home(self) -> None:
        """Dash to the right screen edge, get briefly dizzy, then settle at home."""
        self._release_timer.stop()
        self._wall_hit_timer.stop()
        self._following = False
        self._return_phase = "wall_approach"
        self._wall_x = self._right_edge_x()
        self.blob.set_mood(Mood.IDLE)

    def _right_edge_x(self) -> int:
        screen = QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()
        return max(bounds.left(), bounds.right() - self.ORB_SIZE + 1)

    def _start_wall_recoil(self) -> None:
        if self._return_phase != "dizzy":
            return
        # Recover the face first, then visibly recoil from the edge before going home.
        self.blob.set_mood(Mood.IDLE)
        self._return_phase = "wall_recoil"

    def _target_for_cursor(self) -> QPoint:
        cursor = QCursor.pos()
        screen = QApplication.screenAt(cursor) or QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else self.geometry()

        right_x = cursor.x() + self.CURSOR_GAP
        left_x = cursor.x() - self.ORB_SIZE - self.CURSOR_GAP
        if right_x + self.ORB_SIZE <= bounds.right():
            x = right_x
        else:
            x = left_x
        y = cursor.y() - self.ORB_SIZE // 3

        x = min(max(bounds.left(), x), bounds.right() - self.ORB_SIZE + 1)
        y = min(max(bounds.top(), y), bounds.bottom() - self.ORB_SIZE + 1)
        return QPoint(x, y)

    def _animate_position(self) -> None:
        if self._following:
            target = self._target_for_cursor()
        elif self._return_phase == "wall_approach":
            target = QPoint(self._wall_x, self._home.y())
        elif self._return_phase == "wall_recoil":
            target = QPoint(max(0, self._wall_x - self.WALL_RECOIL_PX), self._home.y())
        else:
            target = self._home

        current = self.pos()
        dx, dy = target.x() - current.x(), target.y() - current.y()
        if abs(dx) <= 2 and abs(dy) <= 2:
            if current != target:
                self.move(target)
            if self._return_phase == "wall_approach":
                self._return_phase = "dizzy"
                self.blob.set_mood(Mood.SURPRISED)
                self._wall_hit_timer.start()
            elif self._return_phase == "wall_recoil":
                self._return_phase = "home"
            elif self._return_phase == "home":
                self._return_phase = "idle"
                self.blob.set_mood(Mood.IDLE)
            return

        self.move(
            QPoint(
                current.x() + round(dx * self.FOLLOW_ALPHA),
                current.y() + round(dy * self.FOLLOW_ALPHA),
            )
        )

    def closeEvent(self, event) -> None:
        self._motion_timer.stop()
        self._release_timer.stop()
        self._wall_hit_timer.stop()
        super().closeEvent(event)
