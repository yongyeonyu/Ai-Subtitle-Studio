# Version: 03.14.17
# Phase: PHASE2
import unittest

from core.accuracy_policy import (
    apply_accuracy_first_defaults,
    apply_accuracy_first_runtime_settings,
)


class AccuracyPolicyTests(unittest.TestCase):
    def test_defaults_choose_precise_quality_and_quality_auto_mode(self):
        settings = apply_accuracy_first_defaults({})

        self.assertEqual(settings["stt_quality_preset"], "precise")
        self.assertEqual(settings["auto_start_mode"], "quality")
        self.assertTrue(settings["stt_ensemble_enabled"])
        self.assertTrue(settings["subtitle_quality_auto_check_after_generate"])

    def test_runtime_keeps_selected_quality_level_but_normalizes_auto_mode(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "auto_start_mode": "fast",
                "stt_quality_preset": "fast",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "stt_ensemble_enabled": False,
                "subtitle_quality_auto_check_after_generate": False,
            }
        )

        self.assertEqual(settings["auto_start_mode"], "quality")
        self.assertEqual(settings["stt_quality_preset"], "fast")
        self.assertIn("사용 안함", settings["selected_model"])
        self.assertFalse(settings["stt_candidate_scoring_enabled"])

    def test_policy_can_be_disabled_for_manual_compatibility(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "accuracy_first_mode": False,
                "stt_quality_preset": "fast",
                "auto_start_mode": "fast",
            }
        )

        self.assertEqual(settings["stt_quality_preset"], "fast")
        self.assertEqual(settings["auto_start_mode"], "quality")


if __name__ == "__main__":
    unittest.main()
