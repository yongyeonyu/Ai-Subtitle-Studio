# Version: 03.14.17
# Phase: PHASE2
import unittest

from core.accuracy_policy import (
    apply_accuracy_first_defaults,
    apply_accuracy_first_runtime_settings,
)


class AccuracyPolicyTests(unittest.TestCase):
    def test_defaults_choose_balanced_quality_and_balanced_auto_mode(self):
        settings = apply_accuracy_first_defaults({})

        self.assertEqual(settings["stt_quality_preset"], "balanced")
        self.assertEqual(settings["auto_start_mode"], "balanced")
        self.assertFalse(settings["stt_ensemble_enabled"])
        self.assertTrue(settings["subtitle_quality_auto_check_after_generate"])

    def test_runtime_keeps_selected_quality_level_and_auto_mode_preset(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "auto_start_mode": "fast",
                "stt_quality_preset": "fast",
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "stt_ensemble_enabled": False,
                "subtitle_quality_auto_check_after_generate": False,
            }
        )

        self.assertEqual(settings["auto_start_mode"], "fast")
        self.assertEqual(settings["stt_quality_preset"], "fast")
        self.assertIn("사용 안함", settings["selected_model"])
        self.assertTrue(settings["stt_candidate_scoring_enabled"])

    def test_auto_balanced_runtime_skips_local_llm_preflight(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "simple_operation_mode": "auto",
                "auto_start_mode": "balanced",
                "stt_quality_preset": "balanced",
                "selected_model": "exaone3.5:2.4b",
                "selected_llm_provider": "ollama",
            }
        )

        self.assertEqual(settings["stt_quality_preset"], "balanced")
        self.assertIn("사용 안함", settings["selected_model"])
        self.assertEqual(settings["selected_llm_provider"], "none")
        self.assertFalse(settings["stt_ensemble_enabled"])
        self.assertTrue(settings["autopilot_enabled"])
        self.assertFalse(settings["operation_mode_choices_visible"])
        self.assertEqual(settings["cut_boundary_policy_mode"], "hybrid")

    def test_auto_runtime_preserves_user_selected_quality_preset(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "simple_operation_mode": "auto",
                "auto_start_mode": "precise",
                "stt_quality_preset": "precise",
                "selected_model": "gemma4:e4b",
                "selected_llm_provider": "ollama",
            }
        )

        self.assertEqual(settings["simple_operation_mode"], "high")
        self.assertEqual(settings["subtitle_mode"], "high")
        self.assertEqual(settings["auto_start_mode"], "precise")
        self.assertEqual(settings["stt_quality_preset"], "precise")
        self.assertTrue(settings["stt_ensemble_enabled"])
        self.assertTrue(settings["stt_ensemble_llm_judge_enabled"])

    def test_auto_runtime_preserves_fast_quality_preset_while_capping_heavy_work(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "simple_operation_mode": "auto",
                "auto_start_mode": "fast",
                "stt_quality_preset": "fast",
                "selected_model": "exaone3.5:7.8b",
                "selected_llm_provider": "ollama",
            }
        )

        self.assertEqual(settings["simple_operation_mode"], "fast")
        self.assertEqual(settings["subtitle_mode"], "fast")
        self.assertEqual(settings["auto_start_mode"], "fast")
        self.assertEqual(settings["stt_quality_preset"], "fast")
        self.assertIn("사용 안함", settings["selected_model"])
        self.assertEqual(settings["selected_llm_provider"], "none")
        self.assertFalse(settings["stt_ensemble_enabled"])

    def test_policy_can_be_disabled_for_manual_compatibility(self):
        settings = apply_accuracy_first_runtime_settings(
            {
                "accuracy_first_mode": False,
                "stt_quality_preset": "fast",
                "auto_start_mode": "fast",
            }
        )

        self.assertEqual(settings["stt_quality_preset"], "fast")
        self.assertEqual(settings["auto_start_mode"], "fast")


if __name__ == "__main__":
    unittest.main()
