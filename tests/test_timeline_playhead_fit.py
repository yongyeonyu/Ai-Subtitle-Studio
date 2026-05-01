# Version: 03.02.06
# Phase: PHASE2
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QTextCursor
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.timeline.timeline_widget import TimelineWidget


class _DummyEditor(EditorSegmentsMixin):
    pass


class _DummyTimelineVideoEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


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

    def test_playhead_uses_overlay_without_canvas_body_repaint(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.canvas.update = Mock()
            timeline.set_playhead(2.5)
            self.app.processEvents()

            self.assertTrue(getattr(timeline.canvas, "_external_playhead_overlay", False))
            self.assertEqual(timeline.canvas.playhead_sec, 2.5)
            timeline.canvas.update.assert_not_called()
            self.assertEqual(timeline._playhead_overlay._sec, 2.5)
            self.assertIs(timeline._playhead_overlay.parent(), timeline.scroll.viewport())
        finally:
            timeline.close()

    def test_playhead_handle_right_click_menu_still_emits_with_overlay(self):
        timeline = TimelineWidget()
        emitted = []
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.set_playhead(2.5)
            timeline.playhead_menu_requested.connect(lambda pos, sec: emitted.append(sec))
            self.app.processEvents()

            handle_pos = QPoint(timeline.canvas._x(2.5), 9)
            QTest.mouseClick(timeline.canvas, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, handle_pos)

            self.assertEqual(emitted, [2.5])
        finally:
            timeline.close()

    def test_playing_segment_sync_does_not_jump_playhead_to_segment_start(self):
        editor = _DummyTimelineVideoEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
        )
        canvas = SimpleNamespace(playhead_sec=4.8, set_active=Mock())
        editor.video_player = SimpleNamespace(media_player=player)
        editor.timeline = SimpleNamespace(canvas=canvas, set_active=Mock(), set_playhead=Mock())
        editor._highlighter = SimpleNamespace(set_current_line=Mock())

        editor._sync_cursor_to_seg({"start": 4.0, "end": 6.0, "line": 3}, ensure_visible=False, move_cursor=False)

        canvas.set_active.assert_called_once_with(4.0)
        editor.timeline.set_active.assert_not_called()
        editor.timeline.set_playhead.assert_not_called()

    def test_playhead_smoothing_ignores_small_backward_jitter(self):
        editor = _DummyTimelineVideoEditor()
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=1.0))
        first = editor._smooth_playhead_sec(1.0, 10.0, 20.0)
        second = editor._smooth_playhead_sec(0.96, 10.016, 20.0)

        self.assertEqual(first, 1.0)
        self.assertGreaterEqual(second, first)

    def test_qml_playhead_overlay_asset_exists_for_gpu_path(self):
        qml_path = Path(__file__).resolve().parents[1] / "ui" / "qml" / "timeline_playhead_overlay.qml"
        self.assertTrue(qml_path.exists())
        text = qml_path.read_text(encoding="utf-8")
        self.assertIn("playheadX", text)
        self.assertIn("visiblePlayhead", text)

    def test_zoom_buttons_anchor_to_visible_playhead(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 100.0
            timeline.global_canvas.total_duration = 100.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(100.0, 10.0))
            self.app.processEvents()

            timeline.scroll.horizontalScrollBar().setValue(200)
            timeline.set_playhead(35.0)
            self.app.processEvents()
            old_playhead_x = timeline.canvas.playhead_sec * timeline.canvas.pps - timeline.scroll.horizontalScrollBar().value()

            timeline.zoom_in()
            self.app.processEvents()

            new_playhead_x = timeline.canvas.playhead_sec * timeline.canvas.pps - timeline.scroll.horizontalScrollBar().value()
            self.assertAlmostEqual(new_playhead_x, old_playhead_x, delta=1.0)
            self.assertGreater(timeline.canvas.pps, 10.0)
        finally:
            timeline.close()

    def test_zoom_buttons_center_offscreen_playhead(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 300.0
            timeline.global_canvas.total_duration = 300.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(300.0, 10.0))
            timeline.scroll.horizontalScrollBar().setValue(0)
            timeline.set_playhead(150.0)
            self.app.processEvents()

            viewport_center = timeline.scroll.viewport().width() / 2.0
            timeline.zoom_in()
            self.app.processEvents()

            new_playhead_x = timeline.canvas.playhead_sec * timeline.canvas.pps - timeline.scroll.horizontalScrollBar().value()
            self.assertAlmostEqual(new_playhead_x, viewport_center, delta=1.0)
        finally:
            timeline.close()


if __name__ == "__main__":
    unittest.main()
