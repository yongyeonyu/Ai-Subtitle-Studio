# Version: 03.14.03
# Phase: PHASE2
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QWheelEvent, QTextCursor
from PyQt6.QtCore import QObject, QPoint, QPointF, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTextEdit, QWidget

from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_helpers import build_segment_lookup
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


class _AutoQualityEditor:
    _schedule_auto_quality_review = EditorWidget._schedule_auto_quality_review
    _run_scheduled_auto_quality_review = EditorWidget._run_scheduled_auto_quality_review

    def __init__(self):
        self.settings = {"subtitle_quality_auto_correct_enabled": True}
        self.sm = SimpleNamespace(is_locked=False)
        self.playing = False
        self.review_calls = []

    def _is_video_playback_active(self):
        return bool(self.playing)

    def _run_quality_review(self, auto_correct=None):
        self.review_calls.append(auto_correct)


class _FakeScrubTimer:
    def __init__(self):
        self.start = Mock()
        self.isActive = Mock(return_value=False)


class _FakeWaveformWorker(QObject):
    ready = pyqtSignal(object, float)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = str(path or "")
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return None

    def wait(self, *_args, **_kwargs):
        return True


class TimelinePlayheadFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_quality_review_defers_while_video_is_playing(self):
        editor = _AutoQualityEditor()
        callbacks = []

        with patch("ui.editor.editor_widget.QTimer.singleShot", side_effect=lambda delay, cb: callbacks.append((delay, cb))):
            editor._schedule_auto_quality_review(delay_ms=10)
            self.assertEqual(callbacks[0][0], 10)

            editor.playing = True
            callbacks.pop(0)[1]()

            self.assertEqual(editor.review_calls, [])
            self.assertTrue(editor._auto_quality_review_pending)
            self.assertTrue(editor._auto_quality_review_scheduled)
            self.assertEqual(callbacks[-1][0], 1800)

            editor.playing = False
            callbacks.pop()[1]()

        self.assertEqual(editor.review_calls, [True])
        self.assertFalse(editor._auto_quality_review_pending)

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

    def test_scrub_updates_playhead_immediately_and_uses_lightweight_preview_seek(self):
        editor = _ClickEditor()
        editor.video_fps = 30.0
        editor._active_seg_start = None
        editor.applied_contexts = []
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

        with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=10.0):
            editor._on_scrub(3.0)

        editor.timeline.set_playhead.assert_called_once_with(3.0)
        editor.video_player.preview_seek.assert_called_once_with(3.0)
        self.assertEqual(editor.applied_contexts, [])
        editor._scrub_settle_timer.start.assert_called_once()

    def test_scrub_throttles_video_seek_during_fast_mouse_moves(self):
        editor = _ClickEditor()
        editor.video_fps = 30.0
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._last_scrub_preview_at = 10.0
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

        with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=10.01):
            editor._on_scrub(4.0)

        editor.timeline.set_playhead.assert_called_once_with(4.0)
        editor.video_player.preview_seek.assert_not_called()
        editor._scrub_preview_timer.start.assert_called_once()
        editor._scrub_settle_timer.start.assert_called_once()

    def test_settled_scrub_syncs_active_segment_without_recentering_timeline(self):
        editor = _ClickEditor()
        editor.video_fps = 30.0
        editor._pending_scrub_sec = 4.0
        editor._active_seg_start = None
        editor._cached_segs = [{"line": 2, "start": 4.0, "end": 5.0, "text": "셋째 줄"}]
        editor._apply_scrub_preview = Mock()
        editor._schedule_background_prefetch = Mock()
        editor._sync_cursor_to_seg = Mock()
        editor.timeline = SimpleNamespace(
            center_to_sec=Mock(),
            canvas=SimpleNamespace(playhead_sec=4.0, _multiclip_boxes=[]),
        )

        editor._apply_settled_scrub()

        editor._apply_scrub_preview.assert_called_once_with(4.0)
        editor._schedule_background_prefetch.assert_called_once()
        editor._sync_cursor_to_seg.assert_called_once_with(
            editor._cached_segs[0],
            ensure_visible=True,
            move_cursor=True,
        )
        editor.timeline.center_to_sec.assert_not_called()

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

    def test_seg_time_changed_schedules_resize_redraw_without_nameerror(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={"scroll_x": 120})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("첫 줄", 1.0, False))

            editor._on_seg_time_changed(0, 1.5, 2.0, "square_left")
            self.app.processEvents()

            ud = block.userData()
            self.assertIsInstance(ud, SubtitleBlockData)
            self.assertAlmostEqual(float(ud.start_sec), 1.5)
            editor.text_edit.update_margins.assert_called_once()
            editor.text_edit.timestampArea.update.assert_called_once()
            editor.timeline._begin_subtitle_resize_keep_view.assert_called_once()
            editor.timeline._finish_subtitle_resize_keep_view.assert_called_once()
            editor._redraw_timeline_preserve_resize_view.assert_called_once_with({"scroll_x": 120})
        finally:
            editor.text_edit.close()

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
        editor._schedule_video_context_refresh = Mock()

        try:
            editor._on_inline_text_changed(0, "입력중")

            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).text(), "원본")
            self.assertEqual(editor._cached_segs[0]["text"], "입력중")
            editor._refresh_video_subtitle_context.assert_not_called()
            editor._schedule_video_context_refresh.assert_not_called()

            editor.timeline.canvas._inline_commit_in_progress = True
            editor._on_inline_text_changed(0, "최종")

            self.assertEqual(editor.text_edit.document().findBlockByNumber(0).text(), "최종")
            self.assertEqual(editor._cached_segs[0]["text"], "최종")
            editor._refresh_video_subtitle_context.assert_not_called()
            editor._schedule_video_context_refresh.assert_called_once_with(24)
        finally:
            editor.text_edit.close()

    def test_line_text_edit_updates_memory_without_full_lookup_rebuild(self):
        editor = _DummyEditor()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("원본")
        block = editor.text_edit.document().findBlockByNumber(0)
        block.setUserData(SubtitleBlockData("00", 1.0, False))
        editor._cached_segs = [
            {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "원본",
                "quality": {"confidence_label": "green"},
            }
        ]
        editor._refresh_cached_line_map()
        editor._subtitle_memory_cache = build_segment_lookup(editor._cached_segs)

        try:
            with patch(
                "ui.editor.editor_segments.build_segment_lookup",
                side_effect=AssertionError("plain text edits should not rebuild every segment lookup"),
            ):
                changed = editor._update_subtitle_memory_line_text(0, "수정")

            self.assertTrue(changed)
            self.assertTrue(editor._segment_cache_valid)
            self.assertFalse(editor._subtitle_text_visibility_changed)
            self.assertEqual(editor._cached_segs[0]["text"], "수정")
            self.assertTrue(editor._cached_segs[0]["quality_stale"])
            self.assertEqual(editor._subtitle_memory_cache["line_map"][0]["text"], "수정")
            self.assertTrue(editor._subtitle_memory_cache["line_map"][0]["quality_stale"])
        finally:
            editor.text_edit.close()

    def test_line_text_edit_repaints_only_timeline_segment_rect(self):
        editor = _DummyEditor()
        segment = {
            "line": 3,
            "start": 10.0,
            "end": 11.0,
            "text": "원본",
            "quality": {"confidence_label": "yellow"},
        }
        dirty_rect = object()
        canvas = SimpleNamespace(
            segments=[segment],
            _segment_visual_style_cache={3: "cached"},
            _segment_for_line=Mock(return_value=segment),
            _segment_repaint_rect=Mock(return_value=dirty_rect),
            _update_dirty_rect=Mock(),
            update=Mock(),
        )
        editor.timeline = SimpleNamespace(canvas=canvas)

        changed = editor._update_timeline_segment_text_line(3, "수정")

        self.assertTrue(changed)
        self.assertEqual(segment["text"], "수정")
        self.assertTrue(segment["quality_stale"])
        self.assertEqual(canvas._segment_visual_style_cache, {})
        canvas._segment_repaint_rect.assert_called_once_with(segment, margin=72)
        canvas._update_dirty_rect.assert_called_once_with(dirty_rect)
        canvas.update.assert_not_called()

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

    def test_wheel_zoom_releases_fit_to_view_lock(self):
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
            event = QWheelEvent(
                QPointF(120, 40),
                QPointF(120, 40),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )

            timeline.wheelEvent(event)
            zoomed_pps = timeline.canvas.pps

            self.assertTrue(event.isAccepted())
            self.assertFalse(timeline._fit_to_view_locked)
            self.assertTrue(timeline._manual_zoom_since_fit)
            self.assertGreater(zoomed_pps, fit_pps)

            timeline.update_segments(
                [{"line": 0, "start": 0.0, "end": 240.0, "text": "생성 중"}],
                active_sec=0.0,
                total_dur=240.0,
            )

            self.assertEqual(timeline.canvas.pps, zoomed_pps)
        finally:
            timeline.close()

    def test_pending_fit_to_view_is_ignored_after_wheel_zoom(self):
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
            timeline.schedule_fit_to_view((0,))
            fit_pps = timeline.canvas.pps
            event = QWheelEvent(
                QPointF(120, 40),
                QPointF(120, 40),
                QPoint(0, 0),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.ControlModifier,
                Qt.ScrollPhase.ScrollUpdate,
                False,
            )

            timeline.wheelEvent(event)
            zoomed_pps = timeline.canvas.pps
            self.assertGreater(zoomed_pps, fit_pps)

            self.app.processEvents()
            self.app.processEvents()

            self.assertFalse(timeline._fit_to_view_locked)
            self.assertEqual(timeline.canvas.pps, zoomed_pps)
        finally:
            timeline.close()

    def test_fit_to_view_lock_blocks_generation_scroll_follow(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 10.0))
            timeline.scroll.horizontalScrollBar().setValue(300)

            timeline.fit_to_view()
            fit_pps = timeline.canvas.pps

            timeline.center_to_sec(120.0, smooth=False)
            timeline.follow_playhead(180.0, smooth=False)
            timeline.follow_playhead_centered(210.0, smooth=False)
            timeline.set_active(30.0)

            self.assertTrue(timeline._fit_to_view_locked)
            self.assertAlmostEqual(timeline.canvas.pps, fit_pps)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertEqual(timeline.canvas.playhead_sec, 210.0)
        finally:
            timeline.close()

    def test_set_active_does_not_recenter_when_segment_is_already_visible(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 300.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 10.0))
            self.app.processEvents()
            timeline.scroll.horizontalScrollBar().setValue(200)
            current_scroll = timeline.scroll.horizontalScrollBar().value()
            timeline.center_to_sec = Mock(side_effect=AssertionError("visible segment should not be recentered"))

            timeline.set_active(35.0)

            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), current_scroll)
            self.assertEqual(timeline._target_scroll_x, float(current_scroll))
            self.assertEqual(timeline._current_scroll_x, float(current_scroll))
        finally:
            timeline.close()

    def test_fit_to_view_lock_reapplies_after_generation_segment_updates(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 60.0
            timeline.global_canvas.total_duration = 60.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(60.0, 10.0))

            timeline.fit_to_view()

            timeline.update_segments(
                [{"line": 0, "start": 0.0, "end": 180.0, "text": "생성 중"}],
                active_sec=0.0,
                total_dur=180.0,
            )

            self.assertTrue(timeline._fit_to_view_locked)
            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(180.0))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertEqual(timeline.global_canvas.view_start, 0.0)
            self.assertEqual(timeline.global_canvas.view_end, 1.0)
        finally:
            timeline.close()

    def test_fit_to_view_uses_total_duration_while_partial_segments_generate(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 240.0
            timeline.global_canvas.total_duration = 240.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(240.0, 10.0))
            timeline.canvas.update_segments(
                [{"line": 0, "start": 0.0, "end": 12.0, "text": "일부 생성"}],
                active_sec=0.0,
                total_dur=240.0,
            )

            timeline.fit_to_view()

            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(240.0))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
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
            self.assertEqual(timeline.canvas._last_playhead_px, timeline.canvas._x(2.5))
            timeline.canvas.update.assert_not_called()
            self.assertEqual(timeline._playhead_overlay._sec, 2.5)
            self.assertIs(timeline._playhead_overlay.parent(), timeline.scroll.viewport())
        finally:
            timeline.close()

    def test_loading_new_single_waveform_clears_stale_duration_and_applies_ready_duration(self):
        timeline = TimelineWidget()
        try:
            timeline.canvas.total_duration = 44.0 * 60.0
            timeline.global_canvas.total_duration = 44.0 * 60.0
            timeline.canvas._multiclip_boxes = [{"start": 0.0, "end": 44.0 * 60.0, "index": 1}]
            timeline._selected_clip_idx = 0
            timeline._selected_clip_duration = 44.0 * 60.0
            timeline._selected_clip_label = "1"
            timeline._waveform_path = "/tmp/old.mp4"

            with patch("ui.timeline.timeline_widget.WaveformWorker", _FakeWaveformWorker):
                timeline.load_waveform("/tmp/new.mp4", force=True)

                self.assertEqual(timeline.canvas.total_duration, 0.0)
                self.assertEqual(timeline.global_canvas.total_duration, 0.0)
                self.assertEqual(timeline.canvas._multiclip_boxes, [])
                self.assertEqual(timeline._selected_clip_idx, -1)

                worker = timeline._wf_worker
                self.assertIsNotNone(worker)
                self.assertTrue(worker.started)

                worker.ready.emit([0.0, 0.5, 0.2], 24.0 * 60.0)
                self.app.processEvents()

            self.assertEqual(timeline.canvas.total_duration, 24.0 * 60.0)
            self.assertEqual(timeline.global_canvas.total_duration, 24.0 * 60.0)
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

    def test_paused_playhead_sync_uses_idle_timer_interval(self):
        editor = _DummyTimelineVideoEditor()
        playing_state = object()
        paused_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=paused_state),
        )
        editor.video_player = SimpleNamespace(media_player=player)
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=4.8),
            set_playback_center_lock=Mock(),
        )
        editor._playhead_timer = SimpleNamespace(
            interval=Mock(side_effect=[16, 80]),
            setInterval=Mock(),
        )
        editor._reset_playhead_smoothing = Mock()

        editor._sync_playhead()
        editor._sync_playhead()

        editor._playhead_timer.setInterval.assert_called_once_with(80)
        editor.timeline.set_playback_center_lock.assert_called_once_with(False)
        editor._reset_playhead_smoothing.assert_called_once_with(4.8)

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

    def test_playing_segment_boundary_moves_focused_editor_cursor(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=4200),
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
        editor.editor_popup = SimpleNamespace(is_visible=Mock(return_value=False))
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        editor.text_edit.hasFocus = Mock(return_value=True)
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._segments = [
            {"start": 4.0, "end": 5.0, "line": 2, "text": "셋째 줄"},
        ]

        try:
            editor._sync_playhead()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 2)
            editor._highlighter.set_current_line.assert_called_once_with(2)
            editor.timeline.canvas.set_active.assert_called_once_with(4.0)
        finally:
            editor.text_edit.close()

    def test_playing_segment_boundary_keeps_user_text_selection(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=4200),
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
        editor.editor_popup = SimpleNamespace(is_visible=Mock(return_value=False))
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        cursor = QTextCursor(editor.text_edit.document().findBlockByNumber(0))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        editor.text_edit.setTextCursor(cursor)
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._segments = [
            {"start": 4.0, "end": 5.0, "line": 2, "text": "셋째 줄"},
        ]

        try:
            editor._sync_playhead()

            self.assertTrue(editor.text_edit.textCursor().hasSelection())
            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            editor._highlighter.set_current_line.assert_called_once_with(2)
            editor.timeline.canvas.set_active.assert_called_once_with(4.0)
        finally:
            editor.text_edit.close()

    def test_playing_segment_boundary_respects_recent_editor_scroll(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=4200),
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
        editor.editor_popup = SimpleNamespace(is_visible=Mock(return_value=False))
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._last_editor_manual_scroll_at = time.monotonic()
        editor._segments = [
            {"start": 4.0, "end": 5.0, "line": 2, "text": "셋째 줄"},
        ]

        try:
            editor._sync_playhead()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 0)
            editor._highlighter.set_current_line.assert_called_once_with(2)
            editor.timeline.canvas.set_active.assert_called_once_with(4.0)
        finally:
            editor.text_edit.close()

    def test_playback_sync_uses_memory_segment_lookup_without_document_scan(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=4200),
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
        editor.editor_popup = SimpleNamespace(is_visible=Mock(return_value=False))
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._cached_segs = None
        editor._segments = []
        editor._subtitle_memory_cache = build_segment_lookup([
            {"start": 0.0, "end": 1.0, "line": 0, "text": "첫 줄"},
            {"start": 4.0, "end": 5.0, "line": 2, "text": "셋째 줄"},
        ])
        editor._get_current_segments = Mock(side_effect=AssertionError("document scan should not run during playback"))

        try:
            editor._sync_playhead()

            editor._get_current_segments.assert_not_called()
            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 2)
            editor.timeline.canvas.set_active.assert_called_once_with(4.0)
        finally:
            editor.text_edit.close()

    def test_settled_scrub_moves_editor_cursor_to_playhead_segment(self):
        editor = _PlaybackEditor()
        editor.video_fps = 30.0
        editor.video_player = SimpleNamespace(
            preview_seek=Mock(),
            set_subtitle_display_time=Mock(),
            media_player=None,
        )
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False),
            set_active=Mock(),
            set_playhead=Mock(),
        )
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄\n셋째 줄")
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._active_seg_start = 0.0
        editor._pending_scrub_sec = 4.2
        editor._schedule_background_prefetch = Mock()
        editor._subtitle_memory_cache = build_segment_lookup([
            {"start": 0.0, "end": 1.0, "line": 0, "text": "첫 줄"},
            {"start": 4.0, "end": 5.0, "line": 2, "text": "셋째 줄"},
        ])
        editor._segments = []

        try:
            editor._apply_settled_scrub()

            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 2)
            editor.timeline.set_active.assert_called_once_with(4.0)
            editor.timeline.set_playhead.assert_any_call(4.0)
            self.assertIsNone(editor._pending_scrub_sec)
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

    def test_playhead_overlay_stays_qwidget_to_keep_canvas_visible(self):
        timeline = TimelineWidget()
        try:
            self.assertIsNone(getattr(timeline._playhead_overlay, "_quick", None))
            self.assertTrue(timeline._playhead_overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertIs(timeline._playhead_overlay.parent(), timeline.scroll.viewport())
        finally:
            timeline.close()

    def test_playhead_busy_state_marks_overlay_and_canvas(self):
        timeline = TimelineWidget()
        try:
            timeline.canvas.total_duration = 10.0
            timeline.set_playhead(2.0)

            timeline.set_playhead_busy(True)

            self.assertTrue(getattr(timeline.canvas, "playhead_busy", False))
            self.assertTrue(getattr(timeline.global_canvas, "playhead_busy", False))
            self.assertTrue(getattr(timeline._playhead_overlay, "_busy", False))

            timeline.set_playhead_busy(False)

            self.assertFalse(getattr(timeline.canvas, "playhead_busy", True))
            self.assertFalse(getattr(timeline._playhead_overlay, "_busy", True))
        finally:
            timeline.close()

    def test_scan_cut_active_toggles_playhead_busy_state(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_player = SimpleNamespace(set_scan_cut_active=Mock())
        editor.timeline = SimpleNamespace(set_playhead_busy=Mock(), set_playback_center_lock=Mock())
        editor._auto_cut_boundary_scan_active = False

        editor._set_scan_cut_button_active(1)
        editor.timeline.set_playhead_busy.assert_called_with(True)

        editor.timeline.set_playhead_busy.reset_mock()
        editor._set_scan_cut_button_active(0)
        editor.timeline.set_playhead_busy.assert_called_with(False)

        editor.timeline.set_playhead_busy.reset_mock()
        editor._set_auto_cut_boundary_scan_active(True)
        editor.timeline.set_playhead_busy.assert_called_with(True)

    def test_auto_cut_boundary_preview_moves_playhead_without_thumbnail_work(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_fps = 30.0
        editor.timeline = SimpleNamespace(
            set_playback_center_lock=Mock(),
            set_playhead=Mock(),
            set_playhead_busy=Mock(),
        )
        editor.video_player = SimpleNamespace(
            info_label=SimpleNamespace(setText=Mock()),
            show_cached_thumbnail_at=Mock(),
            prefetch_thumbnail_at=Mock(),
            frame_step_seek=Mock(),
            seek_direct=Mock(),
        )
        editor._scan_source_and_local_sec = Mock(return_value=("/tmp/video.mp4", 12.0, {"local_sec": 12.0}))

        editor._preview_auto_cut_boundary_scan(12.0, 14.0)

        editor.timeline.set_playhead.assert_called_once_with(12.0)
        editor.video_player.info_label.setText.assert_called()
        editor.video_player.show_cached_thumbnail_at.assert_not_called()
        editor.video_player.prefetch_thumbnail_at.assert_not_called()
        editor.video_player.frame_step_seek.assert_not_called()
        editor.video_player.seek_direct.assert_not_called()
        editor._scan_source_and_local_sec.assert_not_called()

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

    def test_zoom_during_playback_releases_center_locked_overlay(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 120.0
            timeline.global_canvas.total_duration = 120.0
            timeline.canvas.pps = 10.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(120.0, 10.0))
            timeline.set_playhead(40.0)
            timeline.set_playback_center_lock(True)
            self.assertTrue(timeline._playhead_overlay._center_locked)

            timeline.zoom_in()
            self.app.processEvents()
            self.assertFalse(timeline._playhead_overlay._center_locked)

            old_x = timeline._playhead_overlay._sec * timeline.canvas.pps - timeline._playhead_overlay._scroll_x
            timeline.set_playhead(41.0)
            self.app.processEvents()
            new_x = timeline._playhead_overlay._sec * timeline.canvas.pps - timeline._playhead_overlay._scroll_x
            self.assertGreater(new_x, old_x)
        finally:
            timeline.close()


if __name__ == "__main__":
    unittest.main()
