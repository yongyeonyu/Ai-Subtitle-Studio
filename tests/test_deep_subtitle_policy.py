import unittest

from core.personalization.deep_subtitle_policy import (
    adjust_subtitle_timing,
    predict_segment_settings,
    rerank_subtitle_candidates,
    score_cut_boundary,
    select_stt_candidate,
    smooth_subtitle_sequence,
)


class DeepSubtitlePolicyTests(unittest.TestCase):
    def test_setting_policy_predicts_segment_values_from_lora_profile(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "split_length_threshold": 20,
            "sub_max_cps": 12,
        }
        profile = {
            "top_score": 91.0,
            "applied_settings": {"split_length_threshold": 14, "sub_max_cps": 16},
            "examples": [{"text": "BMW X5 고속도로 주행 소음", "cps": 15.5}],
        }

        predicted, metadata = predict_segment_settings(
            {"text": "BMW X5 고속도로 풍절음 확인"},
            settings,
            profile,
        )

        self.assertEqual(predicted["split_length_threshold"], 14)
        self.assertEqual(predicted["sub_max_cps"], 16)
        self.assertIn("split_length_threshold", metadata["applied_keys"])

    def test_setting_policy_predicts_line_count_and_llm_gate_per_segment(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "subtitle_target_line_count_auto_enabled": True,
            "llm_confidence_gate_min_lora_score": 82.0,
        }
        profile = {
            "top_score": 94.0,
            "examples": [
                {
                    "text": "BMW X5 고속도로\n주행 소음",
                    "style_profile": {"line_break": {"line_count": 2}},
                }
            ],
        }

        predicted, metadata = predict_segment_settings(
            {"text": "BMW X5 고속도로 주행 소음"},
            settings,
            profile,
        )

        self.assertEqual(predicted["subtitle_target_line_count"], 2)
        self.assertEqual(predicted["llm_confidence_gate_min_lora_score"], 78.0)
        self.assertIn("subtitle_target_line_count", metadata["applied_keys"])

    def test_stt_selector_prefers_profile_similar_candidate_when_confident(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "deep_stt_candidate_min_score": 0.1,
            "deep_stt_candidate_min_margin": 0.01,
            "split_length_threshold": 16,
        }
        profile = {
            "top_score": 95.0,
            "examples": [{"text": "BMW X5 고속도로 주행 소음"}],
        }
        segment = {
            "text": "비엠더블유 엑스파이브 소음",
            "stt_candidates": [
                {"source": "STT1", "score": 0.61, "text": "비엠더블유 엑스파이브 소음"},
                {"source": "STT2", "score": 0.6, "text": "BMW X5 고속도로 주행 소음"},
            ],
        }

        decision = select_stt_candidate(segment, settings, profile)

        self.assertIsNotNone(decision)
        self.assertEqual(decision["source"], "STT2")
        self.assertEqual(decision["label"], "B")
        self.assertEqual(decision["_deep_candidate_selector_policy"]["task"], "stt_candidate_competition")

    def test_stt_selector_competes_vad_and_recheck_candidate_sources(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "deep_stt_candidate_min_score": 0.1,
            "deep_stt_candidate_min_margin": 0.01,
            "split_length_threshold": 16,
        }
        segment = {
            "text": "노면 소음 확인",
            "stt_candidates": [
                {"source": "STT1", "score": 0.52, "text": "노면 소음 확인"},
            ],
            "stt_recheck_candidates": [
                {"source": "RECHECK", "score": 0.93, "text": "BMW X5 노면 소음 확인"},
            ],
        }

        decision = select_stt_candidate(segment, settings, {"top_score": 75.0, "examples": [{"text": "BMW X5 노면 소음 확인"}]})

        self.assertIsNotNone(decision)
        self.assertEqual(decision["source"], "RECHECK")
        self.assertIn("RECHECK", decision["_deep_candidate_selector_policy"]["source_counts"])

    def test_stt_selector_can_admit_high_similarity_lora_example(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "deep_stt_candidate_min_score": 0.1,
            "deep_stt_candidate_min_margin": 0.01,
            "deep_stt_candidate_lora_min_similarity": 0.8,
            "split_length_threshold": 16,
        }
        profile = {
            "top_score": 98.0,
            "examples": [{"kind": "truth_table", "score": 98.0, "text": "BMW X5 고속도로 주행 소음"}],
        }
        segment = {
            "text": "bmw x5 고속도로 주행 소음",
            "stt_candidates": [
                {"source": "STT1", "score": 0.52, "text": "bmw x5 고속도로 주행 소음"},
            ],
        }

        decision = select_stt_candidate(segment, settings, profile)

        self.assertIsNotNone(decision)
        self.assertTrue(decision["source"].startswith("LORA_"))
        self.assertEqual(decision["text"], "BMW X5 고속도로 주행 소음")

    def test_reranker_avoids_excluded_phrase_and_keeps_safe_candidate(self):
        settings = {
            "deep_subtitle_policy_enabled": True,
            "split_length_threshold": 16,
            "deep_subtitle_reranker_min_margin": 0.0,
        }
        profile = {
            "top_score": 90.0,
            "examples": [{"text": "오늘은 여기까지 정리할게요"}],
            "exclusions": [{"text": "자막 생성 중"}],
        }

        chunks, metadata = rerank_subtitle_candidates(
            "오늘은 여기까지 정리할게요",
            [["오늘은 자막 생성 중 여기까지 정리할게요"], ["오늘은 여기까지 정리할게요"]],
            settings,
            profile,
        )

        self.assertEqual(chunks, ["오늘은 여기까지 정리할게요"])
        self.assertEqual(metadata["task"], "subtitle_rerank")

    def test_timing_policy_gently_aligns_to_word_edges(self):
        row = {
            "start": 10.0,
            "end": 11.0,
            "text": "테스트",
            "words": [{"word": "테스트", "start": 10.08, "end": 11.09}],
        }

        adjusted, metadata = adjust_subtitle_timing(
            row,
            {"deep_subtitle_policy_enabled": True, "deep_timing_max_shift_sec": 0.12},
            {"top_score": 88.0},
        )

        self.assertAlmostEqual(adjusted["start"], 10.08, places=3)
        self.assertAlmostEqual(adjusted["end"], 11.09, places=3)
        self.assertEqual(metadata["task"], "subtitle_timing_adjustment")

    def test_cut_boundary_policy_marks_audio_hint_as_verify(self):
        scored = score_cut_boundary(
            {
                "timeline_sec": 120.0,
                "source": "audio_gain",
                "audio_gain_db_delta": 12.0,
                "score": 60.0,
            },
            {
                "deep_cut_boundary_model_enabled": True,
                "scan_cut_audio_gain_threshold_db": 10.0,
                "deep_cut_boundary_verify_threshold": 0.42,
            },
        )

        self.assertIn(scored["decision"], {"verify", "keep"})
        self.assertGreater(scored["audio_score"], 0.7)

    def test_sequence_smoothing_extends_dense_high_cps_segment(self):
        rows, summary = smooth_subtitle_sequence(
            [
                {"start": 0.0, "end": 0.5, "text": "너무빠른자막입니다"},
                {"start": 1.0, "end": 2.0, "text": "다음 자막"},
            ],
            {
                "deep_subtitle_policy_enabled": True,
                "deep_sequence_max_shift_sec": 0.2,
                "sub_max_cps": 10,
            },
        )

        self.assertGreater(rows[0]["end"], 0.5)
        self.assertEqual(summary["task"], "sequence_smoothing")
        self.assertIn("_deep_sequence_policy", rows[0])

    def test_segment_setting_policy_can_explore_when_lora_confidence_is_low(self):
        predicted, metadata = predict_segment_settings(
            {"text": "탐험 설정 후보", "start": 1.23},
            {
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_exploration_rate": 1.0,
                "split_length_threshold": 16,
                "sub_gap_break_sec": 1.5,
                "sub_max_cps": 12,
                "continuous_threshold": 2.0,
            },
            {"top_score": 20.0},
        )

        self.assertTrue(predicted)
        self.assertIn("exploration", metadata)


if __name__ == "__main__":
    unittest.main()
