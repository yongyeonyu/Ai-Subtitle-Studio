import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

from ui.editor.stable_render_frame import StableRenderFrame


class EditorStableFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_stable_render_frame_keeps_slot_minimum_size(self):
        frame = StableRenderFrame("UnitFrame", render_feature="timeline", min_width=320, min_height=180)
        try:
            frame.add_content(QLabel("content"))

            self.assertGreaterEqual(frame.minimumSizeHint().width(), 320)
            self.assertGreaterEqual(frame.minimumSizeHint().height(), 180)
            self.assertGreaterEqual(frame.sizeHint().width(), 320)
            self.assertGreaterEqual(frame.sizeHint().height(), 180)
            self.assertEqual(frame.property("renderFeature"), "timeline")
        finally:
            frame.close()
            frame.deleteLater()
            self.app.processEvents()

    def test_editor_builds_major_surfaces_inside_stable_frames(self):
        from ui.editor.editor_widget import EditorWidget

        with patch("ui.editor.editor_widget._dm_load_settings", return_value={}), \
             patch("ui.editor.editor_widget._dm_load_corrections", return_value={}), \
             patch("ui.editor.editor_widget._dm_load_rules", return_value={}):
            editor = EditorWidget("unit.mp4", [], media_path=None, defer_media_load=True)
        try:
            self.assertIsInstance(editor.editor_frame, StableRenderFrame)
            self.assertIsInstance(editor.video_frame, StableRenderFrame)
            self.assertIsInstance(editor.timeline_frame, StableRenderFrame)
            self.assertIs(editor.text_edit.parentWidget(), editor.editor_frame)
            self.assertIs(editor.video_player.parentWidget(), editor.video_frame)
            self.assertIs(editor.timeline.parentWidget(), editor.timeline_frame)
            self.assertEqual(editor.editor_frame.property("renderFeature"), "editor")
            self.assertEqual(editor.video_frame.property("renderFeature"), "video")
            self.assertEqual(editor.timeline_frame.property("renderFeature"), "timeline")
            self.assertGreaterEqual(editor.video_frame.height(), 420)
            self.assertGreaterEqual(editor.video_player.height(), 420)
            self.assertGreaterEqual(
                editor.timeline_frame.minimumSizeHint().height(),
                editor.timeline.minimumSizeHint().height(),
            )
        finally:
            editor.close()
            editor.deleteLater()
            self.app.processEvents()

    def test_editor_keeps_fixed_video_height_without_rebalancing_timeline(self):
        from ui.editor.editor_widget import EditorWidget

        with patch("ui.editor.editor_widget._dm_load_settings", return_value={}), \
             patch("ui.editor.editor_widget._dm_load_corrections", return_value={}), \
             patch("ui.editor.editor_widget._dm_load_rules", return_value={}):
            editor = EditorWidget("unit.mp4", [], media_path=None, defer_media_load=True)
        try:
            editor.resize(1680, 1050)
            editor.show()
            for _ in range(6):
                self.app.processEvents()
            editor._rebalance_video_timeline_heights()
            for _ in range(4):
                self.app.processEvents()

            self.assertGreaterEqual(editor.video_frame.height(), 420)
            self.assertGreaterEqual(editor.video_player.height(), 420)
            self.assertEqual(editor.timeline.canvas_height_bonus(), 0)
            self.assertEqual(editor.timeline_frame.height(), editor._timeline_base_height)
        finally:
            editor.close()
            editor.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
