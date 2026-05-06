import unittest

from core.engine.subtitle_uncertainty import (
    UNCERTAINTY_SCHEDULER_SCHEMA,
    annotate_uncertainty_first_segments,
    subtitle_uncertainty_policy,
)


class SubtitleUncertaintyTests(unittest.TestCase):
    def test_policy_marks_high_signal_short_segment_as_easy(self):
        policy = subtitle_uncertainty_policy(
            {
                "start": 0.0,
                "end": 1.5,
                "text": "좋습니다",
                "score": 0.94,
                "_lora_generation_profile": {"top_score": 93.0},
            },
            {"split_length_threshold": 10, "sub_max_duration": 6.0, "sub_max_cps": 12},
        )

        self.assertEqual(policy["schema"], UNCERTAINTY_SCHEDULER_SCHEMA)
        self.assertEqual(policy["bucket"], "easy")
        self.assertTrue(policy["fast_lane"])
        self.assertFalse(policy["precision_pass_required"])

    def test_policy_routes_conflict_and_bad_quality_to_precision(self):
        policy = subtitle_uncertainty_policy(
            {
                "start": 0.0,
                "end": 1.0,
                "text": "너무 긴 자막입니다 너무 긴 자막입니다 너무 긴 자막입니다",
                "stt_ensemble_needs_llm_review": True,
                "score": 0.32,
                "quality": {"confidence_label": "red", "confidence_score": 32},
                "_stt_lattice_policy": {"accepted": False, "confidence": 0.35, "reason": "low_match"},
            },
            {"split_length_threshold": 8, "sub_max_duration": 2.0, "sub_max_cps": 12},
        )

        self.assertEqual(policy["bucket"], "precision")
        self.assertTrue(policy["precision_pass_required"])
        self.assertIn("run_precision_pass", policy["recommended_actions"])
        self.assertIn("prefer_stt_recheck", policy["recommended_actions"])
        self.assertGreater(policy["risk_score"], 52.0)

    def test_annotate_schedules_easy_rows_before_precision_but_keeps_metadata(self):
        rows, plan = annotate_uncertainty_first_segments(
            [
                {"start": 0.0, "end": 1.0, "text": "충돌", "stt_ensemble_needs_llm_review": True, "quality": {"confidence_label": "red"}},
                {"start": 5.0, "end": 6.0, "text": "쉬움", "score": 95, "_lora_segment_score": 96},
                {"start": 2.0, "end": 3.0, "text": "일반"},
            ],
            {"split_length_threshold": 10, "sub_max_duration": 6.0, "sub_max_cps": 12},
        )

        self.assertEqual(plan["process_order"], [1, 2, 0])
        self.assertEqual(plan["bucket_counts"]["easy"], 1)
        self.assertEqual(plan["bucket_counts"]["normal"], 1)
        self.assertEqual(plan["bucket_counts"]["precision"], 1)
        self.assertEqual(rows[0]["_uncertainty_bucket"], "precision")
        self.assertEqual(rows[1]["_uncertainty_bucket"], "easy")
        self.assertEqual(rows[0]["_uncertainty_schedule_summary"]["process_order"], [1, 2, 0])

    def test_disabled_policy_keeps_normal_bucket(self):
        rows, plan = annotate_uncertainty_first_segments(
            [{"start": 0.0, "end": 1.0, "text": "테스트", "score": 99}],
            {"uncertainty_first_enabled": False},
        )

        self.assertFalse(plan["enabled"])
        self.assertEqual(plan["process_order"], [0])
        self.assertEqual(rows[0]["_uncertainty_bucket"], "normal")


if __name__ == "__main__":
    unittest.main()
