import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.editor_segments_manual_edits import EditorSegmentsManualEditsMixin
from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_widget import TimelineWidget


class _SelectionEditor(EditorSegmentsManualEditsMixin):
    def __init__(self):
        self._sync_lock = False
        self._active_seg_start = -1.0
        self._timeline_drag_in_progress = False
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("first\nsecond")
        self.timeline = SimpleNamespace(
            set_active=Mock(),
            set_playhead=Mock(),
            ensure_sec_visible=Mock(),
            center_to_sec=Mock(),
        )
        self.video_player = SimpleNamespace(pause_video=Mock())
        self.editor_popup = SimpleNamespace(is_visible=Mock(return_value=False), close_popup=Mock())
        self._highlighter = SimpleNamespace(set_current_line=Mock())
        self._schedule_visible_quality_refresh = Mock()
        self._schedule_cursor_video_seek = Mock()
        self._quality_tooltip = Mock(return_value="")
        self._timeline_lock_edit_enabled = Mock(return_value=False)
        self._is_video_playback_active = Mock(return_value=False)
        self._cached_segs = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "first"},
            {"line": 1, "start": 5.0, "end": 6.0, "text": "second"},
        ]
        self._subtitle_memory_cache = build_segment_lookup(self._cached_segs)
        self._rebuild_subtitle_memory_cache = Mock(
            side_effect=AssertionError("selection should use the existing memory lookup")
        )
        self._get_current_segments = Mock(side_effect=AssertionError("selection must not rescan subtitle rows"))
        self._mark_dirty = Mock(side_effect=AssertionError("selection must not mark project dirty"))
        self._finalize_edit = Mock(side_effect=AssertionError("selection must not finalize edits"))
        self._on_seg_time_changed = Mock(side_effect=AssertionError("selection must not mutate subtitle timing"))


class NLESelectionViewStateIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_selection_updates_view_state_without_model_save_or_nle_write(self):
        editor = _SelectionEditor()
        try:
            block = editor.text_edit.document().findBlockByNumber(1)
            cursor = QTextCursor(block)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            editor.text_edit.setTextCursor(cursor)

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                editor._on_selection_changed()

            editor.timeline.set_active.assert_called_once_with(5.0)
            editor.timeline.set_playhead.assert_called_once_with(5.0)
            editor.timeline.ensure_sec_visible.assert_called_once()
            editor.timeline.center_to_sec.assert_not_called()
            editor._highlighter.set_current_line.assert_called_once_with(1)
            editor._schedule_cursor_video_seek.assert_called_once_with(5.0)
            editor._rebuild_subtitle_memory_cache.assert_not_called()
            editor._get_current_segments.assert_not_called()
            editor._mark_dirty.assert_not_called()
            editor._finalize_edit.assert_not_called()
            editor._on_seg_time_changed.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            editor.text_edit.close()
            editor.text_edit.deleteLater()
            self.app.processEvents()

    def test_canvas_active_segment_is_visual_only_without_rewriting_timeline_rows(self):
        canvas = TimelineCanvas()
        try:
            rows = [
                {"start": 1.0, "end": 2.0, "line": 0, "text": "A"},
                {"start": 5.0, "end": 6.0, "line": 1, "text": "B"},
            ]
            canvas.update_segments(rows, active_sec=0.0, total_dur=10.0)
            before_rows = [dict(row) for row in canvas.segments]
            canvas.update_segments = Mock(side_effect=AssertionError("active visual must not rewrite canvas rows"))

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                canvas.set_active(5.0)
                canvas.clear_active_visual()

            self.assertEqual(canvas.segments, before_rows)
            self.assertIsNone(canvas.active_seg_start)
            self.assertIsNone(canvas.active_seg_line)
            canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            canvas.close()
            canvas.deleteLater()
            self.app.processEvents()

    def test_timeline_set_active_keeps_selection_view_state_out_of_project_storage(self):
        timeline = TimelineWidget()
        try:
            rows = [
                {"start": 1.0, "end": 2.0, "line": 0, "text": "A"},
                {"start": 5.0, "end": 6.0, "line": 1, "text": "B"},
            ]
            timeline.resize(640, 180)
            timeline.update_segments(rows, active_sec=0.0, total_dur=10.0, fit_view=False)
            before_canvas_rows = [dict(row) for row in timeline.canvas.segments]
            before_global_rows = [dict(row) for row in timeline.global_canvas.segments]
            timeline.canvas.update_segments = Mock(side_effect=AssertionError("active selection must not rewrite canvas rows"))
            timeline.global_canvas.update_segments = Mock(
                side_effect=AssertionError("active selection must not rewrite global rows")
            )

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                timeline.set_active(5.0)

            self.assertEqual(timeline.canvas.segments, before_canvas_rows)
            self.assertEqual(timeline.global_canvas.segments, before_global_rows)
            timeline.canvas.update_segments.assert_not_called()
            timeline.global_canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            timeline.close()
            timeline.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
