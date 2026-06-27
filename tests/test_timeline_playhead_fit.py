# Version: 03.14.03
# Phase: PHASE2
import copy
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QWheelEvent, QTextCursor
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QTextEdit, QWidget

from core.frame_time import frame_to_sec
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_helpers import build_segment_lookup
from ui.editor.editor_pipeline import EditorPipelineMixin
from ui.editor.editor_pipeline_playhead_actions import EditorPipelinePlayheadActionsMixin
from ui.editor.editor_speaker_ops import EditorSpeakerOpsMixin
from ui.editor.editor_widget import EditorWidget
from ui.editor.subtitle_text_edit import SubtitleBlockData
from ui.editor.ux.editor_tab_timing import EditorTabTimingMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.editor_segments_timeline_context import EditorSegmentsTimelineContextMixin
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_canvas import TimelineCanvasBase
from ui.timeline.timeline_global import (
    GlobalCanvasBase,
    MINIMAP_HEIGHT,
    MINIMAP_MARKER_LANE_H,
    MINIMAP_PRELIMINARY_LANE_BG,
    MINIMAP_REFERENCE_LANE_BG,
    MINIMAP_SILENCE_LANE_BG,
    MINIMAP_SUBTITLE_LANE_BG,
    MINIMAP_TOP_LANE_BG,
)


class _DummyEditor(EditorSegmentsMixin):
    pass


class _TabTimingEditor(EditorTabTimingMixin, EditorSegmentsMixin):
    def _current_frame_fps(self) -> float:
        return 30.0

    def _get_current_segments(self):
        return list(getattr(self, "_segments", []) or [])


class _ProjectLoadedPreviewEditor(EditorSegmentsTimelineContextMixin):
    def _build_live_subtitle_preview_segments(self, preview, confirmed):
        return [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "임시 자막",
                "_live_subtitle_preview": True,
            }
        ]


class _GuardedSegmentList(list):
    def __init__(self, *args):
        super().__init__(*args)
        self.fail_on_iter = False

    def __iter__(self):
        if self.fail_on_iter:
            raise AssertionError("cached subtitle context index should avoid rescanning the source list")
        return super().__iter__()


class _DummyTimelineVideoEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


