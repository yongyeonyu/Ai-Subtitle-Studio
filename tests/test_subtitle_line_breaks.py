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
