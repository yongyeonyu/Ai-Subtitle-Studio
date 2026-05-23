import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.editor.editor_widget import (
    EDITOR_VIDEO_PLAYER_16_9_ASPECT,
    EDITOR_VIDEO_PLAYER_MIN_WIDTH,
    EditorWidget,
)


class EditorOpenLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_video_player_width_is_locked_to_height_based_16_9_slot(self):
        editor = EditorWidget(
            video_name="sample.mp4",
            segments=[],
            media_path="",
            defer_media_load=True,
        )
        try:
            editor.resize(1280, 720)
            editor.show()
            self.app.processEvents()

            editor.video_player._source_width = 1920
            editor.video_player._source_height = 1080
            editor.video_player._source_aspect = EDITOR_VIDEO_PLAYER_16_9_ASPECT
            editor._apply_fixed_video_preview_width()
            self.app.processEvents()

            margins = editor.video_player.layout().contentsMargins()
            expected_width = max(
                EDITOR_VIDEO_PLAYER_MIN_WIDTH,
                int(round(editor.video_player.video_container.height() * EDITOR_VIDEO_PLAYER_16_9_ASPECT))
                + margins.left()
                + margins.right(),
            )
            self.assertEqual(editor.video_frame.minimumWidth(), expected_width)
            self.assertEqual(editor.video_frame.maximumWidth(), expected_width)
            self.assertEqual(editor.video_player.minimumWidth(), expected_width)
            self.assertEqual(editor.video_player.maximumWidth(), expected_width)

            editor.video_player._source_width = 1080
            editor.video_player._source_height = 1080
            editor.video_player._source_aspect = 1.0
            editor._apply_fixed_video_preview_width()
            self.app.processEvents()

            self.assertEqual(editor.video_frame.minimumWidth(), expected_width)
            self.assertEqual(editor.video_frame.maximumWidth(), expected_width)
            self.assertEqual(editor.video_player.minimumWidth(), expected_width)
            self.assertEqual(editor.video_player.maximumWidth(), expected_width)
        finally:
            editor.close()

    def test_fixed_video_width_rebalances_initial_splitter_even_when_width_is_unchanged(self):
        editor = EditorWidget(
            video_name="sample.mp4",
            segments=[],
            media_path="",
            defer_media_load=True,
        )
        try:
            editor.resize(1600, 720)
            editor.show()
            self.app.processEvents()

            editor.video_player._source_width = 1920
            editor.video_player._source_height = 1080
            editor.video_player._source_aspect = EDITOR_VIDEO_PLAYER_16_9_ASPECT
            editor._apply_fixed_video_preview_width()
            self.app.processEvents()

            target_width = int(editor.video_frame.maximumWidth())
            total = max(1, int(editor.splitter.width()) - int(editor.splitter.handleWidth()))
            expected_editor_width = max(1, total - target_width)

            editor.splitter.setSizes([280, max(1, total - 280)])
            self.app.processEvents()
            self.assertLess(editor.splitter.sizes()[0], expected_editor_width - 100)

            editor._apply_fixed_video_preview_width()
            self.app.processEvents()

            sizes = editor.splitter.sizes()
            self.assertAlmostEqual(sizes[0], expected_editor_width, delta=2)
            self.assertAlmostEqual(sizes[1], target_width, delta=2)
        finally:
            editor.close()

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
