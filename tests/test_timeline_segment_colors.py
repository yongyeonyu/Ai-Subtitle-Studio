# Version: 03.09.29
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
    subtitle_detection_color,
    voice_activity_segments_for_editor,
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

    def test_subtitle_detection_segments_show_llm_choice_score_and_review_state(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "선택됨",
                "stt_ensemble_llm_selected_source": "STT2",
                "stt_candidates": [{"source": "STT2", "score": 0.82}],
            },
            {
                "start": 1.0,
                "end": 2.0,
                "text": "확인",
                "quality": {"confidence_label": "red", "confidence_score": 40},
            },
        ]

        voice_segments = voice_activity_segments_for_editor(segments, [], [], 2.0)

        self.assertTrue(all(voice_segments[i]["end"] <= voice_segments[i + 1]["start"] for i in range(len(voice_segments) - 1)))
        self.assertEqual(voice_segments[0]["kind"], "llm_selected")
        self.assertEqual(voice_segments[0]["source"], "STT2")
        self.assertEqual(voice_segments[0]["label"], "STT2 LLM 82점")
        self.assertEqual(voice_segments[0]["color"], subtitle_detection_color(82))
        self.assertEqual(voice_segments[1]["kind"], "needs_selection")
        self.assertIn("선택필요", voice_segments[1]["label"])
        self.assertEqual(voice_segments[1]["color"], "#8E8E93")

    def test_subtitle_detection_score_color_steps_from_red_to_green(self):
        self.assertEqual(subtitle_detection_color(0), "#FF453A")
        self.assertEqual(subtitle_detection_color(50), "#FFCC00")
        self.assertEqual(subtitle_detection_color(100), "#34C759")

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
