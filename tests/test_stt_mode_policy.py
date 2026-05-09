# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
import unittest

from core.mode_policy import (
    apply_mode_runtime_settings,
    mode_items,
    normalize_mode,
    resolve_mode_policy,
    selected_mode_from_settings,
)


class STTModePolicyTests(unittest.TestCase):
    def test_stt_mode_is_a_user_facing_mode(self):
        self.assertEqual(normalize_mode("stt"), "stt")
        self.assertEqual(normalize_mode("STT 모드"), "stt")
        self.assertIn(("stt", "STT 모드"), mode_items())
        self.assertEqual(selected_mode_from_settings({"subtitle_mode": "stt"}), "stt")

    def test_stt_mode_policy_does_not_require_whisper_or_llm(self):
        policy = resolve_mode_policy({"subtitle_mode": "stt", "selected_model": "gemma4:e4b"})

        self.assertEqual(policy["mode"], "stt")
        self.assertTrue(policy["stt_mode"]["enabled"])
        self.assertFalse(policy["stt_mode"]["whisper_required"])
        self.assertFalse(policy["stt_mode"]["llm_used"])
        self.assertFalse(policy["stt"]["automatic_whisper_pipeline"])
        self.assertEqual(policy["stt"]["human_input_provider"], "manual")
        self.assertEqual(policy["vad"]["selected"], "dual-vad")
        self.assertEqual(policy["vad"]["models"], ["silero", "ten_vad"])
        self.assertFalse(policy["llm"]["subtitle_enabled"])
        self.assertFalse(policy["llm"]["roughcut_enabled"])
        self.assertEqual(policy["dashboard"]["steps"][3]["value"], "수동 입력")
        self.assertEqual(policy["dashboard"]["steps"][4]["value"], "미사용")

    def test_stt_runtime_settings_do_not_apply_auto_whisper_quality(self):
        settings = apply_mode_runtime_settings(
            {
                "subtitle_mode": "stt",
                "selected_model": "gemma4:e4b",
                "selected_llm_provider": "ollama",
            }
        )

        self.assertEqual(settings["subtitle_mode"], "stt")
        self.assertEqual(settings["stt_quality_preset"], "stt")
        self.assertTrue(settings["stt_mode_enabled"])
        self.assertFalse(settings["stt_mode_require_whisper"])
        self.assertFalse(settings["stt_mode_use_whisper_for_dictation"])
        self.assertFalse(settings["stt_mode_use_llm"])
        self.assertFalse(settings["automatic_whisper_pipeline"])
        self.assertIn("사용 안함", settings["selected_model"])
        self.assertEqual(settings["selected_llm_provider"], "none")
        self.assertFalse(settings["subtitle_llm_runtime_enabled"])
        self.assertFalse(settings["roughcut_llm_enabled"])

    def test_fast_auto_high_modes_remain_unchanged(self):
        fast = apply_mode_runtime_settings({"subtitle_mode": "fast"})
        auto = apply_mode_runtime_settings({"subtitle_mode": "auto"})
        high = apply_mode_runtime_settings({"subtitle_mode": "high"})

        self.assertEqual(fast["stt_quality_preset"], "fast")
        self.assertEqual(auto["stt_quality_preset"], "balanced")
        self.assertEqual(high["stt_quality_preset"], "precise")
        self.assertEqual(fast["subtitle_tool_stack_tools"], ["lora"])
        self.assertEqual(auto["subtitle_tool_stack_tools"], ["lora", "deep_learning"])
        self.assertEqual(high["subtitle_tool_stack_tools"], ["lora", "deep_learning", "llm"])

    def test_fast_auto_high_modes_preserve_user_selected_stt_models(self):
        base = {
            "selected_whisper_model": "user-selected-stt1",
            "selected_whisper_model_secondary": "user-selected-stt2",
        }

        for mode in ("fast", "auto", "high"):
            settings = apply_mode_runtime_settings({**base, "subtitle_mode": mode})
            self.assertEqual(settings["selected_whisper_model"], "user-selected-stt1")
            self.assertEqual(settings["selected_whisper_model_secondary"], "user-selected-stt2")


if __name__ == "__main__":
    unittest.main()