class _ResizeTimelineEditor(EditorTimelineVideoMixin, EditorSegmentsMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


class _SpeakerDropTimelineEditor(EditorSpeakerOpsMixin, EditorTimelineVideoMixin, EditorSegmentsMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0


class _PlaybackEditor(EditorTimelineVideoMixin):
    def _multiclip_active_offset(self) -> float:
        return 0.0

    def _get_current_segments(self):
        return self._segments


class _PlayheadMenuEditor(EditorPipelinePlayheadActionsMixin):
    def __init__(self):
        self.settings = {"playhead_auto_cut_magnet_enabled": False}

    def _current_cut_boundary_level(self) -> str:
        return "medium"

    def _shadow_playhead_active(self) -> bool:
        return False


class _WaveformReadyTimeline(TimelineWidget):
    def __init__(self):
        super().__init__()
        self._test_sender = None

    def sender(self):
        return self._test_sender


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


class _InlineEditEditor(EditorSegmentsMixin):
    _on_inline_text_changed = EditorWidget._on_inline_text_changed


class _TextEditedEditor(EditorSegmentsMixin):
    _on_text_edited = EditorWidget._on_text_edited


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

    def test_segment_start_shortcut_prefers_active_canvas_segment_over_cursor_block(self):
        editor = _DummyEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._redraw_timeline = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 5.0))
        cursor = QTextCursor(first_block)
        editor.text_edit.setTextCursor(cursor)
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=5.0, playhead_sec=6.0))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._set_segment_start_to_playhead()

            self.assertAlmostEqual(first_block.userData().start_sec, 1.0)
            self.assertAlmostEqual(second_block.userData().start_sec, 6.0)
            editor._undo_mgr.push_immediate.assert_called_once()
            editor._redraw_timeline.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_segment_end_shortcut_falls_back_to_cursor_block_without_active_canvas_segment(self):
        editor = _DummyEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._redraw_timeline = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 5.0))
        cursor = QTextCursor(first_block)
        editor.text_edit.setTextCursor(cursor)
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=None, active_seg_start=None, playhead_sec=3.0))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._set_segment_end_to_playhead()

            gap_block = first_block.next()
            self.assertTrue(gap_block.isValid())
            self.assertIsInstance(gap_block.userData(), SubtitleBlockData)
            self.assertTrue(gap_block.userData().is_gap)
            self.assertAlmostEqual(gap_block.userData().start_sec, 3.0)
            editor._undo_mgr.push_immediate.assert_called_once()
            editor._redraw_timeline.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_tab_extends_nearest_previous_subtitle_end_to_playhead(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=2.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 4.0, end_sec=5.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "첫 줄"},
            {"line": 1, "start": 4.0, "end": 5.0, "text": "둘째 줄"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=4.0, playhead_sec=2.6))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(0, 1.0, 2.6, "square_right")
        finally:
            editor.text_edit.close()

    def test_tab_extends_nearest_next_subtitle_start_to_playhead(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=2.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 4.0, end_sec=5.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "첫 줄"},
            {"line": 1, "start": 4.0, "end": 5.0, "text": "둘째 줄"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=0, active_seg_start=1.0, playhead_sec=3.7))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(1, 3.7, 5.0, "square_left")
        finally:
            editor.text_edit.close()

    def test_tab_moves_attached_boundary_as_diamond(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n붙은 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=4.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 4.0, end_sec=6.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 4.0, "text": "앞 자막"},
            {"line": 1, "start": 4.0, "end": 6.0, "text": "붙은 자막"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=4.0, playhead_sec=4.5))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            self.assertEqual(
                editor._on_seg_time_changed.call_args_list,
                [
                    call(0, 1.0, 4.5, "diamond"),
                    call(1, 4.5, 6.0, "diamond"),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_tab_prefers_gap_extension_over_unrelated_nearby_diamond_pair(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("붙은 앞 자막\n현재 자막\n다음 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=3.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 3.0, end_sec=4.0))
        third_block = editor.text_edit.document().findBlockByNumber(2)
        third_block.setUserData(SubtitleBlockData("00", 6.0, end_sec=7.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 3.0, "text": "붙은 앞 자막"},
            {"line": 1, "start": 3.0, "end": 4.0, "text": "현재 자막"},
            {"line": 2, "start": 6.0, "end": 7.0, "text": "다음 자막"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=3.0, playhead_sec=4.5))
        editor.video_player = SimpleNamespace(current_time=0.0)
        editor._subtitle_magnet_policy = lambda allow_sync_override=True: {
            "continuous_threshold_sec": 1.0,
            "lora_micro_merge_gap_sec": 0.3,
            "deep_bridge_gap_sec": 0.3,
            "lora_micro_merge_min_duration": 0.8,
            "split_length_threshold": 20,
        }

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(1, 3.0, 4.5, "square_right")
        finally:
            editor.text_edit.close()

    def test_tab_extends_single_nearest_edge_for_detached_gap(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("짧다\n다음 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=2.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 3.0, end_sec=4.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "짧다", "spk": "00"},
            {"line": 1, "start": 3.0, "end": 4.0, "text": "다음 자막", "spk": "00"},
        ]
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(
                active_seg_line=0,
                active_seg_start=1.0,
                playhead_sec=2.5,
            )
        )
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(0, 1.0, 2.5, "square_right")
        finally:
            editor.text_edit.close()

    def test_tab_moves_nearby_existing_diamond_before_extending_other_edges(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("붙은 앞 자막\n붙은 뒤 자막\n멀리 떨어진 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=4.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 4.0, end_sec=6.0))
        third_block = editor.text_edit.document().findBlockByNumber(2)
        third_block.setUserData(SubtitleBlockData("00", 8.0, end_sec=9.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 4.0, "text": "붙은 앞 자막"},
            {"line": 1, "start": 4.0, "end": 6.0, "text": "붙은 뒤 자막"},
            {"line": 2, "start": 8.0, "end": 9.0, "text": "멀리 떨어진 자막"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=4.0, playhead_sec=4.5))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            self.assertEqual(
                editor._on_seg_time_changed.call_args_list,
                [
                    call(0, 1.0, 4.5, "diamond"),
                    call(1, 4.5, 6.0, "diamond"),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_tab_trims_current_subtitle_start_when_playhead_is_inside_detached_segment(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n현재 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 1.0, end_sec=4.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 5.0, end_sec=8.0))
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 4.0, "text": "앞 자막"},
            {"line": 1, "start": 5.0, "end": 8.0, "text": "현재 자막"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=1, active_seg_start=5.0, playhead_sec=5.6))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(1, 5.6, 8.0, "square_left")
        finally:
            editor.text_edit.close()

    def test_tab_trims_current_subtitle_end_when_playhead_is_inside_detached_segment(self):
        editor = _TabTimingEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor._on_seg_time_changed = Mock()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("현재 자막\n뒤 자막")
        first_block = editor.text_edit.document().findBlockByNumber(0)
        first_block.setUserData(SubtitleBlockData("00", 5.0, end_sec=8.0))
        second_block = editor.text_edit.document().findBlockByNumber(1)
        second_block.setUserData(SubtitleBlockData("00", 9.0, end_sec=11.0))
        editor._segments = [
            {"line": 0, "start": 5.0, "end": 8.0, "text": "현재 자막"},
            {"line": 1, "start": 9.0, "end": 11.0, "text": "뒤 자막"},
        ]
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(active_seg_line=0, active_seg_start=5.0, playhead_sec=7.7))
        editor.video_player = SimpleNamespace(current_time=0.0)

        try:
            editor._trigger_magnet()

            editor._undo_mgr.push_immediate.assert_called_once()
            editor._on_seg_time_changed.assert_called_once_with(0, 5.0, 7.7, "square_right")
        finally:
            editor.text_edit.close()

    def test_tab_no_longer_falls_back_to_canvas_diamond_snap(self):
        editor = _TabTimingEditor()
        editor._on_seg_time_changed = Mock()
        editor._segments = []
        canvas = SimpleNamespace(playhead_sec=3.0, _snap_closest_diamond=Mock())
        editor.timeline = SimpleNamespace(canvas=canvas)

        changed = editor._trigger_magnet()

        self.assertFalse(changed)
        canvas._snap_closest_diamond.assert_not_called()

    def test_timeline_canvas_tab_requests_editor_timing_action(self):
        timeline = TimelineWidget()
        calls = []
        try:
            timeline.tab_timing_requested.connect(lambda: calls.append("tab"))
            timeline.canvas._snap_closest_diamond = Mock()
            timeline.canvas.setFocus()

            QTest.keyClick(timeline.canvas, Qt.Key.Key_Tab)
            self.app.processEvents()

            self.assertTrue(calls)
            timeline.canvas._snap_closest_diamond.assert_not_called()
        finally:
            timeline.close()
            timeline.deleteLater()
            self.app.processEvents()

    def test_project_loaded_stt_preview_does_not_add_subtitle_draft_lane(self):
        editor = _ProjectLoadedPreviewEditor()
        editor._stt_preview_subtitle_drafts_enabled = False
        editor._live_stt_preview_segments = [
            {"start": 0.0, "end": 1.0, "text": "후보", "stt_pending": True, "stt_preview_source": "STT1"}
        ]
        confirmed = [{"start": 1.0, "end": 2.0, "text": "확정"}]

        combined = editor._timeline_segments_with_live_preview(confirmed)

        self.assertEqual([row["text"] for row in combined], ["후보", "확정"])
        self.assertFalse(any(row.get("_live_subtitle_preview") for row in combined))

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

    def test_auto_quality_review_defers_after_recent_editor_activity(self):
        editor = _AutoQualityEditor()
        callbacks = []

        with patch("ui.editor.editor_widget.QTimer.singleShot", side_effect=lambda delay, cb: callbacks.append((delay, cb))):
            editor._schedule_auto_quality_review(delay_ms=10)
            self.assertEqual(callbacks[0][0], 10)

            editor._last_editor_foreground_activity_at = time.monotonic()
            callbacks.pop(0)[1]()

            self.assertEqual(editor.review_calls, [])
            self.assertTrue(editor._auto_quality_review_pending)
            self.assertTrue(editor._auto_quality_review_scheduled)
            self.assertEqual(callbacks[-1][0], 1200)

            editor._last_editor_foreground_activity_at = time.monotonic() - 10.0
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

    def test_cursor_move_does_not_seek_video_while_playing(self):
        editor = _DummyEditor()
        editor._sync_lock = False
        editor._active_seg_start = -1.0
        editor._timeline_lock_edit_enabled = lambda: False
        editor._is_video_playback_active = lambda: True
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            set_playhead=Mock(),
            ensure_sec_visible=Mock(),
            center_to_sec=Mock(),
        )
        editor.video_player = SimpleNamespace(pause_video=Mock(), seek=Mock())
        editor._schedule_cursor_video_seek = Mock()
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor._quality_tooltip = lambda seg: ""
        editor._schedule_visible_quality_refresh = Mock()
        editor._cached_segs = [
            {"line": 0, "start": 1.0, "end": 2.0},
            {"line": 1, "start": 5.0, "end": 6.0},
        ]

        try:
            editor._rebuild_subtitle_memory_cache(editor._cached_segs)
            block = editor.text_edit.document().findBlockByNumber(1)
            editor.text_edit.setTextCursor(QTextCursor(block))

            editor._on_cursor_moved()

            editor.video_player.pause_video.assert_not_called()
            editor._schedule_cursor_video_seek.assert_not_called()
            editor.timeline.ensure_sec_visible.assert_called_once()
            editor.timeline.center_to_sec.assert_not_called()
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

    def test_timeline_click_prefers_clicked_time_when_line_is_ambiguous(self):
        editor = _ClickEditor()
        editor._segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "첫 자막"},
            {"line": 10, "start": 8.0, "end": 9.0, "text": "클릭한 자막"},
        ]
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._highlighter = SimpleNamespace(set_current_line=Mock())
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("\n".join(f"줄 {idx}" for idx in range(11)))
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
            editor._on_timeline_seg_clicked(0, 8.4)

            editor.timeline.set_active.assert_called_once_with(8.0)
            editor.timeline.set_playhead.assert_any_call(8.4)
            self.assertEqual(editor.text_edit.textCursor().blockNumber(), 10)
            self.assertEqual(editor.applied_contexts[0][0]["global_sec"], 8.4)
        finally:
            editor.text_edit.close()

    def test_timeline_click_nearest_start_lookup_avoids_full_segment_iteration(self):
        class GuardedSegments(list):
            def __iter__(self):
                raise AssertionError("nearest-start lookup should use cached indices, not full iteration")

        editor = _ClickEditor()
        first = {"line": 0, "start": 0.0, "end": 1.0, "text": "첫 자막"}
        second = {"line": 10, "start": 8.0, "end": 9.0, "text": "클릭한 자막"}
        guarded = GuardedSegments([first, second])
        cache = {
            "segments": guarded,
            "starts": [0.0, 8.0],
            "visible_segments": guarded,
            "visible_starts": [0.0, 8.0],
            "line_map": {0: first, 10: second},
            "line_numbers": [0, 10],
        }

        seg = editor._segment_for_timeline_click(0, 8.4, cache)

        self.assertIs(seg, second)

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

    def test_scrub_start_prioritizes_manual_editor_runtime_once_per_active_scrub(self):
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
        owner = SimpleNamespace(
            _prioritize_manual_editor_interaction_runtime=Mock(return_value={"prioritized": True, "reason": "editor_scrub_start"})
        )
        editor.window = Mock(return_value=owner)

        with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=10.0):
            editor._on_scrub(3.0)

        owner._prioritize_manual_editor_interaction_runtime.assert_called_once_with(
            editor=editor,
            reason="editor_scrub_start",
            roughcut_reason="편집 시작",
        )

        with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=10.01):
            editor._on_scrub(3.5)

        owner._prioritize_manual_editor_interaction_runtime.assert_called_once()

    def test_timing_drag_preview_updates_playhead_and_uses_lightweight_preview_seek(self):
        editor = _ClickEditor()
        editor.video_fps = 30.0
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._scrub_preview_timer = _FakeScrubTimer()
        editor.timeline = SimpleNamespace(
            set_playhead=Mock(),
            canvas=SimpleNamespace(playhead_sec=0.0, _multiclip_boxes=[]),
        )
        editor.video_player = SimpleNamespace(
            preview_seek=Mock(),
            set_subtitle_display_time=Mock(),
        )

        with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=20.0):
            editor._on_timing_drag_preview(3.0)

        editor.timeline.set_playhead.assert_called_once_with(3.0, preserve_center_lock=True)
        editor.video_player.preview_seek.assert_called_once_with(3.0)
        self.assertEqual(editor._pending_scrub_sec, 3.0)

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
            sync_playhead=False,
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

        editor.timeline.canvas.start_inline_edit.assert_called_once_with(0, 3.0, split_at_playhead=False)

    def test_timeline_double_click_prefers_visible_canvas_segment_over_stale_cache(self):
        editor = _ClickEditor()
        editor._segments = [
            {"line": 0, "start": 1.0, "end": 2.0, "text": "첫 줄"},
            {"line": 1, "start": 3.0, "end": 4.0, "text": "둘째 줄"},
        ]
        editor._active_seg_start = None
        editor.applied_contexts = []
        editor._subtitle_memory_cache = build_segment_lookup(
            [{"line": 0, "start": 1.0, "end": 2.0, "text": "첫 줄"}]
        )
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(
            set_active=Mock(),
            canvas=SimpleNamespace(
                start_inline_edit=Mock(),
                segments=list(editor._segments),
            ),
        )
        editor.video_player = SimpleNamespace(
            pause_video=Mock(),
            seek_direct=Mock(),
        )

        editor._on_timeline_seg_double_clicked(0, 3.0)

        editor.timeline.set_active.assert_called_once_with(3.0)
        editor.timeline.canvas.start_inline_edit.assert_called_once_with(1, 3.0, split_at_playhead=False)

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

    def test_seg_time_changed_marks_editor_dirty(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._is_dirty = False
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
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
            block.setUserData(SubtitleBlockData("첫 줄", 1.0, False, end_sec=2.0))

            editor._on_seg_time_changed(0, 1.5, 2.5, "square_right")
            self.app.processEvents()

            self.assertTrue(editor._is_dirty)
        finally:
            editor.text_edit.close()

    def test_partial_insert_rebuilds_current_segments_after_same_block_count_replacement(self):
        editor = _DummyEditor()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._snap_to_frame = lambda sec: float(sec)
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("기존 자막")
        editor.text_edit.update_margins = Mock()
        editor._schedule_timeline = Mock()
        editor._mark_dirty = Mock()

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))

            initial = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(initial[0]["text"], "기존 자막")
            self.assertTrue(editor._segment_cache_valid)

            editor.clear_segments_in_range(1.0, 2.0)
            editor.insert_partial_segments([
                {"start": 1.0, "end": 2.0, "text": "새 자막", "speaker": "00"}
            ])

            current = editor._get_current_segments()
            self.assertEqual(current[0]["text"], "새 자막")
            self.assertAlmostEqual(float(block.userData().end_sec), 2.0)
        finally:
            editor.text_edit.close()

    def test_partial_inserted_segments_can_resize_without_dropping_following_segments(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._schedule_timeline = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n기존 후반 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=4.0))

            editor._get_current_segments(force_rebuild=True)
            editor.clear_segments_in_range(1.0, 4.0)
            editor.insert_partial_segments([
                {"start": 1.0, "end": 2.0, "text": "메인 자막", "speaker": "00"},
                {"start": 2.0, "end": 3.0, "text": "다음 자막", "speaker": "00"},
            ])

            with patch(
                "ui.editor.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                return_value=None,
            ):
                editor._on_seg_time_changed(1, 1.0, 2.5, "square_right")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "메인 자막", "다음 자막"])
            subtitle_rows = [(seg["start"], seg["end"], seg["text"]) for seg in resized if not seg.get("is_gap")]
            self.assertEqual(subtitle_rows, [
                (0.0, 1.0, "앞 자막"),
                (1.0, 2.5, "메인 자막"),
                (2.5, 3.0, "다음 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_current_segments_preserve_last_explicit_end_without_following_segment(self):
        editor = _DummyEditor()
        editor.video_player = SimpleNamespace(total_time=20.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("뒤쪽 이웃 없는 자막")

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 8.0, False, end_sec=14.0))

            rows = editor._get_current_segments(force_rebuild=True)

            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [
                (8.0, 14.0, "뒤쪽 이웃 없는 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_last_segment_right_resize_works_without_following_segment(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=20.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("단독 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 8.0, False, end_sec=11.0))

            with patch(
                "ui.editor.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                return_value=None,
            ):
                editor._on_seg_time_changed(0, 8.0, 14.0, "square_right")
                self.app.processEvents()

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [
                (8.0, 14.0, "단독 자막"),
            ])
            self.assertAlmostEqual(float(block.userData().end_sec), 14.0)
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_does_not_insert_gap_block_and_allows_repeat_resize(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=3.0))

            initial = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(initial), 2)
            self.assertAlmostEqual(float(initial[1]["start"]), 1.0)

            editor._on_seg_time_changed(1, 2.0, 3.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments()
            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            self.assertEqual(len(resized), 2)
            self.assertAlmostEqual(float(first.userData().end_sec), 1.0)
            self.assertAlmostEqual(float(second.userData().start_sec), 2.0)
            self.assertAlmostEqual(float(second.userData().end_sec), 3.0)
            self.assertAlmostEqual(float(resized[0]["end"]), 1.0)
            self.assertAlmostEqual(float(resized[1]["start"]), 2.0)
            self.assertAlmostEqual(float(resized[1]["end"]), 3.0)

            editor._on_seg_time_changed(1, 1.5, 3.0, "square_left")
            self.app.processEvents()

            resized_again = editor._get_current_segments()
            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            self.assertAlmostEqual(float(second.userData().start_sec), 1.5)
            self.assertAlmostEqual(float(resized_again[1]["start"]), 1.5)
            self.assertAlmostEqual(float(resized_again[1]["end"]), 3.0)
        finally:
            editor.text_edit.close()

    def test_left_resize_partially_overwrites_previous_subtitle_by_trimming_it(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=4.0))

            editor._on_seg_time_changed(1, 1.5, 4.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            self.assertAlmostEqual(float(first.userData().end_sec), 1.5)
            self.assertAlmostEqual(float(second.userData().start_sec), 1.5)
            self.assertEqual([(seg["start"], seg["end"]) for seg in resized], [(0.0, 1.5), (1.5, 4.0)])
        finally:
            editor.text_edit.close()

    def test_left_resize_fully_overwrites_previous_subtitle_by_deleting_it(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 자막\n삭제될 자막\n메인 자막\n끝 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            fourth = editor.text_edit.document().findBlockByNumber(3)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=4.0))
            fourth.setUserData(SubtitleBlockData("00", 5.0, False, end_sec=6.0))

            editor._on_seg_time_changed(2, 0.5, 4.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["첫 자막", "메인 자막", "끝 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 0.5, "첫 자막"),
                (0.5, 4.0, "메인 자막"),
                (5.0, 6.0, "끝 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_right_resize_overwrites_next_subtitles_with_same_trim_delete_rule(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("메인 자막\n삭제될 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.0))

            editor._on_seg_time_changed(0, 0.0, 3.5, "square_right")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "다음 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 3.5, "메인 자막"),
                (3.5, 4.0, "다음 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_excludes_stale_stt_pending_rows_from_native_timing_plan(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n-\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            pending = editor.text_edit.document().findBlockByNumber(1)
            second = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            pending.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=2.5, stt_pending=True, stt_selected_source="STT2"))
            second.setUserData(SubtitleBlockData("00", 4.0, False, end_sec=5.0))

            captured = {}

            def _capture_native_plan(**kwargs):
                captured["segments"] = [dict(seg) for seg in list(kwargs.get("segments") or [])]
                return None

            with patch(
                "ui.editor.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                side_effect=_capture_native_plan,
            ):
                editor._on_seg_time_changed(2, 1.5, 5.0, "square_left")
                self.app.processEvents()

            helper_rows = captured.get("segments") or []
            self.assertEqual([(seg["line"], seg["text"]) for seg in helper_rows], [
                (0, "앞 자막"),
                (2, "메인 자막"),
            ])
            self.assertTrue(all(not seg.get("stt_pending") for seg in helper_rows))
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_preserves_live_stt_preview_after_confirmed_resize(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=12.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())
        editor._live_stt_preview_segments = [
            {
                "start": 2.0,
                "end": 2.6,
                "text": "-",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT2",
            },
            {
                "start": 6.0,
                "end": 6.4,
                "text": "유지",
                "stt_pending": True,
                "_live_stt_preview": True,
                "stt_preview_source": "STT2",
            },
        ]

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 4.0, False, end_sec=5.0))

            before_preview = copy.deepcopy(editor._live_stt_preview_segments)

            with patch(
                "ui.editor.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                return_value=None,
            ):
                editor._on_seg_time_changed(1, 1.5, 5.0, "square_left")
                self.app.processEvents()

            self.assertEqual(editor._live_stt_preview_segments, before_preview)
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_can_apply_native_timing_plan(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("메인 자막\n삭제될 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.0))

            native_plan = {
                "segments": [
                    {"line": 0, "start": 0.0, "end": 3.5, "isGap": False},
                    {"line": 2, "start": 3.5, "end": 4.0, "isGap": False},
                ],
                "deletedLines": [1],
            }
            with patch(
                "ui.editor.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                return_value=native_plan,
            ) as native_helper:
                editor._on_seg_time_changed(0, 0.0, 3.5, "square_right")
                self.app.processEvents()

            native_helper.assert_called_once()
            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "다음 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 3.5, "메인 자막"),
                (3.5, 4.0, "다음 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_with_gap_keeps_resized_subtitle_when_attaching_to_previous_end(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            gap = editor.text_edit.document().findBlockByNumber(1)
            second = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            gap.setUserData(SubtitleBlockData("00", 1.0, True, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(2, 1.0, 3.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "메인 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.0, 3.0, "메인 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_seg_time_changed_with_gap_does_not_delete_resized_anchor_when_overwriting_previous(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n\n메인 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            gap = editor.text_edit.document().findBlockByNumber(1)
            second = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            gap.setUserData(SubtitleBlockData("00", 1.0, True, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(2, 0.0, 3.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 3.0, "메인 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_center_drag_over_single_gap_absorbs_gap_without_final_overlap(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            gap = editor.text_edit.document().findBlockByNumber(1)
            second = editor.text_edit.document().findBlockByNumber(2)
            third = editor.text_edit.document().findBlockByNumber(3)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            gap.setUserData(SubtitleBlockData("00", 1.0, True, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.0))

            editor._on_seg_time_changed(2, 1.0, 2.0, "center")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "center_gap_absorb")
            self.assertEqual(operation.get("metadata", {}).get("silence_gap_deleted_count"), 1)
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "메인 자막", "뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.0, 2.0, "메인 자막"),
                (3.0, 4.0, "뒤 자막"),
            ])
            subtitle_rows = [seg for seg in resized if not seg.get("is_gap")]
            for left, right in zip(subtitle_rows, subtitle_rows[1:]):
                self.assertLessEqual(float(left["end"]), float(right["start"]))
        finally:
            editor.text_edit.close()

    def test_center_drag_free_space_routes_through_nle_caption_move(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 5.0, False, end_sec=6.0))

            editor._on_seg_time_changed(1, 3.0, 4.0, "center")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertFalse(operation.get("metadata", {}).get("taption_reorder"))
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "메인 자막", "뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (3.0, 4.0, "메인 자막"),
                (5.0, 6.0, "뒤 자막"),
            ])
            editor.timeline.update_segments.assert_called()
        finally:
            editor.text_edit.close()

    def test_center_drag_right_preserves_duration_and_trims_overwritten_next_subtitle(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(1, 1.5, 2.5, "center")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "center_overwrite_trim")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.document().blockCount(), 3)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.5, 2.5, "메인 자막"),
                (2.5, 3.0, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_center_drag_left_preserves_duration_and_trims_overwritten_previous_subtitle(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(1, 0.5, 1.5, "center")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "center_overwrite_trim")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.document().blockCount(), 3)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 0.5, "앞 자막"),
                (0.5, 1.5, "메인 자막"),
                (2.0, 3.0, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_center_drag_overwrite_trim_falls_back_when_nle_commit_rejects(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_move_commit_dual_write_pilot",
                side_effect=ValueError("forced-nle-commit-reject"),
            ):
                editor._on_seg_time_changed(1, 1.5, 2.5, "center")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.5, 2.5, "메인 자막"),
                (2.5, 3.0, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_center_drag_native_timing_plan_routes_complex_commit_through_nle(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("메인 자막\n삭제될 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            native_plan = {
                "segments": [
                    {"line": 0, "start": 0.5, "end": 1.5, "isGap": False},
                    {"line": 2, "start": 2.0, "end": 3.0, "isGap": False},
                ],
                "deletedLines": [1],
            }
            with patch(
                "ui.editor.ux.editor_timeline_video.plan_subtitle_timing_edit_via_swift",
                return_value=native_plan,
            ):
                editor._on_seg_time_changed(0, 0.5, 1.5, "center")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "center_overwrite_trim")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "다음 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.5, 1.5, "메인 자막"),
                (2.0, 3.0, "다음 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_center_reorder_commit_reloads_document_in_timeline_order(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(1, 2.0, 3.0, "center_reorder_right")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertTrue(operation.get("metadata", {}).get("taption_reorder"))
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center_reorder_right")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "뒤 자막", "메인 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.0, 2.0, "뒤 자막"),
                (2.0, 3.0, "메인 자막"),
            ])
            editor.timeline.update_segments.assert_called()
        finally:
            editor.text_edit.close()

    def test_center_reorder_commit_falls_back_when_nle_move_rejects_live_route(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_move_dual_write_pilot",
                side_effect=ValueError("forced-nle-reject"),
            ):
                editor._on_seg_time_changed(1, 2.0, 3.0, "center_reorder_right")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "뒤 자막", "메인 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "앞 자막"),
                (1.0, 2.0, "뒤 자막"),
                (2.0, 3.0, "메인 자막"),
            ])
            editor.timeline.update_segments.assert_called()
        finally:
            editor.text_edit.close()

    def test_center_reorder_left_commit_routes_through_nle_caption_move(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n메인 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_time_changed(1, 0.0, 1.0, "center_reorder_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertTrue(operation.get("metadata", {}).get("taption_reorder"))
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "center_reorder_left")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "앞 자막", "뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.0, "메인 자막"),
                (1.0, 2.0, "앞 자막"),
                (2.0, 3.0, "뒤 자막"),
            ])
            editor.timeline.update_segments.assert_called()
        finally:
            editor.text_edit.close()

    def test_diamond_resize_updates_adjacent_subtitles_without_inserting_gap(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))

            editor._on_seg_time_changed(0, 0.0, 1.4, "diamond")
            editor._on_seg_time_changed(1, 1.4, 2.0, "diamond")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.4, "앞 자막"),
                (1.4, 2.0, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_diamond_resize_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))

            editor._on_seg_time_changed(0, 0.0, 1.4, "diamond")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_resize")
            self.assertEqual(operation.get("metadata", {}).get("edge"), "diamond")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.document().blockCount(), 2)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.4, "앞 자막"),
                (1.4, 2.0, "뒤 자막"),
            ])
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
        finally:
            editor.text_edit.close()

    def test_square_left_resize_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 자막\n삭제될 자막\n메인 자막\n끝 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            fourth = editor.text_edit.document().findBlockByNumber(3)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=4.0))
            fourth.setUserData(SubtitleBlockData("00", 5.0, False, end_sec=6.0))

            editor._on_seg_time_changed(2, 0.5, 4.0, "square_left")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_resize")
            self.assertEqual(operation.get("metadata", {}).get("edge"), "square_left")
            self.assertEqual(operation.get("metadata", {}).get("trimmed_neighbor_count"), 1)
            self.assertEqual(operation.get("metadata", {}).get("deleted_neighbor_count"), 1)
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["첫 자막", "메인 자막", "끝 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 0.5, "첫 자막"),
                (0.5, 4.0, "메인 자막"),
                (5.0, 6.0, "끝 자막"),
            ])
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
        finally:
            editor.text_edit.close()

    def test_square_right_resize_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("메인 자막\n삭제될 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.0))

            editor._on_seg_time_changed(0, 0.0, 3.5, "square_right")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_resize")
            self.assertEqual(operation.get("metadata", {}).get("edge"), "square_right")
            self.assertEqual(operation.get("metadata", {}).get("trimmed_neighbor_count"), 1)
            self.assertEqual(operation.get("metadata", {}).get("deleted_neighbor_count"), 1)
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "다음 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 3.5, "메인 자막"),
                (3.5, 4.0, "다음 자막"),
            ])
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
        finally:
            editor.text_edit.close()

    def test_square_resize_falls_back_when_nle_dual_write_rejects_live_route(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("메인 자막\n삭제될 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.0))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_resize_dual_write_pilot",
                side_effect=ValueError("forced-nle-reject"),
            ):
                editor._on_seg_time_changed(0, 0.0, 3.5, "square_right")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["메인 자막", "다음 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 3.5, "메인 자막"),
                (3.5, 4.0, "다음 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_diamond_resize_falls_back_when_nle_dual_write_rejects_live_route(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_resize_dual_write_pilot",
                side_effect=ValueError("forced-nle-reject"),
            ):
                editor._on_seg_time_changed(0, 0.0, 1.4, "diamond")
                editor._on_seg_time_changed(1, 1.4, 2.0, "diamond")
                self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (0.0, 1.4, "앞 자막"),
                (1.4, 2.0, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_diamond_resize_skips_nle_when_micro_segment_would_collapse_on_project_grid(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
            update_segments=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n짧은 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=1.3))
            second.setUserData(SubtitleBlockData("00", 1.3, False, end_sec=1.333333))
            third.setUserData(SubtitleBlockData("00", 3.0, False, end_sec=4.3))

            editor._on_seg_time_changed(0, 1.0, 1.3, "diamond")
            editor._on_seg_time_changed(1, 1.3, 1.333333, "diamond")
            self.app.processEvents()

            resized = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.document().blockCount(), 3)
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in resized], [
                (1.0, 1.3, "앞 자막"),
                (1.3, 1.333333, "짧은 자막"),
                (3.0, 4.3, "뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_segment_delete_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n삭제 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._remove_live_detection_for_range = Mock()
        editor._arm_gap_snapshot_undo_routing = Mock()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            third = editor.text_edit.document().findBlockByNumber(2)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            third.setUserData(SubtitleBlockData("00", 2.0, False, end_sec=3.0))

            editor._on_seg_to_gap(1)
            self.app.processEvents()

            segments = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_delete")
            self.assertEqual(operation.get("metadata", {}).get("delete_mode"), "replace_with_silence_gap")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "", "뒤 자막"])
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"], bool(seg.get("is_gap"))) for seg in segments],
                [(0.0, 1.0, "앞 자막", False), (1.0, 2.0, "", True), (2.0, 3.0, "뒤 자막", False)],
            )
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
            editor._remove_live_detection_for_range.assert_called_once_with(1.0, 2.0)
            editor._arm_gap_snapshot_undo_routing.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_segment_delete_skips_nle_when_live_stt_preview_is_present(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("삭제 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = [
            {"start": 0.1, "end": 0.5, "text": "STT1", "stt_pending": True}
        ]

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))

            with patch("ui.editor.ux.editor_timeline_video.apply_caption_delete_dual_write_pilot") as nle_delete:
                editor._on_seg_to_gap(0)
                self.app.processEvents()

            nle_delete.assert_not_called()
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor._live_stt_preview_segments, [
                {"start": 0.1, "end": 0.5, "text": "STT1", "stt_pending": True}
            ])
            segments = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"], bool(seg.get("is_gap"))) for seg in segments],
                [(0.0, 1.0, "", True), (1.0, 2.0, "뒤 자막", False)],
            )
        finally:
            editor.text_edit.close()

    def test_gap_generate_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(
            update_segments=Mock(),
            set_active=Mock(),
            set_playhead=Mock(),
            center_to_sec=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0, seek=Mock())
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞\n\n뒤")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._remove_live_detection_for_range = Mock()
        editor._arm_gap_snapshot_undo_routing = Mock()

        try:
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 1.0, True, end_sec=5.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0, False, end_sec=6.0))

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "from")
            self.app.processEvents()

            segments = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "gap_generate")
            self.assertEqual(operation.get("metadata", {}).get("mode"), "from")
            self.assertTrue(operation.get("metadata", {}).get("left_gap_preserved"))
            self.assertFalse(operation.get("metadata", {}).get("right_gap_preserved"))
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "뒤"])
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"], bool(seg.get("is_gap"))) for seg in segments],
                [
                    (0.0, 1.0, "앞", False),
                    (1.0, 3.0, "", True),
                    (3.0, 5.0, "새자막", False),
                    (5.0, 6.0, "뒤", False),
                ],
            )
            editor.timeline.update_segments.assert_called()
            editor.timeline.set_active.assert_called_once_with(3.0)
            editor.timeline.set_playhead.assert_called_once_with(3.0)
            editor.timeline.center_to_sec.assert_called_once_with(3.0, smooth=True)
            editor.video_player.seek.assert_called_once_with(3.0)
            editor._remove_live_detection_for_range.assert_called_once_with(3.0, 5.0)
            editor._arm_gap_snapshot_undo_routing.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_gap_generate_skips_nle_when_live_stt_preview_is_present(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞\n\n뒤")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = [
            {"start": 1.0, "end": 5.0, "text": "gap 후보", "stt_pending": True}
        ]

        try:
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 1.0, True, end_sec=5.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0, False, end_sec=6.0))

            with patch("ui.editor.ux.editor_timeline_video.apply_gap_generate_dual_write_pilot") as nle_generate:
                editor._on_gap_generate_requested(1.0, 5.0, 3.0, "to")
                self.app.processEvents()

            nle_generate.assert_not_called()
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor._live_stt_preview_segments, [
                {"start": 1.0, "end": 5.0, "text": "gap 후보", "stt_pending": True}
            ])
            segments = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"], bool(seg.get("is_gap"))) for seg in segments],
                [
                    (0.0, 1.0, "앞", False),
                    (1.0, 3.0, "새자막", False),
                    (3.0, 5.0, "", True),
                    (5.0, 6.0, "뒤", False),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_smart_split_routes_release_commit_through_nle_caption_split(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._active_seg_start = 1.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(
            update_segments=Mock(),
            set_active=Mock(),
            center_to_sec=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("원본 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor._arm_gap_snapshot_undo_routing = Mock()
        editor._mark_dirty = Mock()

        try:
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 1.0, False, end_sec=4.0, segment_id="caption_a"))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 4.0, False, end_sec=5.0, segment_id="caption_b"))

            editor._on_smart_split(0, 2.5, False)

            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_split")
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "timeline_smart_split")
            self.assertEqual(operation.get("metadata", {}).get("left_text"), "원본 자막")
            self.assertEqual(operation.get("metadata", {}).get("right_text"), "새자막")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["원본 자막", "새자막", "다음 자막"])
            segments = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"]) for seg in segments],
                [(1.0, 2.5, "원본 자막"), (2.5, 4.0, "새자막"), (4.0, 5.0, "다음 자막")],
            )
            editor.timeline.update_segments.assert_called()
            editor.timeline.set_active.assert_called_once_with(2.5)
            editor.timeline.center_to_sec.assert_called_once_with(2.5, smooth=True)
            editor._arm_gap_snapshot_undo_routing.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_smart_split_keeps_qtextdocument_fallback_when_nle_rejects(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._active_seg_start = 1.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(
            update_segments=Mock(),
            set_active=Mock(),
            center_to_sec=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("원본 자막\n다음 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor._arm_gap_snapshot_undo_routing = Mock()
        editor._mark_dirty = Mock()

        try:
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 1.0, False, end_sec=4.0, segment_id="caption_a"))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 4.0, False, end_sec=5.0, segment_id="caption_b"))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_split_dual_write_pilot",
                side_effect=ValueError("forced_nle_reject"),
            ):
                editor._on_smart_split(0, 2.5, True)

            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["새자막", "원본 자막", "다음 자막"])
            segments = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"]) for seg in segments],
                [(1.0, 2.5, "새자막"), (2.5, 4.0, "원본 자막"), (4.0, 5.0, "다음 자막")],
            )
            editor.timeline.set_active.assert_called_once_with(2.5)
            editor.timeline.center_to_sec.assert_called_once_with(2.5, smooth=True)
        finally:
            editor.text_edit.close()

    def test_diamond_merge_extends_left_segment_to_right_segment_end(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_merge(0, 1)

            merged = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막 뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in merged], [
                (0.0, 2.5, "앞 자막 뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_diamond_merge_routes_live_editor_mutation_through_nle_dual_write(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._active_seg_start = 0.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_merge(0, 1)
            self.app.processEvents()

            merged = editor._get_current_segments(force_rebuild=True)
            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            self.assertEqual(operation.get("kind"), "caption_merge")
            self.assertEqual(operation.get("metadata", {}).get("operation_family"), "caption_merge")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막 뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in merged], [
                (0.0, 2.5, "앞 자막 뒤 자막"),
            ])
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
            editor._undo_mgr.push_immediate.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_diamond_merge_falls_back_when_nle_dual_write_rejects_live_route(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._active_seg_start = 0.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n뒤 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_merge_dual_write_pilot",
                side_effect=ValueError("forced-nle-reject"),
            ):
                editor._on_diamond_merge(0, 1)
                self.app.processEvents()

            merged = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막 뒤 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in merged], [
                (0.0, 2.5, "앞 자막 뒤 자막"),
            ])
        finally:
            editor.text_edit.close()

    def test_diamond_merge_menu_offers_merge_and_delete(self):
        editor = _ResizeTimelineEditor()

        items = editor._segment_merge_menu_items(0, 1)

        self.assertEqual(
            [(item.get("id"), item.get("label")) for item in items],
            [("merge", "합치기"), ("delete", "지우기")],
        )

    def test_diamond_delete_extends_left_segment_to_right_end_without_appending_text(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n삭제될 자막")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_delete(0, 1)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "앞 자막")])
        finally:
            editor.text_edit.close()

    def test_diamond_delete_can_keep_right_segment_when_current_overwrites_previous(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("삭제될 앞 자막\n현재 자막")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._diamond_delete_keep_line_override = 1

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_delete(0, 1)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["현재 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "현재 자막")])
        finally:
            editor.text_edit.close()

    def test_diamond_delete_routes_keep_left_through_nle_move_commit(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._active_seg_start = 0.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n삭제될 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_delete(0, 1)
            self.app.processEvents()

            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            projection = getattr(editor, "_last_nle_live_editor_projection", {})
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "diamond_delete")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "diamond_delete_keep_left")
            self.assertEqual(operation.get("metadata", {}).get("deleted_row_count"), 1)
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "앞 자막")])
            editor.timeline.update_segments.assert_called()
            editor._schedule_timeline.assert_called()
            editor._undo_mgr.push_immediate.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_diamond_delete_routes_keep_right_through_nle_move_commit(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._active_seg_start = 0.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("삭제될 앞 자막\n현재 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._diamond_delete_keep_line_override = 1

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_delete(0, 1)
            self.app.processEvents()

            operation = getattr(editor, "_last_nle_live_editor_operation", {})
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(operation.get("kind"), "caption_move")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "diamond_delete")
            self.assertEqual(operation.get("metadata", {}).get("commit_mode"), "diamond_delete_keep_right")
            self.assertEqual(operation.get("metadata", {}).get("deleted_row_count"), 1)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["현재 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "현재 자막")])
            editor.timeline.update_segments.assert_called()
            editor._undo_mgr.push_immediate.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_diamond_delete_falls_back_when_nle_move_commit_rejects(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor._active_seg_start = 0.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n삭제될 자막")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock(), setUpdatesEnabled=Mock())
        editor._schedule_timeline = Mock()
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_move_commit_dual_write_pilot",
                side_effect=ValueError("forced-nle-reject"),
            ):
                editor._on_diamond_delete(0, 1)
                self.app.processEvents()

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "앞 자막")])
            editor._undo_mgr.push_immediate.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_diamond_delete_resolves_timeline_row_line_to_document_block(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("이전 줄 1\n이전 줄 2\n이거는 10원짜리인데\n흠\n감사합니다")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()

        canvas_segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "이전 줄 1\n이전 줄 2"},
            {"line": 1, "start": 2.0, "end": 3.0, "text": "이거는 10원짜리인데"},
            {"line": 2, "start": 3.0, "end": 3.5, "text": "흠"},
            {"line": 3, "start": 3.5, "end": 4.0, "text": "감사합니다"},
        ]
        canvas = SimpleNamespace(
            segments=canvas_segments,
            _drag_seg={"line": 1, "start": 2.0, "end": 3.5, "text": "이거는 10원짜리인데"},
            _drag_edge="square_right",
            _drag_merge_pair=(1, 2),
            _drag_s0_start=2.0,
            _drag_s0_end=3.0,
            _drag_adj_l=canvas_segments[0],
            _drag_adj_r=canvas_segments[2],
            _drag_adj_orig_start_l=0.0,
            _drag_adj_orig_end_l=1.0,
            _drag_adj_orig_start_r=3.0,
            _drag_adj_orig_end_r=3.5,
        )
        canvas._segment_for_line = lambda line: next(
            (seg for seg in canvas_segments if int(seg["line"]) == int(line)),
            None,
        )
        editor.timeline = SimpleNamespace(canvas=canvas)

        try:
            blocks = [
                ("00", 0.0, 1.0),
                ("01", 0.0, 1.0),
                ("00", 2.0, 3.0),
                ("00", 3.0, 3.5),
                ("00", 3.5, 4.0),
            ]
            for idx, (speaker, start, end) in enumerate(blocks):
                editor.text_edit.document().findBlockByNumber(idx).setUserData(
                    SubtitleBlockData(speaker, start, False, end_sec=end)
                )

            editor._on_diamond_delete(1, 2)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                editor.text_edit.toPlainText().splitlines(),
                ["이전 줄 1", "이전 줄 2", "이거는 10원짜리인데", "감사합니다"],
            )
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"]) for seg in rows],
                [
                    (0.0, 1.0, "이전 줄 1\n이전 줄 2"),
                    (2.0, 3.5, "이거는 10원짜리인데"),
                    (3.5, 4.0, "감사합니다"),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_diamond_merge_resolves_timeline_row_line_to_document_block(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("이전 줄 1\n이전 줄 2\n이거는 10원짜리인데\n흠\n감사합니다")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()

        canvas_segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "이전 줄 1\n이전 줄 2"},
            {"line": 1, "start": 2.0, "end": 3.0, "text": "이거는 10원짜리인데"},
            {"line": 2, "start": 3.0, "end": 3.5, "text": "흠"},
            {"line": 3, "start": 3.5, "end": 4.0, "text": "감사합니다"},
        ]
        canvas = SimpleNamespace(
            segments=canvas_segments,
            _drag_seg={"line": 1, "start": 2.0, "end": 3.5, "text": "이거는 10원짜리인데"},
            _drag_edge="square_right",
            _drag_merge_pair=(1, 2),
            _drag_s0_start=2.0,
            _drag_s0_end=3.0,
            _drag_adj_l=canvas_segments[0],
            _drag_adj_r=canvas_segments[2],
            _drag_adj_orig_start_l=0.0,
            _drag_adj_orig_end_l=1.0,
            _drag_adj_orig_start_r=3.0,
            _drag_adj_orig_end_r=3.5,
        )
        canvas._segment_for_line = lambda line: next(
            (seg for seg in canvas_segments if int(seg["line"]) == int(line)),
            None,
        )
        editor.timeline = SimpleNamespace(canvas=canvas)

        try:
            blocks = [
                ("00", 0.0, 1.0),
                ("01", 0.0, 1.0),
                ("00", 2.0, 3.0),
                ("00", 3.0, 3.5),
                ("00", 3.5, 4.0),
            ]
            for idx, (speaker, start, end) in enumerate(blocks):
                editor.text_edit.document().findBlockByNumber(idx).setUserData(
                    SubtitleBlockData(speaker, start, False, end_sec=end)
                )

            editor._on_diamond_merge(1, 2)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                editor.text_edit.toPlainText().splitlines(),
                ["이전 줄 1", "이전 줄 2", "이거는 10원짜리인데 흠", "감사합니다"],
            )
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"]) for seg in rows],
                [
                    (0.0, 1.0, "이전 줄 1\n이전 줄 2"),
                    (2.0, 3.5, "이거는 10원짜리인데 흠"),
                    (3.5, 4.0, "감사합니다"),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_diamond_delete_reverse_drag_keeps_dragged_segment_with_line_mismatch(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("이전 줄 1\n이전 줄 2\n이거는 10원짜리인데\n흠\n감사합니다")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()

        canvas_segments = [
            {"line": 0, "start": 0.0, "end": 1.0, "text": "이전 줄 1\n이전 줄 2"},
            {"line": 1, "start": 2.0, "end": 3.0, "text": "이거는 10원짜리인데"},
            {"line": 2, "start": 3.0, "end": 3.5, "text": "흠"},
            {"line": 3, "start": 3.5, "end": 4.0, "text": "감사합니다"},
        ]
        canvas = SimpleNamespace(
            segments=canvas_segments,
            _drag_seg={"line": 2, "start": 2.0, "end": 3.5, "text": "흠"},
            _drag_edge="square_left",
            _drag_merge_pair=(1, 2),
            _drag_s0_start=3.0,
            _drag_s0_end=3.5,
            _drag_adj_l=canvas_segments[1],
            _drag_adj_r=canvas_segments[3],
            _drag_adj_orig_start_l=2.0,
            _drag_adj_orig_end_l=3.0,
            _drag_adj_orig_start_r=3.5,
            _drag_adj_orig_end_r=4.0,
        )
        canvas._segment_for_line = lambda line: next(
            (seg for seg in canvas_segments if int(seg["line"]) == int(line)),
            None,
        )
        editor.timeline = SimpleNamespace(canvas=canvas)

        try:
            blocks = [
                ("00", 0.0, 1.0),
                ("01", 0.0, 1.0),
                ("00", 2.0, 3.0),
                ("00", 3.0, 3.5),
                ("00", 3.5, 4.0),
            ]
            for idx, (speaker, start, end) in enumerate(blocks):
                editor.text_edit.document().findBlockByNumber(idx).setUserData(
                    SubtitleBlockData(speaker, start, False, end_sec=end)
                )

            editor._on_diamond_delete(1, 2)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                editor.text_edit.toPlainText().splitlines(),
                ["이전 줄 1", "이전 줄 2", "흠", "감사합니다"],
            )
            self.assertEqual(
                [(seg["start"], seg["end"], seg["text"]) for seg in rows],
                [
                    (0.0, 1.0, "이전 줄 1\n이전 줄 2"),
                    (2.0, 3.5, "흠"),
                    (3.5, 4.0, "감사합니다"),
                ],
            )
        finally:
            editor.text_edit.close()

    def test_diamond_merge_request_can_choose_delete_action(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("앞 자막\n삭제될 자막")
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._diamond_merge_action_override = lambda *_args: "delete"

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, False, end_sec=1.0))
            second.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.5))

            editor._on_diamond_merge_requested(0, 1)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막"])
            self.assertEqual([(seg["start"], seg["end"], seg["text"]) for seg in rows], [(0.0, 2.5, "앞 자막")])
        finally:
            editor.text_edit.close()

    def test_timestamp_metadata_restore_does_not_revert_recent_timing_edit(self):
        editor = _ResizeTimelineEditor()
        editor.video_fps = 30.0
        editor._snapshot_timeline_view_for_resize = Mock(return_value={})
        editor._redraw_timeline_preserve_resize_view = Mock()
        editor.timeline = SimpleNamespace(
            _begin_subtitle_resize_keep_view=Mock(),
            _finish_subtitle_resize_keep_view=Mock(),
        )
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 줄\n둘째 줄")
        editor.text_edit.update_margins = Mock()
        editor.text_edit.timestampArea = SimpleNamespace(update=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0))
            second.setUserData(SubtitleBlockData("00", 3.4, False, end_sec=5.0))
            editor._rebuild_subtitle_memory_cache()

            editor._on_seg_time_changed(0, 1.0, 2.5, "square_right")
            repaired = editor._restore_all_block_user_data()

            updated = editor.text_edit.document().findBlockByNumber(0).userData()
            self.assertEqual(repaired, 0)
            self.assertAlmostEqual(updated.start_sec, 1.0)
            self.assertAlmostEqual(updated.end_sec, 2.5)
            self.assertTrue(editor._segment_cache_valid)
        finally:
            editor.text_edit.close()

    def test_get_current_segments_drops_overflow_gap_and_clamps_to_clip_duration(self):
        editor = _DummyEditor()
        editor.video_fps = 30.0
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("마지막 자막\n")

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            trailing_gap = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 8.0, False, end_sec=12.0))
            trailing_gap.setUserData(SubtitleBlockData("00", 12.0, True, end_sec=15.0))

            rows = editor._get_current_segments(force_rebuild=True)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "마지막 자막")
            self.assertAlmostEqual(float(rows[0]["start"]), 8.0)
            self.assertAlmostEqual(float(rows[0]["end"]), 10.0)
        finally:
            editor.text_edit.close()

    def test_canvas_speaker_split_preserves_start_and_switches_speaker(self):
        editor = _DummyEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor._sync_lock = False
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("안녕하세요 여러분")
        editor.timeline = SimpleNamespace(set_active=Mock(), center_to_sec=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.2, False, end_sec=3.4))

            editor.split_speaker_segment_with_text(0, 5)

            lines = editor.text_edit.toPlainText().splitlines()
            first = editor.text_edit.document().findBlockByNumber(0).userData()
            second = editor.text_edit.document().findBlockByNumber(1).userData()
            self.assertEqual(lines, ["- 안녕하세요", "- 여러분"])
            self.assertEqual(first.spk_id, "00")
            self.assertEqual(second.spk_id, "01")
            self.assertAlmostEqual(first.start_sec, 1.2)
            self.assertAlmostEqual(second.start_sec, 1.2)
            editor.timeline.set_active.assert_called_once_with(1.2)
            editor.timeline.center_to_sec.assert_called_once_with(1.2, smooth=True)
        finally:
            editor.text_edit.close()

    def test_canvas_speaker_split_preserves_existing_dash_dialogue_lines(self):
        editor = _DummyEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("- 왜?\u2028- 어?")
        editor.video_player = SimpleNamespace(total_time=60.0)
        editor.timeline = SimpleNamespace(set_active=Mock(), center_to_sec=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 27.06, False, end_sec=29.46))

            editor.split_speaker_segment_with_text(0, 99)

            lines = editor.text_edit.toPlainText().splitlines()
            first = editor.text_edit.document().findBlockByNumber(0).userData()
            second = editor.text_edit.document().findBlockByNumber(1).userData()
            self.assertEqual(lines, ["- 왜?", "- 어?"])
            self.assertEqual(first.spk_id, "00")
            self.assertEqual(second.spk_id, "01")
            self.assertAlmostEqual(first.start_sec, 27.06)
            self.assertAlmostEqual(second.start_sec, 27.06)
            self.assertAlmostEqual(first.end_sec, 29.46)
            self.assertAlmostEqual(second.end_sec, 29.46)

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "- 왜?\n- 어?")
            self.assertEqual(rows[0]["speaker_list"], ["00", "01"])
        finally:
            editor.text_edit.close()

    def test_canvas_speaker_split_routes_stable_caption_through_nle_text_edit(self):
        editor = _ResizeTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 0.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("안녕하세요 여러분")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(
            update_segments=Mock(),
            set_active=Mock(),
            center_to_sec=Mock(),
        )
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.2, False, end_sec=3.4))

            editor.split_speaker_segment_with_text(0, 5)

            operation = editor._last_nle_live_editor_operation
            self.assertEqual(operation["kind"], "caption_text_edit")
            self.assertEqual(operation["metadata"]["commit_boundary"], "release")
            self.assertEqual(operation["metadata"]["commit_source"], "timeline_speaker_split")
            self.assertEqual(operation["metadata"]["new_speaker_list"], ["00", "01"])
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["- 안녕하세요", "- 여러분"])

            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "- 안녕하세요\n- 여러분")
            self.assertEqual(rows[0]["speaker_list"], ["00", "01"])
            self.assertAlmostEqual(rows[0]["start"], 1.2)
            self.assertAlmostEqual(rows[0]["end"], 3.4)
            editor.timeline.update_segments.assert_called()
            editor.timeline.set_active.assert_called_with(1.2)
            editor.timeline.center_to_sec.assert_called_with(1.2, smooth=True)
        finally:
            editor.text_edit.close()

    def test_canvas_speaker_split_keeps_qtextdocument_fallback_when_nle_rejects(self):
        editor = _ResizeTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 0.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("안녕하세요 여러분")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(
            update_segments=Mock(),
            set_active=Mock(),
            center_to_sec=Mock(),
        )
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.2, False, end_sec=3.4))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_text_edit_dual_write_pilot",
                side_effect=ValueError("forced_nle_reject"),
            ):
                editor.split_speaker_segment_with_text(0, 5)

            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["- 안녕하세요", "- 여러분"])
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["speaker_list"], ["00", "01"])
            editor.timeline.set_active.assert_called_once_with(1.2)
            editor.timeline.center_to_sec.assert_called_once_with(1.2, smooth=True)
        finally:
            editor.text_edit.close()

    def test_speaker_circle_drop_routes_same_caption_reorder_through_nle_text_edit(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 1.2
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("- 안녕하세요\n- 반갑습니다")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.2, False, end_sec=3.4, segment_id="caption_a"))
            second.setUserData(SubtitleBlockData("01", 1.2, False, end_sec=3.4, segment_id="caption_a"))

            editor._on_speaker_circle_dropped(0, 1)

            operation = editor._last_nle_live_editor_operation
            self.assertEqual(operation["kind"], "caption_text_edit")
            self.assertEqual(operation["metadata"]["commit_boundary"], "release")
            self.assertEqual(operation["metadata"]["commit_source"], "timeline_speaker_drop")
            self.assertEqual(operation["metadata"]["new_speaker_list"], ["01", "00"])
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["- 반갑습니다", "- 안녕하세요"])
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "- 반갑습니다\n- 안녕하세요")
            self.assertEqual(rows[0]["speaker_list"], ["01", "00"])
            self.assertAlmostEqual(rows[0]["start"], 1.2)
            self.assertAlmostEqual(rows[0]["end"], 3.4)
            editor.timeline.update_segments.assert_called()
        finally:
            editor.text_edit.close()

    def test_speaker_circle_drop_keeps_qtextdocument_fallback_when_nle_rejects(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 1.2
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("- 안녕하세요\n- 반갑습니다")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.2, False, end_sec=3.4, segment_id="caption_a"))
            second.setUserData(SubtitleBlockData("01", 1.2, False, end_sec=3.4, segment_id="caption_a"))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_text_edit_dual_write_pilot",
                side_effect=ValueError("forced_nle_reject"),
            ):
                editor._on_speaker_circle_dropped(0, 1)

            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["- 반갑습니다", "- 안녕하세요"])
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["speaker_list"], ["01", "00"])
            editor._highlighter.rehighlight.assert_called_once()
            editor._finalize_edit.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_speaker_circle_drop_does_not_nle_reorder_distinct_captions(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 0.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("첫 자막\n둘째 자막")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0, segment_id="caption_a"))
            second.setUserData(SubtitleBlockData("01", 3.0, False, end_sec=4.0, segment_id="caption_b"))

            with patch("ui.editor.ux.editor_timeline_video.apply_caption_text_edit_dual_write_pilot") as nle_text_edit:
                editor._on_speaker_circle_dropped(0, 1)

            nle_text_edit.assert_not_called()
            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["둘째 자막", "첫 자막"])
            editor._highlighter.rehighlight.assert_called_once()
            editor._finalize_edit.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_change_speaker_for_line_routes_single_caption_through_nle_text_edit(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 1.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("화자 변경")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0, segment_id="caption_a"))

            editor._change_speaker_for_line(0, "01")

            operation = editor._last_nle_live_editor_operation
            self.assertEqual(operation["kind"], "caption_text_edit")
            self.assertEqual(operation["metadata"]["commit_boundary"], "release")
            self.assertEqual(operation["metadata"]["commit_source"], "timeline_speaker_change")
            self.assertEqual(operation["metadata"]["old_speaker"], "00")
            self.assertEqual(operation["metadata"]["new_speaker"], "01")
            self.assertEqual(operation["metadata"]["new_speaker_list"], ["01"])
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["화자 변경"])
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "화자 변경")
            self.assertEqual(rows[0].get("speaker", rows[0].get("spk")), "01")
            self.assertAlmostEqual(rows[0]["start"], 1.0)
            self.assertAlmostEqual(rows[0]["end"], 2.0)
            editor.timeline.update_segments.assert_called()
            editor._finalize_edit.assert_called_once()
            editor._highlighter.rehighlight.assert_not_called()
        finally:
            editor.text_edit.close()

    def test_change_speaker_for_line_keeps_qtextdocument_fallback_when_nle_rejects(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 1.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("화자 변경")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0, segment_id="caption_a"))

            with patch(
                "ui.editor.ux.editor_timeline_video.apply_caption_text_edit_dual_write_pilot",
                side_effect=ValueError("forced_nle_reject"),
            ):
                editor._change_speaker_for_line(0, "01")

            self.assertFalse(hasattr(editor, "_last_nle_live_editor_operation"))
            changed_ud = editor.text_edit.document().findBlockByNumber(0).userData()
            self.assertEqual(changed_ud.spk_id, "01")
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(rows[0].get("speaker", rows[0].get("spk")), "01")
            editor._highlighter.rehighlight.assert_called_once()
            editor._finalize_edit.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_change_speaker_for_line_keeps_multiblock_shape_on_qtextdocument_path(self):
        editor = _SpeakerDropTimelineEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.video_fps = 30.0
        editor._sync_lock = False
        editor._active_seg_start = 1.0
        editor._segment_queue = []
        editor._live_editor_preview_queue = []
        editor._live_editor_preview_segments = []
        editor._live_editor_preview_keys = set()
        editor._live_stt_preview_segments = []
        editor._linked_project_path_for_srt = ""
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("- 첫 줄\n- 둘째 줄")
        editor.video_player = SimpleNamespace(total_time=10.0)
        editor.timeline = SimpleNamespace(update_segments=Mock())
        editor._mark_dirty = Mock()
        editor._finalize_edit = Mock()
        editor._schedule_timeline = Mock()
        editor._undo_mgr = SimpleNamespace(push_immediate=Mock())
        editor._highlighter = SimpleNamespace(rehighlight=Mock())

        try:
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.0, False, end_sec=2.0, segment_id="caption_a"))
            second.setUserData(SubtitleBlockData("01", 1.0, False, end_sec=2.0, segment_id="caption_a"))

            with patch("ui.editor.ux.editor_timeline_video.apply_caption_text_edit_dual_write_pilot") as nle_text_edit:
                editor._change_speaker_for_line(0, "02")

            nle_text_edit.assert_not_called()
            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["- 첫 줄", "- 둘째 줄"])
            self.assertEqual(first.userData().spk_id, "02")
            self.assertEqual(second.userData().spk_id, "02")
            rows = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["text"], "- 첫 줄\n- 둘째 줄")
            self.assertEqual(rows[0]["speaker_list"], ["02"])
            editor._highlighter.rehighlight.assert_called_once()
            editor._finalize_edit.assert_called_once()
        finally:
            editor.text_edit.close()

    def test_live_canvas_inline_edit_skips_editor_document_rewrite(self):
        editor = _InlineEditEditor()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("원본")
        block = editor.text_edit.document().findBlockByNumber(0)
        block.setUserData(
            SubtitleBlockData(
                "",
                0.0,
                False,
                end_sec=1.0,
                quality={"confidence_label": "yellow", "flags": ["quality_stale"]},
                quality_signature="old",
                stt_selected_source="STT1",
            )
        )
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(_edit_active=True, _inline_commit_in_progress=False)
        )
        editor._cached_segs = [
            {
                "line": 0,
                "start": 0.0,
                "end": 1.0,
                "text": "원본",
                "quality": {"confidence_label": "yellow", "flags": ["quality_stale"]},
            }
        ]
        editor._cached_line_map = {0: editor._cached_segs[0]}
        editor._subtitle_memory_cache = build_segment_lookup(editor._cached_segs)
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
            quality = editor.text_edit.document().findBlockByNumber(0).userData().quality
            self.assertEqual(quality["confidence_label"], "green")
            self.assertTrue(quality["manual_confirmed"])
            self.assertIn("manual_confirmed", quality["flags"])
            self.assertNotIn("quality_stale", quality["flags"])
            editor._refresh_video_subtitle_context.assert_not_called()
            editor._schedule_video_context_refresh.assert_called_once_with(24)
        finally:
            editor.text_edit.close()

    def test_editor_text_edit_marks_segment_manual_confirmed_green(self):
        editor = _TextEditedEditor()
        editor.text_edit = QTextEdit()
        editor.text_edit.setPlainText("수정본")
        block = editor.text_edit.document().findBlockByNumber(0)
        block.setUserData(
            SubtitleBlockData(
                "00",
                1.0,
                False,
                end_sec=2.0,
                quality={"confidence_label": "red", "flags": ["high_cps"]},
                quality_signature="old",
            )
        )
        editor._cached_segs = [
            {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "원본",
                "quality": {"confidence_label": "red", "flags": ["high_cps"]},
                "quality_signature": "old",
            }
        ]
        editor._cached_line_map = {0: editor._cached_segs[0]}
        editor._subtitle_memory_cache = build_segment_lookup(editor._cached_segs)
        editor._segment_cache_valid = True
        editor._last_segment_cache_block_count = 1
        editor._sync_lock = False
        editor._inline_updating = False
        editor._subtitle_text_visibility_changed = False
        editor._app_start_time = time.time() - 5.0
        editor.sm = SimpleNamespace(is_locked=False, is_dirty=False, start_editing=Mock())
        editor._schedule_video_context_refresh = Mock()
        editor._schedule_timeline = Mock()
        editor._note_editor_foreground_activity = Mock()

        try:
            cursor = editor.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            editor.text_edit.setTextCursor(cursor)

            editor._on_text_edited()

            data = editor.text_edit.document().findBlockByNumber(0).userData()
            self.assertEqual(data.quality["confidence_label"], "green")
            self.assertTrue(data.quality["manual_confirmed"])
            self.assertIn("manual_confirmed", data.quality["flags"])
            self.assertNotIn("high_cps", data.quality["flags"])
            self.assertEqual(editor._cached_segs[0]["quality"]["confidence_label"], "green")
            self.assertTrue(editor._cached_segs[0]["quality"]["manual_confirmed"])
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
                "ui.editor.editor_segments_text_ops.build_segment_lookup",
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

    def test_subtitle_context_window_reuses_index_for_same_local_segments(self):
        editor = _DummyEditor()
        editor.settings = {
            "editor_video_context_before_sec": 20.0,
            "editor_video_context_after_sec": 20.0,
            "editor_video_context_max_segments": 80,
        }
        segments = _GuardedSegmentList(
            [
                {"line": i, "start": float(i), "end": float(i) + 0.5, "text": f"자막 {i}"}
                for i in range(2000)
            ]
        )

        first = editor._subtitle_context_window_from_segments(segments, center_sec=1000.0)
        segments.fail_on_iter = True
        second = editor._subtitle_context_window_from_segments(segments, center_sec=1001.0)

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertLess(len(second), 90)

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

    def test_initial_time_window_shows_about_fifteen_seconds(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))

            timeline.show_time_window_seconds(15.0)

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, timeline.canvas.pps)
            self.assertAlmostEqual(visible_seconds, 15.0, delta=0.35)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertFalse(timeline._fit_to_view_locked)
            self.assertAlmostEqual(timeline.global_canvas.view_start, 0.0, places=3)
            self.assertAlmostEqual(timeline.global_canvas.view_end, 15.0 / dur, delta=0.01)
        finally:
            timeline.close()

    def test_initial_time_window_can_center_on_restored_playhead(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))

            timeline.show_time_window_seconds(15.0, center_sec=60.0)

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_start = timeline.scroll.horizontalScrollBar().value() / max(0.001, timeline.canvas.pps)
            visible_center = visible_start + (viewport_w / max(0.001, timeline.canvas.pps) / 2.0)
            self.assertAlmostEqual(visible_center, 60.0, delta=0.35)
            self.assertFalse(timeline._fit_to_view_locked)
        finally:
            timeline.close()

    def test_schedule_initial_open_view_reuses_same_window_request(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 50.0))
            timeline.canvas.pps = 50.0
            timeline.scroll.horizontalScrollBar().setValue(700)

            timeline.schedule_initial_open_view(delays=(0,), seconds=10.0, start_sec=0.0)
            self.app.processEvents()

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, float(timeline.canvas.pps))
            self.assertAlmostEqual(visible_seconds, 10.0, delta=0.35)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)

            timeline.canvas.pps = 60.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 60.0))
            timeline.scroll.horizontalScrollBar().setValue(900)

            timeline.schedule_initial_open_view(delays=(0,), seconds=None)
            self.app.processEvents()

            visible_seconds = viewport_w / max(0.001, float(timeline.canvas.pps))
            self.assertAlmostEqual(visible_seconds, 10.0, delta=0.35)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
        finally:
            timeline.close()

    def test_single_waveform_ready_reapplies_initial_open_view_request(self):
        timeline = _WaveformReadyTimeline()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.schedule_initial_open_view(delays=(0,), seconds=10.0, start_sec=0.0)
            self.app.processEvents()

            timeline.canvas.pps = 60.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(180.0, 60.0))
            timeline.scroll.horizontalScrollBar().setValue(900)

            timeline._wf_worker = object()
            timeline._test_sender = timeline._wf_worker
            timeline._on_waveform_ready([0.0, 0.5, 0.25], 180.0)
            self.app.processEvents()

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, float(timeline.canvas.pps))
            self.assertAlmostEqual(visible_seconds, 10.0, delta=0.35)
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
            self.assertAlmostEqual(float(timeline.canvas.total_duration), 180.0, places=3)
        finally:
            timeline.close()

    def test_fit_mode_initial_open_view_reapplies_full_fit_after_waveform_ready(self):
        timeline = _WaveformReadyTimeline()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.pps = 60.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 60.0))
            timeline.scroll.horizontalScrollBar().setValue(900)

            timeline.schedule_initial_open_view(delays=(0,), mode="fit")
            self.app.processEvents()

            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(dur))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)

            timeline.canvas.pps = 72.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, 72.0))
            timeline.scroll.horizontalScrollBar().setValue(1200)

            timeline._wf_worker = object()
            timeline._test_sender = timeline._wf_worker
            timeline._on_waveform_ready([0.0, 0.5, 0.25], dur)
            self.app.processEvents()

            self.assertAlmostEqual(timeline.canvas.pps, timeline._fit_pps_for_duration(dur))
            self.assertEqual(timeline.scroll.horizontalScrollBar().value(), 0)
        finally:
            timeline.close()

    def test_ten_second_edit_window_button_order_and_active_segment_centering(self):
        with patch("ui.timeline.timeline_widget.load_settings", return_value={}):
            timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            self.assertEqual([btn.text() for btn in timeline._zoom_buttons], ["+", "-", "O", "ㅁ"])

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.segments = [
                {"start": 60.0, "end": 64.0, "text": "편집 중", "line": 0},
            ]
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.canvas.set_active(60.0)

            timeline.show_ten_second_edit_window()

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, timeline.canvas.pps)
            visible_start = timeline.scroll.horizontalScrollBar().value() / max(0.001, timeline.canvas.pps)
            visible_center = visible_start + (visible_seconds / 2.0)
            self.assertAlmostEqual(visible_seconds, 10.0, delta=0.35)
            self.assertAlmostEqual(visible_center, 62.0, delta=0.4)
            self.assertFalse(timeline._fit_to_view_locked)
            self.assertTrue(timeline._manual_zoom_since_fit)
        finally:
            timeline.close()

    def test_time_window_dialog_prefills_current_visible_seconds(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(15.0, center_sec=40.0)

            with patch("ui.timeline.timeline_widget.QInputDialog") as dialog_cls:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = False
                timeline._show_time_window_seconds_dialog()

            dialog.setIntValue.assert_called_once_with(15)
            label_text = dialog.setLabelText.call_args.args[0]
            self.assertIn("현재 표시 시간: 15초", label_text)
            self.assertIn("1초 단위", label_text)
        finally:
            timeline.close()

    def test_time_window_dialog_is_deferred_after_right_click_signal(self):
        timeline = TimelineWidget()
        try:
            timeline.show()
            self.app.processEvents()

            with patch.object(timeline, "_show_time_window_seconds_dialog") as show_mock:
                timeline.time_window_btn.customContextMenuRequested.emit(QPoint(4, 4))
                self.assertFalse(show_mock.called)
                self.app.processEvents()
                show_mock.assert_called_once_with()
        finally:
            timeline.close()

    def test_time_window_dialog_uses_window_owner_when_embedded(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        timeline = TimelineWidget()
        layout.addWidget(timeline)
        try:
            host.resize(900, 320)
            host.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(15.0, center_sec=40.0)

            with patch("ui.timeline.timeline_widget.QInputDialog") as dialog_cls:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = False
                timeline._show_time_window_seconds_dialog()

            dialog_cls.assert_called_once_with(host)
        finally:
            host.close()
            timeline.close()

    def test_time_window_dialog_applies_selected_seconds_around_current_center(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(10.0, center_sec=82.0)

            before_center = timeline.scroll.horizontalScrollBar().value() / max(0.001, timeline.canvas.pps)
            before_center += timeline._current_visible_seconds() / 2.0

            with patch("ui.timeline.timeline_widget.QInputDialog") as dialog_cls:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = True
                dialog.intValue.return_value = 20
                timeline._show_time_window_seconds_dialog()

            visible_seconds = timeline.scroll.viewport().width() / max(0.001, float(timeline.canvas.pps))
            visible_start = timeline.scroll.horizontalScrollBar().value() / max(0.001, float(timeline.canvas.pps))
            visible_center = visible_start + (visible_seconds / 2.0)
            self.assertAlmostEqual(visible_seconds, 20.0, delta=0.4)
            self.assertAlmostEqual(visible_center, before_center, delta=0.4)
            self.assertTrue(timeline._manual_zoom_since_fit)
            self.assertFalse(timeline._fit_to_view_locked)
        finally:
            timeline.close()

    def test_time_window_dialog_saves_selected_seconds_to_user_settings(self):
        with patch("ui.timeline.timeline_widget.load_settings", return_value={"selected_model": "exaone"}):
            timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(10.0, center_sec=82.0)

            with patch("ui.timeline.timeline_widget.QInputDialog") as dialog_cls, \
                 patch("ui.timeline.timeline_widget.load_settings", return_value={"selected_model": "exaone"}), \
                 patch("ui.timeline.timeline_widget.save_settings") as save_mock:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = True
                dialog.intValue.return_value = 17
                timeline._show_time_window_seconds_dialog()

            saved = save_mock.call_args.args[0]
            self.assertEqual(saved["selected_model"], "exaone")
            self.assertEqual(saved["timeline_edit_window_seconds"], 17)
            self.assertEqual(timeline._preferred_edit_window_seconds, 17.0)
            self.assertIn("17초", timeline.time_window_btn.toolTip())
        finally:
            timeline.close()

    def test_time_window_dialog_persists_default_value_when_reapplied(self):
        with patch("ui.timeline.timeline_widget.load_settings", return_value={"selected_model": "exaone"}):
            timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(10.0, center_sec=82.0)

            with patch("ui.timeline.timeline_widget.QInputDialog") as dialog_cls, \
                 patch("ui.timeline.timeline_widget.load_settings", return_value={"selected_model": "exaone"}), \
                 patch("ui.timeline.timeline_widget.save_settings") as save_mock:
                dialog = dialog_cls.return_value
                dialog.exec.return_value = True
                dialog.intValue.return_value = 10
                timeline._show_time_window_seconds_dialog()

            save_mock.assert_called_once()
            saved = save_mock.call_args.args[0]
            self.assertEqual(saved["selected_model"], "exaone")
            self.assertEqual(saved["timeline_edit_window_seconds"], 10)
            self.assertEqual(timeline._preferred_edit_window_seconds, 10.0)
            self.assertIn("10초", timeline.time_window_btn.toolTip())
        finally:
            timeline.close()

    def test_time_window_dialog_reads_selected_value_before_dialog_deletion(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 240.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.show_time_window_seconds(10.0, center_sec=82.0)

            class _DeletingIfConfiguredDialog:
                class InputMode:
                    IntInput = object()

                def __init__(self, _owner):
                    self._delete_on_close = False

                def setAttribute(self, attr, enabled):
                    if attr == Qt.WidgetAttribute.WA_DeleteOnClose:
                        self._delete_on_close = bool(enabled)

                def setWindowTitle(self, *_args):
                    return None

                def setInputMode(self, *_args):
                    return None

                def setLabelText(self, *_args):
                    return None

                def setIntRange(self, *_args):
                    return None

                def setIntStep(self, *_args):
                    return None

                def setIntValue(self, *_args):
                    return None

                def setOkButtonText(self, *_args):
                    return None

                def setCancelButtonText(self, *_args):
                    return None

                def setStyleSheet(self, *_args):
                    return None

                def exec(self):
                    return True

                def intValue(self):
                    if self._delete_on_close:
                        raise RuntimeError("wrapped C/C++ object of type QInputDialog has been deleted")
                    return 12

                def releaseMouse(self):
                    return None

                def releaseKeyboard(self):
                    return None

                def deleteLater(self):
                    return None

            with patch("ui.timeline.timeline_widget.QInputDialog", _DeletingIfConfiguredDialog), \
                 patch.object(timeline, "_apply_edit_window_seconds") as apply_mock, \
                 patch.object(timeline, "_save_preferred_edit_window_seconds") as save_mock:
                timeline._show_time_window_seconds_dialog()

            apply_mock.assert_called_once()
            save_mock.assert_called_once_with(12.0)
        finally:
            timeline.close()

    def test_time_window_dialog_restore_releases_toolbar_mouse_grab(self):
        timeline = TimelineWidget()
        try:
            timeline.show()
            self.app.processEvents()

            button = timeline.time_window_btn
            timeline._time_window_dialog_pending = True
            button.setDown(True)
            button.setEnabled(False)
            button.grabMouse()
            self.assertIs(QWidget.mouseGrabber(), button)

            timeline._restore_toolbar_after_time_window_dialog()
            self.app.processEvents()

            self.assertIsNone(QWidget.mouseGrabber())
            self.assertFalse(timeline._time_window_dialog_pending)
            for toolbar_button in timeline._zoom_buttons:
                self.assertEqual(toolbar_button.focusPolicy(), Qt.FocusPolicy.NoFocus)
                self.assertFalse(toolbar_button.isDown())
                self.assertFalse(toolbar_button.hasFocus())
                self.assertTrue(toolbar_button.isEnabled())
        finally:
            try:
                grabber = QWidget.mouseGrabber()
                if grabber is not None:
                    grabber.releaseMouse()
            except Exception:
                pass
            timeline.close()

    def test_time_window_dialog_restore_closes_lingering_popup_and_modal_widgets(self):
        timeline = TimelineWidget()
        popup = QWidget()
        modal = QWidget()
        try:
            timeline.show()
            popup.show()
            modal.show()
            self.app.processEvents()

            timeline._time_window_dialog_pending = True
            with patch("ui.timeline.timeline_widget.QApplication.activePopupWidget", return_value=popup), \
                 patch("ui.timeline.timeline_widget.QApplication.activeModalWidget", return_value=modal):
                timeline._restore_toolbar_after_time_window_dialog()
            self.app.processEvents()

            self.assertFalse(timeline._time_window_dialog_pending)
            self.assertFalse(popup.isVisible())
            self.assertFalse(modal.isVisible())
        finally:
            popup.close()
            modal.close()
            timeline.close()

    def test_time_window_dialog_restore_rejects_tracked_modal_and_reenables_window(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        timeline = TimelineWidget()
        layout.addWidget(timeline)
        dialog = QDialog(host)
        try:
            host.show()
            timeline.show()
            dialog.setModal(True)
            dialog.show()
            self.app.processEvents()

            host.setEnabled(False)
            timeline._time_window_dialog_pending = True
            timeline._time_window_dialog = dialog
            for toolbar_button in timeline._zoom_buttons:
                toolbar_button.setDown(True)
                toolbar_button.setEnabled(False)

            with patch("ui.timeline.timeline_widget.QApplication.activePopupWidget", return_value=None), \
                 patch("ui.timeline.timeline_widget.QApplication.activeModalWidget", return_value=None):
                timeline._restore_toolbar_after_time_window_dialog()
            self.app.processEvents()

            self.assertFalse(timeline._time_window_dialog_pending)
            self.assertTrue(host.isEnabled())
            self.assertFalse(dialog.isVisible())
            self.assertFalse(dialog.isModal())
            for toolbar_button in timeline._zoom_buttons:
                self.assertFalse(toolbar_button.isDown())
                self.assertTrue(toolbar_button.isEnabled())
        finally:
            dialog.close()
            host.close()
            timeline.close()

    def test_show_ten_second_edit_window_uses_saved_user_preference(self):
        with patch("ui.timeline.timeline_widget.load_settings", return_value={"timeline_edit_window_seconds": 20}):
            timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            dur = 180.0
            timeline.canvas.total_duration = dur
            timeline.global_canvas.total_duration = dur
            timeline.canvas.segments = [
                {"start": 60.0, "end": 64.0, "text": "편집 중", "line": 0},
            ]
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(dur, timeline.canvas.pps))
            timeline.canvas.set_active(60.0)

            timeline.show_ten_second_edit_window()

            viewport_w = max(1, timeline.scroll.viewport().width())
            visible_seconds = viewport_w / max(0.001, timeline.canvas.pps)
            visible_start = timeline.scroll.horizontalScrollBar().value() / max(0.001, timeline.canvas.pps)
            visible_center = visible_start + (visible_seconds / 2.0)
            self.assertAlmostEqual(visible_seconds, 20.0, delta=0.4)
            self.assertAlmostEqual(visible_center, 62.0, delta=0.4)
            self.assertIn("20초", timeline.time_window_btn.toolTip())
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

    def test_fit_content_duration_uses_canvas_cached_duration(self):
        timeline = TimelineWidget()
        try:
            timeline.canvas.total_duration = 10.0
            timeline.canvas._segments_content_duration = 123.0
            guarded = _GuardedSegmentList([
                {"line": 0, "start": 0.0, "end": 123.0, "text": "긴 자막"},
            ])
            guarded.fail_on_iter = True
            timeline.canvas.segments = guarded

            self.assertEqual(timeline._fit_content_duration(), 123.0)
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

    def test_playhead_uses_canvas_repaint_when_overlay_is_disabled_for_visibility(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.canvas.update = Mock()
            timeline.set_playhead(2.5)
            self.app.processEvents()

            self.assertFalse(getattr(timeline.canvas, "_external_playhead_overlay", True))
            self.assertEqual(timeline.canvas.playhead_sec, 2.5)
            self.assertEqual(timeline.canvas._last_playhead_px, timeline.canvas._x(2.5))
            timeline.canvas.update.assert_called_once_with()
            self.assertEqual(timeline._playhead_overlay._sec, 2.5)
            self.assertIs(timeline._playhead_overlay.parent(), timeline.scroll.viewport())
            self.assertTrue(timeline._playhead_overlay.isHidden())
        finally:
            timeline.close()

    def test_timeline_playhead_keeps_logical_frame_snap_with_subframe_visual_position(self):
        timeline = TimelineWidget()
        try:
            timeline.canvas.pps = 100.0

            timeline.set_playhead(1.0, visual_sec=1.25)

            self.assertEqual(timeline.canvas.playhead_sec, 1.0)
            self.assertEqual(timeline.global_canvas.playhead_sec, 1.0)
            self.assertAlmostEqual(timeline.canvas._playhead_visual_sec, 1.25)
            self.assertEqual(timeline.canvas._last_playhead_px, 125)
            self.assertTrue(timeline.canvas._playhead_handle_hit_rect().contains(QPoint(125, 8)))
        finally:
            timeline.close()

    def test_playhead_overlay_skips_duplicate_pixel_updates(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.set_playhead(2.5)
            self.app.processEvents()

            timeline._playhead_overlay.update = Mock()
            timeline.set_playhead(2.5)
            timeline._sync_playhead_overlay()
            self.app.processEvents()

            timeline._playhead_overlay.update.assert_not_called()
        finally:
            timeline.close()

    def test_playhead_canvas_repaints_full_2d_owner_instead_of_overlay_dirty_strip(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.set_playhead(2.0)
            self.app.processEvents()

            timeline.canvas.update = Mock()
            timeline._playhead_overlay.update = Mock()
            timeline.set_playhead(3.0)

            timeline.canvas.update.assert_called_once_with()
            timeline._playhead_overlay.update.assert_not_called()
        finally:
            timeline.close()

    def test_shadow_playhead_repaints_canvas_full_2d_owner_without_overlay_dirty_strip(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.update_segments([{"start": 0.0, "end": 10.0, "text": "테스트"}], active_sec=0.0, total_dur=10.0)
            timeline.set_playhead(2.0)
            self.app.processEvents()

            timeline.canvas.update = Mock()
            timeline._playhead_overlay.update = Mock()
            timeline.pin_shadow_playhead(4.0)

            timeline.canvas.update.assert_called_once_with()
            timeline._playhead_overlay.update.assert_not_called()
            self.assertAlmostEqual(timeline.canvas.shadow_playhead_sec, 4.0)
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

    def test_centered_playback_follow_locks_immediately_at_max_zoom(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(900, timeline.height())
            timeline.show()
            self.app.processEvents()

            timeline.canvas.total_duration = 300.0
            timeline.global_canvas.total_duration = 300.0
            timeline.canvas.pps = 500.0
            timeline.canvas.setFixedWidth(timeline._canvas_width_for_duration(300.0, 500.0))
            timeline.scroll.horizontalScrollBar().setValue(0)

            timeline.follow_playhead_centered(40.0, smooth=True)

            self.assertTrue(timeline._playback_center_lock)
            self.assertFalse(timeline._pending_playback_center_lock)
            self.assertTrue(timeline._playhead_overlay._center_locked)
            self.assertTrue(timeline._smooth_scroll_timer.isActive())
            self.assertEqual(timeline.canvas.playhead_sec, 40.0)
            self.assertGreater(timeline._target_scroll_x, 0.0)
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

    def test_playhead_menu_includes_auto_cut_boundary_magnet_toggle(self):
        editor = _PlayheadMenuEditor()

        items = editor._playhead_menu_items()

        magnet = next(item for item in items if item.get("id") == "playhead_auto_cut_magnet")
        self.assertEqual(magnet["label"], "자동 컷 경계 자석")
        self.assertFalse(magnet["checked"])

    def test_playing_segment_sync_does_not_jump_playhead_to_segment_start(self):
        editor = _DummyTimelineVideoEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
        )
        canvas = SimpleNamespace(playhead_sec=4.8, set_active=Mock(), clear_active_visual=Mock())
        editor.video_player = SimpleNamespace(media_player=player)
        editor.timeline = SimpleNamespace(canvas=canvas, set_active=Mock(), set_playhead=Mock())
        editor._highlighter = SimpleNamespace(set_current_line=Mock())

        editor._sync_cursor_to_seg({"start": 4.0, "end": 6.0, "line": 3}, ensure_visible=False, move_cursor=False)

        canvas.clear_active_visual.assert_called_once_with()
        canvas.set_active.assert_not_called()
        editor.timeline.set_active.assert_not_called()
        editor.timeline.set_playhead.assert_not_called()

    def test_paused_segment_sync_updates_video_subtitle_time(self):
        editor = _DummyTimelineVideoEditor()
        playing_state = object()
        paused_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=paused_state),
        )
        editor.video_player = SimpleNamespace(media_player=player, set_subtitle_display_time=Mock())
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=4.8),
            set_active=Mock(),
            set_playhead=Mock(),
        )
        editor._highlighter = SimpleNamespace(set_current_line=Mock())

        editor._sync_cursor_to_seg({"start": 4.0, "end": 6.0, "line": 3}, ensure_visible=False, move_cursor=False)

        editor.timeline.set_playhead.assert_called_once_with(4.0)
        editor.video_player.set_subtitle_display_time.assert_called_once_with(4.0)

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

    def test_sync_playhead_accepts_external_backend_without_playbackstate_enum_attr(self):
        editor = _DummyTimelineVideoEditor()
        player = SimpleNamespace(
            playbackState=Mock(return_value=QMediaPlayer.PlaybackState.PausedState),
        )
        editor.video_player = SimpleNamespace(media_player=player)
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(playhead_sec=3.2),
            set_playback_center_lock=Mock(),
        )
        editor._playhead_timer = SimpleNamespace(
            interval=Mock(return_value=16),
            setInterval=Mock(),
        )
        editor._reset_playhead_smoothing = Mock()

        editor._sync_playhead()

        editor._playhead_timer.setInterval.assert_called_once_with(80)
        editor.timeline.set_playback_center_lock.assert_called_once_with(False)
        editor._reset_playhead_smoothing.assert_called_once_with(3.2)

    def test_playhead_timer_guard_restarts_stopped_timer_before_playback(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_fps = 30.0
        editor._playhead_timer = SimpleNamespace(
            isActive=Mock(return_value=False),
            start=Mock(),
        )

        editor._ensure_playhead_timer_running()

        editor._playhead_timer.start.assert_called_once_with(editor._playhead_active_interval_ms())

    def test_manual_seek_in_silent_gap_syncs_editor_to_nearest_real_segment(self):
        editor = _PlaybackEditor()
        editor._segments = [
            {"start": 10.0, "end": 11.0, "line": 1, "text": "이전"},
            {"start": 20.0, "end": 21.0, "line": 2, "text": "다음"},
        ]
        editor._snap_to_frame = lambda sec: float(sec)
        editor._sync_cursor_to_seg = Mock()
        editor._reset_playhead_smoothing = Mock()
        editor.timeline = SimpleNamespace(set_playhead=Mock(), center_to_sec=Mock())

        editor._sync_after_manual_seek(15.0)

        editor._sync_cursor_to_seg.assert_called_once_with(editor._segments[0], sync_playhead=False)
        editor.timeline.set_playhead.assert_called_once_with(15.0)
        editor.timeline.center_to_sec.assert_called_once_with(15.0, smooth=False)

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
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock(), clear_active_visual=Mock()),
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
            editor.timeline.canvas.clear_active_visual.assert_called_once_with()
            editor.timeline.canvas.set_active.assert_not_called()
            editor.timeline.set_active.assert_not_called()
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
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock(), clear_active_visual=Mock()),
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
            editor.timeline.canvas.clear_active_visual.assert_called_once_with()
            editor.timeline.canvas.set_active.assert_not_called()
            editor.timeline.set_active.assert_not_called()
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
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock(), clear_active_visual=Mock()),
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
            editor.timeline.canvas.clear_active_visual.assert_called_once_with()
            editor.timeline.canvas.set_active.assert_not_called()
            editor.timeline.set_active.assert_not_called()
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
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock(), clear_active_visual=Mock()),
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
            editor.timeline.canvas.clear_active_visual.assert_called_once_with()
            editor.timeline.canvas.set_active.assert_not_called()
            editor.timeline.set_active.assert_not_called()
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
            canvas=SimpleNamespace(playhead_sec=0.0, _edit_active=False, set_active=Mock(), clear_active_visual=Mock()),
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
            editor.timeline.canvas.clear_active_visual.assert_called_once_with()
            editor.timeline.canvas.set_active.assert_not_called()
            editor.timeline.set_active.assert_not_called()
        finally:
            editor.text_edit.close()

    def test_settled_scrub_moves_editor_cursor_without_snapping_playhead_to_segment_start(self):
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
            self.assertNotIn(call(4.0), editor.timeline.set_playhead.mock_calls)
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

            editor.timeline.follow_playhead_centered.assert_called_once_with(27.0, smooth=True, visual_sec=27.0)
            editor.timeline.follow_playhead.assert_not_called()
            editor.video_player.set_subtitle_display_time.assert_called_once_with(27.0)
            self.assertEqual(editor._playhead_display_sec, 27.0)
        finally:
            editor.text_edit.close()

    def test_playhead_sync_uses_smoothed_display_for_timeline_follow(self):
        editor = _PlaybackEditor()
        playing_state = object()
        player = SimpleNamespace(
            PlaybackState=SimpleNamespace(PlayingState=playing_state),
            playbackState=Mock(return_value=playing_state),
            position=Mock(return_value=10_200),
            duration=Mock(return_value=60_000),
        )
        editor.video_player = SimpleNamespace(
            media_player=player,
            current_playback_frame_time=Mock(return_value=(306, 10.2)),
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
        editor._segments = [{"start": 10.0, "end": 11.0, "line": 0, "text": "자막"}]
        editor._playhead_display_sec = 10.0
        editor._playhead_anchor_global_sec = 10.0
        editor._playhead_anchor_mono = 100.0
        editor._last_playhead_smooth_tick = 100.0

        try:
            with patch("ui.editor.editor_timeline_video.time.monotonic", return_value=100.016):
                editor._sync_playhead()

            call_args = editor.timeline.follow_playhead_centered.call_args
            follow_sec = call_args.kwargs["visual_sec"]
            editor.timeline.follow_playhead.assert_not_called()
            self.assertEqual(call_args.args[0], 10.2)
            self.assertGreater(follow_sec, 10.0)
            self.assertLess(follow_sec, 10.2)
            editor.video_player.set_subtitle_display_time.assert_called_once_with(10.2)
            self.assertEqual(editor._playhead_display_sec, follow_sec)
        finally:
            editor.text_edit.close()

    def test_playhead_active_interval_tracks_current_frame_rate(self):
        editor = _DummyTimelineVideoEditor()
        with patch.dict(os.environ, {"AI_SUBTITLE_UI_REFRESH_HZ": "120"}):
            editor.video_fps = 24.0
            self.assertEqual(editor._playhead_active_interval_ms(), 8)

        with patch.dict(os.environ, {"AI_SUBTITLE_UI_REFRESH_HZ": "60"}):
            editor.video_fps = 24.0
            self.assertEqual(editor._playhead_active_interval_ms(), 17)

            editor.video_fps = 60.0
            self.assertEqual(editor._playhead_active_interval_ms(), 17)

    def test_playhead_smoothing_keeps_subframe_display_time(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_fps = 24.0
        editor.timeline = SimpleNamespace(canvas=SimpleNamespace(playhead_sec=10.0))
        editor._playhead_display_sec = 10.0
        editor._playhead_anchor_global_sec = 10.0
        editor._playhead_anchor_mono = 100.0
        editor._last_playhead_smooth_tick = 100.0

        value = editor._smooth_playhead_sec(10.2, 100.016, 60.0)

        self.assertGreater(value, 10.0)
        self.assertLess(value, 10.2)
        self.assertNotAlmostEqual(value, editor._snap_to_frame(value), places=5)

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

    def test_timeline_canvas_prefers_saved_frame_bounds_over_srt_milliseconds(self):
        timeline = TimelineWidget()
        fps = 59.94005994005994
        try:
            timeline.set_frame_rate(fps)
            timeline.update_segments(
                [
                    {
                        "start": 32.015,
                        "end": 34.985,
                        "start_frame": 1919,
                        "end_frame": 2097,
                        "timeline_frame_rate": fps,
                        "text": "와",
                    }
                ],
                active_sec=0.0,
                total_dur=40.0,
            )

            segment = timeline.canvas.segments[0]
            self.assertEqual((segment["start_frame"], segment["end_frame"]), (1919, 2097))
            self.assertAlmostEqual(segment["start"], frame_to_sec(1919, fps), places=9)
            self.assertAlmostEqual(segment["end"], frame_to_sec(2097, fps), places=9)
        finally:
            timeline.close()

    def test_timeline_canvases_do_not_share_opengl_video_surface(self):
        self.assertIs(TimelineCanvasBase, QWidget)
        self.assertIs(GlobalCanvasBase, QWidget)

    def test_global_canvas_uses_expanded_minimap_without_waveform_dependency(self):
        timeline = TimelineWidget()
        try:
            timeline.global_canvas.resize(420, timeline.global_canvas.height())
            timeline.global_canvas.total_duration = 20.0
            timeline.global_canvas.update_segments(
                [
                    {"start": 1.0, "end": 4.0, "text": "첫 자막"},
                    {"start": 6.0, "end": 8.0, "text": "둘째 자막"},
                ],
                20.0,
            )
            timeline.global_canvas.set_vad_segments([])
            self.assertEqual(timeline.global_canvas.height(), MINIMAP_HEIGHT)

            pixmap = timeline.global_canvas._build_static_cache()

            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.height(), MINIMAP_HEIGHT)
        finally:
            timeline.close()

    def test_global_canvas_expands_into_extra_bottom_space(self):
        timeline = TimelineWidget()
        try:
            base_height = timeline.sizeHint().height()
            timeline.resize(900, base_height + 64)
            timeline.show()
            self.app.processEvents()

            self.assertGreater(timeline.global_canvas.height(), MINIMAP_HEIGHT)

            pixmap = timeline.global_canvas._build_static_cache()
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.height(), timeline.global_canvas.height())
        finally:
            timeline.close()

    def test_global_canvas_silence_and_subtitle_lanes_share_expanded_height_evenly(self):
        timeline = TimelineWidget()
        try:
            canvas = timeline.global_canvas
            canvas.resize(420, MINIMAP_HEIGHT)
            canvas.total_duration = 20.0
            stt1 = {"start": 1.0, "end": 4.0, "text": "stt1", "stt_pending": True, "stt_preview_source": "STT1"}
            stt2 = {"start": 2.0, "end": 6.0, "text": "stt2", "stt_pending": True, "stt_preview_source": "STT2"}
            final = {"start": 7.0, "end": 10.0, "text": "final"}
            canvas.update_segments([stt1, stt2, final], 20.0)

            bottom_lane = QRect(0, MINIMAP_MARKER_LANE_H, 420, MINIMAP_HEIGHT - MINIMAP_MARKER_LANE_H - 1)
            lanes = canvas._bottom_lane_layout(bottom_lane, include_stt=True)

            self.assertEqual(list(lanes.keys()), ["SILENCE", "SUBTITLE"])
            self.assertLessEqual(abs(lanes["SILENCE"].height() - lanes["SUBTITLE"].height()), 1)
            self.assertEqual(lanes["SILENCE"].height() + lanes["SUBTITLE"].height(), bottom_lane.height())
            self.assertEqual([row["lane"] for row in canvas._merged_minimap_subtitle_segments(420, 20.0, lane="STT1")], ["STT1"])
            self.assertEqual([row["lane"] for row in canvas._merged_minimap_subtitle_segments(420, 20.0, lane="STT2")], ["STT2"])
            self.assertTrue(all(row["lane"] == "SILENCE" for row in canvas._merged_minimap_silence_segments(420, 20.0)))

            pixmap = canvas._build_static_cache()
            self.assertFalse(pixmap.isNull())
            self.assertEqual(pixmap.height(), MINIMAP_HEIGHT)
        finally:
            timeline.close()

    def test_timeline_update_segments_can_project_final_only_rows_to_global_canvas(self):
        timeline = TimelineWidget()
        try:
            final = {"start": 0.0, "end": 2.0, "text": "final"}
            draft = {"start": 0.5, "end": 1.5, "text": "draft", "_live_subtitle_preview": True}
            stt = {"start": 0.5, "end": 1.5, "text": "stt", "stt_pending": True, "stt_preview_source": "STT1"}

            timeline.update_segments(
                [final, draft, stt],
                active_sec=0.0,
                total_dur=2.0,
                global_rows=[final],
            )

            self.assertEqual([row["text"] for row in timeline.canvas.segments], ["final", "draft", "stt"])
            self.assertEqual(
                [row["_nle_runtime_surface"] for row in timeline.canvas.segments],
                ["timeline_canvas", "timeline_canvas_preview", "timeline_canvas_preview"],
            )
            self.assertEqual([row["text"] for row in timeline.global_canvas.segments], ["final"])
            self.assertEqual(
                [row["lane"] for row in timeline.global_canvas._merged_minimap_subtitle_segments(420, 2.0)],
                ["SUBTITLE"],
            )
        finally:
            timeline.close()

    def test_global_canvas_major_segments_render_outline_without_fill(self):
        timeline = TimelineWidget()
        try:
            canvas = timeline.global_canvas
            canvas.resize(420, canvas.height())
            canvas.total_duration = 20.0
            canvas.update_segments([], 20.0)
            canvas.set_vad_segments([])
            canvas._middle_segments = [
                {
                    "start": 2.0,
                    "end": 8.0,
                    "major_id": "A",
                    "title": "실내 인테리어 소개",
                    "status": "confirmed",
                }
            ]

            pixmap = canvas._build_static_cache()
            image = pixmap.toImage()
            bg = QColor(MINIMAP_TOP_LANE_BG).name()
            top_lane_center_y = max(4, MINIMAP_MARKER_LANE_H // 2)
            inside_x = canvas._sec_to_px(5.0)
            border_x = canvas._sec_to_px(2.0)

            self.assertEqual(image.pixelColor(inside_x, top_lane_center_y).name(), bg)
            self.assertNotEqual(image.pixelColor(border_x, top_lane_center_y).name(), bg)
        finally:
            timeline.close()

    def test_global_canvas_preliminary_lane_renders_above_topicless_reference_lane(self):
        timeline = TimelineWidget()
        try:
            canvas = timeline.global_canvas
            canvas.resize(420, canvas.height())
            canvas.total_duration = 20.0
            canvas.update_segments([], 20.0)
            canvas.set_vad_segments([])
            canvas._preliminary_middle_segments = [
                {
                    "start": 2.0,
                    "end": 8.0,
                    "major_id": "A",
                    "title": "예비 실내 소개",
                    "status": "provisional",
                }
            ]
            canvas._cut_boundary_topicless_middle_segments = [
                {
                    "start": 1.0,
                    "end": 10.0,
                    "major_id": "A",
                    "title": "주제없음",
                    "status": "provisional",
                    "is_topicless_placeholder": True,
                }
            ]

            pixmap = canvas._build_static_cache()
            image = pixmap.toImage()
            top_lane_h = max(1, MINIMAP_MARKER_LANE_H)
            preview_inside_y = max(2, top_lane_h // 4)
            reference_inside_y = max(preview_inside_y + 2, (top_lane_h * 3) // 4)
            inside_x = canvas._sec_to_px(5.0)
            border_x = canvas._sec_to_px(1.0)

            self.assertNotEqual(image.pixelColor(inside_x, preview_inside_y).name(), QColor(MINIMAP_PRELIMINARY_LANE_BG).name())
            self.assertEqual(image.pixelColor(inside_x, reference_inside_y).name(), QColor(MINIMAP_REFERENCE_LANE_BG).name())
            self.assertNotEqual(image.pixelColor(border_x, reference_inside_y).name(), QColor(MINIMAP_REFERENCE_LANE_BG).name())
        finally:
            timeline.close()

    def test_global_canvas_renders_silence_lane_above_subtitle_lane(self):
        timeline = TimelineWidget()
        try:
            canvas = timeline.global_canvas
            canvas.resize(420, canvas.height())
            canvas.total_duration = 10.0
            canvas.update_segments(
                [
                    {"start": 1.0, "end": 4.0, "text": "첫 자막"},
                ],
                10.0,
            )
            canvas.set_vad_segments([])
            timeline.canvas.gap_segments = [
                {"start": 0.0, "end": 1.0, "is_gap": True},
                {"start": 4.0, "end": 10.0, "is_gap": True},
            ]

            pixmap = canvas._build_static_cache()
            image = pixmap.toImage()
            bottom_lane = QRect(0, MINIMAP_MARKER_LANE_H, 420, canvas.height() - MINIMAP_MARKER_LANE_H - 1)
            lanes = canvas._bottom_lane_layout(bottom_lane, include_stt=True)
            silence_y = lanes["SILENCE"].y() + max(2, lanes["SILENCE"].height() // 2)
            subtitle_y = lanes["SUBTITLE"].y() + max(2, lanes["SUBTITLE"].height() // 2)
            subtitle_x = canvas._sec_to_px(2.0)
            silence_x = canvas._sec_to_px(0.4)
            subtitle_px = image.pixelColor(subtitle_x, subtitle_y)
            silence_px = image.pixelColor(silence_x, silence_y)

            self.assertNotEqual(subtitle_px.name(), QColor(MINIMAP_SUBTITLE_LANE_BG).name())
            self.assertNotEqual(silence_px.name(), QColor(MINIMAP_SILENCE_LANE_BG).name())
            self.assertGreater(subtitle_px.blue(), subtitle_px.red())
            self.assertGreater(silence_px.blue(), silence_px.red())
            self.assertGreater(silence_px.red(), 60)
        finally:
            timeline.close()

    def test_global_canvas_merges_nearby_subtitles_for_minimap_readability(self):
        timeline = TimelineWidget()
        try:
            canvas = timeline.global_canvas
            canvas.resize(420, canvas.height())
            canvas.total_duration = 10.0
            canvas.update_segments(
                [
                    {"start": 1.0, "end": 1.20, "text": "오늘은"},
                    {"start": 1.24, "end": 1.40, "text": "여기"},
                ],
                10.0,
            )
            canvas.set_vad_segments([])

            pixmap = canvas._build_static_cache()
            image = pixmap.toImage()
            bottom_lane = QRect(0, MINIMAP_MARKER_LANE_H, 420, canvas.height() - MINIMAP_MARKER_LANE_H - 1)
            lanes = canvas._bottom_lane_layout(bottom_lane, include_stt=True)
            subtitle_y = lanes["SUBTITLE"].y() + max(2, lanes["SUBTITLE"].height() // 2)
            bridge_x = canvas._sec_to_px(1.22)
            bridge_px = image.pixelColor(bridge_x, subtitle_y)

            self.assertNotEqual(bridge_px.name(), QColor(MINIMAP_SUBTITLE_LANE_BG).name())
            self.assertGreater(bridge_px.blue(), bridge_px.red())
        finally:
            timeline.close()

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

    def test_playhead_overlay_stays_hidden_to_keep_canvas_visible(self):
        timeline = TimelineWidget()
        try:
            self.assertIsNone(getattr(timeline._playhead_overlay, "_quick", None))
            self.assertFalse(getattr(timeline._playhead_overlay, "_render_visuals", True))
            self.assertTrue(timeline._playhead_overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertIs(timeline._playhead_overlay.parent(), timeline.scroll.viewport())
            self.assertTrue(timeline._playhead_overlay.isHidden())
            self.assertFalse(getattr(timeline.canvas, "_external_playhead_overlay", True))
            self.assertEqual(getattr(timeline.canvas, "render_backend", ""), "qwidget-2d")
            self.assertEqual(getattr(timeline.global_canvas, "render_backend", ""), "qwidget-2d")
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
            self.assertFalse(getattr(timeline._playhead_overlay, "_render_visuals", True))

            timeline.set_playhead_busy(False)

            self.assertFalse(getattr(timeline.canvas, "playhead_busy", True))
            self.assertFalse(getattr(timeline._playhead_overlay, "_busy", True))
        finally:
            timeline.close()

    def test_scan_cut_active_toggles_playhead_busy_state(self):
        editor = _DummyTimelineVideoEditor()
        editor.video_player = SimpleNamespace(set_scan_cut_active=Mock())
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(),
            set_playhead_busy=Mock(),
            set_playback_center_lock=Mock(),
        )
        editor._auto_cut_boundary_scan_active = False

        editor._set_scan_cut_button_active(1)
        editor.timeline.set_playhead_busy.assert_called_with(True)

        editor.timeline.set_playhead_busy.reset_mock()
        editor._set_scan_cut_button_active(0)
        editor.timeline.set_playhead_busy.assert_called_with(False)

        editor.timeline.set_playhead_busy.reset_mock()
        editor._set_auto_cut_boundary_scan_active(True)
        editor.timeline.set_playhead_busy.assert_called_with(True)
        self.assertFalse(getattr(editor.timeline.canvas, "_scan_cut_input_locked", False))

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

    def test_cancel_scan_cut_unlocks_timeline_input_immediately(self):
        editor = _DummyTimelineVideoEditor()
        canvas = SimpleNamespace()
        editor.timeline = SimpleNamespace(
            canvas=canvas,
            set_playhead_busy=Mock(),
            set_playback_center_lock=Mock(),
        )
        editor.video_player = SimpleNamespace(
            set_scan_cut_active=Mock(),
            info_label=SimpleNamespace(setText=Mock()),
        )
        editor._scan_cut_timer = SimpleNamespace(stop=Mock())
        editor._auto_cut_boundary_scan_active = False
        editor._scan_cut_state = {"cancel_requested": False}
        editor._scan_set_timeline_input_locked(True)

        editor._cancel_scan_cut("same-button-toggle")

        self.assertTrue(editor._scan_cut_cancel_requested)
        self.assertIsNone(editor._scan_cut_state)
        self.assertFalse(getattr(canvas, "_scan_cut_input_locked", True))
        editor.timeline.set_playhead_busy.assert_called_with(False)
        editor.video_player.set_scan_cut_active.assert_called_with(0)

    def test_cancel_scan_cut_releases_capture_and_thumbnail_memory(self):
        editor = _DummyTimelineVideoEditor()
        capture = SimpleNamespace(release=Mock())
        thumb_label = SimpleNamespace(clear_pixmap=Mock())
        video_widget = object()
        video_stack = SimpleNamespace(setCurrentWidget=Mock())
        canvas = SimpleNamespace()
        editor.timeline = SimpleNamespace(
            canvas=canvas,
            set_playhead_busy=Mock(),
            set_playback_center_lock=Mock(),
        )
        editor.video_player = SimpleNamespace(
            set_scan_cut_active=Mock(),
            info_label=SimpleNamespace(setText=Mock()),
            thumb_label=thumb_label,
            video_stack=video_stack,
            video_widget=video_widget,
        )
        editor._scan_cut_timer = SimpleNamespace(stop=Mock())
        editor._auto_cut_boundary_scan_active = False
        editor._scan_cut_state = {"cancel_requested": False}
        editor._scan_cv2_capture = capture
        editor._scan_cv2_source_path = "/tmp/sample.mp4"
        editor._scan_cut_strict_verify_bundle_cache = {"verify_fn": object()}
        editor._scan_logged_capture_resolution = True
        editor._scan_last_preview_sec = 12.0
        editor._scan_last_preview_thumbnail_at = 99.0

        editor._cancel_scan_cut("same-button-toggle")

        capture.release.assert_called_once()
        thumb_label.clear_pixmap.assert_called_once()
        video_stack.setCurrentWidget.assert_called_once_with(video_widget)
        self.assertIsNone(editor._scan_cv2_capture)
        self.assertIsNone(editor._scan_cv2_source_path)
        self.assertIsNone(editor._scan_cut_strict_verify_bundle_cache)
        self.assertFalse(editor._scan_logged_capture_resolution)
        self.assertEqual(editor._scan_last_preview_sec, 0.0)
        self.assertEqual(editor._scan_last_preview_thumbnail_at, 0.0)

    def test_scan_cut_button_starts_visual_search_from_playhead_without_cached_jump(self):
        editor = _DummyTimelineVideoEditor()
        editor.settings = {"cut_boundary_detection_enabled": True}
        editor.video_fps = 30.0
        editor.video_player = SimpleNamespace(
            pause_video=Mock(),
            set_scan_cut_active=Mock(),
            info_label=SimpleNamespace(setText=Mock()),
        )
        editor.timeline = SimpleNamespace(
            canvas=SimpleNamespace(total_duration=60.0),
            set_playhead_busy=Mock(),
            set_playback_center_lock=Mock(),
        )
        editor._scan_jump_to_cached_cut_boundary = Mock(side_effect=AssertionError("cached jump should stay unused"))
        editor._manual_global_sec_from_player = Mock(return_value=3.0)
        editor._scan_threshold = Mock(return_value=24.0)
        editor._scan_interval_ms = Mock(return_value=1)
        editor._scan_max_frames = Mock(return_value=0)
        editor._scan_capture_image_at_global = Mock(return_value=None)
        editor._scan_terminal_log = Mock()
        editor._scan_image_backend_label = Mock(return_value="opencv-gray-cross")

        editor._on_scan_cut_requested(1)

        editor.video_player.pause_video.assert_called_once()
        editor._scan_capture_image_at_global.assert_called_once_with(3.0)
        editor.video_player.set_scan_cut_active.assert_any_call(1)
        editor.video_player.set_scan_cut_active.assert_any_call(0)

    def test_editor_mouse_press_stops_active_scan_cut_immediately(self):
        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            editor._scan_cut_state = {"direction": 1}
            editor._cancel_scan_cut = Mock()

            handled = editor.eventFilter(editor.timeline.canvas, QEvent(QEvent.Type.MouseButtonPress))

            self.assertTrue(handled)
            editor._cancel_scan_cut.assert_called_once_with("mouse-click-stop")
        finally:
            editor.close()

    def test_editor_mouse_press_pauses_playback_on_timeline_click(self):
        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            editor._is_video_playback_active = Mock(return_value=True)
            editor.video_player.pause_video = Mock()

            handled = editor.eventFilter(editor.timeline.canvas, QEvent(QEvent.Type.MouseButtonPress))

            self.assertFalse(handled)
            editor.video_player.pause_video.assert_called_once_with()
        finally:
            editor.close()

    def test_editor_mouse_press_ignores_pause_when_playback_is_idle(self):
        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            editor._is_video_playback_active = Mock(return_value=False)
            editor.video_player.pause_video = Mock()

            handled = editor.eventFilter(editor.text_edit.viewport(), QEvent(QEvent.Type.MouseButtonPress))

            self.assertFalse(handled)
            editor.video_player.pause_video.assert_not_called()
        finally:
            editor.close()

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
