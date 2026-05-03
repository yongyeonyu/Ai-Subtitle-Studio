# Version: 03.00.19
# Phase: PHASE2
import unittest

from core.audio.stt_quality_presets import (
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
)


class STTQualityPresetTests(unittest.TestCase):
    def test_quality_presets_have_three_user_modes(self):
        presets = load_stt_quality_presets()

        self.assertEqual(list(presets), ["fast", "balanced", "precise"])
        self.assertEqual([presets[key]["label"] for key in presets], ["빠른 인식", "균형", "정밀 인식"])

    def test_apply_fast_preset_uses_whisper_only_and_speed_settings(self):
        settings = {"selected_model": "exaone3.5:7.8b", "w_beam_size": 8}

        applied = apply_stt_quality_preset(settings, "fast")

        self.assertEqual(applied["stt_quality_preset"], "fast")
        self.assertEqual(applied["selected_model"], "사용 안함 (Whisper 단독 진행)")
        self.assertEqual(applied["audio_preset"], "실내-마이크무")
        self.assertEqual(applied["selected_audio_ai"], "none")
        self.assertEqual(applied["selected_vad"], "none")
        self.assertEqual(applied["cut_boundary_level"], "off")
        self.assertFalse(applied["cut_boundary_detection_enabled"])
        self.assertLess(applied["w_beam_size"], settings["w_beam_size"])
        self.assertEqual(applied["w_none_temp_max"], 0.0)

    def test_precise_preset_is_stricter_than_balanced(self):
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertGreater(precise["w_beam_size"], balanced["w_beam_size"])
        self.assertLess(precise["w_df_no_speech"], balanced["w_df_no_speech"])
        self.assertEqual(precise["selected_model"], "gemma4:e4b")
        self.assertEqual(balanced["audio_preset"], "실내-마이크유")
        self.assertEqual(balanced["selected_audio_ai"], "deepfilter")
        self.assertEqual(balanced["selected_vad"], "silero")
        self.assertEqual(balanced["cut_boundary_level"], "low")
        self.assertTrue(balanced["cut_boundary_detection_enabled"])
        self.assertEqual(precise["audio_preset"], "실외-마이크유")
        self.assertEqual(precise["selected_audio_ai"], "clearvoice")
        self.assertEqual(precise["selected_vad"], "ten_vad")
        self.assertEqual(precise["cut_boundary_level"], "medium")
        self.assertTrue(precise["cut_boundary_detection_enabled"])

    def test_korean_aliases_normalize(self):
        self.assertEqual(normalize_stt_quality_key("빠른 인식"), "fast")
        self.assertEqual(normalize_stt_quality_key("정밀인식"), "precise")
        self.assertEqual(normalize_stt_quality_key(""), "balanced")


if __name__ == "__main__":
    unittest.main()
