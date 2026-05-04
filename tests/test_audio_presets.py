# Version: 03.14.12
# Phase: PHASE2
import json
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

    def test_curated_audio_preset_does_not_apply_stage_recommendation_fields(self):
        applied = apply_audio_preset({}, "실외-마이크유")

        blocked_keys = {
            "cut_boundary_level",
            "selected_audio_ai",
            "selected_vad",
            "stt_ensemble_enabled",
            "stt_ensemble_llm_judge_enabled",
            "selected_model",
            "roughcut_llm_provider",
            "roughcut_llm_model",
            "audio_preset_recommended_preprocess_model",
        }
        self.assertFalse(blocked_keys.intersection(applied))
        self.assertEqual(applied["audio_preset"], "실외-마이크유")
        self.assertGreaterEqual(applied["df_vol"], 4.8)
        self.assertGreaterEqual(applied["ff_treble_boost"], 3.0)

    def test_apply_default_audio_preset_restores_audio_fields_only(self):
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
        self.assertEqual(applied["selected_audio_ai"], "none")
        self.assertEqual(applied["selected_vad"], "none")
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

    def test_media_processor_applies_auto_tune_after_named_preset(self):
        processor = VideoProcessor()
        with mock.patch.object(config, "DATASET_DIR", "/tmp/missing-settings-dir"):
            processor.set_auto_audio_tune_overrides({
                "ff_hp": 190,
                "selected_audio_ai": "clearvoice",
                "selected_vad": "ten_vad",
            })
            settings = processor._load_all_settings()

        self.assertEqual(settings["ff_hp"], 190)
        self.assertEqual(settings.get("selected_audio_ai"), "clearvoice")
        self.assertEqual(settings.get("selected_vad"), "ten_vad")

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

    def test_adaptive_chunk_audio_routing_writes_per_chunk_routes(self):
        class RoutingProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.commands = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                if index == 0:
                    return {
                        "audio_strategy": "clean_voice",
                        "audio_strategy_label": "깨끗한 음성",
                        "audio_tune_reason": "테스트 구간 1",
                        "confidence": 0.7,
                        "settings": {
                            "selected_audio_ai": "deepfilter",
                            "selected_vad": "silero",
                            "ff_hp": 120,
                            "ff_lp": 4200,
                        },
                        "audio_profile": {"environment": "indoor", "noise_level": "low"},
                    }
                return {
                    "audio_strategy": "noisy_voice",
                    "audio_strategy_label": "잡음 음성",
                    "audio_tune_reason": "테스트 구간 2",
                    "confidence": 0.82,
                    "settings": {
                        "selected_audio_ai": "clearvoice",
                        "selected_vad": "ten_vad",
                        "ff_hp": 180,
                        "ff_lp": 5200,
                        "df_hp": 160,
                    },
                    "audio_profile": {"environment": "outdoor", "noise_level": "high"},
                }

            def _run_media_command_no_progress(self, cmd, *, label, timeout=None, env=None):
                self.commands.append(list(cmd))
                out = str(cmd[-1])
                with open(out, "wb") as f:
                    f.write(b"wav")
                return True

            def _apply_clearvoice(self, source_wav, target_wav):
                with open(target_wav, "wb") as f:
                    f.write(b"clear")
                return True

        processor = RoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 20.0}, {"start": 20.0, "end": 40.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "ffmpeg_filter_threads": 1,
                },
            )

            self.assertTrue(ok)
            self.assertTrue(os.path.exists(os.path.join(chunk_dir, "vad_000_0.000.wav")))
            self.assertTrue(os.path.exists(os.path.join(chunk_dir, "vad_001_20.000.wav")))
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertEqual([r["audio_tune_settings"]["selected_audio_ai"] for r in routes], ["deepfilter", "clearvoice"])
        self.assertEqual([r["audio_tune_settings"]["selected_vad"] for r in routes], ["silero", "ten_vad"])
        filters = [cmd[cmd.index("-af") + 1] for cmd in processor.commands if "-af" in cmd]
        self.assertTrue(any("highpass=f=120" in value for value in filters))
        self.assertTrue(any("highpass=f=180" in value for value in filters))

    def test_adaptive_chunk_audio_routing_offsets_chunk_vad_segments(self):
        class VadRoutingProcessor(VideoProcessor):
            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                return {
                    "audio_strategy": "clean_voice",
                    "audio_strategy_label": "깨끗한 음성",
                    "confidence": 0.75,
                    "settings": {"selected_audio_ai": "deepfilter", "selected_vad": "silero"},
                    "audio_profile": {"environment": "indoor", "noise_level": "low"},
                }

            def _run_media_command_no_progress(self, cmd, *, label, timeout=None, env=None):
                with open(cmd[-1], "wb") as f:
                    f.write(b"wav")
                return True

            def _detect_vad_timestamps(self, wav_path, vad_model, s, *args, **kwargs):
                return [{"start": 0.2, "end": 1.1, "source": vad_model}]

        processor = VadRoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 30.0, "end": 40.0}],
                {"use_basic_filter": True, "audio_chunk_routing_enabled": True, "audio_chunk_route_vad_enabled": True},
            )
            with open(os.path.join(chunk_dir, "vad_strict.json"), "r", encoding="utf-8") as f:
                vad_rows = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(vad_rows[0]["start"], 30.2)
        self.assertEqual(vad_rows[0]["end"], 31.1)
        self.assertEqual(vad_rows[0]["source"], "chunk_silero")
        self.assertTrue(vad_rows[0]["post_stt_align"])

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
