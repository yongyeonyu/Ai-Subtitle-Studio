# Version: 03.06.10
# Phase: PHASE2
import os
import re
import unittest
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
