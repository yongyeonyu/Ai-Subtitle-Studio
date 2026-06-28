import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.timeline.timeline_global import GlobalCanvas
from ui.timeline.timeline_widget import TimelineWidget


class _FakePoint:
    def __init__(self, x: int):
        self._x = int(x)

    def x(self) -> int:
        return self._x


class _MousePressEvent:
    def __init__(self, *, x: int, button=Qt.MouseButton.LeftButton):
        self._point = _FakePoint(x)
        self._button = button
        self.accepted = False

    def button(self):
        return self._button

    def pos(self):
        return self._point

    def accept(self):
        self.accepted = True


class _FakeScrubTimer:
    def __init__(self):
        self.start = Mock()

    def setSingleShot(self, value):
        pass

    @property
    def timeout(self):
        return SimpleNamespace(connect=Mock())


class _PlayheadJumpEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


class TimelinePlayheadJumpIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_global_canvas_click_emits_seek_fraction_without_model_or_nle_write(self):
        canvas = GlobalCanvas()
        try:
            canvas.resize(200, 80)
            rows = [{"start": 0.0, "end": 2.0, "text": "A"}]
            canvas.update_segments(rows, 20.0)
            before_rows = [dict(row) for row in canvas.segments]
            emitted = []
            canvas.seek_frac.connect(emitted.append)
            canvas.update_segments = Mock(side_effect=AssertionError("playhead jump must not rewrite minimap rows"))

            event = _MousePressEvent(x=50)
            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                canvas.mousePressEvent(event)

            self.assertEqual(emitted, [0.25])
            self.assertEqual(canvas.segments, before_rows)
            canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            canvas.close()
            canvas.deleteLater()
            self.app.processEvents()

    def test_timeline_global_seek_emits_scrub_without_rewriting_rows_or_nle_journal(self):
        widget = TimelineWidget()
        try:
            rows = [{"start": 0.0, "end": 2.0, "text": "A", "line": 0}]
            widget.resize(640, 180)
            widget.update_segments(rows, active_sec=0.0, total_dur=100.0, fit_view=False)
            widget.canvas.total_duration = 100.0
            before_canvas_rows = [dict(row) for row in widget.canvas.segments]
            before_global_rows = [dict(row) for row in widget.global_canvas.segments]
            emitted = []
            widget.scrub_sec.connect(emitted.append)
            widget.canvas.update_segments = Mock(side_effect=AssertionError("playhead jump must not rewrite canvas rows"))
            widget.global_canvas.update_segments = Mock(side_effect=AssertionError("playhead jump must not rewrite global rows"))

            with patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                widget._on_global_seek(0.4)

            self.assertEqual(len(emitted), 1)
            self.assertAlmostEqual(emitted[0], 40.0, places=3)
            self.assertEqual(widget.canvas.segments, before_canvas_rows)
            self.assertEqual(widget.global_canvas.segments, before_global_rows)
            widget.canvas.update_segments.assert_not_called()
            widget.global_canvas.update_segments.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_editor_scrub_updates_playhead_preview_without_validation_save_or_nle_write(self):
        editor = _PlayheadJumpEditor()
        editor.video_fps = 30.0
        editor._active_seg_start = None
        editor._scrub_preview_timer = _FakeScrubTimer()
        editor._scrub_settle_timer = _FakeScrubTimer()
        editor.timeline = SimpleNamespace(
            set_playhead=Mock(),
            canvas=SimpleNamespace(playhead_sec=0.0, _multiclip_boxes=[]),
        )
        editor.video_player = SimpleNamespace(
            preview_seek=Mock(),
            set_subtitle_display_time=Mock(),
        )
        heavy_methods = {
            "_get_current_segments": Mock(side_effect=AssertionError("scrub must not validate or rescan subtitle rows")),
            "_sync_cursor_to_seg": Mock(side_effect=AssertionError("scrub settle may sync later, not in immediate jump path")),
            "_schedule_background_prefetch": Mock(side_effect=AssertionError("scrub prefetch must stay out of immediate jump path")),
            "_finalize_edit": Mock(side_effect=AssertionError("scrub must not finalize edits")),
            "_mark_dirty": Mock(side_effect=AssertionError("scrub must not mark project dirty")),
            "_on_seg_time_changed": Mock(side_effect=AssertionError("scrub must not mutate subtitle timing")),
        }
        for name, value in heavy_methods.items():
            setattr(editor, name, value)
        dual_write_names = (
            "apply_caption_delete_dual_write_pilot",
            "apply_caption_merge_dual_write_pilot",
            "apply_caption_move_commit_dual_write_pilot",
            "apply_caption_move_dual_write_pilot",
            "apply_caption_range_replace_dual_write_pilot",
            "apply_caption_resize_dual_write_pilot",
            "apply_caption_split_dual_write_pilot",
            "apply_caption_text_edit_dual_write_pilot",
            "apply_gap_generate_dual_write_pilot",
        )
        patches = [
            patch(f"ui.editor.ux.editor_timeline_video.{name}", Mock(name=name))
            for name in dual_write_names
        ]
        started = [p.start() for p in patches]
        try:
            with patch("ui.editor.ux.editor_timeline_video.time.monotonic", return_value=10.0), \
                 patch("core.project.nle_project_state.record_nle_operation_journal_entry") as record_journal, \
                 patch("core.project.project_io.write_project_file") as write_project:
                editor._on_scrub(3.0)

            editor.timeline.set_playhead.assert_called_once_with(3.0)
            editor.video_player.preview_seek.assert_called_once_with(3.0)
            editor.video_player.set_subtitle_display_time.assert_called_once_with(3.0)
            editor._scrub_settle_timer.start.assert_called_once()
            for heavy in heavy_methods.values():
                heavy.assert_not_called()
            for patched in started:
                patched.assert_not_called()
            record_journal.assert_not_called()
            write_project.assert_not_called()
        finally:
            for p in reversed(patches):
                p.stop()


if __name__ == "__main__":
    unittest.main()
