# Version: 03.06.20
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.timeline.timeline_canvas import TimelineCanvas
from ui.timeline.timeline_constants import DIAMOND_Y, SEG_TOP, SPEAKER_BOT, SPEAKER_TOP
from ui.editor.editor_helpers import make_gap_ud
from ui.editor.editor_timeline_video import EditorTimelineVideoMixin
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


if __name__ == "__main__":
    unittest.main()
