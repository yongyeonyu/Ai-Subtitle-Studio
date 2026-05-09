import unittest
from unittest.mock import patch

from core.native_macos_acceleration import mac_native_backend_plan, mac_native_runtime_overrides
from core.runtime.multi_process import apply_apple_m_subtitle_pipeline_plan


class NativeMacOSAccelerationTests(unittest.TestCase):
    def test_plan_keeps_only_bench_safe_native_routes_enabled_by_default(self):
        with patch("core.native_macos_acceleration.config.IS_MAC", True):
            plan = mac_native_backend_plan({})

        self.assertTrue(plan["enabled"])
        self.assertTrue(plan["stt"]["enabled"])
        self.assertTrue(plan["vad"]["enabled"])
        self.assertTrue(plan["llm"]["enabled"])
        self.assertTrue(plan["quality_scoring"]["enabled"])
        self.assertTrue(plan["common_split"]["enabled"])
        self.assertFalse(plan["lora"]["default_enabled"])
        self.assertFalse(plan["deep_learning"]["default_enabled"])
        self.assertFalse(plan["llm"]["candidate_policy_swift_enabled"])
        self.assertFalse(plan["experimental_swift_policy_enabled"])

    def test_runtime_overrides_force_off_unproven_swift_policy_helpers(self):
        overrides = mac_native_runtime_overrides(
            {
                "native_swift_llm_candidate_policy_enabled": True,
                "native_swift_deep_policy_enabled": True,
                "native_swift_lora_scoring_enabled": True,
            }
        )

        self.assertTrue(overrides["native_cpp_llm_macro_groups_enabled"])
        self.assertTrue(overrides["native_swift_quality_scoring_enabled"])
        self.assertTrue(overrides["native_swift_common_split_enabled"])
        self.assertFalse(overrides["native_swift_llm_candidate_policy_enabled"])
        self.assertFalse(overrides["native_swift_deep_policy_enabled"])
        self.assertFalse(overrides["native_swift_lora_scoring_enabled"])

    def test_experimental_switch_is_required_for_swift_policy_helpers(self):
        settings = {
            "native_swift_policy_experimental_enabled": True,
            "native_swift_llm_candidate_policy_enabled": True,
            "native_swift_deep_policy_enabled": True,
            "native_swift_lora_scoring_enabled": True,
        }

        with patch("core.native_macos_acceleration.config.IS_MAC", True):
            plan = mac_native_backend_plan(settings)
        overrides = mac_native_runtime_overrides(settings)

        self.assertTrue(plan["experimental_swift_policy_enabled"])
        self.assertTrue(plan["llm"]["candidate_policy_swift_enabled"])
        self.assertTrue(plan["deep_learning"]["enabled"])
        self.assertTrue(plan["lora"]["enabled"])
        self.assertTrue(overrides["native_swift_llm_candidate_policy_enabled"])
        self.assertTrue(overrides["native_swift_deep_policy_enabled"])
        self.assertTrue(overrides["native_swift_lora_scoring_enabled"])

    def test_plan_respects_global_native_disable(self):
        with patch("core.native_macos_acceleration.config.IS_MAC", True):
            plan = mac_native_backend_plan({"mac_native_acceleration_enabled": False})

        self.assertFalse(plan["enabled"])
        self.assertFalse(plan["stt"]["enabled"])
        self.assertFalse(plan["quality_scoring"]["enabled"])

    def test_runtime_plan_exposes_native_backend_plan(self):
        snapshot = {
            "system": "Darwin",
            "machine": "arm64",
            "brand_string": "Apple M5",
            "chip_name": "Apple M5",
            "chip_generation": 5,
            "chip_tier": "base",
            "logical_cores": 10,
            "physical_cores": 10,
            "performance_cores": 4,
            "efficiency_cores": 6,
            "gpu_cores": 10,
            "neural_engine_cores": 16,
            "memory_bytes": 16 * 1024 ** 3,
        }
        with patch("core.runtime.multi_process.config.IS_APPLE_SILICON", True), \
             patch("core.runtime.multi_process.hardware_profile", return_value=snapshot):
            settings = apply_apple_m_subtitle_pipeline_plan({})

        native_plan = settings["_apple_m_pipeline_parallel_plan"]["native_backend_plan"]
        self.assertEqual(native_plan["schema"], "ai_subtitle_studio.mac_native_backend_plan.v1")
        self.assertEqual(native_plan["stt"]["route"], "whisperkit_coreml_mlx")
        self.assertEqual(native_plan["lora"]["route"], "python_ranker")


if __name__ == "__main__":
    unittest.main()
