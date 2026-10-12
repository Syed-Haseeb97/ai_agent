"""Regression tests for moving Ruby's visible popups with its orb."""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication

from ui.response_popup import ResponsePopup
from ui.status_popup import StatusPopup


class PopupAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_chat_reposition_tracks_new_anchor_without_hiding(self):
        popup = ResponsePopup()
        popup.show_chat(QPoint(700, 300))
        self.app.processEvents()
        popup.reposition(QPoint(250, 420))
        self.app.processEvents()
        self.assertTrue(popup.isVisible())
        self.assertNotEqual(popup.pos(), QPoint(700, 300))
        popup.hide_popup()
        popup.close()

    def test_status_reposition_tracks_new_anchor_without_resetting_state(self):
        popup = StatusPopup()
        popup.show_message("Thinking…", QPoint(700, 300))
        self.app.processEvents()
        initial_text = popup.eyebrow.text()
        popup.reposition(QPoint(250, 420))
        self.app.processEvents()
        self.assertTrue(popup.isVisible())
        self.assertEqual(popup.eyebrow.text(), initial_text)
        self.assertEqual(popup.eyebrow.text(), "R U B Y  ·  THINKING")
        popup.hide_popup()
        popup.close()


if __name__ == "__main__":
    unittest.main()
