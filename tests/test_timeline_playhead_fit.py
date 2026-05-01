# Version: 03.02.06
# Phase: PHASE2
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_segments import EditorSegmentsMixin
from ui.timeline.timeline_widget import TimelineWidget


class _DummyEditor(EditorSegmentsMixin):
    pass


class TimelinePlayheadFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_selection_moves_timeline_playhead_to_segment_start(self):
        editor = _DummyEditor()
        editor._sync_lock = False
        editor._active_seg_start = -1.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        editor.editor_popup = SimpleNamespace(is_visible=lambda: False, close_popup=Mock())
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            set_playhead=Mock(),
            center_to_sec=Mock(),
        )
        editor.video_player = SimpleNamespace(pause_video=Mock(), seek=Mock())
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._quality_tooltip = lambda seg: ""
        editor._cached_segs = [
            {"line": 0, "start": 1.0, "end": 2.0},
            {"line": 1, "start": 5.0, "end": 6.0},
        ]

        try:
            block = editor.text_edit.document().findBlockByNumber(1)
            cursor = QTextCursor(block)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            editor.text_edit.setTextCursor(cursor)

            editor._on_selection_changed()

            editor.timeline.set_playhead.assert_called_once_with(5.0)
            editor.video_player.seek.assert_called_once_with(5.0)
        finally:
            editor.text_edit.close()

    def test_fit_to_view_allows_long_timeline_below_default_zoom(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 3600.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.pps = 50.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 50.0))
            timeline.scroll.horizontalScrollBar().setValue(1200)
            timeline.global_canvas.update_viewport(0.25, 0.5)

            timeline.fit_to_view()

            self.assertLess(timeline.canvas.pps, 5.0)
            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(dur))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertEqual(timeline._target_scroll_x, 0.0)
            self.assertEqual(timeline._current_scroll_x, 0.0)
            self.assertEqual(timeline.global_canvas.view_start, 0.0)
            self.assertEqual(timeline.global_canvas.view_end, 1.0)
        finally:
            timeline.close()


if __name__ == "__main__":
    unittest.main()
