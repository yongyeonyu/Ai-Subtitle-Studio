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
from core.audio.preset_auto_classifier import candidate_settings_for_id, select_audio_candidate
from core.audio.media_processor import VideoProcessor


class AudioPresetTests(unittest.TestCase):
    def test_clearvoice_defaults_to_fast_16k_model(self):
        processor = VideoProcessor()

        self.assertEqual(processor._clearvoice_model_name({}), "MossFormerGAN_SE_16K")
        self.assertEqual(processor._clearvoice_input_sample_rate({}), 16000)
        self.assertEqual(processor._audio_processing_sample_rate("clearvoice", {}), 16000)

    def test_noisy_voice_route_keeps_vad_and_strong_native_filter(self):
        processor = VideoProcessor()
        settings = candidate_settings_for_id("noisy_voice")

        tune = processor._audio_route_tune_settings(settings, {"audio_chunk_route_vad_enabled": True})
        filter_text = processor._build_macos_native_fast_audio_flatten_filter(settings)
        tune_without_vad = processor._audio_route_tune_settings(settings, {"audio_chunk_route_vad_enabled": False})

        self.assertEqual(tune["selected_audio_ai"], "clearvoice")
        self.assertEqual(tune["selected_vad"], "ten_vad")
        self.assertAlmostEqual(tune["ten_vad_threshold"], 0.58)
        self.assertIn("afftdn=nf=-34", filter_text)
        self.assertIn("volume=4.3", filter_text)
        self.assertNotIn("selected_vad", tune_without_vad)

    def test_external_audio_overlap_preprocess_creates_cleaned_wav(self):
        processor = VideoProcessor()
        calls = []
        enhanced = []

        def _write_wav(path):
            with open(path, "wb") as f:
                f.write(b"RIFF" + b"\0" * 4096)

        def fake_no_progress(cmd, *, label, timeout=None, env=None):
            _ = (timeout, env)
            calls.append((label, list(cmd)))
            _write_wav(str(cmd[-1]))
            return True

        def fake_progress(cmd, *, label, timeout=None, env=None):
            _ = (timeout, env)
            calls.append((label, list(cmd)))
            _write_wav(str(cmd[-1]))
            return True

        def fake_rnnoise(source_wav, target_wav):
            enhanced.append((source_wav, target_wav))
            _write_wav(target_wav)
            return True

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "sample.mp4")
            cleaned_wav = os.path.join(tmpdir, "cleaned.wav")
            _write_wav(video_path)

            settings = {
                "audio_preprocess_audio_overlap_enabled": True,
                "audio_preprocess_audio_overlap_min_sec": 0,
                "audio_preprocess_audio_overlap_chunk_sec": 30,
                "audio_preprocess_audio_overlap_workers": 2,
                "ffmpeg_filter_threads": 1,
            }
            with mock.patch.object(processor, "_run_media_command_no_progress", side_effect=fake_no_progress), \
                 mock.patch.object(processor, "_run_media_command", side_effect=fake_progress), \
                 mock.patch.object(processor, "_apply_rnnoise", side_effect=fake_rnnoise):
                ok, applied = processor._run_overlapped_audio_preprocess(
                    video_path=video_path,
                    work_dir=tmpdir,
                    base_name="sample",
                    cleaned_wav=cleaned_wav,
                    audio_ai="rnnoise",
                    settings=settings,
                    use_basic=True,
                    master_filter="anull",
                    active_filter="anull",
                    direct_start=0.0,
                    direct_end=90.0,
                )
            cleaned_exists = os.path.exists(cleaned_wav)

        self.assertTrue(ok)
        self.assertTrue(applied)
        self.assertTrue(cleaned_exists)
        self.assertEqual(len(enhanced), 3)
        self.assertGreaterEqual(sum(1 for label, _cmd in calls if label == "병렬 오디오 청크 추출"), 3)
        self.assertTrue(any(label == "청크 음성 향상 병합" for label, _cmd in calls))
        self.assertTrue(any("음량 평탄화" in label for label, _cmd in calls))

    def test_external_audio_overlap_preprocess_skips_partial_span(self):
        processor = VideoProcessor()
        settings = {
            "audio_preprocess_audio_overlap_enabled": True,
            "audio_preprocess_audio_overlap_min_sec": 0,
            "clearvoice_native_ffmpeg_enabled": False,
            "macos_native_fast_audio_flatten_enabled": False,
        }

        self.assertTrue(
            processor._can_overlap_preprocess_audio(
                settings,
                audio_ai="clearvoice",
                span_sec=300.0,
                is_partial=False,
            )
        )
        self.assertFalse(
            processor._can_overlap_preprocess_audio(
                settings,
                audio_ai="clearvoice",
                span_sec=300.0,
                is_partial=True,
            )
        )

    def test_clearvoice_uses_native_ffmpeg_fused_path_by_default(self):
        processor = VideoProcessor()

        self.assertTrue(processor._clearvoice_native_ffmpeg_enabled({}))
        self.assertTrue(processor._can_fuse_ffmpeg_preprocess("clearvoice", {}))
        self.assertFalse(
            processor._can_overlap_preprocess_audio(
                {"audio_preprocess_audio_overlap_enabled": True, "audio_preprocess_audio_overlap_min_sec": 0},
                audio_ai="clearvoice",
                span_sec=300.0,
                is_partial=False,
            )
        )

    def test_clearvoice_native_ffmpeg_can_be_disabled_for_legacy_model_path(self):
        processor = VideoProcessor()
        settings = {
            "clearvoice_native_ffmpeg_enabled": False,
            "macos_native_fast_audio_flatten_enabled": False,
        }

        self.assertFalse(processor._clearvoice_native_ffmpeg_enabled(settings))
        self.assertFalse(processor._can_fuse_ffmpeg_preprocess("clearvoice", settings))

    def test_clearvoice_apply_native_ffmpeg_without_python_clearvoice_package(self):
        processor = VideoProcessor()
        calls = []

        def _write_wav(path):
            with open(path, "wb") as f:
                f.write(b"RIFF" + b"\0" * 4096)

        def fake_run(cmd, *, label, timeout=None, env=None):
            _ = (timeout, env)
            calls.append((label, list(cmd)))
            _write_wav(str(cmd[-1]))
            return True

        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "source.wav")
            target = os.path.join(tmpdir, "target.wav")
            _write_wav(source)
            processor._clearvoice_runtime_settings = {"clearvoice_native_ffmpeg_enabled": True}
            with mock.patch.object(processor, "_run_media_command", side_effect=fake_run), \
                 mock.patch("core.audio.media_processor_audio.importlib.util.find_spec", return_value=None):
                ok = processor._apply_clearvoice(source, target)

        self.assertTrue(ok)
        self.assertEqual(calls[0][0], "ClearVoice Native FFmpeg")
        self.assertIn("-af", calls[0][1])

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

    def test_indoor_external_mic_uses_benchmarked_chunk_length(self):
        applied = apply_audio_preset({}, "실내-마이크유")

        self.assertEqual(applied["audio_preset"], "실내-마이크유")
        self.assertEqual(applied["ff_chunk"], 35)

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
        self.assertEqual(settings.get("selected_vad"), "silero")

    def test_media_processor_skips_auto_tune_when_benchmark_locked(self):
        processor = VideoProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = os.path.join(tmp, "user_settings.json")
            with open(settings_path, "w", encoding="utf-8") as handle:
                json.dump({"audio_preset_auto_benchmark_locked": True}, handle)
            with mock.patch.object(config, "DATASET_DIR", tmp):
                processor.set_auto_audio_tune_overrides({
                    "ff_hp": 190,
                    "selected_audio_ai": "clearvoice",
                    "selected_vad": "ten_vad",
                })
                locked = processor._load_all_settings()

        self.assertNotEqual(locked["ff_hp"], 190)
        self.assertNotEqual(locked.get("selected_audio_ai"), "clearvoice")
        self.assertEqual(locked.get("selected_vad"), "silero")

    def test_media_processor_runtime_overrides_survive_apple_m_plan(self):
        processor = VideoProcessor()
        processor._fast_mode_overrides = {
            "stt_selective_secondary_recheck_enabled": False,
            "stt_word_timestamps_mode": "off",
            "stt_word_timestamps_precision_enabled": False,
        }

        with mock.patch.object(config, "IS_APPLE_SILICON", True), \
             mock.patch.object(config, "DATASET_DIR", "/tmp/missing-settings-dir"):
            settings = processor._load_all_settings()

        self.assertFalse(settings["stt_selective_secondary_recheck_enabled"])
        self.assertEqual(settings["stt_word_timestamps_mode"], "off")
        self.assertFalse(settings["stt_word_timestamps_precision_enabled"])

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
        self.assertIn("highpass=f=150", cleanup)
        self.assertIn("lowpass=f=4600", cleanup)
        self.assertIn("acompressor=threshold=-24dB:ratio=3:attack=5:release=55", cleanup)
        self.assertIn("volume=3.2", cleanup)
        self.assertIn("alimiter=limit=0.93", cleanup)
        self.assertNotIn("dynaudnorm", cleanup)
        self.assertNotIn("loudnorm", cleanup)

    def test_deepfilter_fused_ffmpeg_filter_removes_duplicate_heavy_filters(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        fused = processor._build_fused_ffmpeg_filter("deepfilter", settings, use_basic=True)

        self.assertEqual(fused.count("afftdn="), 0)
        self.assertEqual(fused.count("loudnorm="), 0)
        self.assertEqual(fused.count("highpass="), 1)
        self.assertEqual(fused.count("lowpass="), 1)
        self.assertNotIn("dynaudnorm", fused)
        self.assertNotIn("speechnorm", fused)
        self.assertIn("volume=3.2", fused)
        self.assertIn("alimiter=limit=0.93", fused)

    def test_legacy_fused_ffmpeg_filter_can_be_restored_for_comparison(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({"macos_native_fast_audio_flatten_enabled": False}, "야외")

        fused = processor._build_fused_ffmpeg_filter("deepfilter", settings, use_basic=True)

        self.assertEqual(fused.count("afftdn="), 1)
        self.assertEqual(fused.count("loudnorm="), 1)
        self.assertIn("dynaudnorm", fused)
        self.assertIn("speechnorm", fused)
        self.assertIn("volume=4.8", fused)

    def test_audio_filter_none_skips_cleanup_filter_after_ffmpeg_preprocess(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "마이크 없음/풀속도")

        preprocess = processor._build_ffmpeg_preprocess_filter(settings)
        cleanup = processor._build_audio_cleanup_filter("none", settings)

        self.assertIn("highpass=f=110", preprocess)
        self.assertIn("afftdn=nf=-28", preprocess)
        self.assertEqual(cleanup, "anull")

    def test_rnnoise_uses_speech_preserve_cleanup_chain_without_demucs_settings(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        cleanup = processor._build_audio_cleanup_filter("rnnoise", settings)

        self.assertIn("highpass=f=150", cleanup)
        self.assertIn("lowpass=f=4600", cleanup)
        self.assertIn("acompressor=threshold=-24dB", cleanup)
        self.assertIn("volume=3.2", cleanup)
        self.assertIn("alimiter=limit=0.93", cleanup)
        self.assertNotIn("speechnorm", cleanup)
        self.assertNotIn("demucs", cleanup.lower())

    def test_auto_audio_quality_risk_prefers_clearvoice_over_rnnoise_even_for_long_media(self):
        profile = {
            "environment": "indoor",
            "noise_level": "medium",
            "low_rumble": False,
            "quiet": False,
            "hot_signal": False,
            "speech_confidence": 0.46,
        }
        features = {"speech_confidence": 0.46, "media_duration_sec": 7200.0}

        result = select_audio_candidate(profile, features, use_lora_prior=False)

        self.assertEqual(result["id"], "noisy_voice")
        self.assertEqual(result["settings"]["selected_audio_ai"], "clearvoice")
        self.assertIn("자막 품질", result["reason"])

    def test_auto_audio_duration_does_not_change_filter_choice(self):
        profile = {
            "environment": "outdoor",
            "noise_level": "high",
            "low_rumble": False,
            "quiet": False,
            "hot_signal": False,
            "speech_confidence": 0.6,
        }
        short = select_audio_candidate(profile, {"speech_confidence": 0.6, "media_duration_sec": 60.0}, use_lora_prior=False)
        long = select_audio_candidate(profile, {"speech_confidence": 0.6, "media_duration_sec": 10800.0}, use_lora_prior=False)

        self.assertEqual(short["settings"]["selected_audio_ai"], "clearvoice")
        self.assertEqual(long["settings"]["selected_audio_ai"], "clearvoice")
        self.assertEqual(short["id"], long["id"])

    def test_experimental_enhancers_use_light_cleanup_chain(self):
        processor = VideoProcessor()
        settings = apply_audio_preset({}, "야외")

        resemble_cleanup = processor._build_audio_cleanup_filter("resemble_enhance", settings)
        self.assertIn("highpass=f=150", resemble_cleanup)
        self.assertIn("lowpass=f=4600", resemble_cleanup)
        self.assertIn("acompressor=threshold=-24dB", resemble_cleanup)
        self.assertNotIn("speechnorm", resemble_cleanup)
        self.assertNotIn("loudnorm", resemble_cleanup)
        self.assertNotIn("afftdn", resemble_cleanup)

        clearvoice_cleanup = processor._build_audio_cleanup_filter("clearvoice", settings)
        self.assertIn("highpass=f=150", clearvoice_cleanup)
        self.assertIn("lowpass=f=4600", clearvoice_cleanup)
        self.assertIn("volume=3.2", clearvoice_cleanup)
        self.assertNotIn("speechnorm", clearvoice_cleanup)
        self.assertNotIn("loudnorm", clearvoice_cleanup)
        self.assertNotIn("afftdn", clearvoice_cleanup)

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
        self.assertTrue(filters)
        self.assertTrue(all("highpass=f=150" in value for value in filters))
        self.assertTrue(all("loudnorm" not in value for value in filters))

    def test_adaptive_chunk_audio_routing_applies_hysteresis_before_render(self):
        class RoutingProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                if index == 0:
                    return {
                        "audio_strategy": "clean_voice",
                        "audio_strategy_label": "깨끗한 음성",
                        "audio_tune_reason": "테스트 1",
                        "confidence": 0.84,
                        "feature_confidence": 0.84,
                        "settings": {"selected_audio_ai": "deepfilter", "selected_vad": "silero"},
                        "audio_profile": {"environment": "indoor", "noise_level": "low", "volatile_scene": False},
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                    }
                return {
                    "audio_strategy": "noisy_voice",
                    "audio_strategy_label": "잡음 음성",
                    "audio_tune_reason": "테스트 2",
                    "confidence": 0.81,
                    "feature_confidence": 0.81,
                    "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"},
                    "audio_profile": {"environment": "indoor", "noise_level": "low", "volatile_scene": False},
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = RoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_profile_memory_enabled": False,
                    "audio_chunk_route_switch_confirmation_enabled": False,
                    "audio_chunk_route_hysteresis_enabled": True,
                    "audio_chunk_route_hysteresis_margin": 0.05,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["deepfilter", "deepfilter"])
        self.assertEqual(routes[1]["audio_strategy"], "clean_voice")
        self.assertTrue(routes[1]["hysteresis_applied"])

    def test_adaptive_chunk_audio_routing_prefers_baseline_when_noisy_voice_is_not_clearly_better(self):
        class GuardProcessor(VideoProcessor):
            def _preview_chunk_audio_route(
                self,
                sample_path,
                *,
                route_features,
                route_profile,
                candidate_scores,
                settings,
                tmpdir,
                force=False,
            ):
                _ = (sample_path, route_features, route_profile, settings, tmpdir, force)
                rows = []
                for row in candidate_scores:
                    cid = str(row.get("id") or "")
                    if cid == "benchmark_locked_baseline":
                        rows.append(
                            {
                                "id": cid,
                                "label": "기본 High 유지",
                                "signature": row.get("signature"),
                                "preview_ok": True,
                                "score": 0.68,
                                "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                            }
                        )
                    else:
                        rows.append(
                            {
                                "id": cid,
                                "label": str(row.get("label") or cid),
                                "signature": row.get("signature"),
                                "preview_ok": True,
                                "score": 0.69,
                                "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"},
                            }
                        )
                rows.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
                return rows[0], rows

        processor = GuardProcessor()
        guarded = processor._maybe_apply_audio_route_baseline_guard(
            "/tmp/sample.wav",
            route_features={"high_band_ratio": 0.2, "low_band_ratio": 0.3},
            route_profile={"speech_confidence": 0.62, "noise_level": "high", "volatile_scene": False},
            candidate_scores=[
                {"id": "noisy_voice", "label": "Noisy Voice", "score": 0.93},
                {"id": "clean_voice", "label": "Clean Voice", "score": 0.44},
            ],
            selected_strategy="noisy_voice",
            selected_label="Noisy Voice",
            selected_confidence=0.69,
            selected_settings={"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"},
            preview_self_score=0.69,
            settings={"selected_audio_ai": "none", "selected_vad": "silero"},
            tmpdir="/tmp",
        )

        self.assertIsNotNone(guarded)
        self.assertTrue(bool(guarded.get("applied")))
        self.assertEqual(guarded.get("audio_strategy"), "benchmark_locked_baseline")
        self.assertGreaterEqual(float(guarded.get("margin") or 0.0), 0.05)

    def test_adaptive_chunk_audio_routing_keeps_specialist_route_for_challenging_audio_when_preview_gap_is_large(self):
        class GuardProcessor(VideoProcessor):
            def _preview_chunk_audio_route(
                self,
                sample_path,
                *,
                route_features,
                route_profile,
                candidate_scores,
                settings,
                tmpdir,
                force=False,
            ):
                _ = (sample_path, route_features, route_profile, settings, tmpdir, force)
                rows = []
                for row in candidate_scores:
                    cid = str(row.get("id") or "")
                    if cid == "benchmark_locked_baseline":
                        rows.append(
                            {
                                "id": cid,
                                "label": "기본 High 유지",
                                "signature": row.get("signature"),
                                "preview_ok": True,
                                "score": 0.63,
                                "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                            }
                        )
                    else:
                        rows.append(
                            {
                                "id": cid,
                                "label": str(row.get("label") or cid),
                                "signature": row.get("signature"),
                                "preview_ok": True,
                                "score": 0.76,
                                "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"},
                            }
                        )
                rows.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
                return rows[0], rows

        processor = GuardProcessor()
        guarded = processor._maybe_apply_audio_route_baseline_guard(
            "/tmp/sample.wav",
            route_features={"high_band_ratio": 0.2, "low_band_ratio": 0.3},
            route_profile={
                "speech_confidence": 0.63,
                "noise_level": "high",
                "volatile_scene": True,
                "mic_present": False,
                "environment": "outdoor",
            },
            candidate_scores=[
                {"id": "noisy_voice", "label": "Noisy Voice", "score": 0.93},
                {"id": "clean_voice", "label": "Clean Voice", "score": 0.44},
            ],
            selected_strategy="noisy_voice",
            selected_label="Noisy Voice",
            selected_confidence=0.76,
            selected_settings={"selected_audio_ai": "clearvoice", "selected_vad": "ten_vad"},
            preview_self_score=0.76,
            settings={"selected_audio_ai": "none", "selected_vad": "silero"},
            tmpdir="/tmp",
        )

        self.assertIsNotNone(guarded)
        self.assertFalse(bool(guarded.get("applied")))
        self.assertIn("adaptive route 유지", str(guarded.get("reason") or ""))

    def test_audio_route_high_noise_confidence_cap_prevents_stt2_hint_flooding(self):
        processor = VideoProcessor()

        # 변경 금지: X5 회귀에서 noise=high만으로 0.81 confidence 구간까지
        # STT2 힌트가 붙어 정확한 STT1 세그먼트가 흔들렸다. high-risk라도
        # 별도 confidence cap 이하일 때만 STT2 rescue를 켠다.
        self.assertFalse(processor._audio_route_secondary_recheck_hint(0.81, "high", {}))
        self.assertTrue(processor._audio_route_secondary_recheck_hint(0.70, "high", {}))
        self.assertTrue(processor._audio_route_secondary_recheck_hint(0.67, "medium", {}))

    def test_audio_route_confident_audio_filter_keeps_base_vad(self):
        processor = VideoProcessor()
        tune = {
            "selected_audio_ai": "clearvoice",
            "selected_vad": "ten_vad",
            "ten_vad_threshold": 0.58,
        }
        settings = {
            "audio_chunk_route_vad_enabled": True,
            "audio_chunk_route_vad_preserve_base_min_confidence": 0.78,
            "selected_vad": "silero",
            "vad_threshold": 0.36,
        }

        self.assertTrue(processor._audio_route_preserve_base_vad_for_confident_route(0.83, settings))
        preserved = processor._audio_route_with_base_vad_settings(tune, settings)

        self.assertEqual(preserved["selected_audio_ai"], "clearvoice")
        self.assertEqual(preserved["selected_vad"], "silero")
        self.assertEqual(preserved["vad_threshold"], 0.36)

    def test_adaptive_chunk_audio_routing_can_split_large_windows_for_environment_changes(self):
        processor = VideoProcessor()

        expanded = processor._maybe_expand_grouped_chunks_for_audio_route(
            [{"start": 0.0, "end": 180.0}],
            {
                "audio_chunk_route_split_enabled": True,
                "audio_chunk_route_max_span_sec": 120.0,
                "whisper_chunk_overlap_sec": 10.0,
            },
        )

        self.assertEqual(expanded, [{"start": 0.0, "end": 120.0}, {"start": 112.0, "end": 180.0}])

    def test_adaptive_chunk_audio_routing_selectively_splits_only_ambiguous_challenging_segments(self):
        processor = VideoProcessor()
        grouped = [
            {"start": 0.0, "end": 180.0},
            {"start": 180.0, "end": 360.0},
        ]
        route_logs = {
            0: {
                "audio_strategy": "noisy_voice",
                "confidence": 0.72,
                "feature_confidence": 0.61,
                "self_score": 0.72,
                "preview_route_switched": True,
                "candidate_scores": [
                    {"id": "noisy_voice", "score": 0.72},
                    {"id": "clean_voice", "score": 0.68},
                ],
                "preview_scores": [
                    {"id": "noisy_voice", "score": 0.72},
                    {"id": "clean_voice", "score": 0.66},
                ],
                "audio_profile": {
                    "noise_level": "high",
                    "volatile_scene": True,
                    "environment": "outdoor",
                    "mic_present": False,
                },
            },
            1: {
                "audio_strategy": "noisy_voice",
                "confidence": 0.95,
                "feature_confidence": 0.94,
                "self_score": 0.95,
                "preview_route_switched": False,
                "candidate_scores": [
                    {"id": "noisy_voice", "score": 0.95},
                    {"id": "clean_voice", "score": 0.71},
                ],
                "preview_scores": [
                    {"id": "noisy_voice", "score": 0.95},
                    {"id": "clean_voice", "score": 0.72},
                ],
                "audio_profile": {
                    "noise_level": "high",
                    "volatile_scene": False,
                    "environment": "outdoor",
                    "mic_present": False,
                },
            },
        }

        expanded = processor._selective_expand_grouped_chunks_for_audio_route(
            grouped,
            route_logs,
            {
                "audio_chunk_route_split_enabled": True,
                "audio_chunk_route_max_span_sec": 120.0,
                "audio_chunk_route_split_confidence_threshold": 0.8,
                "audio_chunk_route_split_candidate_gap_max": 0.07,
                "audio_chunk_route_split_preview_divergence_min": 0.08,
                "whisper_chunk_overlap_sec": 10.0,
            },
        )

        self.assertEqual(
            expanded,
            [
                {"start": 0.0, "end": 120.0},
                {"start": 112.0, "end": 180.0},
                {"start": 180.0, "end": 360.0},
            ],
        )

    def test_adaptive_chunk_audio_routing_keeps_long_specialist_chunk_when_route_is_confident(self):
        processor = VideoProcessor()

        should_split = processor._should_split_audio_route_segment(
            {"start": 0.0, "end": 180.0},
            {
                "audio_strategy": "noisy_voice",
                "confidence": 0.92,
                "feature_confidence": 0.90,
                "self_score": 0.92,
                "preview_route_switched": False,
                "candidate_scores": [
                    {"id": "noisy_voice", "score": 0.92},
                    {"id": "clean_voice", "score": 0.76},
                ],
                "preview_scores": [
                    {"id": "noisy_voice", "score": 0.92},
                    {"id": "clean_voice", "score": 0.75},
                ],
                "audio_profile": {
                    "noise_level": "high",
                    "volatile_scene": True,
                    "environment": "outdoor",
                    "mic_present": False,
                },
            },
            {
                "audio_chunk_route_split_enabled": True,
                "audio_chunk_route_max_span_sec": 120.0,
                "audio_chunk_route_split_confidence_threshold": 0.8,
                "audio_chunk_route_split_candidate_gap_max": 0.07,
                "audio_chunk_route_split_preview_divergence_min": 0.08,
                "whisper_chunk_overlap_sec": 10.0,
            },
        )

        self.assertFalse(should_split)

    def test_adaptive_chunk_audio_routing_does_not_undo_baseline_guard_with_hysteresis(self):
        class GuardedRoutingProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                _ = tmpdir
                if index == 0:
                    return {
                        "audio_strategy": "noisy_voice",
                        "audio_strategy_label": "잡음 음성",
                        "audio_tune_reason": "테스트 noisy",
                        "confidence": 0.83,
                        "self_score": 0.83,
                        "feature_confidence": 0.83,
                        "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "none"},
                        "audio_profile": {"environment": "outdoor", "noise_level": "high", "volatile_scene": False},
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                        "baseline_guard_applied": False,
                    }
                return {
                    "audio_strategy": "benchmark_locked_baseline",
                    "audio_strategy_label": "기본 High 유지",
                    "audio_tune_reason": "테스트 baseline",
                    "confidence": 0.72,
                    "self_score": 0.72,
                    "feature_confidence": 0.72,
                    "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                    "audio_profile": {"environment": "outdoor", "noise_level": "high", "volatile_scene": False},
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                    "baseline_guard_applied": True,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = GuardedRoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_hysteresis_enabled": True,
                    "audio_chunk_route_hysteresis_margin": 0.2,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["clearvoice", "none"])
        self.assertEqual(routes[1]["audio_strategy"], "benchmark_locked_baseline")
        self.assertEqual(routes[1]["audio_tune_settings"]["selected_audio_ai"], "none")
        self.assertFalse(routes[1].get("hysteresis_applied"))

    def test_adaptive_chunk_audio_routing_reuses_profile_memory_for_similar_chunks(self):
        class ProfileMemoryProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                _ = tmpdir
                profile = {
                    "environment": "outdoor",
                    "noise_level": "high",
                    "low_rumble": False,
                    "quiet": False,
                    "hot_signal": False,
                    "volatile_scene": False,
                    "speech_density": 0.82,
                    "speech_confidence": 0.7,
                    "mic_present": False,
                }
                if index == 0:
                    return {
                        "audio_strategy": "noisy_voice",
                        "audio_strategy_label": "잡음 음성",
                        "audio_tune_reason": "테스트 noisy",
                        "confidence": 0.78,
                        "self_score": 0.78,
                        "feature_confidence": 0.78,
                        "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "none"},
                        "audio_profile": dict(profile),
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                    }
                return {
                    "audio_strategy": "clip_fallback",
                    "audio_strategy_label": "기존 청크 유지",
                    "audio_tune_reason": "테스트 fallback",
                    "confidence": 0.52,
                    "self_score": 0.52,
                    "feature_confidence": 0.52,
                    "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                    "audio_profile": dict(profile),
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = ProfileMemoryProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_profile_memory_enabled": True,
                    "audio_chunk_route_profile_memory_min_confidence": 0.64,
                    "audio_chunk_route_profile_memory_margin": 0.04,
                    "audio_chunk_route_hysteresis_enabled": False,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["clearvoice", "clearvoice"])
        self.assertTrue(routes[1]["profile_memory_applied"])
        self.assertEqual(routes[1]["audio_strategy"], "noisy_voice")
        self.assertEqual(routes[1]["audio_tune_settings"]["selected_audio_ai"], "clearvoice")

    def test_adaptive_chunk_audio_routing_requires_confirmation_before_switching_profiles(self):
        class ConfirmationProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                _ = tmpdir
                profile = {"environment": "outdoor", "noise_level": "high", "volatile_scene": False}
                if index == 0:
                    return {
                        "audio_strategy": "clean_voice",
                        "audio_strategy_label": "깨끗한 음성",
                        "audio_tune_reason": "기준 chunk",
                        "confidence": 0.84,
                        "self_score": 0.84,
                        "feature_confidence": 0.84,
                        "settings": {"selected_audio_ai": "deepfilter", "selected_vad": "silero"},
                        "audio_profile": dict(profile),
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                    }
                return {
                    "audio_strategy": "noisy_voice",
                    "audio_strategy_label": "잡음 음성",
                    "audio_tune_reason": "한 번만 흔들리는 noisy chunk",
                    "confidence": 0.86,
                    "self_score": 0.86,
                    "feature_confidence": 0.86,
                    "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "none"},
                    "audio_profile": dict(profile),
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = ConfirmationProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_profile_memory_enabled": False,
                    "audio_chunk_route_switch_confirmation_enabled": True,
                    "audio_chunk_route_switch_confirmation_margin": 0.04,
                    "audio_chunk_route_switch_confirmation_strong_margin": 0.11,
                    "audio_chunk_route_switch_confirmation_min_streak": 2,
                    "audio_chunk_route_hysteresis_enabled": False,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["deepfilter", "deepfilter"])
        self.assertTrue(routes[1]["switch_confirmation_applied"])
        self.assertEqual(routes[1]["audio_strategy"], "clean_voice")

    def test_adaptive_chunk_audio_routing_switches_after_confirmed_repeated_profile(self):
        class ConfirmationProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                _ = tmpdir
                profile = {"environment": "outdoor", "noise_level": "high", "volatile_scene": False}
                if index == 0:
                    return {
                        "audio_strategy": "clean_voice",
                        "audio_strategy_label": "깨끗한 음성",
                        "audio_tune_reason": "기준 chunk",
                        "confidence": 0.84,
                        "self_score": 0.84,
                        "feature_confidence": 0.84,
                        "settings": {"selected_audio_ai": "deepfilter", "selected_vad": "silero"},
                        "audio_profile": dict(profile),
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                    }
                return {
                    "audio_strategy": "noisy_voice",
                    "audio_strategy_label": "잡음 음성",
                    "audio_tune_reason": "반복 확인되는 noisy chunk",
                    "confidence": 0.88 if index == 2 else 0.87,
                    "self_score": 0.88 if index == 2 else 0.87,
                    "feature_confidence": 0.88 if index == 2 else 0.87,
                    "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "none"},
                    "audio_profile": dict(profile),
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = ConfirmationProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [
                    {"start": 0.0, "end": 10.0},
                    {"start": 10.0, "end": 20.0},
                    {"start": 20.0, "end": 30.0},
                ],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_profile_memory_enabled": False,
                    "audio_chunk_route_switch_confirmation_enabled": True,
                    "audio_chunk_route_switch_confirmation_margin": 0.04,
                    "audio_chunk_route_switch_confirmation_strong_margin": 0.11,
                    "audio_chunk_route_switch_confirmation_min_streak": 2,
                    "audio_chunk_route_hysteresis_enabled": False,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["deepfilter", "deepfilter", "clearvoice"])
        self.assertTrue(routes[1]["switch_confirmation_applied"])
        self.assertTrue(routes[2]["switch_confirmation_approved"])
        self.assertEqual(routes[2]["audio_strategy"], "noisy_voice")

    def test_adaptive_chunk_audio_routing_profile_memory_respects_baseline_guard(self):
        class GuardRespectProcessor(VideoProcessor):
            def __init__(self):
                super().__init__()
                self.rendered_audio_ai = []

            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                _ = tmpdir
                profile = {
                    "environment": "outdoor",
                    "noise_level": "high",
                    "low_rumble": False,
                    "quiet": False,
                    "hot_signal": False,
                    "volatile_scene": False,
                    "speech_density": 0.82,
                    "speech_confidence": 0.7,
                    "mic_present": False,
                }
                if index == 0:
                    return {
                        "audio_strategy": "noisy_voice",
                        "audio_strategy_label": "잡음 음성",
                        "audio_tune_reason": "테스트 noisy",
                        "confidence": 0.78,
                        "self_score": 0.78,
                        "feature_confidence": 0.78,
                        "settings": {"selected_audio_ai": "clearvoice", "selected_vad": "none"},
                        "audio_profile": dict(profile),
                        "precision_review": False,
                        "secondary_recheck_hint": False,
                    }
                return {
                    "audio_strategy": "benchmark_locked_baseline",
                    "audio_strategy_label": "기본 High 유지",
                    "audio_tune_reason": "테스트 baseline guard",
                    "confidence": 0.58,
                    "self_score": 0.58,
                    "feature_confidence": 0.58,
                    "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                    "audio_profile": dict(profile),
                    "precision_review": False,
                    "secondary_recheck_hint": False,
                    "baseline_guard_applied": True,
                }

            def _write_adaptive_chunk_from_media(self, _media_path, out_path, _seg, settings, *, tmpdir):
                _ = tmpdir
                self.rendered_audio_ai.append(str(settings.get("selected_audio_ai") or "none"))
                with open(out_path, "wb") as f:
                    f.write(b"wav")
                return True

        processor = GuardRespectProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": False,
                    "audio_chunk_route_profile_memory_enabled": True,
                    "audio_chunk_route_profile_memory_min_confidence": 0.64,
                    "audio_chunk_route_profile_memory_margin": 0.04,
                    "audio_chunk_route_hysteresis_enabled": False,
                },
            )
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(processor.rendered_audio_ai, ["clearvoice", "none"])
        self.assertFalse(routes[1].get("profile_memory_applied"))
        self.assertEqual(routes[1]["audio_strategy"], "benchmark_locked_baseline")
        self.assertEqual(routes[1]["audio_tune_settings"]["selected_audio_ai"], "none")

    def test_adaptive_chunk_audio_routing_caps_parallel_workers(self):
        class RoutingProcessor(VideoProcessor):
            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                return {
                    "audio_strategy": "ffmpeg",
                    "audio_strategy_label": "기본",
                    "confidence": 0.8,
                    "settings": {"selected_audio_ai": "none", "selected_vad": "none"},
                    "audio_profile": {"environment": "indoor", "noise_level": "low"},
                }

            def _run_media_command_no_progress(self, cmd, *, label, timeout=None, env=None):
                with open(cmd[-1], "wb") as f:
                    f.write(b"wav")
                return True

        class ImmediateFuture:
            def __init__(self, result):
                self._result = result

            def result(self):
                return self._result

        max_workers_seen = []
        submitted = []

        class CapturingExecutor:
            def __init__(self, *, max_workers, thread_name_prefix=None):
                max_workers_seen.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn, item):
                submitted.append(item)
                return ImmediateFuture(fn(item))

        processor = RoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            with mock.patch(
                "core.audio.audio_runtime_services.runtime_parallel_worker_plan",
                return_value=(8, {"reductions": []}),
            ), mock.patch("core.audio.media_processor_audio.ThreadPoolExecutor", CapturingExecutor):
                ok = processor._write_adaptive_grouped_chunks_from_media(
                    media,
                    chunk_dir,
                    [{"start": 0.0, "end": 10.0}, {"start": 10.0, "end": 20.0}, {"start": 20.0, "end": 30.0}],
                    {
                        "use_basic_filter": True,
                        "audio_chunk_routing_enabled": True,
                        "audio_chunk_route_vad_enabled": False,
                        "audio_chunk_route_max_workers": 2,
                    },
                )

        self.assertTrue(ok)
        self.assertEqual(max_workers_seen, [2, 2])
        self.assertEqual(len(submitted), 6)

    def test_adaptive_audio_routing_respects_string_false_settings(self):
        self.assertFalse(VideoProcessor._adaptive_audio_routing_enabled({"audio_chunk_routing_enabled": "false"}))
        self.assertFalse(
            VideoProcessor._adaptive_audio_routing_enabled(
                {
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_routing_disabled": "true",
                }
            )
        )
        self.assertFalse(
            VideoProcessor._adaptive_audio_routing_enabled(
                {
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_routing_benchmark_locked": True,
                }
            )
        )

    def test_adaptive_chunk_audio_routing_respects_string_false_vad_flag(self):
        class NoVadRoutingProcessor(VideoProcessor):
            def _classify_chunk_audio_route(self, _media_path, _seg, _settings, *, index, tmpdir):
                return {
                    "audio_strategy": "ffmpeg",
                    "audio_strategy_label": "기본",
                    "confidence": 0.8,
                    "settings": {"selected_audio_ai": "none", "selected_vad": "silero"},
                    "audio_profile": {"environment": "indoor", "noise_level": "low"},
                }

            def _run_media_command_no_progress(self, cmd, *, label, timeout=None, env=None):
                with open(cmd[-1], "wb") as f:
                    f.write(b"wav")
                return True

            def _detect_vad_timestamps(self, *_args, **_kwargs):
                raise AssertionError("string false should disable route VAD")

        processor = NoVadRoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 0.0, "end": 10.0}],
                {
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": "false",
                },
            )

        self.assertTrue(ok)

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

    def test_adaptive_chunk_audio_routing_reuses_precomputed_vad_segments(self):
        class CachedVadRoutingProcessor(VideoProcessor):
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

            def _detect_vad_timestamps(self, *_args, **_kwargs):
                raise AssertionError("precomputed VAD segments should bypass chunk-level VAD rescans")

        processor = CachedVadRoutingProcessor()
        with tempfile.TemporaryDirectory() as tmp:
            media = os.path.join(tmp, "media.mp4")
            open(media, "wb").close()
            chunk_dir = os.path.join(tmp, "chunks")
            ok = processor._write_adaptive_grouped_chunks_from_media(
                media,
                chunk_dir,
                [{"start": 30.0, "end": 40.0}],
                {"use_basic_filter": True, "audio_chunk_routing_enabled": True, "audio_chunk_route_vad_enabled": True},
                precomputed_vad_segments=[
                    {"start": 30.2, "end": 31.1, "source": "ten_vad", "post_stt_align": True, "vad_word_filter": False}
                ],
            )
            with open(os.path.join(chunk_dir, "vad_strict.json"), "r", encoding="utf-8") as f:
                vad_rows = json.load(f)
            with open(os.path.join(chunk_dir, "audio_routes.json"), "r", encoding="utf-8") as f:
                routes = json.load(f)

        self.assertTrue(ok)
        self.assertEqual(vad_rows[0]["start"], 30.2)
        self.assertEqual(vad_rows[0]["end"], 31.1)
        self.assertEqual(vad_rows[0]["source"], "ten_vad")
        self.assertEqual(routes[0]["vad_segments"], 1)

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
