# Version: 03.06.10
# Phase: PHASE2
import os
import re
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QTextEdit

from core.audio.diarize import assign_speakers_to_segments, merge_speaker_overlap_subtitles
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

    def test_merge_speaker_overlap_subtitles_formats_netflix_style_lines(self):
        speaker_map = [
            {"start": 0.0, "end": 1.2, "speaker": "SPEAKER_00"},
            {"start": 1.2, "end": 2.4, "speaker": "SPEAKER_01"},
        ]
        segments = assign_speakers_to_segments(
            [
                {"start": 0.0, "end": 1.45, "text": "안녕하세요 소설가유모씨입니다"},
                {"start": 1.15, "end": 2.0, "text": "안녕하세요"},
            ],
            speaker_map,
        )

        merged = merge_speaker_overlap_subtitles(segments)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "- 안녕하세요 소설가유모씨입니다\n- 안녕하세요")
        self.assertEqual(merged[0]["speaker_list"], ["00", "01"])

    def test_assign_speakers_to_segments_propagates_word_level_speakers(self):
        speaker_map = [
            {"start": 0.0, "end": 1.0, "speaker": "SPEAKER_00"},
            {"start": 1.0, "end": 2.0, "speaker": "SPEAKER_01"},
        ]

        rows = assign_speakers_to_segments(
            [
                {
                    "start": 0.0,
                    "end": 2.0,
                    "text": "안녕하세요 반갑습니다",
                    "words": [
                        {"word": "안녕하세요", "start": 0.1, "end": 0.7},
                        {"word": "반갑습니다", "start": 1.1, "end": 1.7},
                    ],
                }
            ],
            speaker_map,
        )

        self.assertEqual(rows[0]["speaker"], "00")
        self.assertEqual(rows[0]["speaker_list"], ["00", "01"])
        self.assertEqual([word["speaker"] for word in rows[0]["words"]], ["00", "01"])


if __name__ == "__main__":
    unittest.main()
