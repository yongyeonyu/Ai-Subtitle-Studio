import unittest

from core.settings_simplifier import (
    apply_simple_operation_mode,
    normalize_simple_operation_mode,
    simple_operation_mode_items,
)


class SettingsSimplifierTests(unittest.TestCase):
    def test_apply_simple_operation_mode_forces_autopilot_controls(self):
        settings = apply_simple_operation_mode(
            {
                "chunk_time_limit": 99999,
                "subtitle_bundle_autopilot_enabled": False,
                "roughcut_llm_rows_auto_enabled": False,
                "llm_threads_auto_enabled": False,
                "user_prompt": "custom prompt",
            },
            "balanced",
        )

        self.assertEqual(settings["simple_operation_mode"], "auto")
        self.assertTrue(settings["settings_simplified_ui_enabled"])
        self.assertTrue(settings["subtitle_bundle_autopilot_enabled"])
        self.assertTrue(settings["roughcut_llm_rows_auto_enabled"])
        self.assertTrue(settings["llm_threads_auto_enabled"])
        self.assertEqual(settings["chunk_time_limit"], settings["subtitle_bundle_target_sec"])
        self.assertEqual(settings["user_prompt"], "")
        self.assertFalse(settings["operation_mode_choices_visible"])
        self.assertEqual(settings["cut_boundary_policy_mode"], "hybrid")
        self.assertEqual(settings["cut_boundary_hybrid_fast_level"], "low")
        self.assertEqual(settings["scan_cut_level"], "low")
        self.assertEqual(settings["simple_operation_mode_policy"]["schema"], "ai_subtitle_studio.simple_operation_mode.v1")

    def test_operation_mode_aliases_and_items_are_stable(self):
        self.assertEqual(normalize_simple_operation_mode("빠름"), "fast")
        self.assertEqual(normalize_simple_operation_mode("accuracy"), "high")
        self.assertEqual(normalize_simple_operation_mode("STT 모드"), "stt")
        self.assertEqual([item[0] for item in simple_operation_mode_items()], ["fast", "auto", "high", "stt"])
        self.assertEqual(
            [item[0] for item in simple_operation_mode_items(include_advanced=True)],
            ["fast", "auto", "high", "stt"],
        )

    def test_mode_controls_quality_choice_directly(self):
        settings = apply_simple_operation_mode(
            {
                "simple_operation_mode": "auto",
                "auto_start_mode": "precise",
                "stt_quality_preset": "precise",
            },
            "high",
        )

        self.assertEqual(settings["simple_operation_mode"], "high")
        self.assertEqual(settings["subtitle_mode"], "high")
        self.assertEqual(settings["auto_start_mode"], "precise")
        self.assertEqual(settings["stt_quality_preset"], "precise")


if __name__ == "__main__":
    unittest.main()
