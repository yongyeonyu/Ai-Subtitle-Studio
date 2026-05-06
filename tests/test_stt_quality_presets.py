# Version: 03.00.19
# Phase: PHASE2
import unittest

from core.audio.stt_quality_presets import (
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    save_stt_quality_user_preset,
)


class STTQualityPresetTests(unittest.TestCase):
    def test_quality_presets_have_three_user_modes(self):
        presets = load_stt_quality_presets()

        self.assertEqual(list(presets), ["fast", "balanced", "precise"])
        self.assertEqual([presets[key]["label"] for key in presets], ["Fast", "Auto", "High"])

    def test_apply_fast_preset_uses_whisper_only_and_speed_settings(self):
        settings = {"selected_model": "exaone3.5:7.8b", "w_beam_size": 8}

        applied = apply_stt_quality_preset(settings, "fast")

        self.assertEqual(applied["stt_quality_preset"], "fast")
        self.assertEqual(applied["selected_model"], "사용 안함 (Whisper 단독 진행)")
        self.assertNotIn("audio_preset", applied)
        self.assertNotIn("selected_audio_ai", applied)
        self.assertNotIn("selected_vad", applied)
        self.assertEqual(applied["cut_boundary_level"], "off")
        self.assertFalse(applied["cut_boundary_detection_enabled"])
        self.assertTrue(applied["stt_candidate_scoring_enabled"])
        self.assertLess(applied["w_beam_size"], settings["w_beam_size"])
        self.assertEqual(applied["w_none_temp_max"], 0.0)

    def test_precise_preset_is_stricter_than_balanced(self):
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertGreater(precise["w_beam_size"], balanced["w_beam_size"])
        self.assertLess(precise["w_df_no_speech"], balanced["w_df_no_speech"])
        self.assertEqual(precise["selected_model"], "gemma4:e4b")
        self.assertNotIn("audio_preset", balanced)
        self.assertNotIn("selected_audio_ai", balanced)
        self.assertNotIn("selected_vad", balanced)
        self.assertEqual(balanced["cut_boundary_level"], "low")
        self.assertTrue(balanced["cut_boundary_detection_enabled"])
        self.assertTrue(balanced["stt_candidate_scoring_enabled"])
        self.assertNotIn("audio_preset", precise)
        self.assertNotIn("selected_audio_ai", precise)
        self.assertNotIn("selected_vad", precise)
        self.assertEqual(precise["cut_boundary_level"], "medium")
        self.assertTrue(precise["cut_boundary_detection_enabled"])
        self.assertTrue(precise["stt_ensemble_enabled"])
        self.assertTrue(precise["stt_candidate_scoring_enabled"])
        self.assertTrue(precise["stt_ensemble_llm_judge_enabled"])
        self.assertEqual(precise["roughcut_llm_model"], "exaone3.5:7.8b")
        self.assertEqual(precise["roughcut_llm_provider"], "ollama")

    def test_korean_aliases_normalize(self):
        self.assertEqual(normalize_stt_quality_key("빠름"), "fast")
        self.assertEqual(normalize_stt_quality_key("보통"), "balanced")
        self.assertEqual(normalize_stt_quality_key("높음"), "precise")
        self.assertEqual(normalize_stt_quality_key("빠른 인식"), "fast")
        self.assertEqual(normalize_stt_quality_key("정밀인식"), "precise")
        self.assertEqual(normalize_stt_quality_key(""), "balanced")

    def test_saved_user_preset_overrides_stage_settings_without_audio(self):
        settings = apply_stt_quality_preset({}, "balanced")
        settings.update(
            {
                "selected_whisper_model": "custom-stt",
                "selected_model": "custom-llm",
                "selected_audio_ai": "deepfilter",
                "selected_vad": "silero",
            }
        )

        saved = save_stt_quality_user_preset(settings, "balanced")
        applied = apply_stt_quality_preset(saved, "balanced")

        self.assertEqual(applied["selected_whisper_model"], "custom-stt")
        self.assertEqual(applied["selected_model"], "custom-llm")
        self.assertEqual(applied["selected_audio_ai"], "deepfilter")
        self.assertEqual(applied["selected_vad"], "silero")
        user_settings = saved["stt_quality_user_presets"]["balanced"]["settings"]
        self.assertNotIn("selected_audio_ai", user_settings)
        self.assertNotIn("selected_vad", user_settings)


if __name__ == "__main__":
    unittest.main()
