import os
import tempfile
import unittest
from unittest.mock import patch

from core.audio.audio_extract_backend_router import select_audio_extract_backend
from core.audio.stt_backend_router import select_stt_backend
from core.audio.vad_backend_router import select_vad_backend
from core.cut_boundary_backend_router import apply_cut_boundary_backend_settings, select_cut_boundary_backend
from core.optimization.profile_store import load_optimization_profile, save_optimization_profile
from core.optimization.quality_gate import quality_gate_passed
from core.optimization.types import OptimizationProfile


class RuntimeOptimizationProfileTests(unittest.TestCase):
    def test_profile_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = OptimizationProfile(
                selected_backends={"stt": "mlx", "vad": "ten_vad"},
                selected_models={"stt": "mlx-community/whisper-large-v3-turbo"},
            )
            save_optimization_profile(profile, dataset_dir=tmp)

            loaded = load_optimization_profile(dataset_dir=tmp)

            self.assertEqual(loaded.selected_backends["stt"], "mlx")
            self.assertEqual(loaded.selected_models["stt"], "mlx-community/whisper-large-v3-turbo")

    def test_quality_gate_preserves_stt_accuracy(self):
        baseline = {"cer": 0.10, "timing_mae_ms": 80.0}
        good = {"cer": 0.102, "timing_mae_ms": 120.0}
        bad = {"cer": 0.11, "timing_mae_ms": 120.0}

        self.assertTrue(quality_gate_passed(baseline, good, task="stt"))
        self.assertFalse(quality_gate_passed(baseline, bad, task="stt"))

    def test_vad_policy_can_choose_fast_or_quality(self):
        self.assertEqual(select_vad_backend("silero", {"vad_backend_policy": "fast"}).provider, "ten_vad")
        self.assertEqual(select_vad_backend("ten_vad", {"vad_backend_policy": "quality"}).provider, "silero")

    def test_audio_extract_fast_policy_lowers_direct_chunk_threshold_for_safe_filters(self):
        choice = select_audio_extract_backend(
            {"audio_extract_backend_policy": "fast"},
            audio_ai="deepfilter",
            span_sec=120.0,
        )

        self.assertEqual(choice.backend, "ffmpeg_direct_chunks")
        self.assertEqual(choice.direct_chunk_min_sec, 60.0)

    def test_audio_extract_auto_policy_uses_configured_direct_chunk_threshold(self):
        settings = {
            "audio_extract_backend_policy": "auto",
            "direct_ffmpeg_chunk_min_sec": 60.0,
            "runtime_backend_autotune_enabled": False,
        }

        self.assertEqual(
            select_audio_extract_backend(settings, audio_ai="deepfilter", span_sec=90.0).backend,
            "ffmpeg_direct_chunks",
        )
        self.assertEqual(
            select_audio_extract_backend(settings, audio_ai="deepfilter", span_sec=59.0).backend,
            "ffmpeg_cli",
        )

    def test_audio_extract_auto_policy_uses_native_direct_chunks_for_clearvoice_ffmpeg(self):
        settings = {
            "audio_extract_backend_policy": "auto",
            "direct_ffmpeg_chunk_min_sec": 60.0,
            "clearvoice_native_ffmpeg_enabled": True,
            "runtime_backend_autotune_enabled": False,
        }

        choice = select_audio_extract_backend(settings, audio_ai="clearvoice", span_sec=120.0)

        self.assertEqual(choice.backend, "ffmpeg_direct_chunks")
        self.assertEqual(choice.reason, "auto_long_media")

    def test_stt_fast_policy_prefers_mlx_turbo_on_mac_large_v3(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True):
            choice = select_stt_backend(
                "mlx-community/whisper-large-v3-mlx",
                {"stt_backend_policy": "fast", "runtime_backend_autotune_enabled": False},
            )

        self.assertEqual(choice.backend, "mlx")
        self.assertIn("turbo", choice.model)

    def test_stt_auto_policy_maps_generic_large_models_to_mac_native_mlx(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router._whisperkit_ready", return_value=False):
            choice = select_stt_backend(
                "large-v3-turbo",
                {"stt_backend_policy": "auto", "runtime_backend_autotune_enabled": False},
            )

        self.assertEqual(choice.backend, "mlx")
        self.assertEqual(choice.model, "mlx-community/whisper-large-v3-turbo")
        self.assertEqual(choice.reason, "mac_native_mlx_auto_alias")

    def test_komixv2_models_route_to_matching_backends(self):
        self.assertEqual(
            select_stt_backend(
                "whisper-medium-komixv2",
                {"stt_backend_policy": "quality", "runtime_backend_autotune_enabled": False},
            ).backend,
            "transformers",
        )
        self.assertEqual(
            select_stt_backend(
                "seastar105/whisper-medium-komixv2",
                {"stt_backend_policy": "quality", "runtime_backend_autotune_enabled": False},
            ).backend,
            "transformers",
        )
        with patch("core.audio.stt_backend_router.config.IS_MAC", True):
            self.assertEqual(
                select_stt_backend(
                    "youngouk/whisper-medium-komixv2-mlx",
                    {"stt_backend_policy": "quality", "runtime_backend_autotune_enabled": False},
                ).backend,
                "mlx",
            )

    def test_whisper_cpp_model_routes_to_native_backend(self):
        self.assertEqual(
            select_stt_backend(
                "whisper.cpp:large-v3-turbo",
                {"stt_backend_policy": "quality", "runtime_backend_autotune_enabled": False},
            ).backend,
            "whisper_cpp",
        )
        self.assertEqual(
            select_stt_backend(
                "whisper_cpp:/models/ggml-large-v3.bin",
                {"stt_backend_policy": "quality", "runtime_backend_autotune_enabled": False},
            ).backend,
            "whisper_cpp",
        )
        with patch("core.audio.stt_backend_router._whisperkit_ready", return_value=False), \
             patch("core.audio.stt_backend_router._whisper_cpp_ready", return_value=True):
            native_choice = select_stt_backend(
                "large-v3-turbo",
                {"stt_backend_policy": "native", "runtime_backend_autotune_enabled": False},
            )
        self.assertEqual(native_choice.backend, "whisper_cpp")
        self.assertEqual(native_choice.model, "whisper.cpp:large-v3-turbo")

    def test_native_stt_policy_prefers_whisperkit_when_ready(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router._whisper_cpp_ready", return_value=False), \
             patch("core.audio.stt_backend_router._whisperkit_ready", return_value=True):
            native_choice = select_stt_backend(
                "large-v3-turbo",
                {
                    "stt_backend_policy": "native",
                    "runtime_backend_autotune_enabled": False,
                },
            )

        self.assertEqual(native_choice.backend, "whisperkit_persistent")
        self.assertEqual(native_choice.model, "whisperkit-persistent:large-v3-v20240930_turbo_632MB")

    def test_native_stt_policy_falls_back_to_mlx_when_native_experimental_paths_are_not_ready_or_opted_in(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router._whisper_cpp_ready", return_value=False), \
             patch("core.audio.stt_backend_router._whisperkit_ready", return_value=True):
            native_choice = select_stt_backend(
                "large-v3-turbo",
                {
                    "stt_backend_policy": "native",
                    "runtime_backend_autotune_enabled": False,
                    "whisperkit_native_auto_enabled": False,
                },
            )

        self.assertEqual(native_choice.backend, "mlx")
        self.assertEqual(native_choice.model, "mlx-community/whisper-large-v3-turbo")

    def test_profiled_whisperkit_backend_gets_persistent_model_prefix(self):
        with patch("core.audio.stt_backend_router.profile_backend", return_value="whisperkit_persistent"), \
             patch("core.audio.stt_backend_router.profile_model", return_value="large-v3-turbo"):
            choice = select_stt_backend("large-v3-turbo", {"stt_backend_policy": "auto"})

        self.assertEqual(choice.backend, "whisperkit_persistent")
        self.assertEqual(choice.model, "whisperkit-persistent:large-v3-v20240930_turbo_632MB")

    def test_profiled_whisperkit_backend_does_not_capture_custom_mlx_models(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router.profile_backend", return_value="whisperkit_persistent"), \
             patch("core.audio.stt_backend_router.profile_model", return_value=""):
            choice = select_stt_backend(
                "youngouk/whisper-medium-komixv2-mlx",
                {"stt_backend_policy": "auto"},
            )

        self.assertEqual(choice.backend, "mlx")
        self.assertEqual(choice.model, "youngouk/whisper-medium-komixv2-mlx")
        self.assertEqual(choice.reason, "autotuned_backend_unsupported_whisperkit_fallback")

    def test_profiled_stt_model_does_not_replace_user_selected_model(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True), \
             patch("core.audio.stt_backend_router.profile_backend", return_value="mlx"), \
             patch("core.audio.stt_backend_router.profile_model", return_value="profile-stt-model"):
            choice = select_stt_backend(
                "user-selected-stt-model",
                {"stt_backend_policy": "auto"},
            )

        self.assertEqual(choice.backend, "mlx")
        self.assertEqual(choice.model, "user-selected-stt-model")
        self.assertEqual(choice.reason, "autotuned_backend")

    def test_explicit_whisperkit_prefix_falls_back_for_unsupported_custom_model(self):
        with patch("core.audio.stt_backend_router.config.IS_MAC", True):
            choice = select_stt_backend(
                "whisperkit-persistent:youngouk/whisper-medium-komixv2-mlx",
                {"stt_backend_policy": "auto", "runtime_backend_autotune_enabled": False},
            )

        self.assertEqual(choice.backend, "mlx")
        self.assertEqual(choice.model, "youngouk/whisper-medium-komixv2-mlx")
        self.assertEqual(choice.reason, "explicit_whisperkit_unsupported_model_fallback")

    def test_cut_boundary_router_uses_existing_preview_proxy(self):
        with tempfile.TemporaryDirectory() as tmp, patch("core.video_preview_proxy.config.DATASET_DIR", tmp):
            media_path = os.path.join(tmp, "source.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"media")
            from core.video_preview_proxy import preview_proxy_path_for

            proxy = preview_proxy_path_for(media_path)
            os.makedirs(os.path.dirname(proxy), exist_ok=True)
            with open(proxy, "wb") as handle:
                handle.write(b"proxy")

            choice = select_cut_boundary_backend(media_path, {"cut_boundary_backend_policy": "fast"})

        self.assertEqual(choice.backend, "opencv_proxy_fast")
        self.assertEqual(choice.scan_path, proxy)
        self.assertTrue(choice.use_proxy)

    def test_cut_boundary_auto_policy_uses_native_cpp_when_available(self):
        with patch("core.native_cut_boundary.native_cut_boundary_enabled", return_value=True):
            choice = select_cut_boundary_backend(
                "clip.mp4",
                {"cut_boundary_backend_policy": "auto", "runtime_backend_autotune_enabled": False},
            )

        self.assertEqual(choice.backend, "native_opencv")
        self.assertEqual(choice.reason, "auto_native_cpp_available")

    def test_fast_cut_policy_caps_opencv_thread_multiplication(self):
        settings = apply_cut_boundary_backend_settings({"cut_boundary_backend_policy": "fast"})

        self.assertEqual(settings["scan_cut_cv2_threads_per_worker"], 1)
        self.assertTrue(settings["scan_cut_pioneer_sequential_decode_enabled"])
        self.assertTrue(settings["scan_cut_ffmpeg_scene_prepass_enabled"])
        self.assertTrue(settings["scan_cut_ffmpeg_scene_replace_opencv_enabled"])
        self.assertEqual(settings["scan_cut_pioneer_workers"], 4)


if __name__ == "__main__":
    unittest.main()
