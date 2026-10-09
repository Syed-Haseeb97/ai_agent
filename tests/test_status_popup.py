import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from ui.status_popup import StatusPopup


class StatusPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.popup = StatusPopup()

    def tearDown(self):
        self.popup.hide_popup()
        self.popup.close()
        self.popup.deleteLater()
        self.app.processEvents()

    def test_listening_has_clear_hierarchy_and_accent(self):
        self.popup.show_message("Listening…", QPoint(500, 300))
        self.assertEqual(self.popup.eyebrow.text(), "R U B Y  ·  LISTENING")
        self.assertEqual(self.popup.detail.text(), "I'm all ears")
        self.assertEqual(self.popup.icon.text(), "◉")
        self.assertTrue(self.popup._activity_timer.isActive())

    def test_thinking_uses_quiet_supportive_copy(self):
        self.popup.show_message("Thinking…", QPoint(500, 300))
        self.assertEqual(self.popup.eyebrow.text(), "R U B Y  ·  THINKING")
        self.assertEqual(self.popup.detail.text(), "Putting it together")
        self.assertEqual(self.popup.icon.text(), "✧")

    def test_speaking_explains_interrupt_action(self):
        self.popup.show_message("Speaking… • click to interrupt", QPoint(500, 300))
        self.assertEqual(self.popup.eyebrow.text(), "R U B Y  ·  SPEAKING")
        self.assertEqual(self.popup.detail.text(), "Tap Ruby to interrupt")

    def test_error_stops_activity_animation_and_shows_attention(self):
        self.popup.show_message("⚠️ Something broke", QPoint(500, 300), duration_ms=3500)
        self.assertEqual(self.popup.eyebrow.text(), "R U B Y  ·  NEEDS ATTENTION")
        self.assertIn("Something broke", self.popup.detail.text())
        self.assertFalse(self.popup._activity_timer.isActive())

    def test_hide_stops_all_timers(self):
        self.popup.show_message("Listening…", QPoint(500, 300), duration_ms=1000)
        self.popup.hide_popup()
        self.assertFalse(self.popup._hide_timer.isActive())
        self.assertFalse(self.popup._activity_timer.isActive())
        self.assertFalse(self.popup.isVisible())

    def test_capsule_has_compact_fixed_size_and_never_activates(self):
        self.assertEqual((self.popup.width(), self.popup.height()), (258, 66))
        self.assertTrue(self.popup.testAttribute(self.popup.WidgetAttribute.WA_ShowWithoutActivating))


if __name__ == "__main__":
    unittest.main()
