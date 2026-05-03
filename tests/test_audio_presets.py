# Version: 03.04.01
# Phase: PHASE2
import os
import tempfile
import unittest
from unittest import mock

from core.runtime import config
from core.audio.audio_presets import (
    apply_audio_preset,
    apply_default_audio_preset,
    load_audio_presets,
    resolve_audio_preset_combo_data,
    uses_default_audio_preset,
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

    def test_curated_audio_preset_applies_full_stack_recommendation_fields(self):
        applied = apply_audio_preset({}, "실외-마이크유")

        self.assertEqual(applied["cut_boundary_level"], "medium")
        self.assertEqual(applied["selected_audio_ai"], "clearvoice")
        self.assertEqual(applied["selected_vad"], "ten_vad")
        self.assertTrue(applied["stt_ensemble_enabled"])
        self.assertTrue(applied["stt_ensemble_llm_judge_enabled"])
        self.assertEqual(applied["selected_model"], "gemma4:e4b")
        self.assertEqual(applied["roughcut_llm_provider"], "ollama")
        self.assertEqual(applied["roughcut_llm_model"], "exaone3.5:7.8b")
        self.assertEqual(applied["audio_preset_recommended_preprocess_model"], "ffmpeg-outdoor-strong")

    def test_apply_default_audio_preset_restores_default_audio_stack(self):
        applied = apply_default_audio_preset(
            {
                "audio_preset": "야외",
                "selected_audio_ai": "none",
                "selected_vad": "none",
                "ff_chunk": 20,
                "gap_push_rate": 0.82,
            }
        )

        self.assertEqual(applied["audio_preset"], "")
        self.assertEqual(applied["selected_audio_ai"], "deepfilter")
        self.assertEqual(applied["selected_vad"], "silero")
        self.assertEqual(applied["ff_chunk"], 30)
        self.assertEqual(applied["gap_push_rate"], 0.7)

    def test_default_audio_stack_is_recognized_as_default_mode(self):
        applied = apply_default_audio_preset(
            {
                "audio_preset": "실외-마이크유",
                "selected_audio_ai": "clearvoice",
                "selected_vad": "ten_vad",
            }
        )

        self.assertTrue(uses_default_audio_preset(applied))
        self.assertEqual(resolve_audio_preset_combo_data(applied), "__default__")

    def test_manual_empty_audio_preset_is_not_forced_to_default_mode(self):
        manual = {
            "audio_preset": "",
            "selected_audio_ai": "none",
            "selected_vad": "silero",
        }

        self.assertFalse(uses_default_audio_preset(manual))
        self.assertEqual(resolve_audio_preset_combo_data(manual), "")

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

    def test_experimental_enhancers_use_light_cleanup_chain(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        for audio_ai in ("resemble_enhance", "clearvoice"):
            cleanup = processor._build_audio_cleanup_filter(audio_ai, settings)
            self.assertIn("highpass=f=170", cleanup)
            self.assertIn("lowpass=f=5200", cleanup)
            self.assertIn("speechnorm", cleanup)
            self.assertIn("loudnorm", cleanup)
            self.assertNotIn("afftdn", cleanup)

    def test_rnnoise_fallback_cleanup_label_uses_ffmpeg(self):
        self.assertEqual(VideoProcessor._audio_cleanup_label("rnnoise", False), "FFMPEG")
        self.assertEqual(VideoProcessor._audio_cleanup_label("rnnoise", True), "RNNoise")
        self.assertEqual(VideoProcessor._audio_cleanup_label("resemble_enhance", False), "FFMPEG")
        self.assertEqual(VideoProcessor._audio_cleanup_label("resemble_enhance", True), "Resemble Enhance")
        self.assertEqual(VideoProcessor._audio_cleanup_label("clearvoice", True), "ClearVoice")
        self.assertEqual(VideoProcessor._audio_cleanup_label("deepfilter", False), "DeepFilter")

    def test_ten_vad_flags_merge_into_speech_segments(self):
        processor = VideoProcessor()

        segments = processor._vad_flags_to_segments(
            [0, 1, 1, 0, 0, 1, 1, 0],
            hop_sec=0.1,
            min_speech_sec=0.1,
            min_silence_sec=0.25,
            speech_pad_sec=0.05,
            source="ten_vad",
            for_post_stt_align=True,
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["source"], "ten_vad")
        self.assertTrue(segments[0]["post_stt_align"])
        self.assertAlmostEqual(segments[0]["start"], 0.05)
        self.assertAlmostEqual(segments[0]["end"], 0.75)

    def test_resemble_enhance_cli_can_resolve_isolated_local_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli_dir = os.path.join(tmp, ".codex_work", "resemble_enhance", "bin")
            os.makedirs(cli_dir)
            cli_path = os.path.join(cli_dir, "resemble-enhance")
            with open(cli_path, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")

            with (
                mock.patch.object(config, "BASE_DIR", tmp),
                mock.patch("core.audio.media_processor.shutil.which", return_value=None),
                mock.patch("core.audio.media_processor.sys.executable", ""),
            ):
                self.assertEqual(VideoProcessor()._resolve_python_cli("resemble-enhance"), cli_path)

    def test_resemble_enhance_command_uses_env_binary_and_explicit_device(self):
        processor = VideoProcessor()
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return True

        with tempfile.TemporaryDirectory() as tmp:
            env_cli = os.path.join(tmp, "resemble-enhance")
            with open(env_cli, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")
            source = os.path.join(tmp, "source.wav")
            target = os.path.join(tmp, "target.wav")
            with open(source, "wb") as f:
                f.write(b"RIFF")

            with (
                mock.patch.dict(os.environ, {"RESEMBLE_ENHANCE_BINARY": env_cli}, clear=False),
                mock.patch.object(processor, "_run_media_command", side_effect=fake_run),
                mock.patch.object(processor, "_copy_first_wav_from_dir", return_value=True),
                mock.patch.object(processor, "_resemble_enhance_device", return_value="mps"),
            ):
                self.assertTrue(processor._apply_resemble_enhance(source, target))

        self.assertEqual(calls[0][0][0], env_cli)
        self.assertIn("--denoise_only", calls[0][0])
        self.assertIn("--device", calls[0][0])
        self.assertEqual(calls[0][0][-1], "mps")
        self.assertEqual(calls[0][1]["label"], "Resemble Enhance 음성 향상")

    def test_resemble_enhance_command_wraps_isolated_cli_with_project_runner(self):
        processor = VideoProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = os.path.join(tmp, "resemble_enhance", "bin")
            os.makedirs(bin_dir)
            cli = os.path.join(bin_dir, "resemble-enhance")
            python = os.path.join(bin_dir, "python")
            for path in (cli, python):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("#!/bin/sh\n")
            with mock.patch.object(config, "BASE_DIR", os.path.dirname(os.path.dirname(__file__))):
                cmd = processor._resemble_enhance_command(cli, "/in", "/out", "mps")

        self.assertEqual(cmd[0], python)
        self.assertTrue(cmd[1].endswith("core/audio/resemble_enhance_runner.py"))
        self.assertEqual(cmd[-1], "mps")


if __name__ == "__main__":
    unittest.main()
