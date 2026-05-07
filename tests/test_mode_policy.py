import unittest

from core.mode_policy import (
    ENGINE_DASHBOARD_STEPS,
    apply_mode_runtime_settings,
    preflight_mode_decision,
    resolve_mode_policy,
    selected_mode_from_settings,
)


class ModePolicyTests(unittest.TestCase):
    def test_legacy_auto_preserves_fast_and_high_quality_choice(self):
        self.assertEqual(
            selected_mode_from_settings({"simple_operation_mode": "auto", "stt_quality_preset": "fast"}),
            "fast",
        )
        self.assertEqual(
            selected_mode_from_settings({"simple_operation_mode": "auto", "stt_quality_preset": "precise"}),
            "high",
        )
        self.assertEqual(selected_mode_from_settings({"simple_operation_mode": "balanced"}), "auto")

    def test_runtime_modes_apply_stage_policy(self):
        fast = apply_mode_runtime_settings({"subtitle_mode": "fast"})
        auto = apply_mode_runtime_settings({"subtitle_mode": "auto"})
        high = apply_mode_runtime_settings({"subtitle_mode": "high"})

        self.assertEqual(fast["stt_quality_preset"], "fast")
        self.assertEqual(fast["cut_boundary_level"], "off")
        self.assertFalse(fast["stt_ensemble_enabled"])
        self.assertTrue(fast["stt_selective_secondary_recheck_enabled"])
        self.assertLessEqual(fast["stt_low_score_recheck_max_segments"], 16)
        self.assertIn("사용 안함", fast["selected_model"])
        self.assertEqual(fast["selected_llm_provider"], "none")
        self.assertEqual(fast["subtitle_tool_stack_tools"], ["lora"])
        self.assertTrue(fast["editor_lora_runtime_enabled"])
        self.assertFalse(fast["deep_subtitle_policy_enabled"])
        self.assertFalse(fast["subtitle_llm_macro_chunk_enabled"])

        self.assertEqual(auto["stt_quality_preset"], "balanced")
        self.assertEqual(auto["cut_boundary_level"], "low")
        self.assertFalse(auto["stt_ensemble_enabled"])
        self.assertTrue(auto["stt_ensemble_llm_judge_enabled"])
        self.assertIn("사용 안함", auto["selected_model"])
        self.assertEqual(auto["selected_llm_provider"], "none")
        self.assertEqual(auto["subtitle_tool_stack_tools"], ["lora", "deep_learning"])
        self.assertTrue(auto["deep_subtitle_policy_enabled"])
        self.assertTrue(auto["deep_stt_candidate_selector_enabled"])
        self.assertFalse(auto["subtitle_llm_macro_chunk_enabled"])

        self.assertEqual(high["stt_quality_preset"], "precise")
        self.assertEqual(high["cut_boundary_level"], "medium")
        self.assertTrue(high["stt_ensemble_enabled"])
        self.assertTrue(high["vad_dual_model_enabled"])
        self.assertEqual(high["subtitle_tool_stack_tools"], ["lora", "deep_learning", "llm"])
        self.assertTrue(high["deep_subtitle_policy_enabled"])
        self.assertTrue(high["subtitle_llm_macro_chunk_enabled"])

    def test_mode_tool_stack_overrides_subtitle_llm_by_quality_mode(self):
        fast = apply_mode_runtime_settings(
            {
                "subtitle_mode": "fast",
                "selected_model": "custom-llm",
                "selected_llm_provider": "ollama",
                "subtitle_llm_user_selected": True,
            }
        )
        auto = apply_mode_runtime_settings(
            {
                "subtitle_mode": "auto",
                "selected_model": "custom-llm",
                "selected_llm_provider": "ollama",
                "subtitle_llm_user_selected": True,
            }
        )
        high = apply_mode_runtime_settings(
            {
                "subtitle_mode": "high",
                "selected_model": "custom-llm",
                "selected_llm_provider": "ollama",
                "subtitle_llm_user_selected": True,
            }
        )

        self.assertEqual(fast["selected_model"], "custom-llm")
        self.assertEqual(auto["selected_model"], "custom-llm")
        self.assertEqual(high["selected_model"], "custom-llm")
        self.assertFalse(fast["subtitle_llm_runtime_enabled"])
        self.assertFalse(auto["subtitle_llm_runtime_enabled"])
        self.assertTrue(high["subtitle_llm_runtime_enabled"])
        self.assertFalse(fast["mode_policy_snapshot"]["llm"]["subtitle_enabled"])
        self.assertFalse(auto["mode_policy_snapshot"]["llm"]["subtitle_enabled"])
        self.assertTrue(high["mode_policy_snapshot"]["llm"]["subtitle_enabled"])
        self.assertFalse(fast["mode_policy_snapshot"]["subtitle_tool_stack"]["llm"])
        self.assertFalse(auto["mode_policy_snapshot"]["subtitle_tool_stack"]["llm"])
        self.assertTrue(high["mode_policy_snapshot"]["subtitle_tool_stack"]["llm"])

    def test_selected_llm_is_effective_only_in_high_mode(self):
        from core.engine import subtitle_settings

        auto = apply_mode_runtime_settings(
            {
                "subtitle_mode": "auto",
                "selected_model": "custom-llm",
                "selected_llm_provider": "ollama",
                "subtitle_llm_user_selected": True,
            }
        )
        high = apply_mode_runtime_settings(
            {
                "subtitle_mode": "high",
                "selected_model": "custom-llm",
                "selected_llm_provider": "ollama",
                "subtitle_llm_user_selected": True,
            }
        )

        with unittest.mock.patch("core.engine.subtitle_settings._get_user_settings", return_value=auto):
            self.assertIn("사용 안함", subtitle_settings.get_selected_llm())
        with unittest.mock.patch("core.engine.subtitle_settings._get_user_settings", return_value=high):
            self.assertEqual(subtitle_settings.get_selected_llm(), "custom-llm")

    def test_dashboard_has_ten_stable_steps_and_reasons(self):
        policy = resolve_mode_policy({"subtitle_mode": "high", "selected_model": "gemma4:e4b"})
        dashboard = policy["dashboard"]

        self.assertEqual([step["key"] for step in dashboard["steps"]], [key for key, _label in ENGINE_DASHBOARD_STEPS])
        self.assertEqual(len(dashboard["steps"]), 10)
        self.assertTrue(all(str(step.get("reason") or "").strip() for step in dashboard["steps"]))

    def test_auto_preflight_routes_easy_and_difficult_media(self):
        easy = preflight_mode_decision(
            {"stt_confidence": 94.0, "noise_level": 0.1, "cut_density": 0.05},
            {"subtitle_mode": "auto"},
        )
        hard = preflight_mode_decision(
            {"stt_confidence": 48.0, "noise_level": 0.8, "cut_density": 0.9},
            {"subtitle_mode": "auto"},
        )

        self.assertEqual(easy["route"], "fast_path")
        self.assertEqual(hard["route"], "high_validation")


if __name__ == "__main__":
    unittest.main()
