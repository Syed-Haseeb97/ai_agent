import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from ui.response_popup import ResponsePopup


class ResponsePopupInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.popup = ResponsePopup()

    @classmethod
    def tearDownClass(cls):
        cls.popup.hide_popup()
        cls.popup.close()
        cls.popup.deleteLater()
        cls.app.processEvents()

    def setUp(self):
        self.popup.clear_history()
        self.popup.input_edit.clear()
        self.popup._dismiss_on_deactivate = True
        self.popup.move(40, 40)
        self.popup.show()
        self.app.processEvents()

    def tearDown(self):
        self.popup.hide_popup()
        self.app.processEvents()

    def _mouse_press(self, global_pos):
        pos = QPointF(global_pos)
        return QMouseEvent(
            QEvent.Type.MouseButtonPress,
            pos,
            pos,
            pos,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_clicking_outside_hides_chat(self):
        outside = QWidget()
        outside.setGeometry(700, 700, 80, 80)
        event = self._mouse_press(QPoint(720, 720))
        self.app.sendEvent(outside, event)
        self.assertFalse(self.popup.isVisible())
        outside.close()

    def test_click_inside_chat_does_not_dismiss_it(self):
        global_pos = self.popup.input_edit.mapToGlobal(QPoint(12, 12))
        event = self._mouse_press(global_pos)
        self.app.sendEvent(self.popup.input_edit, event)
        self.assertTrue(self.popup.isVisible())

    def test_close_button_hides_and_disarms_outside_dismissal(self):
        self.popup.close_button.click()
        self.assertFalse(self.popup.isVisible())
        self.assertFalse(self.popup._dismiss_on_deactivate)

    def test_user_content_is_escaped_as_plain_text(self):
        self.popup._append("user", "<script>alert('x')</script> & hello")
        html = self.popup.history.document().toHtml()
        self.assertIn("<script>alert('x')</script> & hello", self.popup.history.toPlainText())
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp; hello", html)

    def test_input_and_panel_have_polished_fixed_geometry(self):
        self.assertEqual(self.popup.size().width(), 456)
        self.assertEqual(self.popup.size().height(), 570)
        self.assertEqual(self.popup.input_edit.objectName(), "input")
        self.assertEqual(self.popup.history.objectName(), "history")


if __name__ == "__main__":
    unittest.main()
