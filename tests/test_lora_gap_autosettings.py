import unittest

from core.personalization.lora_optimizer import build_setting_candidate_bundles


class LoraGapAutoSettingsTests(unittest.TestCase):
    def test_setting_candidates_include_gap_slider_values(self):
        rows = [
            {"start_sec": 0.0, "end_sec": 1.2, "duration_sec": 1.2, "char_count": 13, "cps": 10.8},
            {"start_sec": 1.7, "end_sec": 3.1, "duration_sec": 1.4, "char_count": 17, "cps": 12.1},
            {"start_sec": 4.7, "end_sec": 6.4, "duration_sec": 1.7, "char_count": 21, "cps": 12.4},
        ]
        bundles = build_setting_candidate_bundles(
            rows,
            base_settings={
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.7,
                "single_subtitle_end": 0.2,
                "sub_min_duration": 0.2,
                "sub_max_duration": 6.0,
                "sub_dedup_window": 0.5,
                "sub_gap_break_sec": 1.5,
            },
            multimodal_context={
                "row_count": 1,
                "has_audio": True,
                "scene_environment": "car",
                "noise_sources": ["engine"],
            },
        )

        baseline = next(item for item in bundles if item["bundle_id"] == "baseline_precise")
        settings = dict(baseline["settings"])
        for key in (
            "continuous_threshold",
            "gap_push_rate",
            "single_subtitle_end",
            "split_length_threshold",
            "sub_min_duration",
            "sub_max_duration",
            "sub_max_cps",
            "sub_dedup_window",
            "sub_gap_break_sec",
        ):
            self.assertIn(key, settings)
        self.assertEqual(settings["selected_audio_ai"], "clearvoice")
        self.assertGreaterEqual(settings["gap_push_rate"], 0.76)

    def test_setting_candidates_include_forced_exploration_bundle(self):
        rows = [
            {
                "start_sec": float(index * 2),
                "end_sec": float(index * 2 + 1),
                "duration_sec": 1.0,
                "char_count": 16,
                "cps": 16.0,
            }
            for index in range(4)
        ]
        bundles = build_setting_candidate_bundles(
            rows,
            base_settings={
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.7,
                "single_subtitle_end": 0.2,
                "sub_min_duration": 0.2,
                "sub_max_duration": 6.0,
                "sub_dedup_window": 0.5,
                "sub_gap_break_sec": 1.5,
                "lora_user_settings_exploration_rate": 1.0,
                "lora_user_settings_exploration_min_truth_rows": 0,
                "lora_user_settings_exploration_max_bundles": 2,
            },
            multimodal_context={"row_count": 1, "has_audio": True, "scene_environment": "indoor"},
            exploration_seed="unit-test-explore",
        )

        exploration = [item for item in bundles if item.get("exploration")]
        self.assertEqual(len(exploration), 2)
        self.assertTrue(exploration[0]["bundle_id"].startswith("explore_adaptive_"))
        self.assertIn(exploration[0]["settings"]["selected_audio_ai"], {"clearvoice", "deepfilter", "none"})


if __name__ == "__main__":
    unittest.main()
