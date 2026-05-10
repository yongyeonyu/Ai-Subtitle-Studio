import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.subtitle_text_edit import SubtitleTextEdit


class SubtitleTextEditScrollTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_scroll_path_defers_heavy_timestamp_refresh(self):
        editor = SubtitleTextEdit()
        try:
            editor.setPlainText("\n".join(f"line {idx:04d}" for idx in range(400)))
            editor._timestamp_update_timer.stop()
            editor._margin_update_timer.stop()

            editor._on_vertical_scroll_changed(120)

            self.assertTrue(editor._scroll_repaint_timer.isActive())
            self.assertTrue(editor._scroll_idle_refresh_timer.isActive())
            self.assertFalse(editor._timestamp_update_timer.isActive())
            self.assertFalse(editor._margin_update_timer.isActive())
        finally:
            editor.close()
            editor.deleteLater()


if __name__ == "__main__":
    unittest.main()
