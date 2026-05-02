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
from ui.timeline.timeline_constants import (
    ANALYSIS_TOP,
    DIAMOND_Y,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_TOP,
    STT2_TOP,
    VOICE_ACTIVITY_TOP,
)
from ui.timeline.timeline_paint import (
    stt_candidate_selected,
    stt_candidate_selected_by_llm,
    stt_candidate_selection_state,
    stt_candidate_unselected,
)
from ui.editor.editor_helpers import make_gap_ud
from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
from ui.editor.editor_video_controls import EditorVideoControlsMixin
from ui.editor.subtitle_text_edit import SubtitleBlockData


class _Undo:
    def push_immediate(self):
        pass


class _GapGenerateEditor(EditorTimelineVideoMixin):
    settings = {"spk1_id": "00"}

    def _multiclip_active_offset(self) -> float:
        return 0.0

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

    def test_diamond_hit_has_small_margin_only(self):
        canvas = self._canvas()

        self.assertEqual(canvas._diamond_index_at(209, DIAMOND_Y, margin=5), 0)
        self.assertIsNone(canvas._diamond_index_at(211, DIAMOND_Y, margin=5))

    def test_speaker_menu_hit_target_is_center_label_only(self):
        canvas = self._canvas()
        canvas.segments[0]["speaker"] = "00"
        y = (SPEAKER_TOP + SPEAKER_BOT) // 2

        self.assertIs(canvas._speaker_lane_seg_at(canvas._x(1.5), y), canvas.segments[0])
        self.assertIsNone(canvas._speaker_lane_seg_at(canvas._x(1.05), y))

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

    def test_delete_review_segment_routes_to_gap_conversion(self):
        editor = _ReviewEditor()
        try:
            editor._delete_review_segment(3)
            self.assertEqual(editor.deleted_lines, [3])
        finally:
            editor.text_edit.close()


if __name__ == "__main__":
    unittest.main()
