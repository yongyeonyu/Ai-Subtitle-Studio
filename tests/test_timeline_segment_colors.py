# Version: 03.02.07
# Phase: PHASE2
import unittest

from ui.timeline.timeline_paint import SEGMENT_TEXT_KIND_STYLES, segment_text_kind
from ui.timeline.timeline_analysis import editor_analysis_markers


class TimelineSegmentColorTests(unittest.TestCase):
    def test_voice_and_silence_labels_use_distinct_kinds(self):
        self.assertEqual(segment_text_kind("음성"), "speech")
        self.assertEqual(segment_text_kind(" 무 음 "), "silence")
        self.assertEqual(segment_text_kind("일반 자막"), "")

    def test_voice_and_silence_styles_are_visually_distinct(self):
        speech = SEGMENT_TEXT_KIND_STYLES["speech"]
        silence = SEGMENT_TEXT_KIND_STYLES["silence"]
        self.assertNotEqual(speech["fill"], silence["fill"])
        self.assertNotEqual(speech["border"], silence["border"])
        self.assertNotEqual(speech["text"], silence["text"])

    def test_analysis_voice_and_silence_markers_use_distinct_colors(self):
        markers = editor_analysis_markers(
            [],
            [{"start": 0.0, "end": 1.0}],
            [{"start": 1.0, "end": 2.0}],
            2.0,
        )
        colors = {marker["label"]: marker["color"] for marker in markers}
        self.assertEqual(colors["음성"], "#34C759")
        self.assertEqual(colors["무음"], "#FF9500")


if __name__ == "__main__":
    unittest.main()
