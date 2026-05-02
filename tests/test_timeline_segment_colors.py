# Version: 03.02.07
# Phase: PHASE2
import unittest
from types import SimpleNamespace

from ui.timeline.timeline_paint import (
    SEGMENT_TEXT_KIND_STYLES,
    segment_text_kind,
    subtitle_segment_visual_style,
)
from ui.timeline.timeline_analysis import (
    MAJOR_SEGMENT_COLORS,
    editor_analysis_markers,
    roughcut_major_color,
    roughcut_markers,
)


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

    def test_subtitle_segment_visual_style_is_zoom_stable_for_quality_colors(self):
        seg = {
            "start": 0.0,
            "end": 1.0,
            "text": "일반 자막",
            "quality": {"confidence_label": "red"},
        }

        compact_style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")
        expanded_style = subtitle_segment_visual_style(seg, active=False, hover=False, quality_filter="all")

        self.assertEqual(compact_style["fill"], expanded_style["fill"])
        self.assertEqual(compact_style["border"], expanded_style["border"])
        self.assertEqual(compact_style["fill"], "#4A1F24")
        self.assertEqual(compact_style["border"], "#FF453A")

    def test_subtitle_segment_visual_style_keeps_text_kind_over_zoom(self):
        seg = {"start": 0.0, "end": 1.0, "text": "음성"}

        style = subtitle_segment_visual_style(seg, active=True, hover=True, quality_filter="all")

        self.assertEqual(style["fill"], SEGMENT_TEXT_KIND_STYLES["speech"]["fill"])
        self.assertEqual(style["border"], SEGMENT_TEXT_KIND_STYLES["speech"]["border"])

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

    def test_roughcut_major_palette_has_distinct_a_to_z_colors(self):
        colors = [roughcut_major_color(chr(65 + i), i) for i in range(26)]

        self.assertEqual(len(MAJOR_SEGMENT_COLORS), 26)
        self.assertEqual(len(set(colors)), 26)
        self.assertEqual(colors, list(MAJOR_SEGMENT_COLORS))

    def test_roughcut_cut_safety_labels_and_colors_are_distinct(self):
        result = SimpleNamespace(
            edit_decisions=[
                SimpleNamespace(source_start=0.0, source_end=1.0, action="keep", safety="ideal"),
                SimpleNamespace(source_start=1.0, source_end=2.0, action="keep", safety="acceptable"),
                SimpleNamespace(source_start=2.0, source_end=3.0, action="keep", safety="risky"),
            ]
        )

        markers = roughcut_markers(result)

        self.assertEqual([marker["label"] for marker in markers], ["정상", "주의", "위험"])
        self.assertEqual([marker["color"] for marker in markers], ["#34C759", "#FFCC00", "#FF453A"])


if __name__ == "__main__":
    unittest.main()
