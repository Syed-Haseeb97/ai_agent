import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication

from ui.cursor_companion import CursorCompanion


class CursorCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.orb = CursorCompanion()

    def tearDown(self):
        self.orb.close()
        self.orb.deleteLater()
        self.app.processEvents()

    def test_overlay_is_click_through_and_non_activating(self):
        self.assertTrue(self.orb.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(self.orb.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertTrue(self.orb.windowFlags() & Qt.WindowType.WindowTransparentForInput)

    def test_follow_and_release_are_stateful_and_graceful(self):
        self.orb.follow_cursor()
        self.assertTrue(self.orb.following_cursor)
        self.orb.release_cursor()
        self.assertTrue(self.orb._release_timer.isActive())
        self.orb.follow_cursor()
        self.assertFalse(self.orb._release_timer.isActive())
        self.assertTrue(self.orb.following_cursor)
        self.orb.return_home()
        self.assertFalse(self.orb.following_cursor)

    def test_cursor_target_is_clamped_to_available_screen(self):
        target = self.orb._target_for_cursor()
        screen = QApplication.screenAt(target) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        self.assertGreaterEqual(target.x(), bounds.left())
        self.assertGreaterEqual(target.y(), bounds.top())
        self.assertLessEqual(target.x() + self.orb.width() - 1, bounds.right())
        self.assertLessEqual(target.y() + self.orb.height() - 1, bounds.bottom())

    def test_motion_interpolates_instead_of_teleporting(self):
        self.orb.move(QPoint(0, 0))
        self.orb._home = QPoint(100, 100)
        self.orb.return_home()
        self.orb._animate_position()
        self.assertNotEqual(self.orb.pos(), QPoint(100, 100))
        self.assertLess(self.orb.x(), 100)
        self.assertLess(self.orb.y(), 100)


if __name__ == "__main__":
    unittest.main()
