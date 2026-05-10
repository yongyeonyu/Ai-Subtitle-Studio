# Version: 03.09.26
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_widget import TimelineWidget
from ui.timeline.timeline_constants import (
    ANALYSIS_TOP,
    DIAMOND_Y,
    RULER_H,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_TOP,
    STT2_TOP,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
)
from ui.timeline.timeline_paint import (
    build_stt_selection_index,
    stt_candidate_selected,
    stt_candidate_selected_by_llm,
    stt_candidate_selection_state,
    stt_candidate_unselected,
)
from ui.timeline.timeline_analysis import subtitle_detection_segments_for_editor
from ui.editor.editor_helpers import make_gap_ud
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_scan_cut_core import EditorScanCutCoreMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.editor_video_controls import EditorVideoControlsMixin
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

        for y in (VOICE_ACTIVITY_TOP + 4, ANALYSIS_TOP + 4):
            QTest.mouseClick(
                canvas,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                QPoint(canvas._x(1.5), y),
            )

        self.assertEqual(scrubbed, [])
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
        self.assertEqual(clicked, [(0, 1.0)])

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
            self.assertEqual(editor._live_stt_preview_segments, [])
            self.assertEqual(editor.timeline.canvas.voice_activity_segments, [])
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

    def test_gap_generate_trims_detection_only_inside_selected_gap_range(self):
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

            editor._on_gap_generate_requested(1.0, 5.0, 3.0, "from")

            self.assertEqual(editor.text_edit.toPlainText().splitlines(), ["앞", "", "새자막", "뒤"])
            self.assertAlmostEqual(doc.findBlockByNumber(0).userData().start_sec, 0.0)
            self.assertAlmostEqual(doc.findBlockByNumber(3).userData().start_sec, 5.0)
            self.assertEqual(
                [(round(seg["start"], 1), round(seg["end"], 1)) for seg in editor._live_stt_preview_segments],
                [(0.2, 0.8), (1.0, 3.0), (5.2, 5.8)],
            )
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
            self.assertEqual(
                [(round(seg["start"], 1), round(seg["end"], 1)) for seg in editor._live_stt_preview_segments],
                [(16.0, 20.0)],
            )
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
            QTest.mouseMove(canvas, QPoint(canvas._x(12.0), RULER_H + WAVE_H + 8))
            self.app.processEvents()

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

    def test_scan_boundary_delete_removes_requested_boundary_from_editor_state(self):
        class DummyTimeline:
            def __init__(self):
                self.scan_boundary_times = None
                self.canvas = type("Canvas", (), {"_hover_scan_boundary_idx": 0, "update": lambda _self: None})()

            def set_scan_boundary_times(self, times):
                self.scan_boundary_times = list(times or [])

        class DummyEditor(EditorScanCutCoreMixin):
            def __init__(self):
                self.timeline = DummyTimeline()
                self.video_player = None
                self.dirty = False
                self._auto_cut_boundary_scan_lines = [
                    {"timeline_sec": 5.0, "status": "provisional"},
                    {"timeline_sec": 10.0, "status": "provisional"},
                ]

            def _snap_to_frame(self, sec):
                return round(float(sec), 3)

            def _mark_dirty(self):
                self.dirty = True

        editor = DummyEditor()

        editor._on_provisional_cut_boundary_delete_requested(0, 5.0)

        self.assertEqual([row["timeline_sec"] for row in editor._auto_cut_boundary_scan_lines], [10.0])
        self.assertEqual([row["timeline_sec"] for row in editor.timeline.scan_boundary_times], [10.0])
        self.assertTrue(editor.dirty)

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
        self.assertEqual(captured["frame_count"], 900)
        self.assertEqual(captured["scan_profile"]["level"], "medium")
        self.assertEqual(result["frame"], 205)
        self.assertAlmostEqual(result["sec"], 205.0 / 30.0, places=3)

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

    def test_set_active_repaints_only_segment_region(self):
        canvas = self._canvas()
        canvas.resize(500, canvas.height())

        with patch.object(canvas, "update") as update:
            canvas.set_active(1.0)

        update.assert_called_once()
        args = update.call_args.args
        self.assertEqual(len(args), 1)
        rect = args[0]
        self.assertLess(rect.width(), canvas.width())
        self.assertGreaterEqual(rect.left(), 0)
        self.assertLessEqual(rect.right(), canvas.width())

    def test_active_segment_uses_line_not_nearby_start_time(self):
        canvas = self._canvas()
        canvas.segments = [
            {"start": 1.00, "end": 1.30, "text": "앞", "line": 0},
            {"start": 1.20, "end": 1.60, "text": "뒤", "line": 1},
        ]

        canvas.set_active(1.0)

        self.assertTrue(canvas._is_active_segment(canvas.segments[0]))
        self.assertFalse(canvas._is_active_segment(canvas.segments[1]))

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

    def test_new_subtitle_placeholder_clears_when_inline_edit_starts(self):
        canvas = self._canvas()
        canvas.segments = [
            {"start": 1.0, "end": 2.0, "text": "새자막", "line": 0},
        ]
        emitted = []
        canvas.sig_inline_text_changed.connect(
            lambda line, text: emitted.append((line, text, getattr(canvas, "_inline_commit_in_progress", False)))
        )

        canvas.start_inline_edit(0, 1.0)

        self.assertTrue(canvas._edit_active)
        self.assertEqual(canvas._edit_text, "")
        self.assertEqual(canvas._edit_orig, "")
        self.assertEqual(canvas._edit_cursor, 0)
        self.assertEqual(canvas.segments[0]["text"], "")
        self.assertEqual(emitted, [(0, "", True)])

    def test_review_segment_right_click_emits_review_menu_request(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.segments[0]["quality"] = {"confidence_label": "red", "flags": ["high_cps"]}
        emitted = []
        canvas.seg_right_clicked.connect(lambda start, _pos: emitted.append(start))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), SEG_TOP + 10),
        )

        self.assertEqual(emitted, [1.0])
        self.assertFalse(canvas._edit_active)

    def test_confirmed_segment_right_click_emits_review_menu_request(self):
        canvas = self._canvas()
        canvas.resize(420, canvas.height())
        canvas.segments[0]["quality"] = {
            "confidence_label": "green",
            "manual_confirmed": True,
            "flags": ["manual_confirmed"],
        }
        emitted = []
        canvas.seg_right_clicked.connect(lambda start, _pos: emitted.append(start))

        QTest.mouseClick(
            canvas,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(canvas._x(1.5), SEG_TOP + 10),
        )

        self.assertEqual(emitted, [1.0])
        self.assertFalse(canvas._edit_active)

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

    def test_manual_stt_candidate_selection_removes_selected_preview_highlight(self):
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

            def update_segments(self, segments, active_sec=None, total_dur=0.0):
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
                ["STT2"],
            )
            self.assertFalse(any(
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

    def test_yellow_segment_timing_confirmation_is_required_until_confirmed(self):
        canvas = TimelineCanvas()
        try:
            seg = {
                "line": 0,
                "start": 1.0,
                "end": 2.0,
                "text": "확인 필요",
                "quality": {"confidence_label": "yellow", "flags": []},
            }
            self.assertTrue(canvas._segment_timing_confirmation_needed(seg))

            seg["quality"]["manual_confirmed"] = True
            seg["quality"]["flags"] = ["manual_confirmed"]
            self.assertFalse(canvas._segment_timing_confirmation_needed(seg))
        finally:
            canvas.deleteLater()

    def test_yellow_diamond_drag_emits_both_adjacent_segment_updates(self):
        canvas = self._canvas()
        try:
            canvas.frame_rate = 100.0
            canvas.total_duration = 4.0
            for seg in canvas.segments:
                seg["quality"] = {"confidence_label": "yellow", "flags": []}
            emitted = []
            confirmed = []
            canvas.seg_time_changed.connect(
                lambda line, start, end, edge: emitted.append((line, start, end, edge))
            )
            canvas.seg_timing_confirm_requested.connect(lambda lines: confirmed.extend(lines))

            canvas._drag_edge = "diamond"
            canvas._drag_diamond_pair = (0, 1)
            canvas._drag_diamond_orig = 2.0
            canvas._drag_snap_candidates_cache = [{"time": 2.2, "kind": "test"}]
            with patch.object(canvas, "_ask_review_timing_confirmation", return_value="confirm"):
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
            self.assertEqual(confirmed, [0, 1])
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

    def test_confirm_review_segment_confirms_adjacent_silence_gap(self):
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
            self.assertTrue(gap_data.quality["manual_confirmed"])
            self.assertTrue(gap_data.quality["linked_silence"])
            self.assertIn("linked_silence", gap_data.quality["flags"])
            self.assertEqual(getattr(gap_data, "linked_silence_for_line"), 0)
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

    def test_temporary_review_segment_unlinks_adjacent_silence_gap(self):
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
            self.assertFalse(gap_data.quality["manual_confirmed"])
            self.assertFalse(gap_data.quality["linked_silence"])
            self.assertNotIn("linked_silence", gap_data.quality["flags"])
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

    def test_segment_delete_removes_overlapping_live_detection_candidates(self):
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

            editor._on_seg_to_gap(0)

            self.assertEqual(len(editor._live_stt_preview_segments), 1)
            self.assertAlmostEqual(editor._live_stt_preview_segments[0]["start"], 12.2)
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
        self.assertTrue(any(item["kind"] == "linked_silence" for item in detections))

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
