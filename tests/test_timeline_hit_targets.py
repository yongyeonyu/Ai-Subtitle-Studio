# Version: 03.09.26
# Phase: PHASE2
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit, QWidget
from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_global import GlobalCanvas
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_constants import (
    DIAMOND_Y,
    HANDLE_R,
    RULER_H,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_TOP,
    STT2_TOP,
    SUBTITLE_BOT,
    SUBTITLE_TOP,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
)
from ui.timeline.timeline_paint import (
    build_stt_selection_index,
    should_paint_subtitle_segment_text,
    stt_preview_selection_badge_rect,
    stt_candidate_selected,
    stt_candidate_selected_by_llm,
    stt_candidate_selection_state,
    stt_candidate_unselected,
)
from ui.timeline.timeline_segment_style import official_boundary_marker_visual
from ui.timeline.timeline_analysis import subtitle_detection_segments_for_editor
from ui.editor.editor_helpers import make_gap_ud
from ui.editor.editor_multiclip_context import EditorMulticlipContextMixin
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_scan_cut_core import EditorScanCutCoreMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.editor_video_controls import EditorVideoControlsMixin
from ui.editor.undo_manager import UndoManager
from ui.editor.ux.timeline_playhead_mode import dispatch_playhead_arrow_step
from ui.editor import timeline_scan_cut_relative_refine as scan_cut_relative_refine
from ui.editor.subtitle_text_edit import SubtitleBlockData


class _Undo:
    def push_immediate(self):
        pass


class _TimelineTextEdit(QTextEdit):
    def update_margins(self):
        pass


class _GapGenerateEditor(EditorTimelineVideoMixin, EditorSegmentsMixin):
    settings = {"spk1_id": "00"}

    def _multiclip_active_offset(self) -> float:
        return 0.0

    def _redraw_timeline_preserve_resize_view(self, state: dict) -> None:
        self.redraw_requested = True

    def _invalidate_segment_cache(self):
        super()._invalidate_segment_cache()
        self.invalidated = True

    def _finalize_edit(self):
        self.finalized = True

    def _mark_dirty(self):
        self.dirty = True


class _GapGenerateUndoRouteEditor(EditorMulticlipContextMixin, _GapGenerateEditor):
    pass


class _ReviewEditor(EditorVideoControlsMixin, EditorSegmentsMixin):
    def __init__(self):
        self.text_edit = QTextEdit()
        self._undo_mgr = _Undo()
        self._segments = []
        self.dirty = False
        self.finalized = False
        self.refreshed = False
        self.deleted_lines = []

    def _get_current_segments(self):
        return self._segments

    def _segment_for_line(self, line: int):
        for seg in self._segments:
            if int(seg.get("line", -1)) == int(line):
                return seg
        return None

    def _mark_dirty(self):
        self.dirty = True

    def _finalize_edit(self):
        self.finalized = True

    def _refresh_video_subtitle_context(self):
        self.refreshed = True

    def _on_seg_to_gap(self, line_num: int):
        self.deleted_lines.append(int(line_num))


class TimelineHitTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_llm_review_segment_state_sets_and_clears_blue_highlight_payload(self):
        canvas = TimelineCanvas()
        try:
            canvas.set_llm_review_segment({"active": True, "start": 1.0, "end": 2.5, "text": "검사 중"})
            self.assertIsNotNone(canvas.llm_review_segment)
            self.assertEqual(canvas.llm_review_segment["start"], 1.0)
            self.assertEqual(canvas.llm_review_segment["end"], 2.5)

            canvas.set_llm_review_segment({"active": False})
            self.assertIsNone(canvas.llm_review_segment)
        finally:
            canvas.deleteLater()

    def _canvas(self):
        canvas = TimelineCanvas()
        canvas.pps = 100.0
        canvas.total_duration = 3.0
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "앞", "line": 0},
            {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
        ]
        return canvas

    def test_segment_arrow_hit_uses_exact_visible_polygon_without_margin(self):
        canvas = self._canvas()
        handle_y = SEG_TOP + 32

        hit = canvas._handle_drag_at(188, handle_y)
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], "square_right")

        self.assertIsNone(canvas._handle_drag_at(200, handle_y))

    def test_tablet_profile_expands_segment_handle_hit_target(self):
        canvas = self._canvas()
        canvas.setProperty("responsive_profile_override", "tablet_landscape")
        canvas.resize(1180, canvas.height())
        handle_y = SEG_TOP + 32

        hit = canvas._handle_drag_at(200, handle_y)

        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], "square_right")

    def test_compact_subtitle_segment_edges_remain_resizable_next_to_gap(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 200.0
            canvas.total_duration = 2.0
            canvas.segments = [
                {"start": 1.00, "end": 1.06, "text": "짧은 자막", "line": 0},
            ]
            canvas.gap_segments = [
                {"start": 0.0, "end": 1.0, "text": "무음구간", "line": -1, "is_gap": True, "active": True},
                {"start": 1.06, "end": 2.0, "text": "", "line": -1, "is_gap": True, "active": False},
            ]
            handle_y = SEG_TOP + 32

            left_hit = canvas._handle_drag_at(canvas._x(1.00), handle_y)
            right_hit = canvas._handle_drag_at(canvas._x(1.06), handle_y)

            self.assertIsNotNone(left_hit)
            self.assertEqual(left_hit[1], "square_left")
            self.assertIsNotNone(right_hit)
            self.assertEqual(right_hit[1], "square_right")
        finally:
            canvas.deleteLater()

    def test_active_shared_boundary_click_prefers_current_segment_left_handle(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 1},
            ]
            canvas.set_active(1.0)

            hit = canvas._handle_drag_at(canvas._x(1.0), SEG_TOP + 32)

            self.assertIsNotNone(hit)
            self.assertEqual(hit[0]["line"], 1)
            self.assertEqual(hit[1], "square_left")
        finally:
            canvas.deleteLater()

    def test_waveform_right_arrow_jumps_to_next_segment(self):
        canvas = TimelineCanvas()
        try:
            canvas.focus_mode = "waveform"
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 0.0, "end": 0.8, "text": "앞", "line": 0},
                {"start": 1.2, "end": 2.0, "text": "다음", "line": 1},
            ]
            canvas.set_playhead(0.2)
            emitted = []
            canvas.scrub_sec.connect(emitted.append)

            QTest.keyClick(canvas, Qt.Key.Key_Right)

            self.assertEqual(emitted, [1.2])
        finally:
            canvas.deleteLater()

    def test_segment_right_arrow_also_emits_forward_frame_step(self):
        canvas = TimelineCanvas()
        try:
            canvas.focus_mode = "segment"
            emitted = []
            canvas.step_frame.connect(emitted.append)

            QTest.keyClick(canvas, Qt.Key.Key_Right)

            self.assertEqual(emitted, [1])
        finally:
            canvas.deleteLater()

    def test_canvas_x_and_scrub_roundtrip_snap_to_nearest_frame(self):
        canvas = TimelineCanvas()
        try:
            canvas.set_frame_rate(24.0)
            canvas.pps = 240.0

            snapped_x = canvas._x(1.01)
            snapped_sec = canvas._sec_from_x(snapped_x)

            self.assertEqual(snapped_x, canvas._x(1.0))
            self.assertAlmostEqual(snapped_sec, 1.0, places=6)
        finally:
            canvas.deleteLater()

    def test_subtitle_text_body_bounds_clear_segment_handles(self):
        canvas = self._canvas()
        try:
            seg = canvas.segments[0]

            body_left, body_right = canvas._subtitle_segment_text_body_bounds(seg)

            self.assertGreaterEqual(body_left, canvas._x(seg["start"]) + HANDLE_R + 6)
            self.assertLessEqual(body_right, canvas._x(seg["end"]) - HANDLE_R - 6)
        finally:
            canvas.deleteLater()

    def test_editing_segment_border_renders_green(self):
        canvas = self._canvas()
        try:
            seg = canvas.segments[0]
            canvas.active_seg_start = seg["start"]
            canvas._edit_active = True
            canvas._edit_line = int(seg["line"])
            canvas.resize(360, canvas.height())
            canvas.show()
            self.app.processEvents()

            image = canvas.grab().toImage()
            border_color = image.pixelColor(canvas._x(seg["start"]), SUBTITLE_TOP + 10)

            self.assertGreater(border_color.green(), 160)
            self.assertGreater(border_color.green(), border_color.red())
            self.assertGreater(border_color.green(), border_color.blue())
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_editing_segment_renders_playhead_behind_subtitle_band(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(420, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.playhead_sec = 1.8
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "", "line": 0},
            ]
            canvas.show()
            self.app.processEvents()

            sample_y = SUBTITLE_TOP + 18
            playhead_x = canvas._x(canvas.playhead_sec)
            neighbor_x = playhead_x + 6

            image = canvas.grab().toImage()
            normal_playhead_px = image.pixelColor(playhead_x, sample_y).name()
            normal_neighbor_px = image.pixelColor(neighbor_x, sample_y).name()

            canvas._edit_active = True
            canvas._edit_line = 0
            canvas.update()
            self.app.processEvents()

            image = canvas.grab().toImage()
            editing_playhead_px = image.pixelColor(playhead_x, sample_y).name()
            editing_neighbor_px = image.pixelColor(neighbor_x, sample_y).name()

            self.assertNotEqual(normal_playhead_px, normal_neighbor_px)
            self.assertEqual(editing_playhead_px, editing_neighbor_px)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_arrow_hold_accelerates_from_one_to_sixty_four_x(self):
        canvas = TimelineCanvas()
        try:
            emitted = []
            canvas.step_frame.connect(emitted.append)

            with patch("ui.timeline.timeline_input.time.monotonic", return_value=100.0):
                canvas._begin_arrow_key_hold(1)
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=100.20):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=100.30):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=100.51):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=101.01):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=101.51):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=102.01):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=102.51):
                canvas._emit_arrow_key_hold_step()
            with patch("ui.timeline.timeline_input.time.monotonic", return_value=103.99):
                canvas._emit_arrow_key_hold_step()

            self.assertEqual(emitted, [1, 1, 2, 4, 8, 16, 32, 64])
        finally:
            canvas.deleteLater()

    def test_canvas_inline_editor_space_toggles_play_pause(self):
        holder = QWidget()
        holder._toggle_video_play = Mock()
        canvas = TimelineCanvas(holder)
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "캔버스 자막", "line": 0},
            ]
            canvas.start_inline_edit(0, 1.0)
            inline_editor = canvas._ensure_inline_editor()

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
                " ",
            )
            inline_editor.keyPressEvent(event)

            holder._toggle_video_play.assert_called_once_with()
            self.assertEqual(inline_editor.toPlainText(), "캔버스 자막")
            self.assertTrue(event.isAccepted())
        finally:
            canvas.close()
            canvas.deleteLater()
            holder.deleteLater()

    def test_canvas_inline_editor_typing_pauses_video_playback(self):
        holder = QWidget()
        holder._pause_playback_for_keyboard_edit = Mock()
        canvas = TimelineCanvas(holder)
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "캔버스 자막", "line": 0},
            ]
            canvas.start_inline_edit(0, 1.0)
            inline_editor = canvas._ensure_inline_editor()

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_A,
                Qt.KeyboardModifier.NoModifier,
                "a",
            )
            inline_editor.keyPressEvent(event)

            holder._pause_playback_for_keyboard_edit.assert_called_once_with()
        finally:
            canvas.close()
            canvas.deleteLater()
            holder.deleteLater()

    def test_canvas_inline_editor_one_word_arrow_keys_stay_in_edit_mode(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "단어", "line": 0},
            ]
            canvas.start_inline_edit(0, 1.0)
            inline_editor = canvas._ensure_inline_editor()

            for key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                event = QKeyEvent(
                    QKeyEvent.Type.KeyPress,
                    key,
                    Qt.KeyboardModifier.NoModifier,
                )
                inline_editor.keyPressEvent(event)

                self.assertTrue(bool(getattr(canvas, "_edit_active", False)))
                self.assertEqual(inline_editor.toPlainText(), "단어")
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_canvas_keypress_space_toggles_play_pause_while_inline_edit_is_active(self):
        holder = QWidget()
        holder._toggle_video_play = Mock()
        canvas = TimelineCanvas(holder)
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "캔버스 자막", "line": 0},
            ]
            canvas.start_inline_edit(0, 1.0)

            event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
                " ",
            )
            canvas.keyPressEvent(event)

            holder._toggle_video_play.assert_called_once_with()
            self.assertTrue(canvas._edit_active)
            self.assertTrue(event.isAccepted())
        finally:
            canvas.close()
            canvas.deleteLater()
            holder.deleteLater()

    def test_canvas_keypress_space_toggles_play_pause_after_inline_edit_enter_commit(self):
        holder = QWidget()
        holder._toggle_video_play = Mock()
        canvas = TimelineCanvas(holder)
        try:
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "캔버스 자막", "line": 0},
            ]
            canvas.start_inline_edit(0, 1.0)
            inline_editor = canvas._ensure_inline_editor()

            commit_event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier,
            )
            inline_editor.keyPressEvent(commit_event)
            self.assertFalse(canvas._edit_active)
            self.assertTrue(commit_event.isAccepted())

            play_event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Space,
                Qt.KeyboardModifier.NoModifier,
                " ",
            )
            canvas.keyPressEvent(play_event)

            holder._toggle_video_play.assert_called_once_with()
            self.assertTrue(play_event.isAccepted())
        finally:
            canvas.close()
            canvas.deleteLater()
            holder.deleteLater()

    def test_inline_edit_enter_restores_canvas_focus_before_editing_mode_signal(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.5, "text": "캔버스 자막", "line": 0},
            ]
            focus_at_end = []
            canvas.sig_editing_mode.connect(
                lambda active: focus_at_end.append(QApplication.focusWidget()) if not active else None
            )
            canvas.show()
            canvas.activateWindow()
            canvas.setFocus()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0)
            inline_editor = canvas._ensure_inline_editor()
            inline_editor.setFocus()
            self.app.processEvents()

            commit_event = QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                Qt.KeyboardModifier.NoModifier,
            )
            inline_editor.keyPressEvent(commit_event)
            self.app.processEvents()

            self.assertFalse(canvas._edit_active)
            self.assertTrue(focus_at_end)
            self.assertIs(focus_at_end[-1], canvas)
            self.assertIsNot(QApplication.focusWidget(), inline_editor)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_segment_drag_snap_ignores_stt_preview_lanes(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "메인 자막", "line": 0},
                {
                    "start": 2.12,
                    "end": 3.0,
                    "text": "STT1 후보",
                    "line": 1,
                    "stt_pending": True,
                    "_live_stt_preview": True,
                    "stt_preview_source": "STT1",
                },
            ]

            target = canvas.segments[0]
            canvas._setup_drag(target, "square_right", canvas._x(target["end"]))
            canvas._apply_drag(0.11)

            self.assertAlmostEqual(target["end"], 2.11)
            self.assertNotEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "stt1")
        finally:
            canvas.deleteLater()

    def test_update_segments_snaps_loaded_segment_bounds_to_frame_rate(self):
        canvas = TimelineCanvas()
        try:
            canvas.set_frame_rate(24.0)
            rows = [
                {"start": 1.01, "end": 2.07, "text": "프레임 보정", "line": 0},
            ]

            canvas.update_segments(rows, active_sec=1.01, total_dur=5.0)

            self.assertAlmostEqual(canvas.segments[0]["start"], canvas._snap_to_frame(1.01))
            self.assertAlmostEqual(canvas.segments[0]["end"], canvas._snap_to_frame(2.07))
            self.assertAlmostEqual(canvas.active_seg_start, canvas._snap_to_frame(1.01))
        finally:
            canvas.deleteLater()

    def test_left_resize_can_drag_across_previous_subtitle(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "메인", "line": 1},
            ]

            seg = canvas.segments[1]
            canvas._setup_drag(seg, "square_left", canvas._x(seg["start"]))
            canvas._apply_drag(-1.5)

            self.assertAlmostEqual(seg["start"], 0.5)
        finally:
            canvas.deleteLater()

    def test_left_resize_live_updates_previous_shared_boundary(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 1},
            ]

            seg = canvas.segments[1]
            canvas._setup_drag(seg, "square_left", canvas._x(seg["start"]))
            canvas._apply_drag(-0.4)

            self.assertAlmostEqual(canvas.segments[0]["end"], 0.6)
            self.assertAlmostEqual(canvas.segments[1]["start"], 0.6)
        finally:
            canvas.deleteLater()

    def test_right_resize_live_updates_next_shared_boundary(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
            ]

            seg = canvas.segments[0]
            canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
            canvas._apply_drag(0.4)

            self.assertAlmostEqual(canvas.segments[0]["end"], 2.4)
            self.assertAlmostEqual(canvas.segments[1]["start"], 2.4)
        finally:
            canvas.deleteLater()

    def test_left_resize_to_previous_start_sets_merge_preview_pair(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 1},
            ]

            seg = canvas.segments[1]
            canvas._setup_drag(seg, "square_left", canvas._x(seg["start"]))
            canvas._apply_drag(-1.0)

            self.assertEqual(canvas._drag_merge_pair, (0, 1))
        finally:
            canvas.deleteLater()

    def test_right_resize_to_next_end_sets_merge_preview_pair(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "현재", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "뒤", "line": 1},
            ]

            seg = canvas.segments[0]
            canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
            canvas._apply_drag(1.0)

            self.assertEqual(canvas._drag_merge_pair, (0, 1))
        finally:
            canvas.deleteLater()

    def test_diamond_hit_rect_allows_lower_click_slop(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 1},
            ]

            dia = canvas._diamond_index_at(canvas._x(1.0), DIAMOND_Y + 12, margin=5)

            self.assertEqual(dia, 0)
        finally:
            canvas.deleteLater()

    def test_inline_editor_speaker_split_request_emits_current_line_and_cursor(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(640, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 3.0
            canvas.segments = [
                {"start": 0.0, "end": 2.0, "text": "화자 전환 테스트", "line": 0},
            ]
            speaker_splits = []
            canvas.sig_speaker_split_request.connect(lambda line, cursor: speaker_splits.append((line, cursor)))
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 0.0)
            editor = canvas._inline_editor
            cursor = editor.textCursor()
            cursor.setPosition(3)
            editor.setTextCursor(cursor)
            canvas._commit_inline_edit_with_speaker_split()

            self.assertEqual(speaker_splits, [(0, 3)])
            self.assertFalse(canvas._edit_active)
        finally:
            canvas.deleteLater()

    def test_inline_text_commit_routes_through_nle_caption_text_edit(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(640, canvas.height())
            canvas.frame_rate = 30.0
            canvas.pps = 120.0
            canvas.total_duration = 3.0
            canvas.segments = [
                {"start": 0.0, "end": 2.0, "text": "원본", "line": 0},
            ]
            emitted = []
            canvas.sig_inline_text_changed.connect(
                lambda line, text: emitted.append((line, text, getattr(canvas, "_inline_commit_in_progress", False)))
            )
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 0.0)
            editor = canvas._inline_editor
            editor.setPlainText("수정")
            canvas._commit_inline_edit()

            operation = getattr(canvas, "_last_nle_timeline_operation", {})
            projection = getattr(canvas, "_last_nle_timeline_projection", {})
            self.assertEqual(operation.get("kind"), "caption_text_edit")
            self.assertEqual(operation.get("metadata", {}).get("commit_boundary"), "release")
            self.assertEqual(operation.get("metadata", {}).get("commit_source"), "timeline_inline_text")
            self.assertEqual(operation.get("metadata", {}).get("old_text"), "원본")
            self.assertEqual(operation.get("metadata", {}).get("new_text"), "수정")
            self.assertEqual(projection.get("overlap_count"), 0)
            self.assertEqual(projection.get("max_active_segments"), 1)
            self.assertEqual(canvas.segments[0]["text"], "수정")
            self.assertEqual(emitted[-1], (0, "수정", True))
            self.assertFalse(canvas._edit_active)
        finally:
            canvas.deleteLater()

    def test_inline_text_commit_falls_back_when_nle_rejects(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(640, canvas.height())
            canvas.frame_rate = 30.0
            canvas.pps = 120.0
            canvas.total_duration = 3.0
            canvas.segments = [
                {"start": 0.0, "end": 2.0, "text": "원본", "line": 0},
            ]
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 0.0)
            editor = canvas._inline_editor
            editor.setPlainText("수정")
            with patch(
                "ui.editor.ux.timeline_canvas_editing.apply_caption_text_edit_dual_write_pilot",
                side_effect=ValueError("forced-nle-text-reject"),
            ):
                canvas._commit_inline_edit()

            self.assertFalse(hasattr(canvas, "_last_nle_timeline_operation"))
            self.assertEqual(canvas.segments[0]["text"], "수정")
            self.assertFalse(canvas._edit_active)
        finally:
            canvas.deleteLater()

    def test_inline_edit_fast_refresh_schedules_followup_repaints(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(640, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 3.0
            canvas.segments = [
                {"start": 0.0, "end": 2.0, "text": "편집 잔상", "line": 0},
            ]
            canvas._edit_line = 0

            with patch.object(canvas, "update") as update, \
                 patch.object(canvas, "repaint") as repaint, \
                 patch("ui.editor.ux.timeline_canvas_editing.QTimer.singleShot") as single_shot:
                canvas._request_inline_edit_fast_refresh(0, immediate=True)

            update.assert_called()
            repaint.assert_called_once()
            self.assertEqual([call.args[0] for call in single_shot.call_args_list], [0, 16, 48])
        finally:
            canvas.deleteLater()

    def test_auto_gap_generation_can_be_disabled_for_direct_srt_resize(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.auto_generate_gap_segments = False
            rows = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
            ]
            canvas.update_segments(rows, active_sec=None, total_dur=5.0)
            self.assertEqual(canvas.gap_segments, [])

            seg = canvas.segments[0]
            canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
            canvas._apply_drag(-0.5)
            canvas.mouseReleaseEvent(object())

            self.assertAlmostEqual(seg["end"], 0.5)
            self.assertEqual(canvas.gap_segments, [])
        finally:
            canvas.deleteLater()

    def test_auto_gap_disabled_still_preserves_explicit_gap_rows(self):
        canvas = TimelineCanvas()
        try:
            canvas.auto_generate_gap_segments = False
            rows = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "무음구간", "line": -1, "is_gap": True},
                {"start": 3.0, "end": 4.0, "text": "뒤", "line": 1},
            ]

            canvas.update_segments(rows, active_sec=None, total_dur=5.0)

            self.assertEqual([(g["start"], g["end"]) for g in canvas.gap_segments], [(1.0, 2.0)])
            self.assertTrue(canvas.gap_segments[0].get("_explicit_gap"))
        finally:
            canvas.deleteLater()

    def test_disabled_gap_insert_controls_do_not_surface_plus_slots(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.show_gap_insert_controls = False
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
            ]
            canvas.gap_segments = [
                {"start": 1.0, "end": 2.0, "text": "무음구간", "line": -1, "is_gap": True, "_explicit_gap": True},
            ]

            self.assertIsNone(canvas._gap_at(canvas._x(1.5), SEG_TOP + 12))
            self.assertNotIn("gap", {item.get("kind") for item in canvas._drag_snap_candidates()})
        finally:
            canvas.deleteLater()

    def test_segment_handle_drag_does_not_snap_to_playhead(self):
        canvas = self._canvas()
        canvas.frame_rate = 100.0
        canvas.total_duration = 4.0
        canvas.playhead_sec = 3.37
        seg = canvas.segments[1]

        canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
        canvas._apply_drag(0.36)

        self.assertAlmostEqual(seg["end"], 3.36)
        self.assertNotAlmostEqual(seg["end"], canvas.playhead_sec)

    def test_segment_handle_drag_ignores_stt_preview_neighbor_limit(self):
        canvas = self._canvas()
        canvas.frame_rate = 100.0
        canvas.total_duration = 4.0
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "자막", "line": 0},
            {"start": 2.05, "end": 2.4, "text": "프리뷰", "line": 99, "stt_pending": True},
            {"start": 3.0, "end": 4.0, "text": "다음", "line": 1},
        ]
        seg = canvas.segments[0]

        canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
        canvas._apply_drag(0.5)

        self.assertAlmostEqual(seg["end"], 2.5)

    def test_active_segment_keeps_center_drag_hit_target_even_when_short(self):
        canvas = TimelineCanvas()
        try:
            canvas.pps = 100.0
            canvas.total_duration = 2.0
            canvas.segments = [
                {"start": 1.0, "end": 1.35, "text": "짧은 자막", "line": 0},
            ]
            canvas.set_active(1.0)

            self.assertTrue(canvas._center_drag_hit(canvas.segments[0], canvas._x(1.17), SEG_TOP + 32))
        finally:
            canvas.deleteLater()

    def test_center_drag_can_move_across_adjacent_subtitle_for_overwrite_flow(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "메인", "line": 1},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 2},
            ]

            seg = canvas.segments[1]
            canvas.set_active(seg["start"])
            canvas._setup_drag(seg, "center", canvas._x(1.5))
            canvas._apply_drag(0.5)

            self.assertAlmostEqual(seg["start"], 1.5)
            self.assertAlmostEqual(seg["end"], 2.5)
        finally:
            canvas.deleteLater()

    def test_center_drag_reorders_across_adjacent_subtitle_preview(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "메인", "line": 1},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 2},
            ]

            seg = canvas.segments[1]
            with patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(seg, "center", canvas._x(1.5))
                canvas._apply_drag(1.0)

            self.assertAlmostEqual(canvas.segments[2]["start"], 1.0)
            self.assertAlmostEqual(canvas.segments[2]["end"], 2.0)
            self.assertAlmostEqual(seg["start"], 2.0)
            self.assertAlmostEqual(seg["end"], 3.0)
            self.assertEqual(getattr(canvas, "_drag_center_reorder_direction", None), "right")
        finally:
            canvas.deleteLater()

    def test_center_drag_reorder_release_emits_reorder_edge(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "메인", "line": 1},
                {"start": 2.0, "end": 3.0, "text": "뒤", "line": 2},
            ]
            emitted = []
            canvas.seg_time_changed.connect(lambda line, start, end, edge: emitted.append((line, start, end, edge)))

            seg = canvas.segments[1]
            with patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(seg, "center", canvas._x(1.5))
                canvas._apply_drag(1.0)
            canvas.mouseReleaseEvent(SimpleNamespace())

            self.assertEqual(len(emitted), 1)
            self.assertEqual(emitted[0][0], 1)
            self.assertAlmostEqual(emitted[0][1], 2.0)
            self.assertAlmostEqual(emitted[0][2], 3.0)
            self.assertEqual(emitted[0][3], "center_reorder_right")
        finally:
            canvas.deleteLater()

    def test_drag_start_clears_inline_edit_preedit(self):
        canvas = self._canvas()
        canvas._edit_active = False
        canvas._ime_preedit = "깜박"
        canvas._cursor_vis = True

        canvas._setup_drag(canvas.segments[0], "square_right", canvas._x(2.0))

        self.assertEqual(canvas._ime_preedit, "")
        self.assertFalse(canvas._cursor_vis)

    def test_diamond_hit_has_small_margin_only(self):
        canvas = self._canvas()

        self.assertEqual(canvas._diamond_index_at(209, DIAMOND_Y, margin=5), 0)
        self.assertIsNone(canvas._diamond_index_at(211, DIAMOND_Y, margin=5))

    def test_attached_subtitle_visual_rects_meet_at_diamond_frame_boundary(self):
        canvas = self._canvas()
        try:
            left, right = canvas.segments
            left_rect = canvas._subtitle_segment_visual_rect(
                left,
                canvas._x(left["start"]),
                canvas._x(left["end"]),
                SUBTITLE_TOP,
                SUBTITLE_BOT,
            )
            right_rect = canvas._subtitle_segment_visual_rect(
                right,
                canvas._x(right["start"]),
                canvas._x(right["end"]),
                SUBTITLE_TOP,
                SUBTITLE_BOT,
            )

            self.assertEqual(len(canvas._diamond_pairs()), 1)
            self.assertEqual(left_rect.x() + left_rect.width(), right_rect.x())
        finally:
            canvas.deleteLater()

    def test_one_frame_gap_does_not_show_attached_diamond(self):
        canvas = TimelineCanvas()
        try:
            canvas.set_frame_rate(30.0)
            canvas.pps = 300.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "앞", "line": 0},
                {"start": 2.0 + (1.0 / 30.0), "end": 3.0, "text": "뒤", "line": 1},
            ]
            left, right = canvas.segments
            left_rect = canvas._subtitle_segment_visual_rect(
                left,
                canvas._x(left["start"]),
                canvas._x(left["end"]),
                SUBTITLE_TOP,
                SUBTITLE_BOT,
            )
            right_rect = canvas._subtitle_segment_visual_rect(
                right,
                canvas._x(right["start"]),
                canvas._x(right["end"]),
                SUBTITLE_TOP,
                SUBTITLE_BOT,
            )

            self.assertEqual(canvas._diamond_pairs(), [])
            self.assertGreater(right_rect.x(), left_rect.x() + left_rect.width())
        finally:
            canvas.deleteLater()

    def test_tablet_profile_expands_diamond_hit_target(self):
        canvas = self._canvas()
        canvas.setProperty("responsive_profile_override", "tablet_landscape")
        canvas.resize(1180, canvas.height())

        self.assertEqual(canvas._diamond_index_at(218, DIAMOND_Y, margin=5), 0)

    def test_tablet_profile_expands_scan_boundary_and_playhead_targets(self):
        canvas = self._canvas()
        canvas.setProperty("responsive_profile_override", "tablet_landscape")
        canvas.resize(1180, canvas.height())
        canvas.scan_boundary_times = [{"timeline_sec": 2.0, "status": "pending"}]
        canvas.playhead_sec = 1.0
        boundary_y = RULER_H + WAVE_H + 10

        self.assertIsNotNone(canvas._scan_boundary_hit_at(canvas._x(2.0) + 18, boundary_y, margin=7))
        self.assertTrue(canvas._playhead_handle_hit_rect().contains(canvas._x(1.0) + 16, 8))

    def test_playhead_handle_drag_preserves_keyboard_focus_mode(self):
        canvas = self._canvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.total_duration = 4.0
            canvas.set_playhead(1.0)
            canvas.focus_mode = "segment"
            canvas.show()
            self.app.processEvents()

            handle_pos = QPoint(canvas._x(1.0), 8)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, handle_pos)
            self.app.processEvents()
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, handle_pos)

            self.assertEqual(canvas.focus_mode, "segment")
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_playhead_click_preserves_keyboard_focus_mode(self):
        canvas = self._canvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.total_duration = 5.0
            canvas.show()
            self.app.processEvents()

            scrubbed = []
            canvas.scrub_sec.connect(scrubbed.append)

            canvas.focus_mode = "segment"
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(3.2), RULER_H + 8),
            )
            self.app.processEvents()
            self.assertEqual(canvas.focus_mode, "segment")
            self.assertAlmostEqual(scrubbed[-1], 3.2)

            canvas.focus_mode = "waveform"
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), SEG_TOP + 32),
            )
            self.app.processEvents()
            self.assertEqual(canvas.focus_mode, "waveform")
            self.assertAlmostEqual(scrubbed[-1], 1.5)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_left_right_dispatch_restores_keyboard_selected_focus_mode(self):
        target = SimpleNamespace(focus_mode="segment", update=Mock())

        def mutate_mode(_direction):
            target.focus_mode = "waveform"
            return True

        target._dispatch_frame_step = mutate_mode

        self.assertTrue(dispatch_playhead_arrow_step(target, 1))
        self.assertEqual(target.focus_mode, "segment")
        target.update.assert_called_once()

    def test_tablet_profile_expands_timeline_zoom_buttons(self):
        timeline = TimelineWidget()
        try:
            timeline.setProperty("responsive_profile_override", "tablet_landscape")
            timeline.resize(1180, timeline.height())
            timeline._apply_responsive_touch_targets()

            for button in timeline._zoom_buttons:
                self.assertGreaterEqual(button.width(), 48)
                self.assertGreaterEqual(button.height(), 44)
        finally:
            timeline.deleteLater()

    def test_diamond_hit_ignores_interleaved_stt_preview_segments(self):
        canvas = self._canvas()
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "앞", "line": 0},
            {"start": 1.2, "end": 1.8, "text": "프리뷰", "line": 20, "stt_pending": True},
            {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
        ]

        self.assertEqual(canvas._diamond_index_at(200, DIAMOND_Y, margin=5), 0)
        pair = canvas._diamond_pair_for_index(0)
        self.assertIsNotNone(pair)
        self.assertEqual((pair[0], pair[1]), (0, 2))

    def test_speaker_menu_hit_target_is_center_label_only(self):
        canvas = self._canvas()
        canvas.segments[0]["speaker"] = "00"
        y = (SPEAKER_TOP + SPEAKER_BOT) // 2

        self.assertIs(canvas._speaker_lane_seg_at(canvas._x(1.5), y), canvas.segments[0])
        self.assertIsNone(canvas._speaker_lane_seg_at(canvas._x(1.05), y))

    def test_speaker_hit_rect_reuses_settings_and_rect_cache(self):
        canvas = self._canvas()
        canvas.segments[0]["speaker"] = "00"
        settings = {
            "spk1_id": "00",
            "spk1_name": "주인공",
            "spk1_color": "#579DFF",
            "max_speakers": 1,
        }

        with patch("ui.timeline.timeline_input.current_speaker_settings", return_value=settings) as current_settings:
            first = canvas._speaker_lane_hit_rect_for_seg(canvas.segments[0])
            second = canvas._speaker_lane_hit_rect_for_seg(canvas.segments[0])

        self.assertEqual(first, second)
        self.assertEqual(current_settings.call_count, 1)
        self.assertEqual(len(getattr(canvas, "_speaker_hit_rect_cache", {}) or {}), 1)

    def test_gap_hit_target_detects_silent_segment(self):
        canvas = self._canvas()
        canvas.update_segments(canvas.segments, active_sec=1.0, total_dur=4.0)

        gap = canvas._gap_at(canvas._x(3.0), SEG_TOP + 12)

        self.assertIsNotNone(gap)
        self.assertAlmostEqual(gap["start"], 3.0)
        self.assertAlmostEqual(gap["end"], 4.0)

    def test_voice_and_analysis_lanes_do_not_scrub_or_select(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.active_seg_start = 1.0
        scrubbed = []
        clicked = []
        dragged = []
        canvas.scrub_sec.connect(lambda sec: scrubbed.append(sec))
        canvas.seg_clicked.connect(lambda line, start: clicked.append((line, start)))
        canvas.drag_started.connect(lambda: dragged.append(True))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), VOICE_ACTIVITY_TOP + 4),
        )

        self.assertEqual(scrubbed, [1.5])
        self.assertEqual(clicked, [])
        self.assertEqual(dragged, [])
        self.assertFalse(canvas._is_scrubbing)
        self.assertIsNone(canvas._drag_seg)

    def test_subtitle_center_click_no_longer_deletes_segment(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        deleted = []
        clicked = []
        canvas.seg_to_gap.connect(lambda line: deleted.append(line))
        canvas.seg_clicked.connect(lambda line, start: clicked.append((line, start)))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), SEG_TOP + 32),
        )

        self.assertEqual(deleted, [])
        self.assertEqual(clicked, [(0, 1.5)])

    def test_processing_input_lock_blocks_canvas_edit_clicks(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas._editor_processing_input_locked = True
        clicked = []
        scrubbed = []
        canvas.seg_clicked.connect(lambda line, start: clicked.append((line, start)))
        canvas.scrub_sec.connect(lambda sec: scrubbed.append(sec))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), SEG_TOP + 32),
        )

        self.assertEqual(clicked, [])
        self.assertEqual(scrubbed, [])

    def test_global_canvas_right_click_requests_roughcut_llm_without_seeking(self):
        timeline = TimelineWidget()
        try:
            timeline.resize(640, timeline.sizeHint().height())
            timeline.global_canvas.resize(640, timeline.global_canvas.height())
            emitted = []
            seeked = []
            timeline.roughcut_llm_run_requested.connect(lambda: emitted.append(True))
            timeline.global_canvas.seek_frac.connect(lambda frac: seeked.append(frac))

            with patch("ui.timeline.timeline_global.show_context_menu", return_value="roughcut_llm") as menu:
                QTest.mouseClick(
                    timeline.global_canvas,
                    Qt.MouseButton.RightButton,
                    Qt.KeyboardModifier.NoModifier,
                    QPoint(80, 12),
                )

            self.assertEqual(emitted, [True])
            self.assertEqual(seeked, [])
            self.assertEqual(menu.call_args[0][2][0]["label"], "러프컷 LLM 실행")
        finally:
            timeline.deleteLater()

    def test_single_gesture_center_drag_starts_without_prior_selection(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 0.0, "end": 1.0, "text": "앞 자막", "line": 0},
                {"start": 1.0, "end": 2.0, "text": "메인 자막", "line": 1},
                {"start": 2.0, "end": 3.0, "text": "뒤 자막", "line": 2},
            ]
            dragged = []
            clicked = []
            canvas.drag_started.connect(lambda: dragged.append(True))
            canvas.seg_clicked.connect(lambda line, start: clicked.append((line, start)))
            canvas.show()
            self.app.processEvents()

            start = QPoint(canvas._x(1.5), SEG_TOP + 32)
            end = QPoint(canvas._x(1.8), SEG_TOP + 32)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(canvas, end, delay=1)
            self.app.processEvents()
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)

            self.assertEqual(clicked, [(1, 1.5)])
            self.assertTrue(dragged)
            self.assertGreater(canvas.segments[1]["start"], 1.0)
            self.assertAlmostEqual(canvas.segments[1]["end"] - canvas.segments[1]["start"], 1.0, places=3)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_right_click_above_subtitles_does_not_create_smart_split(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.playhead_sec = 1.5
        smart_splits = []
        canvas.sig_smart_split.connect(lambda *args: smart_splits.append(args))
        try:
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), SEG_TOP - 6),
            )

            self.assertEqual(smart_splits, [])
        finally:
            canvas.close()

    def test_gap_delete_menu_emits_gap_to_segs(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        emitted = []
        canvas.gap_to_segs.connect(lambda start, end: emitted.append((start, end)))
        try:
            with patch("ui.timeline.timeline_input.show_context_menu", return_value="delete"):
                canvas._show_gap_generate_menu({"start": 1.0, "end": 5.0}, QPoint(10, 10), canvas._x(2.0))

            self.assertEqual(emitted, [(1.0, 5.0)])
        finally:
            canvas.close()

    def test_gap_delete_attaches_adjacent_subtitles_and_removes_gap_block(self):
        class DummyCanvas:
            def __init__(self):
                self.segments = [
                    {"start": 0.0, "end": 2.0, "text": "앞", "line": 0},
                    {"start": 5.0, "end": 7.0, "text": "뒤", "line": 2},
                ]
                self.voice_activity_segments = [{"start": 2.0, "end": 5.0, "label": "무음구간"}]

            def _invalidate_marker_caches(self):
                self.invalidated = True

            def update(self):
                self.updated = True

        class DummyTimeline:
            def __init__(self):
                self.canvas = DummyCanvas()

        editor = _GapGenerateEditor()
        editor.finalized = False
        editor.redraw_requested = False
        editor.invalidated = False
        editor._undo_mgr = _Undo()
        editor.timeline = DummyTimeline()
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = _TimelineTextEdit()
        editor._live_stt_preview_segments = [{"start": 2.4, "end": 4.0, "text": "무음 후보"}]
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(2.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))

            editor._on_gap_to_segs(2.0, 5.0)

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "뒤"])
            self.assertFalse(doc.findBlockByNumber(0).userData().is_gap)
            self.assertFalse(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(0).userData().start_sec, 0.0)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 4.1)
            self.assertEqual(editor._live_stt_preview_segments, [{"start": 2.4, "end": 4.0, "text": "무음 후보"}])
            self.assertEqual(editor.timeline.canvas.voice_activity_segments, [])
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_plus_inserts_auto_gap_subtitle_in_chronological_position(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = _TimelineTextEdit()
        try:
            unrelated_text = "일단 홈페이지 가입하시면 뭐 뭐가 됐든 커피도 주고"
            editor.text_edit.setPlainText(f"앞 자막\n뭐야 이 안에\n{unrelated_text}")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0, end_sec=2.0))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 5.0, end_sec=6.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 100.0, end_sec=101.0))

            editor._on_gap_activated(2.0, 5.0)

            self.assertEqual(
                editor.text_edit.toPlainText().splitlines(),
                ["앞 자막", "새 자막", "뭐야 이 안에", unrelated_text],
            )
            inserted = doc.findBlockByNumber(1)
            inserted_ud = inserted.userData()
            self.assertIsInstance(inserted_ud, SubtitleBlockData)
            self.assertFalse(inserted_ud.is_gap)
            self.assertAlmostEqual(inserted_ud.start_sec, 2.0)
            self.assertAlmostEqual(inserted_ud.end_sec, 5.0)
            current = editor._get_current_segments(force_rebuild=True)
            added = next(seg for seg in current if abs(seg["start"] - 2.0) < 0.05)
            self.assertEqual(added["text"], "새 자막")
            self.assertNotIn(unrelated_text, added["text"])
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_plus_replaces_explicit_gap_without_merging_next_subtitle(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = _TimelineTextEdit()
        try:
            next_text = "일단 홈페이지 가입하시면 뭐 뭐가 됐든 커피도 주고"
            editor.text_edit.setPlainText(f"앞 자막\n\n{next_text}")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0, end_sec=2.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(2.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0, end_sec=6.0))

            editor._on_gap_activated(2.0, 5.0)

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞 자막", "새 자막", next_text])
            inserted = doc.findBlockByNumber(1)
            inserted_ud = inserted.userData()
            self.assertIsInstance(inserted_ud, SubtitleBlockData)
            self.assertFalse(inserted_ud.is_gap)
            self.assertAlmostEqual(inserted_ud.start_sec, 2.0)
            self.assertAlmostEqual(inserted_ud.end_sec, 5.0)
            current = editor._get_current_segments(force_rebuild=True)
            added = next(seg for seg in current if abs(seg["start"] - 2.0) < 0.05)
            self.assertEqual(added["text"], "새 자막")
            self.assertNotIn(next_text, added["text"])
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_generate_to_playhead_splits_gap_and_adds_new_subtitle(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "to")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "새자막", "", "뒤"])
            self.assertFalse(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 1.0)
            self.assertTrue(doc.findBlockByNumber(2).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(2).userData().start_sec, 3.0)
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_generate_undo_routes_to_snapshot_before_textedit_undo(self):
        editor = _GapGenerateUndoRouteEditor()
        editor.finalized = False
        editor._undo_mgr = UndoManager(editor)
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor._timeline_timer = SimpleNamespace(start=Mock())
        editor.text_edit = _TimelineTextEdit()
        editor.text_edit.setUndoRedoEnabled(True)
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))
            editor.text_edit.show()
            editor.text_edit.setFocus()
            self.app.processEvents()

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "to")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "새자막", "", "뒤"])
            self.assertEqual(getattr(editor, "_snapshot_undo_revision", None), editor._editor_doc_revision())

            editor._route_undo()

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "뒤"])
            self.assertIsInstance(doc.findBlockByNumber(1).userData(), SubtitleBlockData)
            self.assertTrue(doc.findBlockByNumber(1).userData().is_gap)

            editor._route_redo()

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "새자막", "", "뒤"])
            self.assertFalse(doc.findBlockByNumber(1).userData().is_gap)
        finally:
            editor.text_edit.close()

    def test_gap_generate_from_playhead_keeps_left_gap(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "from")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "뒤"])
            self.assertTrue(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 1.0)
            self.assertFalse(doc.findBlockByNumber(2).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(2).userData().start_sec, 3.0)
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_generate_to_at_silence_start_still_creates_minimum_subtitle(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))

            editor._on_gap_generate_requested(1.0, 5.0, 1.0, "to")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "새자막", "", "뒤"])
            self.assertFalse(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 1.0)
            self.assertTrue(doc.findBlockByNumber(2).userData().is_gap)
            self.assertGreater(doc.findBlockByNumber(2).userData().start_sec, 1.0)
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_generate_preserves_live_stt_preview_inside_selected_gap_range(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))
            editor._live_stt_preview_segments = [
                {"start": 0.2, "end": 0.8, "text": "앞 후보", "stt_pending": True},
                {"start": 1.0, "end": 5.0, "text": "gap 후보", "stt_pending": True},
                {"start": 5.2, "end": 5.8, "text": "뒤 후보", "stt_pending": True},
            ]
            before_preview = [dict(seg) for seg in editor._live_stt_preview_segments]

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "from")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "뒤"])
            self.assertAlmostEqual(doc.findBlockByNumber(0).userData().start_sec, 0.0)
            self.assertAlmostEqual(doc.findBlockByNumber(3).userData().start_sec, 5.0)
            self.assertEqual(editor._live_stt_preview_segments, before_preview)
        finally:
            editor.text_edit.close()

    def test_gap_generate_from_playhead_is_clamped_to_silence_marker(self):
        class DummyCanvas:
            def generation_silence_markers_cached(self):
                return [
                    {"start": 10.0, "end": 15.0, "kind": "generation_silence", "label": "무음구간"},
                ]

        class DummyTimeline:
            canvas = DummyCanvas()

            def set_active(self, _sec):
                pass

            def set_playhead(self, _sec):
                pass

            def center_to_sec(self, _sec, smooth=False):
                pass

        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = DummyTimeline()
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        editor._live_stt_preview_segments = [
            {"start": 12.2, "end": 14.5, "text": "무음 안 후보", "stt_pending": True},
            {"start": 16.0, "end": 20.0, "text": "무음 밖 후보", "stt_pending": True},
        ]
        before_preview = [dict(seg) for seg in editor._live_stt_preview_segments]
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(10.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 22.0))

            editor._on_gap_generate_requested(10.0, 22.0, 12.0, "from")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "", "뒤"])
            self.assertTrue(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 10.0)
            self.assertFalse(doc.findBlockByNumber(2).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(2).userData().start_sec, 12.0)
            self.assertTrue(doc.findBlockByNumber(3).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(3).userData().start_sec, 15.0)
            self.assertAlmostEqual(doc.findBlockByNumber(4).userData().start_sec, 22.0)
            self.assertEqual(editor._live_stt_preview_segments, before_preview)
        finally:
            editor.text_edit.close()

    def test_gap_generate_from_at_silence_end_still_creates_minimum_subtitle(self):
        editor = _GapGenerateEditor()
        editor.finalized = False
        editor._undo_mgr = _Undo()
        editor.timeline = None
        editor.video_player = None
        editor.video_fps = 30.0
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("앞\n\n뒤")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 0.0))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(1.0))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 5.0))

            editor._on_gap_generate_requested(1.0, 5.0, 5.0, "from")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "뒤"])
            self.assertTrue(doc.findBlockByNumber(1).userData().is_gap)
            self.assertAlmostEqual(doc.findBlockByNumber(1).userData().start_sec, 1.0)
            self.assertFalse(doc.findBlockByNumber(2).userData().is_gap)
            self.assertLess(doc.findBlockByNumber(2).userData().start_sec, 5.0)
            self.assertTrue(editor.finalized)
        finally:
            editor.text_edit.close()

    def test_gap_generate_menu_scope_uses_silence_marker_inside_wider_gap(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        canvas.playhead_sec = 12.0
        canvas.generation_silence_markers_cached = lambda: [
            {"start": 10.0, "end": 15.0, "kind": "generation_silence", "label": "무음구간"},
        ]
        try:
            scope = canvas._gap_generation_scope_for_pivot({"start": 10.0, "end": 22.0}, 12.0)
            self.assertEqual(scope, (10.0, 15.0))
        finally:
            canvas.close()

    def test_gap_generate_menu_scope_ignores_lower_audio_silence_lane(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        canvas.playhead_sec = 12.0
        canvas.generation_silence_markers_cached = lambda: [
            {"start": 10.0, "end": 15.0, "kind": "generation_silence", "label": "무음구간"},
        ]
        canvas.analysis_markers_cached = lambda: [
            {"start": 10.0, "end": 22.0, "kind": "silence", "label": "무음"},
        ]
        try:
            scope = canvas._gap_generation_scope_for_pivot({"start": 10.0, "end": 22.0}, 12.0)
            self.assertEqual(scope, (10.0, 15.0))
        finally:
            canvas.close()

    def test_roughcut_major_right_click_requests_provisional_cut_boundary(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        canvas.resize(260, canvas.height())
        canvas.roughcut_major_markers_cached = lambda: [
            {"start": 5.0, "end": 15.0, "kind": "roughcut_major", "label": "A 주제없음"}
        ]
        emitted = []
        canvas.provisional_cut_boundary_requested.connect(lambda sec: emitted.append(sec))
        try:
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(12.0), RULER_H + WAVE_H + 8),
            )

            self.assertEqual(emitted, [12.0])
        finally:
            canvas.close()

    def test_scan_boundary_hover_sets_cyan_highlight_index(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        canvas.scan_boundary_times = [
            {"timeline_sec": 12.0, "status": "provisional"},
        ]
        canvas.resize(260, canvas.height())
        canvas.show()
        self.app.processEvents()
        try:
            hit = canvas._scan_boundary_hit_at(canvas._x(12.0), RULER_H + WAVE_H + 8, margin=7)
            self.assertIsNotNone(hit)
            canvas._set_hover_scan_boundary(hit)
            self.assertEqual(canvas._hover_scan_boundary_idx, 0)
        finally:
            canvas.close()

    def test_scan_boundary_right_click_uses_delete_menu_before_create(self):
        canvas = TimelineCanvas()
        canvas.set_frame_rate(30.0)
        canvas.pps = 10.0
        canvas.resize(260, canvas.height())
        canvas.scan_boundary_times = [
            {"timeline_sec": 12.0, "status": "provisional"},
        ]
        canvas.roughcut_major_markers_cached = lambda: [
            {"start": 5.0, "end": 15.0, "kind": "roughcut_major", "label": "A 주제없음"}
        ]
        created = []
        menu_hits = []
        canvas.provisional_cut_boundary_requested.connect(lambda sec: created.append(sec))
        canvas._show_scan_boundary_menu = lambda hit, gpos: menu_hits.append(hit)
        try:
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(12.0), RULER_H + WAVE_H + 8),
            )

            self.assertEqual(created, [])
            self.assertEqual(len(menu_hits), 1)
            self.assertEqual(menu_hits[0]["index"], 0)
            self.assertAlmostEqual(menu_hits[0]["sec"], 12.0)
        finally:
            canvas.close()

    def test_scan_boundary_create_records_nle_marker_edit_operation(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = None
                self.canvas = type(
                    "Canvas",
                    (),
                    {
                        "_hover_scan_boundary_idx": None,
                        "segments": [{"id": "caption_1", "start": 0.0, "end": 3.0, "text": "one"}],
                        "update": lambda _self: None,
                    },
                )()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self.video_player = SimpleNamespace(total_time=8.0, info_label=SimpleNamespace(setText=lambda _text: None))
                self.dirty = False
                self._auto_cut_boundary_scan_lines = []
                self._project_boundary_times = []
                self._current_project_path = ""
                self.media_path = ""

            def _current_frame_fps(self):
                return 30.0

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _mark_dirty(self):
                self.dirty = True

        editor = DummyEditor()

        editor._on_provisional_cut_boundary_requested(5.0)

        operation = getattr(editor, "_last_nle_cut_boundary_operation", {})
        self.assertEqual(operation.get("kind"), "marker_edit")
        self.assertEqual(operation.get("metadata", {}).get("action"), "create")
        self.assertEqual(operation.get("metadata", {}).get("commit_source"), "provisional_cut_boundary_create")
        self.assertEqual(operation.get("metadata", {}).get("after_marker_count"), 1)
        self.assertEqual([row["timeline_sec"] for row in editor._auto_cut_boundary_scan_lines], [5.0])
        self.assertEqual([row["timeline_sec"] for row in editor.timeline.scan_boundary_times], [5.0])
        self.assertTrue(editor.dirty)

    def test_scan_boundary_delete_removes_requested_boundary_from_editor_state(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = None
                self.canvas = type(
                    "Canvas",
                    (),
                    {
                        "_hover_scan_boundary_idx": 0,
                        "segments": [{"id": "caption_1", "start": 0.0, "end": 3.0, "text": "one"}],
                        "update": lambda _self: None,
                    },
                )()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self.video_player = SimpleNamespace(total_time=12.0, info_label=SimpleNamespace(setText=lambda _text: None))
                self.dirty = False
                self._auto_cut_boundary_scan_lines = [
                    {"timeline_sec": 5.0, "status": "provisional"},
                    {"timeline_sec": 10.0, "status": "provisional"},
                ]
                self._project_boundary_times = []
                self._current_project_path = ""
                self.media_path = ""

            def _current_frame_fps(self):
                return 30.0

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _mark_dirty(self):
                self.dirty = True

        editor = DummyEditor()

        editor._on_provisional_cut_boundary_delete_requested(0, 5.0)

        self.assertEqual([row["timeline_sec"] for row in editor._auto_cut_boundary_scan_lines], [10.0])
        self.assertEqual([row["timeline_sec"] for row in editor.timeline.scan_boundary_times], [10.0])
        operation = getattr(editor, "_last_nle_cut_boundary_operation", {})
        self.assertEqual(operation.get("kind"), "marker_edit")
        self.assertEqual(operation.get("metadata", {}).get("action"), "delete")
        self.assertEqual(operation.get("metadata", {}).get("commit_source"), "provisional_cut_boundary_delete")
        self.assertEqual(operation.get("metadata", {}).get("before_marker_count"), 2)
        self.assertEqual(operation.get("metadata", {}).get("after_marker_count"), 1)
        self.assertTrue(editor.dirty)

    def test_scan_boundary_ignores_stale_auto_rows_after_backend_completion(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = []
                self.canvas = type("Canvas", (), {})()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])
                return True

        class DummyBackend:
            def __init__(self):
                self._cut_boundary_prescan_completed = True
                self._cut_boundary_prescan_thread = None
                self._cut_boundary_follower_thread = None

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self._window = type("Window", (), {"backend": DummyBackend(), "backend_fast": None})()
                self._auto_cut_boundary_scan_active = False
                self._auto_cut_boundary_scan_lines = []

            def window(self):
                return self._window

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

        editor = DummyEditor()

        editor._set_auto_cut_boundary_scan_lines([{"timeline_sec": 12.0, "status": "provisional"}])

        self.assertEqual(editor._auto_cut_boundary_scan_lines, [])
        self.assertEqual(editor.timeline.scan_boundary_times, [])

    def test_scan_boundary_hides_checked_audio_rows_from_ui_preview_only(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = []
                self.canvas = type("Canvas", (), {})()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])
                return True

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self._auto_cut_boundary_scan_active = True
                self._auto_cut_boundary_scan_lines = []

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _scan_cut_should_ignore_stale_preview_rows(self, rows):
                return False

        editor = DummyEditor()

        editor._set_auto_cut_boundary_scan_lines(
            [
                {
                    "timeline_sec": 12.0,
                    "status": "checked",
                    "scan_checked": True,
                    "source": "audio_gain_provisional",
                    "audio_gain_db_delta": 11.0,
                },
                {
                    "timeline_sec": 18.0,
                    "status": "provisional",
                    "source": "visual_provisional",
                },
            ]
        )

        self.assertEqual(
            [row["timeline_sec"] for row in editor._auto_cut_boundary_scan_lines],
            [18.0],
        )
        self.assertEqual(
            [row["timeline_sec"] for row in editor.timeline.scan_boundary_times],
            [18.0],
        )

    def test_scan_boundary_replaces_preview_snapshot_instead_of_reviving_removed_rows(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = []
                self.canvas = type("Canvas", (), {})()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])
                return True

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self._auto_cut_boundary_scan_active = True
                self._auto_cut_boundary_scan_lines = [
                    {
                        "timeline_sec": 9.0,
                        "status": "provisional",
                        "source": "audio_gain_provisional",
                    },
                    {
                        "timeline_sec": 18.0,
                        "status": "provisional",
                        "source": "visual_provisional",
                    },
                ]

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _scan_cut_should_ignore_stale_preview_rows(self, rows):
                return False

        editor = DummyEditor()

        editor._set_auto_cut_boundary_scan_lines(
            [
                {
                    "timeline_sec": 18.0,
                    "status": "provisional",
                    "source": "visual_provisional",
                },
            ]
        )

        self.assertEqual(
            [row["timeline_sec"] for row in editor._auto_cut_boundary_scan_lines],
            [18.0],
        )
        self.assertEqual(
            [row["timeline_sec"] for row in editor.timeline.scan_boundary_times],
            [18.0],
        )

    def test_scan_verify_cut_boundary_candidate_forces_medium_profile(self):
        class FakeCv2:
            CAP_PROP_FPS = 5
            CAP_PROP_FRAME_COUNT = 7

        class FakeCap:
            def get(self, prop):
                if prop == FakeCv2.CAP_PROP_FPS:
                    return 30.0
                if prop == FakeCv2.CAP_PROP_FRAME_COUNT:
                    return 900.0
                return 0.0

        captured = {}

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.settings = {
                    "scan_cut_boundary_level": "off",
                    "scan_cut_follower_strict_multiplier": 1.0,
                }

            def _current_frame_fps(self):
                return 30.0

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _scan_get_cv2_module(self):
                return FakeCv2()

            def _scan_get_cv2_capture(self, _source_path):
                return FakeCap()

            def _scan_source_and_local_sec(self, global_sec):
                return "/tmp/test.mp4", float(global_sec), {}

            def _scan_cut_strict_verify_bundle(self):
                def _profile(settings):
                    return {"level": settings.get("scan_cut_boundary_level"), "positions": (0, 2, 4, 6, 8)}

                def _verify(_cap, _cv2_mod, **kwargs):
                    captured.update(kwargs)
                    return {
                        "passed": True,
                        "frame": 205,
                        "sec": 205.0 / 30.0,
                        "score": 98.4,
                        "regions": 5,
                        "mode": "gray_window_color_avg",
                    }

                return {"profile_fn": _profile, "verify_fn": _verify}

        editor = DummyEditor()

        result = editor._scan_verify_cut_boundary_candidate(150, 30.0, reason="strong_window")

        self.assertIsNotNone(result)
        self.assertTrue(result["passed"])
        self.assertEqual(captured["settings"]["scan_cut_boundary_level"], "medium")
        self.assertGreaterEqual(captured["settings"]["scan_cut_follower_strict_multiplier"], 1.12)
        self.assertLessEqual(captured["settings"]["scan_cut_auto_verify_rollback_frames"], 18)
        self.assertLessEqual(captured["settings"]["scan_cut_auto_verify_forward_frames"], 14)
        self.assertEqual(captured["settings"]["scan_cut_color_avg_window_frames"], 12)
        self.assertEqual(captured["frame_count"], 900)
        self.assertEqual(captured["scan_profile"]["level"], "medium")
        self.assertEqual(result["frame"], 205)
        self.assertAlmostEqual(result["sec"], 205.0 / 30.0, places=3)

    def test_scan_verify_cut_boundary_candidate_promotes_strong_window_provisional_when_only_color_avg_fails(self):
        class FakeCv2:
            CAP_PROP_FPS = 5
            CAP_PROP_FRAME_COUNT = 7

        class FakeCap:
            def get(self, prop):
                if prop == FakeCv2.CAP_PROP_FPS:
                    return 59.94
                if prop == FakeCv2.CAP_PROP_FRAME_COUNT:
                    return 2400.0
                return 0.0

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.settings = {"scan_cut_boundary_level": "medium"}

            def _current_frame_fps(self):
                return 59.94

            def _snap_to_frame(self, sec):
                return round(float(sec), 6)

            def _scan_get_cv2_module(self):
                return FakeCv2()

            def _scan_get_cv2_capture(self, _source_path):
                return FakeCap()

            def _scan_source_and_local_sec(self, global_sec):
                return "/tmp/test.mp4", float(global_sec), {}

            def _scan_cut_strict_verify_bundle(self):
                def _profile(settings):
                    return {"level": settings.get("scan_cut_boundary_level"), "positions": (0, 2, 4, 6, 8)}

                def _verify(_cap, _cv2_mod, **_kwargs):
                    return {
                        "passed": False,
                        "reason": "color_avg_failed",
                        "provisional_frame": 312,
                        "provisional_sec": 312.0 / 59.94,
                        "provisional_score": 56.33,
                        "provisional_regions": 9,
                        "provisional_mode": "1f",
                    }

                return {"profile_fn": _profile, "verify_fn": _verify}

        editor = DummyEditor()

        result = editor._scan_verify_cut_boundary_candidate(312, 59.94, reason="strong_window")

        self.assertIsNotNone(result)
        self.assertTrue(result["passed"])
        self.assertEqual(result["frame"], 312)
        self.assertEqual(result["mode"], "manual_provisional_1f")
        self.assertEqual(result["reason"], "manual_provisional_color_override")

    def test_relative_refine_uses_strict_verified_frame(self):
        class DummyEditor:
            def __init__(self):
                self.settings = {
                    "scan_cut_relative_stages": [3, 1],
                    "scan_cut_relative_rollback_frames": 0,
                    "scan_cut_strong_window_threshold": 75.0,
                    "scan_cut_strong_window_regions_required": 2,
                }
                self._scan_last_region_hits = 0
                self._scan_last_region_deltas = []

            def _current_frame_fps(self):
                return 30.0

            def _scan_verify_cut_boundary_candidate(self, coarse_frame, fps, *, reason=""):
                self.coarse_frame = int(coarse_frame)
                self.coarse_reason = str(reason)
                return {
                    "available": True,
                    "passed": True,
                    "frame": 44,
                    "sec": 44.0 / 30.0,
                    "score": 123.0,
                    "regions": 5,
                    "mode": "gray_window_color_avg",
                }

        editor = DummyEditor()

        def fake_capture(_self, sec, region_mode="fast4", **_kwargs):
            return int(round(float(sec) * 30.0))

        def fake_delta(self, left, right):
            boundary = 42
            hit = int(left) <= boundary < int(right)
            self._scan_last_region_hits = 4 if hit else 1
            self._scan_last_region_deltas = [80.0, 79.0, 78.0, 77.0] if hit else [10.0, 9.0, 8.0, 7.0]
            return 95.0 if hit else 12.0

        with patch.object(scan_cut_relative_refine, "_rel_capture_image_at_global", new=fake_capture), patch.object(
            scan_cut_relative_refine, "_rel_image_delta", new=fake_delta
        ):
            result = scan_cut_relative_refine._rel_refine_boundary(editor, 40, 45, 30.0, "strong_window")

        self.assertEqual(editor.coarse_frame, 42)
        self.assertEqual(editor.coarse_reason, "strong_window")
        self.assertEqual(result, (44, 44.0 / 30.0, 123.0, 5, "strict_gray_window_color_avg"))

    def test_strong_window_candidate_accepts_312_style_cut_even_with_stale_runtime_threshold(self):
        class DummyEditor:
            def __init__(self):
                self.settings = {
                    "scan_cut_strong_window_threshold": 75.0,
                    "scan_cut_ignore_initial_seconds": 10.0,
                }
                self._scan_last_region_hits = 4
                self._scan_last_visual_cut_metrics = {}

        editor = DummyEditor()
        editor._scan_last_visual_cut_metrics = {
            "pixel_ratio": 0.831,
            "motion_jump": 47.2,
            "edge_ratio": 0.202,
        }
        accepted = scan_cut_relative_refine._rel_is_candidate(editor, 58.93, 43.19, 23.54)

        editor._scan_last_visual_cut_metrics = {
            "pixel_ratio": 0.661,
            "motion_jump": 27.4,
            "edge_ratio": 0.195,
        }
        rejected = scan_cut_relative_refine._rel_is_candidate(editor, 46.40, 44.45, 37.52)

        self.assertEqual(accepted, (True, "strong_window"))
        self.assertEqual(rejected, (False, ""))

    def test_manual_scan_ignore_initial_seconds_clamps_stale_default(self):
        class DummyEditor:
            def __init__(self):
                self.settings = {"scan_cut_ignore_initial_seconds": 10.0}

        editor = DummyEditor()

        self.assertEqual(scan_cut_relative_refine._rel_ignore_initial_seconds(editor), 5.0)

    def test_relative_refine_rejects_when_strict_verify_fails(self):
        class DummyEditor:
            def __init__(self):
                self.settings = {
                    "scan_cut_relative_stages": [3, 1],
                    "scan_cut_relative_rollback_frames": 0,
                    "scan_cut_strong_window_threshold": 75.0,
                    "scan_cut_strong_window_regions_required": 2,
                }
                self._scan_last_region_hits = 0
                self._scan_last_region_deltas = []

            def _current_frame_fps(self):
                return 30.0

            def _scan_verify_cut_boundary_candidate(self, _coarse_frame, _fps, *, reason=""):
                return {
                    "available": True,
                    "passed": False,
                    "reason": "gray_failed",
                    "provisional_sec": 1.433,
                    "provisional_mode": "gray_window_rollback",
                }

        editor = DummyEditor()

        def fake_capture(_self, sec, region_mode="fast4", **_kwargs):
            return int(round(float(sec) * 30.0))

        def fake_delta(self, left, right):
            boundary = 42
            hit = int(left) <= boundary < int(right)
            self._scan_last_region_hits = 4 if hit else 1
            self._scan_last_region_deltas = [80.0, 79.0, 78.0, 77.0] if hit else [10.0, 9.0, 8.0, 7.0]
            return 95.0 if hit else 12.0

        with patch.object(scan_cut_relative_refine, "_rel_capture_image_at_global", new=fake_capture), patch.object(
            scan_cut_relative_refine, "_rel_image_delta", new=fake_delta
        ):
            result = scan_cut_relative_refine._rel_refine_boundary(editor, 40, 45, 30.0, "strong_window")

        self.assertIsNone(result)

    def test_manual_found_cut_promotes_to_confirmed_boundary_ui_and_clears_provisional_duplicate(self):
        class DummySignal:
            def __init__(self):
                self.calls = []

            def emit(self, payload):
                self.calls.append(list(payload or []))

        class DummyOwner:
            def __init__(self):
                self._project_boundary_times = []
                self._sig_update_project_boundary_times = DummySignal()

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.settings = {}
                self._project_boundary_times = []
                self._auto_cut_boundary_scan_lines = [
                    {"timeline_sec": 5.205, "time": 5.205, "status": "provisional", "reason": "strong_window"}
                ]
                self.timeline = type("Timeline", (), {})()
                self.timeline.set_boundary_times = Mock(return_value=True)
                self.timeline.set_scan_boundary_times = Mock(return_value=True)
                self.timeline.canvas = type("Canvas", (), {"boundary_times": [], "scan_boundary_times": []})()
                self._owner = DummyOwner()

            def _current_frame_fps(self):
                return 59.94

            def _snap_to_frame(self, sec):
                return round(float(sec), 6)

            def window(self):
                return self._owner

        editor = DummyEditor()
        row = editor._build_confirmed_cut_boundary_record(
            312.0 / 59.94,
            frame=312,
            score=83.34,
            regions=12,
            reason="relative_strict_manual_provisional_1f",
        )

        merged = editor._apply_confirmed_cut_boundary_to_ui(row)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "manual_verified")
        self.assertTrue(merged[0]["verified"])
        self.assertEqual(merged[0]["status"], "confirmed")
        self.assertEqual(editor._owner._project_boundary_times, merged)
        self.assertEqual(editor._owner._sig_update_project_boundary_times.calls[-1], merged)
        editor.timeline.set_boundary_times.assert_called_once_with(merged)
        self.assertEqual(editor._auto_cut_boundary_scan_lines, [])
        editor.timeline.set_scan_boundary_times.assert_called_with([])

    def test_manual_found_cut_sanitizes_boundary_rows_before_storing(self):
        class DummySignal:
            def __init__(self):
                self.calls = []

            def emit(self, payload):
                self.calls.append(list(payload or []))

        class DummyOwner:
            def __init__(self):
                self._project_boundary_times = []
                self._sig_update_project_boundary_times = DummySignal()

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.settings = {}
                self._project_boundary_times = []
                self._auto_cut_boundary_scan_lines = []
                self.timeline = type("Timeline", (), {})()
                self.timeline.set_boundary_times = Mock(return_value=True)
                self.timeline.set_scan_boundary_times = Mock(return_value=True)
                self.timeline.canvas = type("Canvas", (), {"boundary_times": [], "scan_boundary_times": []})()
                self._owner = DummyOwner()

            def _current_frame_fps(self):
                return 59.94

            def _snap_to_frame(self, sec):
                return round(float(sec), 6)

            def window(self):
                return self._owner

        editor = DummyEditor()
        row = editor._build_confirmed_cut_boundary_record(
            312.0 / 59.94,
            frame=312,
            score=83.34,
            regions=12,
            reason="relative_strict_manual_provisional_1f",
        )
        row["debug_payload"] = {"nested": ["should", "drop"]}

        merged = editor._apply_confirmed_cut_boundary_to_ui(row, remove_nearby_provisionals=False)

        self.assertEqual(len(merged), 1)
        self.assertNotIn("debug_payload", merged[0])
        self.assertEqual(merged[0]["timeline_frame"], 312)
        self.assertEqual(merged[0]["source"], "manual_verified")

    def test_official_boundary_marker_visual_distinguishes_manual_verified_rows(self):
        visual = official_boundary_marker_visual(
            {
                "source": "manual_verified",
                "line_color": "#7FDBFF",
                "reason": "relative_strict_manual_provisional_1f",
            }
        )

        self.assertEqual(visual["color"], "#7FDBFF")
        self.assertEqual(visual["width"], 2)
        self.assertEqual(visual["style"], "solid")

    def test_set_active_repaints_full_canvas_in_single_owner_2d_mode(self):
        canvas = self._canvas()
        canvas.resize(500, canvas.height())

        with patch.object(canvas, "update") as update:
            canvas.set_active(1.0)

        update.assert_called_once()
        self.assertEqual(update.call_args.args, ())

    def test_active_segment_uses_line_not_nearby_start_time(self):
        canvas = self._canvas()
        canvas.segments = [
            {"start": 1.00, "end": 1.30, "text": "앞", "line": 0},
            {"start": 1.20, "end": 1.60, "text": "뒤", "line": 1},
        ]

        canvas.set_active(1.0)

        self.assertTrue(canvas._is_active_segment(canvas.segments[0]))
        self.assertFalse(canvas._is_active_segment(canvas.segments[1]))

    def test_playback_does_not_retarget_active_segment_to_playhead(self):
        canvas = self._canvas()
        canvas.segments = [
            {"start": 1.00, "end": 2.00, "text": "앞", "line": 0},
            {"start": 2.00, "end": 3.00, "text": "뒤", "line": 1},
        ]
        canvas.active_seg_line = 0
        canvas.active_seg_start = 1.0
        canvas.playhead_sec = 2.4
        canvas._timeline_playback_active = lambda: True

        self.assertTrue(canvas._is_active_segment(canvas.segments[0]))
        self.assertFalse(canvas._is_active_segment(canvas.segments[1]))

    def test_legacy_external_playhead_overlay_flag_does_not_bypass_single_owner_2d_repaint(self):
        canvas = self._canvas()
        canvas.resize(640, canvas.height())
        canvas._external_playhead_overlay = True
        canvas._timeline_playback_active = lambda: True
        canvas.playhead_sec = 1.2
        canvas._last_playhead_px = canvas._x(1.2)

        with patch.object(canvas, "update") as update:
            canvas.set_playhead(2.4)

        update.assert_called_once_with()

    def test_hovered_arrow_stays_active_when_segment_objects_refresh(self):
        canvas = self._canvas()
        old_seg = canvas.segments[0]
        canvas._hover_handle = (old_seg, "right")
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "앞 갱신", "line": 0},
            {"start": 2.0, "end": 3.0, "text": "뒤", "line": 1},
        ]

        self.assertTrue(canvas._hover_handle_matches(canvas.segments[0], "right"))
        self.assertFalse(canvas._hover_handle_matches(canvas.segments[0], "left"))
        self.assertFalse(canvas._hover_handle_matches(canvas.segments[1], "right"))

    def test_arrow_drag_does_not_rebuild_gaps_on_every_mouse_move(self):
        canvas = self._canvas()
        canvas.segments[1]["start"] = 2.5
        seg = canvas.segments[0]
        canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))

        with patch("ui.timeline.timeline_input._build_gaps") as build_gaps:
            canvas._apply_drag(0.2)

        build_gaps.assert_not_called()
        self.assertGreater(seg["end"], 2.0)

    def test_center_segment_move_prefers_subtitle_boundary_snap_beyond_gap(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 6.0
            canvas.segments = [
                {"start": 2.0, "end": 3.0, "text": "이동", "line": 0},
                {"start": 4.0, "end": 5.0, "text": "다음", "line": 1},
            ]
            canvas.gap_segments = [
                {"start": 3.0, "end": 4.0, "text": "", "is_gap": True, "_explicit_gap": True}
            ]
            moving = canvas.segments[0]
            with patch(
                "ui.editor.ux.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=None,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(moving, "center", canvas._x(2.5))
                canvas._apply_drag(1.0)

            self.assertAlmostEqual(moving["start"], 3.0)
            self.assertAlmostEqual(moving["end"], 4.0)
            self.assertTrue(bool(getattr(canvas, "_drag_suppresses_gap_candidate_attachment", False)))
            self.assertEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "subtitle")
        finally:
            canvas.deleteLater()

    def test_center_segment_move_suppresses_single_gap_snap_without_subtitle_target(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 6.0
            canvas.segments = [
                {"start": 2.0, "end": 3.0, "text": "이동", "line": 0},
            ]
            canvas.gap_segments = [
                {"start": 3.0, "end": 4.0, "text": "", "is_gap": True, "_explicit_gap": True}
            ]
            moving = canvas.segments[0]
            with patch(
                "ui.editor.ux.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=None,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(moving, "center", canvas._x(2.5))
                canvas._apply_drag(1.5)

            self.assertAlmostEqual(moving["start"], 3.5)
            self.assertAlmostEqual(moving["end"], 4.5)
            self.assertTrue(bool(getattr(canvas, "_drag_suppresses_gap_candidate_attachment", False)))
            self.assertNotEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "gap")
        finally:
            canvas.deleteLater()

    def test_center_segment_move_prefers_subtitle_boundary_beyond_voice_silence(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 6.0
            canvas.segments = [
                {"start": 2.0, "end": 3.0, "text": "이동", "line": 0},
                {"start": 4.0, "end": 5.0, "text": "다음", "line": 1},
            ]
            canvas.voice_activity_segments = [
                {"start": 3.0, "end": 4.0, "kind": "silence", "label": "무음구간"}
            ]
            native_candidates = [
                {"time": 2.0, "kind": "subtitle", "sourceLine": 0},
                {"time": 3.0, "kind": "subtitle", "sourceLine": 0},
                {"time": 4.0, "kind": "subtitle", "sourceLine": 1},
                {"time": 5.0, "kind": "subtitle", "sourceLine": 1},
                {"time": 3.0, "kind": "voice_activity"},
                {"time": 4.0, "kind": "voice_activity"},
            ]
            moving = canvas.segments[0]
            with patch(
                "ui.editor.ux.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=native_candidates,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(moving, "center", canvas._x(2.5))
                canvas._apply_drag(1.0)

            self.assertAlmostEqual(moving["start"], 3.0)
            self.assertAlmostEqual(moving["end"], 4.0)
            self.assertTrue(bool(getattr(canvas, "_drag_suppresses_gap_candidate_attachment", False)))
            self.assertEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "subtitle")
        finally:
            canvas.deleteLater()

    def test_center_segment_move_suppresses_voice_silence_snap_without_subtitle_target(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 6.0
            canvas.segments = [
                {"start": 2.0, "end": 3.0, "text": "이동", "line": 0},
            ]
            canvas.voice_activity_segments = [
                {"start": 3.0, "end": 4.0, "kind": "silence", "label": "무음구간"}
            ]
            native_candidates = [
                {"time": 2.0, "kind": "subtitle", "sourceLine": 0},
                {"time": 3.0, "kind": "subtitle", "sourceLine": 0},
                {"time": 3.0, "kind": "voice_activity"},
                {"time": 4.0, "kind": "voice_activity"},
            ]
            moving = canvas.segments[0]
            with patch(
                "ui.editor.ux.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=native_candidates,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(moving, "center", canvas._x(2.5))
                canvas._apply_drag(0.95)

            self.assertAlmostEqual(moving["start"], canvas._snap_to_frame(2.95))
            self.assertAlmostEqual(moving["end"], canvas._snap_to_frame(3.95))
            self.assertTrue(bool(getattr(canvas, "_drag_suppresses_gap_candidate_attachment", False)))
            self.assertNotEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "voice_activity")
        finally:
            canvas.deleteLater()

    def test_boundary_release_emits_visible_snapped_boundary(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 30.0
            canvas.pps = 100.0
            canvas.total_duration = 6.0
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "현재", "line": 0},
                {"start": 3.0, "end": 4.0, "text": "다음", "line": 1},
            ]
            emitted = []
            canvas.seg_time_changed.connect(
                lambda line, start, end, edge: emitted.append((line, start, end, edge))
            )
            current = canvas.segments[0]
            with patch(
                "ui.editor.ux.timeline_subtitle_segment_editing.build_subtitle_drag_snap_base_via_swift",
                return_value=None,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_timing_drag_via_swift",
                return_value=None,
            ):
                canvas._setup_drag(current, "square_right", canvas._x(2.0))
                canvas._apply_drag(0.95)

            self.assertAlmostEqual(current["end"], 3.0)

            canvas.mouseReleaseEvent(SimpleNamespace())

            self.assertEqual(len(emitted), 1)
            line, start, end, edge = emitted[0]
            self.assertEqual(line, 0)
            self.assertAlmostEqual(start, 1.0)
            self.assertAlmostEqual(end, 3.0)
            self.assertEqual(edge, "square_right")
        finally:
            canvas.deleteLater()

    def test_new_subtitle_placeholder_clears_when_inline_edit_starts(self):
        canvas = self._canvas()
        try:
            canvas.segments = [
                {"start": 1.0, "end": 2.0, "text": "새자막", "line": 0},
            ]
            emitted = []
            canvas.sig_inline_text_changed.connect(
                lambda line, text: emitted.append((line, text, getattr(canvas, "_inline_commit_in_progress", False)))
            )
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0)

            self.assertTrue(canvas._edit_active)
            self.assertEqual(canvas._edit_text, "")
            self.assertEqual(canvas._edit_orig, "")
            self.assertEqual(canvas._edit_cursor, 0)
            self.assertEqual(canvas.segments[0]["text"], "")
            self.assertEqual(emitted, [(0, "", True)])
            self.assertIsNotNone(canvas._inline_editor)
            self.assertTrue(canvas._inline_editor.isVisible())
            self.assertEqual(canvas._inline_editor.font().pointSize(), 13)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_inline_edit_entry_traces_preview_without_nle_commit_or_row_rewrite(self):
        canvas = TimelineCanvas()

        class FakeTraceLogger:
            def __init__(self):
                self.events = []

            def log_event(self, event, **fields):
                self.events.append({"event": event, **fields})
                return True

        fake_logger = FakeTraceLogger()
        try:
            canvas.resize(520, canvas.height())
            canvas.frame_rate = 30.0
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.playhead_sec = 1.4
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "원본", "line": 0, "id": "subtitle_vector_1"},
            ]
            before_rows = [dict(row) for row in canvas.segments]
            emitted = []
            canvas.sig_inline_text_changed.connect(lambda line, text: emitted.append((line, text)))
            canvas.show()
            self.app.processEvents()

            with patch(
                "ui.editor.ux.timeline_canvas_editing.current_app_trace_logger",
                return_value=fake_logger,
            ), patch(
                "ui.editor.ux.timeline_canvas_editing.apply_caption_text_edit_dual_write_pilot"
            ) as nle_text_edit, patch(
                "core.project.nle_project_state.record_nle_operation_journal_entry"
            ) as record_journal:
                canvas.start_inline_edit(0, 1.0)

            self.assertTrue(canvas._edit_active)
            self.assertEqual(canvas.segments, before_rows)
            self.assertEqual(emitted, [])
            nle_text_edit.assert_not_called()
            record_journal.assert_not_called()
            self.assertFalse(hasattr(canvas, "_last_nle_timeline_operation"))

            self.assertEqual(len(fake_logger.events), 1)
            event = fake_logger.events[0]
            self.assertEqual(event["event"], "timeline_inline_edit_entry")
            self.assertEqual(event["stage"], "ui-ux")
            self.assertEqual(event["event_type"], "inline_edit_entry")
            self.assertEqual(event["action"], "inline_edit_entry")
            self.assertEqual(event["commit_boundary"], "none")
            self.assertEqual(event["commit_source"], "timeline_inline_edit_entry")
            self.assertFalse(event["nle_write_allowed"])
            self.assertFalse(event["normal_caption_row_rewrite_allowed"])
            self.assertFalse(event["placeholder_clear_applied"])
            self.assertFalse(event["caption_payload_included"])
            self.assertTrue(event["visible"])
            self.assertNotIn("text", event)
            self.assertNotIn("old_text", event)
            self.assertNotIn("new_text", event)
            self.assertNotIn("target_ids", event)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_native_inline_editor_backspace_clears_segment_text_live(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "로맨틱아!", "line": 0},
            ]
            emitted = []
            canvas.sig_inline_text_changed.connect(lambda line, text: emitted.append((line, text)))
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0)
            editor = canvas._inline_editor
            self.assertIsNotNone(editor)
            editor.setFocus()
            editor.selectAll()

            QTest.keyClick(editor, Qt.Key.Key_Backspace)
            self.app.processEvents()

            self.assertEqual(editor.toPlainText(), "")
            self.assertEqual(canvas._edit_text, "")
            self.assertEqual(canvas.segments[0]["text"], "")
            self.assertIn((0, ""), emitted)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_native_inline_editor_routes_canvas_click_to_exact_cursor_position(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "정확한 클릭 위치", "line": 0},
            ]
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0)
            editor = canvas._inline_editor

            self.assertIsNotNone(editor)
            self.assertTrue(editor.isVisible())
            self.assertEqual(canvas._subtitle_segment_font().pointSize(), 13)
            self.assertEqual(canvas._stt_preview_font().pointSize(), 13)

            start_cursor = editor.textCursor()
            start_cursor.setPosition(0)
            editor.setTextCursor(start_cursor)
            click_point = editor.viewport().mapTo(canvas, editor.cursorRect(start_cursor).center())

            handled = canvas._route_inline_editor_click(click_point.x(), click_point.y())

            self.assertTrue(handled)
            self.assertEqual(editor.textCursor().position(), 0)
            self.assertEqual(canvas._edit_cursor, 0)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_native_inline_editor_stays_inside_subtitle_segment_text_box(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "세그먼트 안에서 바로 편집", "line": 0},
            ]
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0)
            editor = canvas._inline_editor

            self.assertIsNotNone(editor)
            self.assertFalse(editor.isWindow())
            self.assertIs(editor.parentWidget(), canvas)
            self.assertEqual(editor.property("timelineInlineEditorRole"), "segment-inline-locked")
            self.assertGreaterEqual(editor.geometry().top(), SUBTITLE_TOP)
            self.assertLessEqual(editor.geometry().bottom(), SUBTITLE_BOT)
            self.assertLessEqual(editor.geometry().height(), (SUBTITLE_BOT - SUBTITLE_TOP))
            self.assertFalse(editor.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
            self.assertTrue(editor.viewport().testAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent))
            self.assertIn("background: #", editor.styleSheet())
            self.assertNotIn("background: transparent", editor.styleSheet())
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_native_inline_editor_suppresses_background_segment_text(self):
        self.assertFalse(
            should_paint_subtitle_segment_text(
                native_inline_active=True,
                rect_width=220,
                dense_segment_mode=False,
                focus_detail=True,
            )
        )
        self.assertTrue(
            should_paint_subtitle_segment_text(
                native_inline_active=False,
                rect_width=220,
                dense_segment_mode=False,
                focus_detail=True,
            )
        )

    def test_selected_stt_preview_badge_anchors_to_right_edge(self):
        rect = QRect(200, STT1_TOP, 420, 28)
        badge = stt_preview_selection_badge_rect(rect, 36)

        self.assertEqual(badge.right(), rect.right() - 4)
        self.assertGreater(badge.center().x(), rect.center().x())

    def test_global_canvas_context_menu_includes_subtitle_post_llm_actions(self):
        canvas = GlobalCanvas()
        try:
            labels = [
                item.get("label")
                for item in canvas._context_menu_items()
                if not item.get("separator")
            ]

            self.assertIn("러프컷 LLM 실행", labels)
            self.assertIn("띄워쓰기 맞춤법 검사", labels)
            self.assertIn("영어로 번역", labels)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_top_subtitle_button_menu_includes_overlay_gpu_export(self):
        timeline = TimelineWidget()
        try:
            labels = [
                item.get("label")
                for item in timeline._subtitle_button_menu_items()
                if not item.get("separator")
            ]

            self.assertIn("자막자석 실행", labels)
            self.assertIn("텍스트 높이 조절", labels)
            self.assertIn("투명 자막 MOV 출력", labels)
            self.assertIn("영상+자막 오버레이 출력 (GPU)", labels)
            self.assertLess(
                labels.index("텍스트 높이 조절"),
                labels.index("투명 자막 MOV 출력"),
            )
            self.assertLess(
                labels.index("투명 자막 MOV 출력"),
                labels.index("영상+자막 오버레이 출력 (GPU)"),
            )
        finally:
            timeline.close()
            timeline.deleteLater()

    def test_inline_edit_enter_uses_playhead_split_when_started_with_split_mode(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.pps = 120.0
            canvas.total_duration = 4.0
            canvas.playhead_sec = 1.8
            canvas.segments = [
                {"start": 1.0, "end": 2.8, "text": "정확한 클릭 위치", "line": 0},
            ]
            emitted = []
            canvas.sig_split_request.connect(lambda line, sec, cursor: emitted.append((line, sec, cursor)))
            canvas.show()
            self.app.processEvents()

            canvas.start_inline_edit(0, 1.0, split_at_playhead=True)
            editor = canvas._inline_editor

            self.assertIsNotNone(editor)
            self.assertAlmostEqual(float(getattr(canvas, "_pending_split_sec", 0.0)), 1.8, places=6)

            cursor = editor.textCursor()
            cursor.setPosition(4)
            editor.setTextCursor(cursor)
            canvas._sync_inline_editor_state_from_widget(text_changed=False)

            QTest.keyClick(editor, Qt.Key.Key_Return)
            self.app.processEvents()

            self.assertEqual(emitted, [(0, 1.8, 4)])
            self.assertFalse(canvas._edit_active)
            self.assertFalse(hasattr(canvas, "_pending_split_sec"))
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_review_segment_right_click_menu_merges_review_actions_into_first_menu(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.segments[0]["quality"] = {"confidence_label": "red", "flags": ["high_cps"]}
        captured = {}

        def _capture_menu(_owner, _gpos, items):
            captured["labels"] = [str(item.get("label", "")) for item in items]
            return None

        with patch("ui.timeline.timeline_input.show_context_menu", side_effect=_capture_menu):
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), SEG_TOP + 10),
            )

        self.assertEqual(captured["labels"], ["자막 확정", "자막 분할", "자막 삭제"])
        self.assertNotIn("검토 메뉴", captured["labels"])

    def test_review_segment_right_click_emits_primary_review_action_request(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.segments[0]["quality"] = {"confidence_label": "red", "flags": ["high_cps"]}
        emitted = []
        canvas.seg_right_clicked.connect(lambda start, _pos: emitted.append(start))

        with patch("ui.timeline.timeline_input.show_context_menu", return_value="primary"):
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), SEG_TOP + 10),
            )

        self.assertEqual(emitted, [1.0])
        self.assertFalse(canvas._edit_active)

    def test_confirmed_segment_right_click_emits_primary_review_action_request(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.segments[0]["quality"] = {
            "confidence_label": "green",
            "manual_confirmed": True,
            "flags": ["manual_confirmed"],
        }
        emitted = []
        canvas.seg_right_clicked.connect(lambda start, _pos: emitted.append(start))

        with patch("ui.timeline.timeline_input.show_context_menu", return_value="primary"):
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), SEG_TOP + 10),
            )

        self.assertEqual(emitted, [1.0])
        self.assertFalse(canvas._edit_active)

    def test_normal_segment_right_click_split_action_enters_split_mode(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.playhead_sec = 1.8
        canvas.show()
        self.app.processEvents()

        with patch("ui.timeline.timeline_input.show_context_menu", return_value="split"):
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.RightButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.6), SEG_TOP + 10),
            )

        self.assertTrue(canvas._edit_active)
        self.assertAlmostEqual(float(getattr(canvas, "_pending_split_sec", 0.0)), 1.8, places=6)
        self.assertIsNotNone(canvas._inline_editor)
        self.assertTrue(canvas._inline_editor.isVisible())

    def test_smart_split_mode_blocks_outside_click_resize_interactions(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.playhead_sec = 1.8
        canvas.show()
        self.app.processEvents()
        canvas.start_inline_edit(0, 1.0, split_at_playhead=True)
        self.assertTrue(canvas._edit_active)

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.0), SEG_TOP + 32),
        )
        self.app.processEvents()

        self.assertTrue(canvas._edit_active)
        self.assertFalse(canvas._drag_seg)
        self.assertIsNone(canvas._drag_edge)
        self.assertTrue(hasattr(canvas, "_pending_split_sec"))

    def test_stt_candidate_lane_click_emits_candidate_selection(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        stt1 = {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1", "stt_pending": True}
        stt2 = {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2", "stt_pending": True}
        canvas.segments.extend([stt1, stt2])
        emitted = []
        canvas.stt_candidate_selected.connect(lambda seg: emitted.append(seg["text"]))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), STT1_TOP + 8),
        )
        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), STT2_TOP + 8),
        )

        self.assertEqual(emitted, ["STT1 후보", "STT2 후보"])

    def test_stt_candidate_is_not_edit_or_drag_target(self):
        canvas = self._canvas()
        stt1 = {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1", "stt_pending": True}
        canvas.segments = [stt1]
        canvas.active_seg_start = 1.0

        QTest.keyClick(canvas, Qt.Key.Key_F2)
        canvas.mouseDoubleClickEvent(
            type(
                "Event",
                (),
                {
                    "button": lambda self: Qt.MouseButton.LeftButton,
                    "pos": lambda self: QPoint(canvas._x(1.5), STT1_TOP + 8),
                },
            )()
        )

        self.assertFalse(canvas._edit_active)
        self.assertIsNone(canvas._handle_drag_at(canvas._x(1.0), STT1_TOP + 8))

    def test_stt_candidate_selected_by_llm_matches_source_and_overlap(self):
        candidate = {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2", "stt_pending": True}
        final = {
            "start": 1.05,
            "end": 2.05,
            "text": "STT2 후보",
            "stt_ensemble_llm_selected_source": "STT2",
            "stt_candidates": [{"source": "STT2", "text": "STT2 후보"}],
        }

        self.assertTrue(stt_candidate_selected_by_llm(candidate, [final]))
        self.assertFalse(stt_candidate_selected_by_llm({**candidate, "stt_preview_source": "STT1"}, [final]))

    def test_manual_stt_candidate_selection_marks_winner_and_loser(self):
        stt1 = {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1", "stt_pending": True}
        stt2 = {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2", "stt_pending": True}
        final = {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_selected_source": "STT1"}

        self.assertEqual(stt_candidate_selection_state(stt1, [final]), "manual")
        self.assertTrue(stt_candidate_selected(stt1, [final]))
        self.assertTrue(stt_candidate_unselected(stt2, [final]))

    def test_indexed_stt_candidate_selection_matches_linear_scan(self):
        finals = [
            {"start": float(i * 2), "end": float(i * 2 + 1), "text": f"final {i}"}
            for i in range(500)
        ]
        finals.append(
            {
                "start": 777.05,
                "end": 778.05,
                "text": "선택",
                "stt_ensemble_llm_selected_source": "STT2",
                "stt_candidates": [{"source": "STT2", "text": "STT2 후보"}],
            }
        )
        candidate = {
            "start": 777.0,
            "end": 778.0,
            "text": "STT2 후보",
            "stt_preview_source": "STT2",
            "stt_pending": True,
        }
        index = build_stt_selection_index(finals)

        self.assertEqual(stt_candidate_selection_state(candidate, finals), "llm")
        self.assertEqual(stt_candidate_selection_state(candidate, finals, index), "llm")
        self.assertEqual(
            stt_candidate_selection_state({**candidate, "stt_preview_source": "STT1"}, finals, index),
            "unselected",
        )
        far_candidate = {**candidate, "start": 9999.0, "end": 10000.0}
        self.assertEqual(stt_candidate_selection_state(far_candidate, finals), "")
        self.assertEqual(stt_candidate_selection_state(far_candidate, finals, index), "")

    def test_manual_stt_candidate_selection_keeps_preview_lanes_visible(self):
        class DummyScroll:
            def __init__(self):
                self.value_ = 0

            def value(self):
                return self.value_

            def setValue(self, value):
                self.value_ = int(value)

        class DummyTimeline:
            def __init__(self):
                self.updated_segments = []
                self.scroll = type("Scroll", (), {"horizontalScrollBar": lambda _self: DummyScroll()})()

            def update_segments(self, segments, active_sec=None, total_dur=0.0, *, global_rows=None):
                self.updated_segments = list(segments or [])

            def set_active(self, _sec):
                pass

            def set_playhead(self, _sec, preserve_center_lock=False):
                pass

        class DummyEditor(EditorSegmentsMixin):
            def __init__(self):
                self.video_fps = 30.0
                self._segments = [{"line": 0, "start": 1.0, "end": 2.0, "text": "기존"}]
                self._live_stt_preview_segments = [
                    {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1", "stt_pending": True},
                    {"start": 1.0, "end": 2.0, "text": "STT2 후보", "stt_preview_source": "STT2", "stt_pending": True},
                ]
                self.timeline = DummyTimeline()
                self.text_edit = QTextEdit()
                self.video_player = type("Player", (), {"total_time": 4.0, "seek": lambda _self, _sec: None})()
                self._undo_mgr = _Undo()

            def _get_current_segments(self):
                return list(self._segments)

            def _reload_segments_from_list(self, segments, preserve_view=False):
                self._segments = list(segments or [])

        editor = DummyEditor()
        try:
            editor.select_stt_candidate_as_subtitle(
                {"start": 1.0, "end": 2.0, "text": "STT1 후보", "stt_preview_source": "STT1", "stt_pending": True}
            )

            self.assertEqual(
                [seg.get("stt_preview_source") for seg in editor._live_stt_preview_segments],
                ["STT1", "STT2"],
            )
            self.assertTrue(any(
                seg.get("stt_pending") and seg.get("stt_preview_source") == "STT1"
                for seg in editor.timeline.updated_segments
            ))
        finally:
            editor.text_edit.close()

    def test_confirm_review_segment_clears_review_flags(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("확인 필요")
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "red", "flags": ["high_cps"], "confidence_score": 40},
                    quality_signature="old",
                )
            )
            editor._segments = [
                {"line": 0, "start": 1.0, "end": 2.0, "text": "확인 필요", "quality": {"confidence_label": "red", "flags": ["high_cps"]}}
            ]

            editor._confirm_review_segment(0)

            data = block.userData()
            self.assertEqual(data.quality["confidence_label"], "green")
            self.assertTrue(data.quality["manual_confirmed"])
            self.assertNotIn("high_cps", data.quality["flags"])
            self.assertIn("manual_confirmed", data.quality["flags"])
            self.assertTrue(editor.dirty)
            self.assertTrue(editor.finalized)
            self.assertTrue(editor.refreshed)
        finally:
            editor.text_edit.close()

    def test_timeline_review_action_from_canvas_bypasses_second_popup(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("삭제할 자막")
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "red", "flags": ["high_cps"]},
                )
            )
            editor._segments = [
                {"line": 0, "start": 1.0, "end": 2.0, "text": "삭제할 자막", "quality": {"confidence_label": "red", "flags": ["high_cps"]}}
            ]
            editor.timeline = SimpleNamespace(canvas=SimpleNamespace(_pending_timeline_review_action="delete"))

            with patch("ui.editor.editor_video_controls.show_context_menu") as menu:
                editor._on_timeline_seg_right_clicked(1.0, QPoint())

            self.assertEqual(editor.deleted_lines, [0])
            menu.assert_not_called()
            self.assertFalse(hasattr(editor.timeline.canvas, "_pending_timeline_review_action"))
        finally:
            editor.text_edit.close()

    def test_yellow_diamond_drag_emits_both_adjacent_segment_updates(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            for seg in canvas.segments:
                seg["quality"] = {"confidence_label": "yellow", "flags": []}
            emitted = []
            canvas.seg_time_changed.connect(
                lambda line, start, end, edge: emitted.append((line, start, end, edge))
            )

            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_snap_candidates_cache = [{"time": 2.2, "kind": "test"}]
            canvas._apply_drag(0.2)
            canvas.mouseReleaseEvent(object())

            self.assertAlmostEqual(canvas.segments[0]["end"], 2.2)
            self.assertAlmostEqual(canvas.segments[1]["start"], 2.2)
            self.assertEqual(
                emitted,
                [
                    (0, 1.0, 2.2, "diamond"),
                    (1, 2.2, 3.0, "diamond"),
                ],
            )
        finally:
            canvas.deleteLater()

    def test_square_right_drag_emits_live_preview_sec_for_video_frame(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            emitted = []
            target = canvas.segments[1]
            canvas.drag_preview_sec.connect(emitted.append)

            canvas._setup_drag(target, "square_right", canvas._x(target["end"]))
            canvas._apply_drag(0.2)

            self.assertTrue(bool(emitted))
            self.assertAlmostEqual(emitted[-1], 3.2)
        finally:
            canvas.deleteLater()

    def test_diamond_drag_emits_live_preview_sec_for_video_frame(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            emitted = []
            canvas.drag_preview_sec.connect(emitted.append)

            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_snap_candidates_cache = [{"time": 2.2, "kind": "test"}]
            canvas._apply_drag(0.2)

            self.assertTrue(bool(emitted))
            self.assertAlmostEqual(emitted[-1], 2.2)
        finally:
            canvas.deleteLater()

    def test_diamond_drag_uses_live_cut_snap_candidate(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_snap_candidates_cache = []
            canvas._drag_live_cut_snap_candidates = Mock(
                return_value=[{"time": 2.11, "kind": "cut_live", "source": {"score": 32.0}}]
            )

            canvas._apply_drag(0.05)

            canvas._drag_live_cut_snap_candidates.assert_called_once()
            self.assertAlmostEqual(canvas.segments[0]["end"], 2.11)
            self.assertAlmostEqual(canvas.segments[1]["start"], 2.11)
            self.assertEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "cut_live")
        finally:
            canvas.deleteLater()

    def test_live_cut_snap_candidate_resolves_global_context(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas._resolve_active_context = Mock(
                return_value={
                    "clip_file": __file__,
                    "local_sec": 1.19,
                    "clip_start": 1.0,
                    "fps": 100.0,
                }
            )
            canvas._detect_live_cut_boundary_record = Mock(
                return_value={"local_sec": 1.23, "frame": 123, "score": 40.0}
            )
            canvas._schedule_drag_live_cut_async = Mock()
            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0

            candidates = canvas._drag_live_cut_snap_candidates(2.19, edge="diamond")

            self.assertEqual(candidates, [])
            canvas._detect_live_cut_boundary_record.assert_not_called()
            canvas._schedule_drag_live_cut_async.assert_called_once()
            request = canvas._schedule_drag_live_cut_async.call_args.args[0]
            self.assertEqual(request["media_path"], os.path.abspath(__file__))
            self.assertEqual(request["direction"], 1)
            self.assertAlmostEqual(request["origin_local_sec"], 1.0, places=2)
            self.assertAlmostEqual(request["target_local_sec"], 1.19, places=2)
            self.assertAlmostEqual(request["search_start_local_sec"], 1.0, places=2)
            self.assertAlmostEqual(request["search_end_local_sec"], 1.19, places=2)
        finally:
            canvas.deleteLater()

    def test_live_cut_snap_candidate_uses_reverse_direction_window_when_dragging_left(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas._resolve_active_context = Mock(
                return_value={
                    "clip_file": __file__,
                    "local_sec": 1.70,
                    "clip_start": 0.0,
                    "fps": 100.0,
                }
            )
            canvas._detect_live_cut_boundary_record = Mock(
                return_value={"local_sec": 1.66, "frame": 166, "score": 31.0}
            )
            canvas._schedule_drag_live_cut_async = Mock()
            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas.segments[0]["end"] = 2.0

            candidates = canvas._drag_live_cut_snap_candidates(1.70, edge="diamond")

            self.assertEqual(candidates, [])
            canvas._detect_live_cut_boundary_record.assert_not_called()
            request = canvas._schedule_drag_live_cut_async.call_args.args[0]
            self.assertEqual(request["direction"], -1)
            self.assertAlmostEqual(request["search_start_local_sec"], 1.70, places=2)
            self.assertAlmostEqual(request["search_end_local_sec"], 2.0, places=2)
            self.assertEqual(request["origin_frame"], 200)
            self.assertEqual(request["target_frame"], 170)
        finally:
            canvas.deleteLater()

    def test_live_cut_snap_returns_cached_async_candidate_without_blocking(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas._resolve_active_context = Mock(
                return_value={
                    "clip_file": __file__,
                    "local_sec": 1.30,
                    "clip_start": 1.0,
                    "fps": 100.0,
                }
            )
            canvas._schedule_drag_live_cut_async = Mock()
            canvas._detect_live_cut_boundary_record = Mock()
            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_live_cut_async_candidate = {
                "time": 2.23,
                "kind": "cut_live",
                "source": {
                    "media_path": __file__,
                    "local_sec": 1.23,
                    "clip_start": 1.0,
                    "fps": 100.0,
                    "frame": 123,
                },
            }

            candidates = canvas._drag_live_cut_snap_candidates(2.30, edge="diamond")

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["kind"], "cut_live")
            self.assertAlmostEqual(candidates[0]["time"], 2.23)
            canvas._detect_live_cut_boundary_record.assert_not_called()
            canvas._schedule_drag_live_cut_async.assert_called_once()
            self.assertAlmostEqual(canvas._drag_shadow_playhead_sec or 0.0, 2.23, places=4)
        finally:
            canvas.deleteLater()

    def test_live_cut_async_result_reapplies_current_diamond_drag(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_last_delta = 0.30
            canvas._drag_live_cut_session_id = 7
            canvas._drag_live_cut_async_busy = True
            canvas._apply_drag = Mock()

            canvas._on_drag_live_cut_async_result(
                {
                    "session_id": 7,
                    "token": 1,
                    "request": {
                        "media_path": __file__,
                        "fps": 100.0,
                        "clip_start": 1.0,
                        "direction": 1,
                        "search_start_local_sec": 1.0,
                        "search_end_local_sec": 1.30,
                        "score_start_frame": 99,
                        "search_start_frame": 100,
                        "search_end_frame": 130,
                        "signature": (__file__, 100.0, 100, 130, 100, 130),
                    },
                    "candidate": {"local_sec": 1.23, "frame": 123, "score": 42.0},
                    "scores": [(42.0, 123)],
                }
            )

            self.assertFalse(canvas._drag_live_cut_async_busy)
            self.assertEqual((canvas._drag_live_cut_async_candidate or {}).get("kind"), "cut_live")
            self.assertAlmostEqual(canvas._drag_live_cut_async_candidate["time"], 2.23)
            canvas._apply_drag.assert_called_once_with(0.30)
        finally:
            canvas.deleteLater()

    def test_live_cut_snap_reuses_expanded_score_cache(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas._compute_live_cut_boundary_scores = Mock(return_value=[(25.0, 110)])

            first = canvas._detect_live_cut_boundary_record(
                __file__,
                1.20,
                100.0,
                direction=1,
                search_start_local_sec=0.20,
                search_end_local_sec=1.20,
            )
            second = canvas._detect_live_cut_boundary_record(
                __file__,
                1.25,
                100.0,
                direction=1,
                search_start_local_sec=0.25,
                search_end_local_sec=1.25,
            )

            canvas._compute_live_cut_boundary_scores.assert_called_once()
            self.assertEqual(int(first["frame"]), 110)
            self.assertEqual(int(second["frame"]), 110)
        finally:
            canvas.deleteLater()

    def test_live_cut_snap_has_stronger_magnet_threshold(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 60.0
            canvas.pps = 200.0
            base = canvas._drag_snap_threshold_sec()

            threshold = canvas._snap_candidate_threshold_sec({"kind": "cut_live"}, base)

            self.assertGreaterEqual(threshold, 6.0 / 60.0)
            self.assertGreater(threshold, base)
        finally:
            canvas.deleteLater()

    def test_segment_drag_release_cleans_up_drag_state_without_popup(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            canvas.segments[1]["quality"] = {"confidence_label": "yellow", "flags": []}
            finished = []
            canvas.drag_finished.connect(lambda: finished.append(True))

            seg = canvas.segments[1]
            canvas._setup_drag(seg, "square_right", canvas._x(seg["end"]))
            canvas._apply_drag(0.2)
            canvas.mouseReleaseEvent(object())

            self.assertIsNone(canvas._drag_seg)
            self.assertIsNone(canvas._drag_edge)
            self.assertEqual(len(finished), 1)
            self.assertAlmostEqual(canvas.segments[1]["end"], 3.2)
        finally:
            canvas.deleteLater()

    def test_drag_release_persists_user_alignment_guide_and_future_drag_snaps_to_it(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.segments = [
                {"start": 1.0, "end": 1.8, "text": "앞", "line": 0},
                {"start": 2.5, "end": 3.0, "text": "중간", "line": 1},
                {"start": 3.6, "end": 4.1, "text": "뒤", "line": 2},
            ]

            moving = canvas.segments[2]
            canvas._setup_drag(moving, "square_left", canvas._x(moving["start"]))
            canvas._apply_drag(-0.32)
            canvas.mouseReleaseEvent(object())
            self.assertEqual([round(sec, 2) for sec in canvas.user_alignment_guides], [3.28])

            canvas._setup_drag(moving, "square_left", canvas._x(moving["start"]))
            canvas._apply_drag(0.17)
            canvas.mouseReleaseEvent(object())
            self.assertEqual([round(sec, 2) for sec in canvas.user_alignment_guides], [3.45])

            target = canvas.segments[1]
            canvas._setup_drag(target, "square_right", canvas._x(target["end"]))
            canvas._apply_drag(0.43)

            self.assertAlmostEqual(target["end"], 3.45)
            self.assertEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "user_guide")
        finally:
            canvas.deleteLater()

    def test_shadow_playhead_becomes_drag_snap_target(self):
        canvas = TimelineCanvas()
        try:
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.playhead_sec = 3.45
            canvas.set_shadow_playhead(3.45)
            canvas.segments = [
                {"start": 1.0, "end": 1.8, "text": "앞", "line": 0},
                {"start": 2.5, "end": 3.0, "text": "중간", "line": 1},
                {"start": 3.7, "end": 4.1, "text": "뒤", "line": 2},
            ]

            target = canvas.segments[1]
            canvas._setup_drag(target, "square_right", canvas._x(target["end"]))
            self.assertAlmostEqual(canvas.shadow_playhead_sec, 3.45)
            canvas._apply_drag(0.43)

            self.assertAlmostEqual(target["end"], 3.45)
            self.assertEqual(dict(canvas._drag_snap_candidate or {}).get("kind"), "shadow_playhead")
            self.assertIsNone(canvas.shadow_playhead_sec)
        finally:
            canvas.deleteLater()

    def test_mouse_click_materializes_last_arrow_frame_as_shadow_playhead(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.playhead_sec = 2.0
            canvas._arm_shadow_playhead(2.0)
            scrubbed = []
            canvas.scrub_sec.connect(scrubbed.append)

            QTest.mouseClick(
                canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(3.2), SEG_TOP + 32),
            )

            self.assertEqual(scrubbed, [3.2])
            self.assertAlmostEqual(canvas.shadow_playhead_sec or 0.0, 2.0, places=4)
            self.assertIsNone(getattr(canvas, "_shadow_playhead_armed_sec", None))
        finally:
            canvas.deleteLater()

    def test_left_drag_playhead_handle_scrubs_without_opening_menu(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.playhead_sec = 1.0
            scrubbed = []
            menus = []
            canvas.scrub_sec.connect(scrubbed.append)
            canvas.playhead_menu_requested.connect(lambda *_args: menus.append(True))
            canvas.show()
            self.app.processEvents()

            start = QPoint(canvas._x(1.0), 9)
            end = QPoint(canvas._x(1.5), 9)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(canvas, end, delay=1)
            self.app.processEvents()
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)

            self.assertEqual(menus, [])
            self.assertTrue(scrubbed)
            self.assertAlmostEqual(scrubbed[-1], 1.5, places=3)
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_locks_until_next_drag(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.playhead_sec = 1.0
            scrubbed = []
            canvas.scrub_sec.connect(scrubbed.append)
            canvas._playhead_auto_cut_snap_sec = Mock(
                side_effect=lambda target, previous: (1.25, True) if float(target) > 1.05 else (target, False)
            )
            canvas.show()
            self.app.processEvents()

            start = QPoint(canvas._x(1.0), 9)
            first = QPoint(canvas._x(1.20), 9)
            second = QPoint(canvas._x(1.80), 9)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(canvas, first, delay=1)
            QTest.mouseMove(canvas, second, delay=1)
            self.app.processEvents()
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, second)

            self.assertIn(1.25, [round(value, 2) for value in scrubbed])
            self.assertNotIn(1.80, [round(value, 2) for value in scrubbed])
            self.assertIsNone(getattr(canvas, "_playhead_cut_magnet_locked_sec", None))
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_pins_shadow_at_found_boundary(self):
        canvas = TimelineCanvas()
        try:
            canvas.resize(520, canvas.height())
            canvas.frame_rate = 100.0
            canvas.pps = 100.0
            canvas.total_duration = 5.0
            canvas.playhead_sec = 1.0
            canvas._arm_shadow_playhead(1.0)
            scrubbed = []
            canvas.scrub_sec.connect(scrubbed.append)
            canvas._playhead_auto_cut_snap_sec = Mock(
                side_effect=lambda target, previous: (1.25, True) if float(target) > 1.05 else (target, False)
            )
            canvas.show()
            self.app.processEvents()

            start = QPoint(canvas._x(1.0), 9)
            end = QPoint(canvas._x(1.20), 9)
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
            QTest.mouseMove(canvas, end, delay=1)
            self.app.processEvents()
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)

            self.assertIn(1.25, [round(value, 2) for value in scrubbed])
            self.assertAlmostEqual(canvas.shadow_playhead_sec or 0.0, 1.25, places=3)
            self.assertIsNone(getattr(canvas, "_shadow_playhead_armed_sec", None))
        finally:
            canvas.close()
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_requires_strict_verification(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.settings = {"playhead_auto_cut_magnet_enabled": True}
            canvas._resolve_active_context = Mock(
                return_value={
                    "clip_file": __file__,
                    "local_sec": 1.40,
                    "clip_start": 0.0,
                    "fps": 100.0,
                }
            )
            canvas._detect_live_cut_boundary_record = Mock(
                return_value={"local_sec": 1.25, "frame": 125, "score": 31.0, "median_score": 8.0}
            )
            canvas._playhead_cut_magnet_verify_candidate = Mock(return_value=None)

            snapped, locked = canvas._playhead_auto_cut_snap_sec(1.40, 1.00)

            self.assertFalse(locked)
            self.assertAlmostEqual(snapped, 1.40, places=3)
        finally:
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_uses_strict_verified_frame(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.settings = {"playhead_auto_cut_magnet_enabled": True}
            canvas._resolve_active_context = Mock(
                return_value={
                    "clip_file": __file__,
                    "local_sec": 1.40,
                    "clip_start": 0.0,
                    "fps": 100.0,
                }
            )
            canvas._detect_live_cut_boundary_record = Mock(
                return_value={"local_sec": 1.25, "frame": 125, "score": 31.0, "median_score": 8.0}
            )
            canvas._playhead_cut_magnet_verify_candidate = Mock(
                return_value={
                    "local_sec": 1.22,
                    "frame": 122,
                    "score": 31.0,
                    "median_score": 8.0,
                    "strict_verified": True,
                }
            )

            snapped, locked = canvas._playhead_auto_cut_snap_sec(1.40, 1.00)

            self.assertTrue(locked)
            self.assertAlmostEqual(snapped, 1.22, places=3)
        finally:
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_prefers_confirmed_boundary(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.settings = {"playhead_auto_cut_magnet_enabled": True}
            canvas.boundary_times = [1.22]
            canvas._detect_live_cut_boundary_record = Mock(side_effect=AssertionError("live probe should not run"))

            snapped, locked = canvas._playhead_auto_cut_snap_sec(1.40, 1.00)

            self.assertTrue(locked)
            self.assertAlmostEqual(snapped, 1.22, places=3)
        finally:
            canvas.deleteLater()

    def test_playhead_auto_cut_magnet_ignores_origin_confirmed_boundary_on_next_drag(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.settings = {"playhead_auto_cut_magnet_enabled": True}
            canvas.boundary_times = [1.22, 1.60]
            canvas._playhead_cut_magnet_origin_sec = 1.22
            canvas._detect_live_cut_boundary_record = Mock(side_effect=AssertionError("live probe should not run"))

            snapped, locked = canvas._playhead_auto_cut_snap_sec(1.80, 1.22)

            self.assertTrue(locked)
            self.assertAlmostEqual(snapped, 1.60, places=3)
        finally:
            canvas.deleteLater()


    def test_timing_confirm_request_confirms_review_segment(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("이동한 자막")
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "yellow", "flags": ["quality_stale"]},
                    quality_signature="old",
                )
            )
            editor._segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.0,
                    "text": "이동한 자막",
                    "quality": {"confidence_label": "yellow", "flags": ["quality_stale"]},
                }
            ]

            editor._on_timeline_timing_confirm_requested([0, 0])

            data = block.userData()
            self.assertEqual(data.quality["confidence_label"], "green")
            self.assertTrue(data.quality["manual_confirmed"])
            self.assertIn("manual_confirmed", data.quality["flags"])
            self.assertNotIn("quality_stale", data.quality["flags"])
        finally:
            editor.text_edit.close()

    def test_segment_timing_edit_marks_segment_manual_confirmed_green(self):
        editor = _GapGenerateEditor()
        editor._undo_mgr = _Undo()
        editor.video_player = None
        editor.video_fps = 30.0
        editor.timeline = None
        editor.text_edit = _TimelineTextEdit()
        editor.dirty = False
        try:
            editor.text_edit.setPlainText("길이 수정")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    is_gap=False,
                    end_sec=2.0,
                    quality={"confidence_label": "yellow", "flags": ["quality_stale"]},
                    quality_signature="old",
                )
            )

            editor._on_seg_time_changed(0, 1.0, 2.4, "square_right")

            data = doc.findBlockByNumber(0).userData()
            self.assertAlmostEqual(data.end_sec, 2.4, places=3)
            self.assertEqual(data.quality["confidence_label"], "green")
            self.assertTrue(data.quality["manual_confirmed"])
            self.assertIn("manual_confirmed", data.quality["flags"])
            self.assertNotIn("quality_stale", data.quality["flags"])
            self.assertTrue(editor.dirty)
        finally:
            editor.text_edit.close()

    def test_confirm_review_segment_does_not_link_adjacent_silence_gap(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("확인 필요\n")
            doc = editor.text_edit.document()
            subtitle_block = doc.findBlockByNumber(0)
            gap_block = doc.findBlockByNumber(1)
            subtitle_block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "red", "flags": ["high_cps"]},
                )
            )
            gap_block.setUserData(make_gap_ud(2.0))
            editor._segments = [
                {"line": 0, "start": 1.0, "end": 2.0, "text": "확인 필요", "quality": {"confidence_label": "red", "flags": ["high_cps"]}},
                {"line": 1, "start": 2.0, "end": 4.0, "text": "", "is_gap": True},
            ]

            editor._confirm_review_segment(0)

            gap_data = gap_block.userData()
            self.assertEqual(gap_data.quality, {})
            self.assertFalse(hasattr(gap_data, "linked_silence_for_line"))
        finally:
            editor.text_edit.close()

    def test_confirm_review_segment_accumulates_lora_pair_from_edited_text(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("수정한 자막")
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "red", "flags": ["high_cps"]},
                    stt_candidates=[
                        {"source": "STT1", "text": "수정전 자막", "score": 0.8},
                    ],
                )
            )
            editor._segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.0,
                    "text": "수정한 자막",
                    "quality": {"confidence_label": "red", "flags": ["high_cps"]},
                    "stt_candidates": [{"source": "STT1", "text": "수정전 자막", "score": 0.8}],
                }
            ]
            calls = []

            with patch(
                "core.personalization.deferred_editor_learning.enqueue_deferred_editor_learning",
                side_effect=lambda segments, **kwargs: calls.append({"segments": segments, **kwargs}) or {"queued": True},
            ):
                editor._confirm_review_segment(0)

            self.assertEqual(len(calls), 1)
            seg = calls[0]["segments"][0]
            self.assertEqual(seg["text"], "수정한 자막")
            self.assertEqual(seg["stt_selected_source"], "STT1")
            self.assertEqual(calls[0]["trigger"], "manual_confirm_segment")
        finally:
            editor.text_edit.close()

    def test_mark_review_segment_temporary_clears_confirmed_state(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("확정 자막")
            block = editor.text_edit.document().findBlockByNumber(0)
            block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={
                        "confidence_label": "green",
                        "flags": ["manual_confirmed"],
                        "manual_confirmed": True,
                    },
                    quality_signature="old",
                )
            )
            editor._segments = [
                {
                    "line": 0,
                    "start": 1.0,
                    "end": 2.0,
                    "text": "확정 자막",
                    "quality": {"confidence_label": "green", "flags": ["manual_confirmed"], "manual_confirmed": True},
                }
            ]

            editor._mark_review_segment_temporary(0)

            data = block.userData()
            self.assertEqual(data.quality["confidence_label"], "yellow")
            self.assertFalse(data.quality["manual_confirmed"])
            self.assertTrue(data.quality["manual_temporary"])
            self.assertNotIn("manual_confirmed", data.quality["flags"])
            self.assertIn("manual_temporary", data.quality["flags"])
            self.assertTrue(editor.dirty)
            self.assertTrue(editor.finalized)
            self.assertTrue(editor.refreshed)
        finally:
            editor.text_edit.close()

    def test_temporary_review_segment_leaves_adjacent_gap_metadata_unchanged(self):
        editor = _ReviewEditor()
        try:
            editor.text_edit.setPlainText("확정 자막\n")
            doc = editor.text_edit.document()
            subtitle_block = doc.findBlockByNumber(0)
            gap_block = doc.findBlockByNumber(1)
            subtitle_block.setUserData(
                SubtitleBlockData(
                    "00",
                    1.0,
                    quality={"confidence_label": "green", "flags": ["manual_confirmed"], "manual_confirmed": True},
                )
            )
            gap_ud = make_gap_ud(2.0)
            gap_ud.quality = {
                "confidence_label": "green",
                "flags": ["manual_confirmed", "linked_silence"],
                "manual_confirmed": True,
                "linked_silence": True,
            }
            gap_block.setUserData(gap_ud)
            editor._segments = [
                {"line": 0, "start": 1.0, "end": 2.0, "text": "확정 자막", "quality": {"confidence_label": "green", "flags": ["manual_confirmed"], "manual_confirmed": True}},
                {"line": 1, "start": 2.0, "end": 4.0, "text": "", "is_gap": True},
            ]

            editor._mark_review_segment_temporary(0)

            gap_data = gap_block.userData()
            self.assertTrue(gap_data.quality["manual_confirmed"])
            self.assertTrue(gap_data.quality["linked_silence"])
            self.assertIn("linked_silence", gap_data.quality["flags"])
        finally:
            editor.text_edit.close()

    def test_delete_review_segment_routes_to_gap_conversion(self):
        editor = _ReviewEditor()
        try:
            editor._delete_review_segment(3)
            self.assertEqual(editor.deleted_lines, [3])
        finally:
            editor.text_edit.close()

    def test_delete_review_segment_accepts_first_line_zero(self):
        editor = _ReviewEditor()
        try:
            editor._delete_review_segment(0)
            self.assertEqual(editor.deleted_lines, [0])
        finally:
            editor.text_edit.close()

    def test_segment_delete_keeps_new_gap_separate_from_previous_gap(self):
        editor = _GapGenerateEditor()
        editor._undo_mgr = _Undo()
        editor.settings = {"spk1_id": "00"}
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("오오오 괜찮아?\n\n한국어 수업 중\n다음")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 6.0, is_gap=False))
            doc.findBlockByNumber(1).setUserData(make_gap_ud(7.2))
            doc.findBlockByNumber(2).setUserData(SubtitleBlockData("00", 8.6, is_gap=False))
            doc.findBlockByNumber(3).setUserData(SubtitleBlockData("00", 10.8, is_gap=False))

            editor._on_seg_to_gap(2)
            segments = editor._get_current_segments()
            gaps = [seg for seg in segments if seg.get("is_gap")]

            self.assertEqual(len(gaps), 2)
            self.assertAlmostEqual(gaps[0]["start"], 7.2)
            self.assertAlmostEqual(gaps[0]["end"], 8.6)
            self.assertAlmostEqual(gaps[1]["start"], 8.6)
            self.assertAlmostEqual(gaps[1]["end"], 10.8)
        finally:
            editor.text_edit.close()

    def test_segment_delete_preserves_overlapping_live_stt_preview_candidates(self):
        editor = _GapGenerateEditor()
        editor._undo_mgr = _Undo()
        editor.settings = {"spk1_id": "00"}
        editor.text_edit = QTextEdit()
        try:
            editor.text_edit.setPlainText("한국어 수업 중\n다음")
            doc = editor.text_edit.document()
            doc.findBlockByNumber(0).setUserData(SubtitleBlockData("00", 8.0, is_gap=False))
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("00", 12.0, is_gap=False))
            editor._live_stt_preview_segments = [
                {"start": 8.5, "end": 9.5, "text": "STT1", "stt_pending": True},
                {"start": 12.2, "end": 12.8, "text": "STT2", "stt_pending": True},
            ]
            before_preview = [dict(seg) for seg in editor._live_stt_preview_segments]

            editor._on_seg_to_gap(0)

            self.assertEqual(editor._live_stt_preview_segments, before_preview)
        finally:
            editor.text_edit.close()

    def test_canvas_preserves_confirmed_silence_gap_metadata(self):
        canvas = TimelineCanvas()
        canvas.update_segments(
            [
                {"line": 0, "start": 0.0, "end": 1.0, "text": "자막"},
                {
                    "line": 1,
                    "start": 1.0,
                    "end": 2.0,
                    "text": "",
                    "is_gap": True,
                    "quality": {
                        "confidence_label": "green",
                        "flags": ["manual_confirmed", "linked_silence"],
                        "manual_confirmed": True,
                        "linked_silence": True,
                    },
                    "linked_silence_for_line": 0,
                },
                {"line": 2, "start": 2.0, "end": 3.0, "text": "다음"},
            ],
            active_sec=0.0,
            total_dur=3.0,
        )

        self.assertEqual(len(canvas.gap_segments), 1)
        self.assertTrue(canvas.gap_segments[0]["quality"]["linked_silence"])
        self.assertEqual(canvas.gap_segments[0]["linked_silence_for_line"], 0)
        detections = subtitle_detection_segments_for_editor(
            canvas.segments,
            [],
            canvas.gap_segments,
            3.0,
        )
        self.assertEqual(
            detections,
            [{
                "start": 0.0,
                "end": 3.0,
                "kind": "idle",
                "label": "음성",
                "color": "#34C759",
                "priority": 0,
                "alpha": 92,
                "source": "subtitle_detection",
                "score": None,
                "selection_state": "",
            }],
        )

    def test_canvas_keeps_explicit_adjacent_gaps_split(self):
        canvas = TimelineCanvas()
        canvas.update_segments(
            [
                {"line": 0, "start": 0.0, "end": 7.2, "text": "오오오 괜찮아?"},
                {"line": 1, "start": 7.2, "end": 8.6, "text": "", "is_gap": True},
                {"line": 2, "start": 8.6, "end": 10.8, "text": "", "is_gap": True},
                {"line": 3, "start": 10.8, "end": 12.0, "text": "다음"},
            ],
            active_sec=0.0,
            total_dur=12.0,
        )

        self.assertEqual(
            [(round(g["start"], 1), round(g["end"], 1)) for g in canvas.gap_segments],
            [(7.2, 8.6), (8.6, 10.8)],
        )


if __name__ == "__main__":
    unittest.main()
