import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import EditorWidget


class EditorOpenLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_initial_open_layout_moves_editor_to_top_and_applies_saved_time_window(self):
        segments = [
            {
                "start": float(index) + 0.95,
                "end": float(index) + 1.75,
                "text": f"자막 {index}",
                "speaker": "00",
            }
            for index in range(40)
        ]
        with patch("ui.timeline.timeline_widget.load_settings", return_value={"timeline_edit_window_seconds": 8}):
            editor = EditorWidget(
                video_name="sample.mp4",
                segments=segments,
                media_path="",
                defer_media_load=True,
            )
        try:
            editor.resize(1280, 720)
            editor.show()
            self.app.processEvents()

            text_bar = editor.text_edit.verticalScrollBar()
            text_bar.setValue(int(text_bar.maximum()))
            self.app.processEvents()
            self.assertGreaterEqual(int(text_bar.value()), int(text_bar.minimum()))

            editor._schedule_initial_open_layout((0,))
            self.app.processEvents()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            self.assertEqual(int(text_bar.value()), int(text_bar.minimum()))

            viewport_w = max(1, editor.timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, float(editor.timeline.canvas.pps))
            self.assertAlmostEqual(visible_seconds, 8.0, delta=0.35)
            self.assertEqual(editor.timeline.scroll.horizontalScrollBar().value(), 0)
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
