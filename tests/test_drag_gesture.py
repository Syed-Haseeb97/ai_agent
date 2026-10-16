"""Regression tests for Ruby's click-versus-drag gesture threshold."""

import unittest

from PyQt6.QtCore import QPoint

from ui.drag_gesture import drag_threshold_exceeded


class DragGestureTests(unittest.TestCase):
    def test_stationary_release_is_not_a_drag(self):
        self.assertFalse(drag_threshold_exceeded(QPoint(900, 40), QPoint(900, 40), 10))

    def test_small_pointer_jitter_stays_a_click(self):
        self.assertFalse(drag_threshold_exceeded(QPoint(900, 40), QPoint(903, 42), 10))

    def test_horizontal_reposition_is_a_drag(self):
        self.assertTrue(drag_threshold_exceeded(QPoint(900, 40), QPoint(100, 40), 10))

    def test_diagonal_reposition_is_a_drag(self):
        self.assertTrue(drag_threshold_exceeded(QPoint(900, 40), QPoint(100, 900), 10))

    def test_exact_threshold_counts_as_drag(self):
        self.assertTrue(drag_threshold_exceeded(QPoint(10, 10), QPoint(20, 10), 10))


if __name__ == "__main__":
    unittest.main()
