# Version: 03.09.16
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.timeline.timeline_constants import (
    CANVAS_H,
    FOCUS_BORDER_COLOR,
    FOCUS_BORDER_WIDTH,
    DIAMOND_Y,
    RULER_H,
    SCORE_BOT,
    SCORE_H,
    SCORE_TOP,
    SEG_BOT,
    SEG_TOP,
    SPEAKER_BOT,
    SPEAKER_TOP,
    STT1_BOT,
    STT1_TOP,
    STT2_BOT,
    STT2_TOP,
    STT_PREVIEW_LANE_H,
    STT_PREVIEW_VERTICAL_INSET,
    SUBTITLE_BOT,
    SUBTITLE_LANE_H,
    SUBTITLE_TOP,
    VOICE_ACTIVITY_BOT,
    VOICE_ACTIVITY_TOP,
    WAVE_H,
)


class TimelineLayoutConstantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_canvas_height_allows_stt1_stt2_preview_lanes(self):
        self.assertEqual(CANVAS_H, 324)
        self.assertGreaterEqual(SEG_TOP - (RULER_H + WAVE_H), 34)
        self.assertEqual(SEG_BOT, CANVAS_H)
        self.assertGreater(SUBTITLE_TOP, RULER_H + WAVE_H)
        self.assertLess(SCORE_TOP, SUBTITLE_TOP)
        self.assertEqual(SCORE_BOT, SUBTITLE_TOP - 2)
        self.assertEqual(SCORE_H, SCORE_BOT - SCORE_TOP)
        self.assertEqual(DIAMOND_Y, SCORE_TOP + (SCORE_H // 2))
        self.assertGreater(STT1_TOP, SUBTITLE_TOP)
        self.assertEqual(STT1_BOT, STT2_TOP)
        self.assertGreater(STT2_TOP, STT1_TOP)
        self.assertLess(STT2_BOT, SPEAKER_BOT)
        self.assertEqual(SUBTITLE_BOT - SUBTITLE_TOP, SUBTITLE_LANE_H)
        self.assertEqual(STT1_BOT - STT1_TOP, STT_PREVIEW_LANE_H)
        self.assertEqual(STT2_BOT - STT2_TOP, STT_PREVIEW_LANE_H)
        self.assertGreater(STT_PREVIEW_LANE_H, SUBTITLE_LANE_H)
        self.assertEqual(SPEAKER_BOT - SPEAKER_TOP, 24)
        self.assertEqual(VOICE_ACTIVITY_BOT - VOICE_ACTIVITY_TOP, 0)
        self.assertEqual(STT_PREVIEW_VERTICAL_INSET, 2)
        self.assertEqual(SPEAKER_BOT, SEG_BOT)

    def test_focus_border_style_is_shared_with_editor_panel(self):
        from ui.editor.editor_widget import EditorWidget

        editor = EditorWidget(
            "sample.m4a",
            [{"start": 0.0, "end": 1.0, "text": "테스트", "speaker": "00"}],
        )
        try:
            editor.show()
            self.app.processEvents()
            editor.text_edit.setFocus()
            self.app.processEvents()
            editor._sync_editor_focus_border()

            border = editor._editor_focus_border
            style = border.styleSheet()
            self.assertIn(f"border: {FOCUS_BORDER_WIDTH}px solid {FOCUS_BORDER_COLOR}", style)
            self.assertTrue(border.isVisible())
        finally:
            editor.close()


if __name__ == "__main__":
    unittest.main()
