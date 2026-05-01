# Version: 03.04.01
# Phase: PHASE2
import unittest

from core.audio.audio_presets import (
    apply_audio_preset,
    load_audio_presets,
)
from core.audio.media_processor import VideoProcessor


class AudioPresetTests(unittest.TestCase):
    def test_outdoor_preset_boosts_stt1_frontend_audio(self):
        applied = apply_audio_preset({}, "야외")

        self.assertGreaterEqual(applied["df_vol"], 4.8)
        self.assertGreaterEqual(applied["df_eq_g"], 12)
        self.assertLessEqual(applied["ff_nf"], -26)
        self.assertGreaterEqual(applied["ff_dynaudnorm_m"], 16.0)
        self.assertGreaterEqual(applied["ff_treble_boost"], 3.0)
        self.assertGreaterEqual(applied["w_df_no_speech"], 0.62)

    def test_no_mic_fast_preset_keeps_audio_ai_off_but_strengthens_ffmpeg(self):
        applied = apply_audio_preset({}, "마이크 없음/풀속도")

        self.assertGreaterEqual(applied["none_vol"], 5.0)
        self.assertGreaterEqual(applied["ff_dynaudnorm_m"], 14.0)
        self.assertGreaterEqual(applied["w_none_no_speech"], 0.90)

    def test_audio_preset_only_applies_audio_fields(self):
        applied = apply_audio_preset(
            {
                "selected_whisper_model": "custom-stt1",
                "selected_model": "custom-llm",
                "selected_audio_ai": "none",
                "selected_vad": "none",
                "use_basic_filter": False,
            },
            "야외",
        )

        self.assertEqual(applied["selected_whisper_model"], "custom-stt1")
        self.assertEqual(applied["selected_model"], "custom-llm")
        self.assertEqual(applied["selected_audio_ai"], "none")
        self.assertEqual(applied["selected_vad"], "none")
        self.assertFalse(applied["use_basic_filter"])
        self.assertGreaterEqual(applied["df_vol"], 4.8)

    def test_loaded_presets_use_audio_presets_json_values(self):
        presets = load_audio_presets()

        self.assertIn("야외", presets)
        outdoor = presets["야외"]["settings"]
        self.assertGreaterEqual(outdoor["df_vol"], 4.8)
        self.assertEqual(outdoor["df_lp"], 5200)

    def test_media_processor_uses_ffmpeg_and_cleanup_preset_fields(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        preprocess = processor._build_ffmpeg_preprocess_filter(settings)
        cleanup = processor._build_audio_cleanup_filter("deepfilter", settings)

        self.assertIn("highpass=f=120", preprocess)
        self.assertIn("lowpass=f=4200", preprocess)
        self.assertIn("afftdn=nf=-26", preprocess)
        self.assertIn("dynaudnorm=f=150:g=9:m=16:p=0.97", preprocess)
        self.assertIn("equalizer=f=3200", preprocess)
        self.assertIn("highpass=f=170", cleanup)
        self.assertIn("lowpass=f=5200", cleanup)
        self.assertIn("afftdn=nf=-26", cleanup)
        self.assertIn("volume=4.8", cleanup)

    def test_audio_filter_none_skips_cleanup_filter_after_ffmpeg_preprocess(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "마이크 없음/풀속도")

        preprocess = processor._build_ffmpeg_preprocess_filter(settings)
        cleanup = processor._build_audio_cleanup_filter("none", settings)

        self.assertIn("highpass=f=110", preprocess)
        self.assertIn("afftdn=nf=-28", preprocess)
        self.assertEqual(cleanup, "anull")

    def test_rnnoise_uses_fast_cleanup_chain_without_demucs_settings(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        cleanup = processor._build_audio_cleanup_filter("rnnoise", settings)

        self.assertIn("highpass=f=170", cleanup)
        self.assertIn("lowpass=f=5200", cleanup)
        self.assertIn("speechnorm", cleanup)
        self.assertIn("volume=4.8", cleanup)
        self.assertNotIn("demucs", cleanup.lower())


if __name__ == "__main__":
    unittest.main()
