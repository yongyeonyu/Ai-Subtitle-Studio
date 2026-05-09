import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QRect, QSize

from ui.dialogs.qml_popup import _bounded_popup_size, _clamp_popup_pos


class ContextMenuBoundsTests(unittest.TestCase):
    def test_popup_height_is_limited_to_available_screen(self):
        available = QRect(0, 0, 320, 240)

        bounded = _bounded_popup_size(QSize(260, 900), available, margin=8)

        self.assertEqual(bounded.width(), 260)
        self.assertEqual(bounded.height(), 224)

    def test_popup_width_is_limited_to_available_screen(self):
        available = QRect(0, 0, 220, 240)

        bounded = _bounded_popup_size(QSize(320, 120), available, margin=8)

        self.assertEqual(bounded.width(), 204)
        self.assertEqual(bounded.height(), 120)

    def test_popup_position_is_clamped_inside_screen(self):
        available = QRect(0, 0, 320, 240)

        pos = _clamp_popup_pos(QPoint(260, 220), QSize(120, 100), available, margin=8)

        self.assertEqual(pos.x(), 192)
        self.assertEqual(pos.y(), 132)


if __name__ == "__main__":
    unittest.main()
