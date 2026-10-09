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
        self.move(self._home)
        self._following = False

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

    @pyqtSlot(object)
    def follow_cursor(self, _action=None) -> None:
        """Begin following before an action; cancel a pending release if needed."""
        self._release_timer.stop()
        self._following = True

    @pyqtSlot(object)
    def release_cursor(self, _action=None) -> None:
        """Keep following briefly after fast clicks/moves so the motion is visible."""
        if self._following:
            self._release_timer.start()

    def return_home(self) -> None:
        self._release_timer.stop()
        self._following = False

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
        target = self._target_for_cursor() if self._following else self._home
        current = self.pos()
        dx, dy = target.x() - current.x(), target.y() - current.y()
        if abs(dx) <= 2 and abs(dy) <= 2:
            if current != target:
                self.move(target)
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
        super().closeEvent(event)
