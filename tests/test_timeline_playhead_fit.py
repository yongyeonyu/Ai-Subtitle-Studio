# Version: 03.14.03
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
from PyQt6.QtWidgets import QApplication, QTextEdit, QWidget

from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_widget import EditorWidget
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_canvas import TimelineCanvasBase
from ui.timeline.timeline_global import GlobalCanvasBase


class _DummyEditor(EditorSegmentsMixin):
    pass


class _DummyTimelineVideoEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


class _PlaybackEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0

    def _get_current_segments(self):
        return self._segments


class _ClickEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0

    def _global_to_local_sec(self, sec: float) -> float:
        return float(sec)

    def _resolve_active_context(self, global_sec=None, clip_idx=None):
        return {
            "clip_file": "/tmp/current.mp4",
            "clip_idx": 0,
            "global_sec": float(global_sec or 0.0),
            "local_sec": float(global_sec or 0.0),
            "local_segments": [],
        }

    def _apply_active_context(self, ctx, autoplay=False, show_thumbnail=True):
        self.applied_contexts.append((ctx, autoplay, show_thumbnail))

    def _get_current_segments(self):
        return self._segments


class _InlineEditEditor:
    _on_inline_text_changed = EditorWidget._on_inline_text_changed


class _PipelineFitEditor(EditorPipelineMixin):
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

    def test_timeline_click_does_not_force_full_redraw(self):
        editor = _ClickEditor()
        editor._segments = [{"line": 0, "start": 3.0, "end": 4.0, "text": "클릭"}]
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._redraw_timeline = Mock()
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("클릭")
        editor.text_edit.setFocus = Mock()
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            set_playhead=Mock(),
            center_to_sec=Mock(),
            canvas=SimpleNamespace(playhead_sec=0.0),
        )
        editor.video_player = SimpleNamespace(
            pause_video=Mock(),
            seek_direct=Mock(),
            media_player=SimpleNamespace(
                PlaybackState=SimpleNamespace(PlayingState=object()),
                playbackState=Mock(return_value=None),
            ),
        )

        try:
            editor._on_timeline_seg_clicked(0, 3.0)

            editor.timeline.set_active.assert_called_once_with(3.0)
            editor.timeline.center_to_sec.assert_called_once()
            editor.text_edit.setFocus.assert_called_once()
            editor._redraw_timeline.assert_not_called()
        finally:
            editor.text_edit.close()

    def test_timeline_click_with_lock_edit_does_not_focus_or_move_editor_cursor(self):
        editor = _ClickEditor()
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "첫 줄"},
            {"line": 1, "start": 3.0, "end": 4.0, "text": "둘째 줄"},
        ]
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        editor.text_edit.setFocus = Mock()
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            set_playhead=Mock(),
            center_to_sec=Mock(),
            lock_chk=SimpleNamespace(isChecked=Mock(return_value=True)),
            canvas=SimpleNamespace(playhead_sec=0.0, setFocus=Mock()),
        )
        editor.video_player = SimpleNamespace(
            pause_video=Mock(),
            seek_direct=Mock(),
            media_player=SimpleNamespace(
                PlaybackState=SimpleNamespace(PlayingState=object()),
                playbackState=Mock(return_value=None),
            ),
        )

        try:
            editor._on_timeline_seg_clicked(1, 3.0)

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            editor.text_edit.setFocus.assert_not_called()
            editor.timeline.canvas.setFocus.assert_called_once()
            editor.timeline.set_active.assert_called_once_with(3.0)
        finally:
            editor.text_edit.close()

    def test_lock_edit_allows_canvas_inline_edit(self):
        editor = _ClickEditor()
        editor._segments = [{"line": 0, "start": 3.0, "end": 4.0, "text": "클릭"}]
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            lock_chk=SimpleNamespace(isChecked=Mock(return_value=True)),
            canvas=SimpleNamespace(start_inline_edit=Mock()),
        )
        editor.video_player = SimpleNamespace(
            pause_video=Mock(),
            seek_direct=Mock(),
        )

        editor._on_timeline_seg_double_clicked(0, 3.0)

        editor.timeline.canvas.start_inline_edit.assert_called_once_with(0, 3.0)

    def test_live_canvas_inline_edit_skips_editor_document_rewrite(self):
        editor = _InlineEditEditor()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("원본")
        block = editor.text_edit.document().findBlockByNumber(0)
        block.setUserData(SubtitleBlockData("", 0.0, False))
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(_edit_active=True, _inline_commit_in_progress=False)
        )
        editor._cached_segs = [{"line": 0, "start": 0.0, "end": 1.0, "text": "원본"}]
        editor._refresh_video_subtitle_context = Mock()

        try:
            editor._on_inline_text_changed(0, "입력중")

            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).text(), "원본")
            self.assertEqual(editor._cached_segs[0]["text"], "입력중")
            editor._refresh_video_subtitle_context.assert_not_called()

            editor.timeline.canvas._inline_commit_in_progress = True
            editor._on_inline_text_changed(0, "최종")

            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).text(), "최종")
            self.assertEqual(editor._cached_segs[0]["text"], "최종")
            editor._refresh_video_subtitle_context.assert_called_once()
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

    def test_fit_to_view_uses_full_multiclip_range_even_when_clip_is_selected(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            boxes = [
                {"index": 1, "start": 0.0, "end": 30.0},
                {"index": 2, "start": 30.0, "end": 75.0},
                {"index": 3, "start": 75.0, "end": 120.0},
            ]
            timeline.canvas._multiclip_boxes = list(boxes)
            timeline.canvas.total_duration = 120.0
            timeline.global_canvas.total_duration = 120.0
            timeline._waveform_mode = "multi"
            timeline._selected_clip_idx = 1
            timeline._selected_clip_offset = 30.0
            timeline._selected_clip_duration = 45.0
            timeline.canvas.pps = 20.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(120.0, 20.0))
            timeline.scroll.horizontalScrollBar().setValue(300)

            timeline.fit_to_view()

            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(120.0))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertEqual(timeline._target_scroll_x, 0.0)
            self.assertEqual(timeline._current_scroll_x, 0.0)
            self.assertEqual(timeline.global_canvas.view_start, 0.0)
            self.assertEqual(timeline.global_canvas.view_end, 1.0)
        finally:
            timeline.close()

    def test_auto_fit_to_view_respects_manual_zoom(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))

            timeline.fit_to_view()
            fit_pps = timeline.canvas.pps
            timeline.zoom_in()
            zoomed_pps = timeline.canvas.pps

            self.assertGreater(zoomed_pps, fit_pps)
            self.assertFalse(timeline.auto_fit_to_view())
            self.assertEqual(timeline.canvas.pps, zoomed_pps)

            timeline.schedule_fit_to_view((0,))
            self.app.processEvents()
            self.assertEqual(timeline.canvas.pps, zoomed_pps)
        finally:
            timeline.close()

    def test_placeholder_refresh_auto_fit_skips_during_playback(self):
        editor = _PipelineFitEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
        )
        editor.video_player = SimpleNamespace(media_player=player)
        timeline = SimpleNamespace(auto_fit_to_view=Mock(return_value=True))

        self.assertFalse(editor._auto_fit_timeline_if_user_view_allows(timeline))
        timeline.auto_fit_to_view.assert_not_called()

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

    def test_timeline_hides_manual_slider_but_keeps_programmatic_scroll(self):
        timeline = TimelineWidget()
        try:
            self.assertEqual(
                timeline.scroll.horizontalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )

            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()
            timeline.canvas.total_duration = 300.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(300.0, 10.0))

            timeline.center_to_sec(120.0, smooth=False)

            self.assertGreater(timeline.scroll.horizontalScrollBar().value(), 0)
        finally:
            timeline.close()

    def test_follow_playhead_starts_smooth_scroll_when_target_moves(self):
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

            timeline.follow_playhead(120.0, smooth=True, threshold_px=24.0)

            self.assertEqual(timeline.canvas.playhead_sec, 120.0)
            self.assertGreater(timeline._target_scroll_x, 0.0)
            self.assertTrue(timeline._smooth_scroll_timer.isActive())

            timeline._update_smooth_scroll()

            self.assertGreater(timeline.scroll.horizontalScrollBar().value(), 0)
        finally:
            timeline.close()

    def test_centered_playback_follow_locks_after_playhead_reaches_center(self):
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

            timeline.follow_playhead_centered(120.0, smooth=True)

            self.assertFalse(timeline._playback_center_lock)
            self.assertFalse(timeline._playhead_overlay._center_locked)
            self.assertTrue(timeline._pending_playback_center_lock)
            self.assertEqual(timeline.canvas.playhead_sec, 120.0)
            self.assertGreater(timeline._target_scroll_x, 0.0)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertTrue(timeline._smooth_scroll_timer.isActive())

            timeline._current_scroll_x = timeline._target_scroll_x
            timeline._update_smooth_scroll()

            self.assertTrue(timeline._playback_center_lock)
            self.assertTrue(timeline._playhead_overlay._center_locked)

            timeline.follow_playhead_centered(121.0, smooth=True)

            self.assertEqual(timeline.canvas.playhead_sec, 121.0)
            self.assertGreater(timeline._target_scroll_x, timeline.scroll.horizontalScrollBar().value())
            self.assertTrue(timeline._smooth_scroll_timer.isActive())

            timeline.set_playhead(2.0)

            self.assertFalse(timeline._playback_center_lock)
            self.assertFalse(timeline._playhead_overlay._center_locked)
        finally:
            timeline.close()

    def test_centered_playback_follow_keeps_early_playhead_moving_until_center(self):
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

            timeline.follow_playhead_centered(10.0, smooth=True)

            self.assertEqual(timeline.canvas.playhead_sec, 10.0)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertFalse(timeline._playback_center_lock)
            self.assertFalse(timeline._pending_playback_center_lock)
            self.assertFalse(timeline._playhead_overlay._center_locked)
            self.assertFalse(timeline._smooth_scroll_timer.isActive())
        finally:
            timeline.close()

    def test_manual_wheel_scroll_releases_center_lock_and_stops_smooth_follow(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 300.0
            timeline.global_canvas.total_duration = 300.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(300.0, 10.0))
            timeline.scroll.horizontalScrollBar().setValue(120)
            timeline.set_playback_center_lock(True)
            timeline._target_scroll_x = 800.0
            timeline._current_scroll_x = 120.0
            timeline._smooth_scroll_timer.start()

            timeline.apply_manual_horizontal_scroll_delta(160)

            current_scroll = timeline.scroll.horizontalScrollBar().value()
            self.assertEqual(current_scroll, 280)
            self.assertFalse(timeline._playback_center_lock)
            self.assertFalse(timeline._pending_playback_center_lock)
            self.assertFalse(timeline._smooth_scroll_timer.isActive())
            self.assertEqual(timeline._target_scroll_x, float(current_scroll))
            self.assertEqual(timeline._current_scroll_x, float(current_scroll))
            self.assertTrue(timeline._manual_scroll_active())
        finally:
            timeline.close()

    def test_centered_playback_follow_respects_recent_manual_scroll(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 300.0
            timeline.global_canvas.total_duration = 300.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(300.0, 10.0))
            timeline.scroll.horizontalScrollBar().setValue(300)
            timeline.apply_manual_horizontal_scroll_delta(0)

            timeline.follow_playhead_centered(120.0, smooth=True)

            self.assertEqual(timeline.canvas.playhead_sec, 120.0)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 300)
            self.assertFalse(timeline._playback_center_lock)
            self.assertFalse(timeline._pending_playback_center_lock)
            self.assertFalse(timeline._smooth_scroll_timer.isActive())
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

    def test_playing_segment_boundary_moves_editor_immediately(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=2100),
            duration=Mock(return_value=10000),
        )
        editor.video_player = SimpleNamespace(
            media_player=player,
            refresh_subtitle_context=Mock(),
            set_subtitle_display_time=Mock(),
        )
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock()),
            follow_playhead=Mock(),
            set_active=Mock(),
            set_playhead=Mock(),
        )
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._segments = [
            {"start": 2.0, "end": 3.0, "line": 1, "text": "둘째 줄"},
        ]

        try:
            editor._sync_playhead()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 1)
            editor._highlighter.set_current_line.assert_called_once_with(1)
            editor.timeline.canvas.set_active.assert_called_once_with(2.0)
            editor.video_player.set_subtitle_display_time.assert_called_once_with(2.1)
            editor.video_player.refresh_subtitle_context.assert_not_called()
            self.assertGreater(float(getattr(editor, "_last_editor_autoscroll_at", 0.0)), 0.0)
        finally:
            editor.text_edit.close()

    def test_playhead_sync_uses_video_frame_time_without_lag_smoothing(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=27_000),
            duration=Mock(return_value=60_000),
        )
        editor.video_player = SimpleNamespace(
            media_player=player,
            current_playback_frame_time=Mock(return_value=(810, 27.0)),
            set_subtitle_display_time=Mock(),
        )
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=10.0, _edit_active=False, set_active=Mock()),
            follow_playhead_centered=Mock(),
            follow_playhead=Mock(),
            set_active=Mock(),
        )
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("자막")
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = None
        editor._segments = [{"start": 27.0, "end": 28.0, "line": 0, "text": "자막"}]
        editor._playhead_display_sec = 10.0
        editor._playhead_anchor_global_sec = 10.0
        editor._playhead_anchor_mono = 100.0

        try:
            editor._sync_playhead()

            editor.timeline.follow_playhead_centered.assert_called_once_with(27.0, smooth=True)
            editor.timeline.follow_playhead.assert_not_called()
            editor.video_player.set_subtitle_display_time.assert_called_once_with(27.0)
            self.assertEqual(editor._playhead_display_sec, 27.0)
        finally:
            editor.text_edit.close()

    def test_playhead_smoothing_ignores_small_backward_jitter(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_fps = 30.0
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=1.0))
        first = editor._smooth_playhead_sec(1.0, 10.0, 20.0)
        second = editor._smooth_playhead_sec(0.96, 10.016, 20.0)

        self.assertEqual(first, 1.0)
        self.assertGreaterEqual(second, first)

    def test_timeline_playhead_snaps_to_current_video_frame(self):
        timeline = TimelineWidget()
        try:
            timeline.set_frame_rate(24.0)
            timeline.update_segments([{"start": 0.0, "end": 2.0, "text": "테스트"}], active_sec=0.0, total_dur=2.0)

            timeline.set_playhead(1.01)

            self.assertAlmostEqual(timeline.canvas.playhead_sec, 1.0, places=6)
            self.assertAlmostEqual(timeline.global_canvas.playhead_sec, 1.0, places=6)
        finally:
            timeline.close()

    def test_timeline_canvases_do_not_share_opengl_video_surface(self):
        self.assertIs(TimelineCanvasBase, QWidget)
        self.assertIs(GlobalCanvasBase, QWidget)

    def test_timeline_close_stops_waveform_threads(self):
        timeline = TimelineWidget()
        worker = SimpleNamespace(
            stop=Mock(),
            isRunning=Mock(return_value=True),
            wait=Mock(return_value=True),
        )
        timeline._wf_worker = worker
        try:
            timeline.stop_waveform_workers()

            worker.stop.assert_called_once()
            worker.wait.assert_called_once()
            self.assertIsNone(timeline._wf_worker)
        finally:
            timeline.close()

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
