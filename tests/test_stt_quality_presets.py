# Version: 03.00.19
# Phase: PHASE2
import unittest

from core.audio.stt_quality_presets import (
    apply_recommended_stt_quality_defaults,
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
    save_stt_quality_user_preset,
)


class STTQualityPresetTests(unittest.TestCase):
    def test_quality_presets_have_four_user_modes_including_stt(self):
        presets = load_stt_quality_presets()

        self.assertEqual(list(presets), ["fast", "balanced", "precise", "stt"])
        self.assertEqual([presets[key]["label"] for key in presets], ["Fast", "Auto", "High", "STT"])

    def test_apply_fast_preset_uses_whisper_only_and_speed_settings(self):
        settings = {"selected_model": "exaone3.5:7.8b", "w_beam_size": 8}

        applied = apply_stt_quality_preset(settings, "fast")

        self.assertEqual(applied["stt_quality_preset"], "fast")
        self.assertEqual(applied["selected_whisper_model"], "youngouk/whisper-medium-komixv2-mlx")
        self.assertNotIn("audio_preset", applied)
        self.assertEqual(applied["selected_audio_ai"], "clearvoice")
        self.assertEqual(applied["selected_vad"], "ten_vad")
        self.assertAlmostEqual(applied["vad_threshold"], 0.50)
        self.assertEqual(applied["cut_boundary_level"], "off")
        self.assertFalse(applied["cut_boundary_detection_enabled"])
        self.assertTrue(applied["stt_candidate_scoring_enabled"])
        self.assertTrue(applied["stt_ensemble_enabled"])
        self.assertTrue(applied["stt_ensemble_selective_enabled"])
        self.assertTrue(applied["stt_selective_secondary_recheck_enabled"])
        self.assertFalse(applied["stt_word_timestamps_precision_enabled"])
        self.assertEqual(applied["stt_word_timestamps_mode"], "selective")
        self.assertLess(applied["w_beam_size"], settings["w_beam_size"])
        self.assertEqual(applied["w_none_temp_max"], 0.0)

    def test_precise_preset_is_stricter_than_balanced(self):
        balanced = apply_stt_quality_preset({}, "balanced")
        precise = apply_stt_quality_preset({}, "precise")

        self.assertGreater(precise["w_beam_size"], balanced["w_beam_size"])
        self.assertLess(precise["w_df_no_speech"], balanced["w_df_no_speech"])
        self.assertEqual(precise["selected_model"], "exaone3.5:7.8b")
        self.assertNotIn("audio_preset", balanced)
        self.assertEqual(balanced["selected_audio_ai"], "none")
        self.assertEqual(balanced["selected_vad"], "silero")
        self.assertEqual(balanced["cut_boundary_level"], "low")
        self.assertTrue(balanced["cut_boundary_detection_enabled"])
        self.assertTrue(balanced["stt_candidate_scoring_enabled"])
        self.assertNotIn("audio_preset", precise)
        self.assertEqual(precise["selected_audio_ai"], "none")
        self.assertEqual(precise["selected_vad"], "ten_vad")
        self.assertEqual(precise["cut_boundary_level"], "medium")
        self.assertTrue(precise["cut_boundary_detection_enabled"])
        self.assertTrue(balanced["stt_ensemble_enabled"])
        self.assertTrue(balanced["stt_ensemble_selective_enabled"])
        self.assertFalse(balanced["stt_word_timestamps_precision_enabled"])
        self.assertTrue(precise["stt_ensemble_enabled"])
        self.assertTrue(precise["stt_candidate_scoring_enabled"])
        self.assertTrue(precise["stt_ensemble_llm_judge_enabled"])
        self.assertTrue(precise["stt_selective_secondary_recheck_enabled"])
        self.assertFalse(precise["stt_word_timestamps_precision_enabled"])
        self.assertEqual(precise["stt_word_timestamps_precision_max_segments"], 32)
        self.assertEqual(precise["ff_chunk"], 180)
        self.assertEqual(precise["whisper_chunk_overlap_sec"], 12.0)
        self.assertTrue(precise["stt_windowed_finalize_enabled"])
        self.assertEqual(precise["stt_window_hysteresis_sec"], 6.0)
        self.assertTrue(precise["audio_chunk_routing_enabled"])
        self.assertTrue(precise["audio_chunk_route_vad_enabled"])
        self.assertEqual(precise["audio_chunk_profile_sec"], 18.0)
        self.assertAlmostEqual(precise["vad_threshold"], 0.46)
        self.assertAlmostEqual(precise["ten_vad_threshold"], 0.46)
        self.assertEqual(precise["roughcut_llm_model"], "exaone3.5:7.8b")
        self.assertEqual(precise["roughcut_llm_provider"], "ollama")

    def test_korean_aliases_normalize(self):
        self.assertEqual(normalize_stt_quality_key("빠름"), "fast")
        self.assertEqual(normalize_stt_quality_key("보통"), "balanced")
        self.assertEqual(normalize_stt_quality_key("높음"), "precise")
        self.assertEqual(normalize_stt_quality_key("stt 모드"), "stt")
        self.assertEqual(normalize_stt_quality_key("받아쓰기"), "stt")
        self.assertEqual(normalize_stt_quality_key("빠른 인식"), "fast")
        self.assertEqual(normalize_stt_quality_key("정밀인식"), "precise")
        self.assertEqual(normalize_stt_quality_key(""), "balanced")

    def test_stt_preset_enables_dedicated_stt_mode_defaults(self):
        applied = apply_stt_quality_preset({}, "stt")

        self.assertEqual(applied["stt_quality_preset"], "stt")
        self.assertTrue(applied["stt_mode_enabled"])
        self.assertEqual(applied["stt_mode_text_input_provider"], "manual")
        self.assertFalse(applied["stt_mode_require_whisper"])
        self.assertFalse(applied["stt_mode_use_llm"])
        self.assertTrue(applied["stt_mode_lora_resegment_enabled"])
        self.assertEqual(applied["stt_mode_vad_models"], ["silero", "ten_vad"])
        self.assertEqual(applied["selected_model"], "사용 안함 (STT 모드)")

    def test_saved_user_preset_overrides_stage_settings_but_keeps_mode_locked_vad(self):
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
        self.assertEqual(applied["selected_audio_ai"], "none")
        self.assertEqual(applied["selected_vad"], "silero")
        user_settings = saved["stt_quality_user_presets"]["balanced"]["settings"]
        self.assertNotIn("selected_audio_ai", user_settings)
        self.assertNotIn("selected_vad", user_settings)

    def test_mode_defaults_do_not_replace_user_selected_stt_models(self):
        settings = {
            "selected_whisper_model": "user-stt1",
            "selected_whisper_model_secondary": "user-stt2",
        }

        fast = apply_stt_quality_preset(settings, "fast")
        balanced = apply_stt_quality_preset(settings, "balanced")
        precise = apply_stt_quality_preset(settings, "precise")

        for applied in (fast, balanced, precise):
            self.assertEqual(applied["selected_whisper_model"], "user-stt1")
            self.assertEqual(applied["selected_whisper_model_secondary"], "user-stt2")

    def test_saved_mode_stt_models_win_when_switching_to_that_mode(self):
        settings = {
            "selected_whisper_model": "current-stt1",
            "selected_whisper_model_secondary": "current-stt2",
            "stt_quality_user_presets": {
                "precise": {
                    "label": "High",
                    "settings": {
                        "selected_whisper_model": "saved-high-stt1",
                        "selected_whisper_model_secondary": "saved-high-stt2",
                    },
                },
            },
        }

        applied = apply_stt_quality_preset(settings, "precise")

        self.assertEqual(applied["selected_whisper_model"], "saved-high-stt1")
        self.assertEqual(applied["selected_whisper_model_secondary"], "saved-high-stt2")

    def test_benchmark_runtime_profile_preserves_explicit_model_routes(self):
        settings = {
            "benchmark_runtime_profile": "unit-bench",
            "selected_whisper_model": "bench-stt",
            "selected_whisper_model_secondary": "bench-stt2",
            "selected_model": "bench-subtitle-llm",
            "selected_llm_provider": "ollama",
            "subtitle_llm_user_selected": True,
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "bench-roughcut-llm",
            "stt_quality_user_presets": {
                "precise": {
                    "label": "High",
                    "settings": {
                        "selected_whisper_model": "slow-stt",
                        "selected_whisper_model_secondary": "slow-stt2",
                        "selected_model": "slow-subtitle-llm",
                        "roughcut_llm_model": "slow-roughcut-llm",
                    },
                },
            },
        }

        applied = apply_stt_quality_preset(settings, "precise")

        self.assertEqual(applied["selected_whisper_model"], "bench-stt")
        self.assertEqual(applied["selected_whisper_model_secondary"], "bench-stt2")
        self.assertEqual(applied["selected_model"], "bench-subtitle-llm")
        self.assertEqual(applied["roughcut_llm_model"], "bench-roughcut-llm")

    def test_recommended_defaults_ignore_old_saved_policy_but_keep_user_choices(self):
        settings = {
            "selected_audio_ai": "clearvoice",
            "selected_vad": "ten_vad",
            "selected_whisper_model": "user-stt1",
            "selected_whisper_model_secondary": "user-stt2",
            "selected_model": "user-subtitle-llm",
            "selected_llm_provider": "ollama",
            "stt_quality_user_presets": {
                "precise": {
                    "label": "High",
                    "settings": {
                        "selected_whisper_model": "old-stt1",
                        "stt_ensemble_enabled": True,
                        "stt_word_timestamps_precision_max_segments": 4,
                    },
                },
            },
        }

        applied = apply_recommended_stt_quality_defaults(settings, "precise")

        self.assertEqual(applied["selected_audio_ai"], "none")
        self.assertEqual(applied["selected_vad"], "ten_vad")
        self.assertEqual(applied["selected_whisper_model"], "user-stt1")
        self.assertEqual(applied["selected_whisper_model_secondary"], "user-stt2")
        self.assertEqual(applied["selected_model"], "user-subtitle-llm")
        self.assertTrue(applied["stt_ensemble_enabled"])
        self.assertEqual(applied["stt_word_timestamps_precision_max_segments"], 32)
        self.assertFalse(applied["stt_word_timestamps_precision_enabled"])

    def test_recommended_defaults_own_stt2_policy_even_when_user_toggle_exists(self):
        settings = {
            "selected_whisper_model": "user-stt1",
            "selected_whisper_model_secondary": "user-stt2",
            "stt_ensemble_enabled": True,
            "stt_ensemble_user_selected": True,
            "stt_quality_user_presets": {
                "precise": {
                    "label": "High",
                    "settings": {
                        "stt_ensemble_enabled": False,
                    },
                },
            },
        }

        applied = apply_recommended_stt_quality_defaults(settings, "precise")

        self.assertEqual(applied["selected_whisper_model_secondary"], "user-stt2")
        self.assertTrue(applied["stt_ensemble_enabled"])
        self.assertNotIn("stt_ensemble_user_selected", applied)


if __name__ == "__main__":
    unittest.main()
