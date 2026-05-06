import unittest

from core.personalization.lora_rule_learning import analyze_truth_table_rows
from core.personalization.subtitle_style_profile import build_subtitle_style_profile
from core.personalization.text_lora_dataset import build_text_lora_dataset


class SubtitleStyleProfileTests(unittest.TestCase):
    def test_style_profile_extracts_line_tone_parenthetical_wave_brand_and_timing(self):
        profile = build_subtitle_style_profile(
            raw_text="BMW X5는 좋네요~\n(자막 설명)",
            speech_text="BMW X5는 좋네요~",
            input_text="bmw x5는 좋네요",
            start_sec=10.0,
            end_sec=11.5,
            previous_end_sec=9.8,
            next_start_sec=11.7,
        )

        self.assertEqual(profile["line_break"]["line_count"], 1)
        self.assertEqual(profile["tone"]["label"], "casual_polite")
        self.assertTrue(profile["parenthetical_policy"]["removed_from_speech"])
        self.assertTrue(profile["wave_marks"]["uses_wave"])
        self.assertIn("BMW X5", profile["brand_name_policy"]["tokens"])
        self.assertEqual(profile["timing_padding"]["previous_gap_sec"], 0.2)
        self.assertEqual(profile["timing_padding"]["next_gap_sec"], 0.2)

    def test_text_lora_dataset_embeds_style_profile_for_runtime_retrieval(self):
        payload = build_text_lora_dataset(
            current_segments=[
                {
                    "start": 1.0,
                    "end": 2.8,
                    "text": "BMW X5 좋아요~\n진짜예요.",
                    "stt_selected_source": "STT1",
                    "stt_candidates": [
                        {"source": "STT1", "text": "bmw x5 좋아요 진짜에요"},
                    ],
                }
            ],
            current_project_path="/tmp/current_project.json",
            project_paths=[],
        )

        self.assertEqual(payload["stats"]["project_segment_pairs"], 1)
        row = payload["items"][0]
        style = row["meta"]["style_profile"]
        self.assertTrue(style["line_break"]["prefers_multiline"])
        self.assertTrue(style["wave_marks"]["uses_wave"])
        self.assertIn("BMW X5", style["brand_name_policy"]["tokens"])
        self.assertEqual(payload["context_items"][0]["subtitle_style_profile"], style)

    def test_truth_rule_learning_summarizes_style_profile_signals(self):
        profile = build_subtitle_style_profile(
            raw_text="EXAONE 모델 좋아요~",
            speech_text="EXAONE 모델 좋아요~",
            start_sec=1.0,
            end_sec=2.0,
        )

        result = analyze_truth_table_rows(
            [
                {
                    "speech_training_text": "EXAONE 모델 좋아요~",
                    "raw_ground_truth_text": "EXAONE 모델 좋아요~",
                    "line_break_pattern": "12",
                    "punctuation_pattern": "~",
                    "duration_sec": 1.0,
                    "char_count": 12,
                    "cps": 12.0,
                    "style_profile": profile,
                }
            ]
        )

        style_summary = result["summary"]["style_profile"]
        self.assertEqual(style_summary["top_tone_labels"][0]["label"], "casual_polite")
        self.assertEqual(style_summary["wave_mark_ratio"], 1.0)
        self.assertEqual(style_summary["brand_name_tokens"][0]["token"], "EXAONE")


if __name__ == "__main__":
    unittest.main()
