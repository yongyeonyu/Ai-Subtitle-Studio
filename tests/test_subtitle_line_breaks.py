# Version: 03.06.10
# Phase: PHASE2
import os
import re
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from ui.editor.editor_segments import EditorSegmentsMixin
from ui.editor.subtitle_text_edit import SubtitleBlockData


class _LineBreakEditor(EditorSegmentsMixin):
    _JUNK_TS_RE = re.compile(r"[\[{(<\[【（《]\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*[\]})>\]】）》]\s*")
    _JUNK_NO_BRACKET_3PART = re.compile(r"(?<!\S)\d{1,3}[:\.]\d{2}[:\.]\d{2,3}(?!\S)")
    _JUNK_NO_BRACKET_3PART_END = re.compile(r"\d{1,3}[:\.]\d{2}[:\.]\d{2,3}\s*$")
    _JUNK_START_RE = re.compile(r"^\s*\d{1,3}[:\.]\d{2}(?:[:\.]\d+)?\s+")


class SubtitleLineBreakTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _editor(self):
        editor = _LineBreakEditor()
        editor.settings = {"spk1_id": "00", "spk2_id": "01"}
        editor.text_edit = QTextEdit()
        editor.text_edit.update_margins = Mock()
        editor._segment_queue = []
        editor._is_initial_load = False
        editor._sync_lock = False
        editor._schedule_timeline = Mock()
        editor._refresh_video_subtitle_context = Mock()
        editor.video_player = type("Video", (), {"total_time": 0.0, "seek": Mock()})()
        return editor

    def test_current_segments_normalize_soft_line_break_for_save(self):
        editor = self._editor()
        try:
            editor.text_edit.setPlainText("첫 줄\u2028둘째 줄")
            block = editor.text_edit.document().begin()
            block.setUserData(SubtitleBlockData("00", 1.0))

            segs = editor._get_current_segments()

            self.assertEqual(segs[0]["text"], "첫 줄\n둘째 줄")
        finally:
            editor.text_edit.close()

    def test_append_segments_restores_soft_line_break_from_project_text(self):
        editor = self._editor()
        try:
            editor._segment_queue = [
                {"start": 1.0, "end": 3.0, "text": "첫 줄\u2028둘째 줄", "speaker_list": ["00"]},
            ]

            editor._flush_queue()

            block = editor.text_edit.document().begin()
            self.assertEqual(block.text(), "첫 줄\u2028둘째 줄")
            segs = editor._get_current_segments()
            self.assertEqual(segs[0]["text"], "첫 줄\n둘째 줄")
        finally:
            editor.text_edit.close()

    def test_flush_queue_keeps_single_speaker_hyphen_multiline_in_one_segment(self):
        editor = self._editor()
        try:
            editor._segment_queue = [
                {"start": 1.0, "end": 3.0, "text": "- 안녕하세요\n- 반갑습니다", "speaker_list": ["00"]},
            ]

            editor._flush_queue()

            first_block = editor.text_edit.document().begin()
            self.assertEqual(first_block.text(), "- 안녕하세요\u2028- 반갑습니다")
            segs = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual(len(segs), 1)
            self.assertEqual(segs[0]["text"], "- 안녕하세요\n- 반갑습니다")
        finally:
            editor.text_edit.close()

    def test_bulk_load_keeps_true_multi_speaker_hyphen_multiline_as_grouped_blocks(self):
        editor = self._editor()
        try:
            loaded = editor._bulk_load_segments_to_document(
                [
                    {"start": 1.0, "end": 3.0, "text": "- 안녕하세요\n- 반갑습니다", "speaker_list": ["00", "01"]},
                ]
            )

            self.assertEqual(len(loaded or []), 1)
            first = editor.text_edit.document().findBlockByNumber(0)
            second = editor.text_edit.document().findBlockByNumber(1)
            self.assertEqual(first.text(), "- 안녕하세요")
            self.assertEqual(second.text(), "- 반갑습니다")
            segs = editor._get_current_segments()
            self.assertEqual(len(segs), 1)
            self.assertEqual(segs[0]["text"], "- 안녕하세요\n- 반갑습니다")
            self.assertEqual(segs[0]["speaker_list"], ["00", "01"])
            self.assertEqual(segs[0]["speaker"], "00")
        finally:
            editor.text_edit.close()

    def test_reload_sync_repairs_corrupted_block_metadata_from_canonical_snapshot(self):
        editor = self._editor()
        try:
            loaded = editor._bulk_load_segments_to_document(
                [
                    {"start": 1.0, "end": 3.0, "text": "- 안녕하세요\n- 반갑습니다", "speaker_list": ["00", "01"]},
                    {"start": 4.0, "end": 5.0, "text": "다음 줄", "speaker_list": ["00"]},
                ]
            )

            self.assertEqual(sorted(getattr(editor.text_edit, "_canonical_timestamp_block_meta_snapshot", {}).keys()), [0, 1, 2])
            editor._rebuild_subtitle_memory_cache(loaded)
            doc = editor.text_edit.document()
            doc.findBlockByNumber(1).setUserData(SubtitleBlockData("01", 8.8, False, end_sec=9.4))
            editor.text_edit._timestamp_block_meta_snapshot = {
                0: {"spk_id": "00", "start_sec": 1.0, "end_sec": 3.0, "is_gap": False},
                1: {"spk_id": "01", "start_sec": 8.8, "end_sec": 9.4, "is_gap": False},
                2: {"spk_id": "00", "start_sec": 4.0, "end_sec": 5.0, "is_gap": False},
            }

            corrupted = editor._get_current_segments(force_rebuild=True)
            self.assertNotEqual(
                [(round(seg["start"], 1), round(seg["end"], 1), seg["text"]) for seg in corrupted],
                [(1.0, 3.0, "- 안녕하세요\n- 반갑습니다"), (4.0, 5.0, "다음 줄")],
            )

            editor._enforce_editor_segment_sync_after_reload(loaded)

            repaired = editor._get_current_segments(force_rebuild=True)
            self.assertEqual(
                [(round(seg["start"], 1), round(seg["end"], 1), seg["text"]) for seg in repaired],
                [(1.0, 3.0, "- 안녕하세요\n- 반갑습니다"), (4.0, 5.0, "다음 줄")],
            )
        finally:
            editor.text_edit.close()

    def test_reload_sync_pushes_editor_canonical_rows_back_to_timeline_canvas(self):
        class _Timeline:
            def __init__(self):
                self.canvas = type(
                    "Canvas",
                    (),
                    {
                        "segments": [
                            {"start": 1.0, "end": 2.0, "text": "예전 자막"},
                            {"start": 2.1, "end": 2.4, "text": "-", "stt_pending": True, "stt_preview_source": "STT2"},
                        ]
                    },
                )()
                self.updated = None

            def update_segments(self, segs, active_sec, total_dur):
                self.updated = (list(segs or []), active_sec, total_dur)
                self.canvas.segments = list(segs or [])

            def update(self):
                pass

        editor = self._editor()
        try:
            editor.timeline = _Timeline()
            expected = [
                {"start": 1.0, "end": 2.0, "text": "메뇨"},
                {"start": 2.0, "end": 3.0, "text": "용유커피"},
            ]

            editor._enforce_timeline_segment_sync_after_reload(expected)

            self.assertIsNotNone(editor.timeline.updated)
            self.assertEqual([seg["text"] for seg in editor.timeline.canvas.segments], ["메뇨", "용유커피"])
            self.assertFalse(any(seg.get("stt_pending") for seg in editor.timeline.canvas.segments))
        finally:
            editor.text_edit.close()

    def test_flush_queue_sorts_out_of_order_generated_segments_before_insert(self):
        editor = self._editor()
        try:
            editor._segment_queue = [
                {"start": 23.2, "end": 23.8, "text": "마지막", "speaker_list": ["00"]},
                {"start": 0.9, "end": 1.5, "text": "처음", "speaker_list": ["00"]},
                {"start": 2.0, "end": 2.7, "text": "둘째", "speaker_list": ["00"]},
            ]

            with patch(
                "core.engine.subtitle_accuracy_pipeline.repair_subtitle_context_consistency",
                return_value=(list(editor._segment_queue), {"applied": False}),
            ):
                editor._flush_queue()

            segs = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual([seg["text"] for seg in segs], ["처음", "둘째", "마지막"])
            self.assertTrue(segs[0]["start"] < segs[1]["start"] < segs[2]["start"])
        finally:
            editor.text_edit.close()

    def test_flush_queue_keeps_finalized_segment_start_and_end_without_gap_repull(self):
        editor = self._editor()
        try:
            editor.text_edit.setPlainText("이전 자막\n")
            doc = editor.text_edit.document()
            first = doc.findBlockByNumber(0)
            gap = doc.findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 0.0, end_sec=1.0))
            gap.setUserData(SubtitleBlockData("00", 1.2, is_gap=True))
            editor.video_player.total_time = 9.0
            editor._segment_queue = [
                {
                    "start": 2.0,
                    "end": 2.5,
                    "text": "확정 자막",
                    "speaker_list": ["00"],
                    "_final_gap_settings_applied": True,
                },
            ]

            with patch("core.engine.subtitle_accuracy_pipeline.repair_subtitle_context_consistency") as repair:
                editor._flush_queue()

            repair.assert_not_called()
            segs = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual(segs[-1]["text"], "확정 자막")
            self.assertAlmostEqual(segs[-1]["start"], 2.0)
            self.assertAlmostEqual(segs[-1]["end"], 2.5)
        finally:
            editor.text_edit.close()

    def test_flush_queue_drops_repeat_previous_duplicate_at_generation_seam(self):
        editor = self._editor()
        try:
            editor.text_edit.setPlainText("호핑은 없네?\n")
            doc = editor.text_edit.document()
            first = doc.findBlockByNumber(0)
            gap = doc.findBlockByNumber(1)
            first.setUserData(SubtitleBlockData("00", 1.0, end_sec=2.0))
            gap.setUserData(SubtitleBlockData("00", 2.2, is_gap=True))
            editor.video_player.total_time = 9.0
            editor._segment_queue = [
                {
                    "start": 2.0,
                    "end": 2.6,
                    "text": "호핑은 없네?",
                    "speaker_list": ["00"],
                    "_final_gap_settings_applied": True,
                },
                {
                    "start": 2.7,
                    "end": 3.2,
                    "text": "해핑",
                    "speaker_list": ["00"],
                    "_final_gap_settings_applied": True,
                },
            ]

            editor._flush_queue()

            segs = [seg for seg in editor._get_current_segments() if not seg.get("is_gap")]
            self.assertEqual([seg["text"] for seg in segs], ["호핑은 없네?", "해핑"])
        finally:
            editor.text_edit.close()


if __name__ == "__main__":
    unittest.main()
