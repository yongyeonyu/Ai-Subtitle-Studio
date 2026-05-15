from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.runtime_eta import add_history, build_runtime_eta_payload, get_expected_time


class RuntimeETAPayloadTests(unittest.TestCase):
    def test_build_payload_preserves_legacy_true_only_string_bool_behavior(self):
        payload = build_runtime_eta_payload(
            "QUALITY:STT:test|LLM:none|DIA:X",
            60.0,
            settings={
                "stt_quality_preset": "balanced",
                "stt_ensemble_enabled": "maybe",
                "cut_boundary_cache_enabled": "",
                "vad_detection_cache_enabled": "yes",
                "stt_persistent_runtime_reuse_enabled": "unknown",
                "audio_preset_auto_disabled": "on",
            },
            media_info={"duration": 60.0, "fps": 30.0, "width": 1920, "height": 1080},
            runtime_flags={"prefetch_audio_hit": "mystery", "likely_warm_start": ""},
            store_path="/tmp/runtime-eta-string-bool.json",
        )

        self.assertFalse(payload["variant"]["stt_ensemble_enabled"])
        self.assertFalse(payload["runtime"]["cut_boundary_cache_enabled"])
        self.assertTrue(payload["runtime"]["vad_cache_enabled"])
        self.assertFalse(payload["runtime"]["stt_runtime_reuse_enabled"])
        self.assertFalse(payload["runtime"]["prefetch_audio_hit"])
        self.assertFalse(payload["runtime"]["likely_warm_start"])
        self.assertFalse(payload["runtime"]["auto_audio_tune_enabled"])

    def test_build_payload_contains_variant_media_and_cache_features(self):
        payload = build_runtime_eta_payload(
            "QUALITY:STT:test|LLM:codex|DIA:O",
            180.0,
            settings={
                "stt_quality_preset": "high",
                "selected_whisper_model": "stt-primary",
                "selected_whisper_model_secondary": "stt-secondary",
                "stt_ensemble_enabled": True,
                "selected_model": "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
                "selected_llm_provider": "openai",
                "selected_vad": "silero",
                "selected_audio_ai": "deepfilter",
                "max_speakers": 2,
                "cut_boundary_cache_enabled": True,
                "vad_detection_cache_enabled": True,
                "stt_persistent_runtime_reuse_enabled": True,
                "prefetch_ahead": 3,
            },
            media_info={"duration": 180.0, "fps": 59.94, "width": 3840, "height": 2160},
            startup_diagnostic={
                "audio": {"quality": {"score": 88}},
                "cut_density": {"per_minute": 1.75},
                "speakers": {"count": 2},
            },
            queue_index=1,
            total_files=3,
            runtime_flags={"likely_warm_start": True},
            store_path="/tmp/runtime-eta-test.json",
        )

        self.assertEqual(payload["variant"]["mode"], "precise")
        self.assertEqual(payload["variant"]["stt_secondary"], "stt-secondary")
        self.assertTrue(payload["variant"]["diarization_enabled"])
        self.assertEqual(payload["media"]["fps"], 59.94)
        self.assertEqual(payload["media"]["pixel_count"], 3840 * 2160)
        self.assertEqual(payload["media"]["audio_quality_score"], 88.0)
        self.assertEqual(payload["media"]["speaker_hint"], 2)
        self.assertEqual(payload["runtime"]["cache_state"], "warm")
        self.assertTrue(payload["runtime"]["likely_warm_start"])

    def test_build_payload_includes_post_generation_roughcut_eta_when_enabled(self):
        payload = build_runtime_eta_payload(
            "QUALITY:STT:test|LLM:roughcut|DIA:X",
            600.0,
            settings={
                "stt_quality_preset": "balanced",
                "editor_roughcut_draft_enabled": True,
                "roughcut_llm_enabled": True,
                "roughcut_run_after_subtitle_generation": True,
                "roughcut_llm_use_override": True,
                "roughcut_llm_provider": "ollama",
                "roughcut_llm_model": "roughcut-local",
            },
            media_info={"duration": 600.0, "fps": 30.0, "width": 1920, "height": 1080},
            store_path="/tmp/runtime-eta-roughcut.json",
        )

        self.assertTrue(payload["runtime"]["roughcut_post_generation_enabled"])
        self.assertGreater(payload["runtime"]["roughcut_estimated_sec"], 0.0)
        self.assertGreaterEqual(payload["runtime"]["roughcut_chunk_count"], 1)
        self.assertEqual(payload["variant"]["roughcut_llm_provider"], "ollama")
        self.assertEqual(payload["variant"]["roughcut_llm_model"], "roughcut-local")

    def test_get_expected_time_prefers_native_prediction_when_available(self):
        with mock.patch("core.runtime_eta.request_native_core_task", return_value={"predicted_processing_sec": 123.4}):
            predicted = get_expected_time(
                "QUALITY:STT:test|LLM:codex|DIA:X",
                300.0,
                settings={"stt_quality_preset": "balanced"},
                media_info={"duration": 300.0, "fps": 30.0, "width": 1920, "height": 1080},
                store_path="/tmp/runtime-eta-native.json",
            )
        self.assertEqual(predicted, 123.4)

    def test_get_expected_time_adds_roughcut_eta_to_native_prediction(self):
        settings = {
            "stt_quality_preset": "balanced",
            "editor_roughcut_draft_enabled": True,
            "roughcut_llm_enabled": True,
            "roughcut_run_after_subtitle_generation": True,
            "roughcut_llm_use_override": True,
            "roughcut_llm_provider": "ollama",
            "roughcut_llm_model": "roughcut-local",
        }
        payload = build_runtime_eta_payload(
            "QUALITY:STT:test|LLM:roughcut|DIA:X",
            600.0,
            settings=settings,
            media_info={"duration": 600.0, "fps": 30.0, "width": 1920, "height": 1080},
            store_path="/tmp/runtime-eta-native-roughcut.json",
        )
        expected = float(payload["runtime"]["roughcut_estimated_sec"] or 0.0)
        with mock.patch("core.runtime_eta.request_native_core_task", return_value={"predicted_processing_sec": 123.4}):
            predicted = get_expected_time(
                "QUALITY:STT:test|LLM:roughcut|DIA:X",
                600.0,
                settings=settings,
                media_info={"duration": 600.0, "fps": 30.0, "width": 1920, "height": 1080},
                store_path="/tmp/runtime-eta-native-roughcut.json",
            )
        self.assertAlmostEqual(predicted, 123.4 + expected, places=3)

    def test_add_history_fallback_writes_new_schema_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = str(Path(tmp) / "time_history.json")
            with mock.patch("core.runtime_eta.request_native_core_task", return_value=None):
                add_history(
                    "QUALITY:STT:test|LLM:codex|DIA:X",
                    240.0,
                    96.0,
                    settings={
                        "stt_quality_preset": "balanced",
                        "selected_whisper_model": "stt-primary",
                        "selected_model": "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
                        "selected_llm_provider": "openai",
                    },
                    media_info={"duration": 240.0, "fps": 30.0, "width": 1920, "height": 1080},
                    store_path=store_path,
                )

            saved = Path(store_path).read_text(encoding="utf-8")
            self.assertIn("ai_subtitle_studio.runtime_eta_store.v2", saved)
            self.assertIn("\"variants\"", saved)
            self.assertIn("\"runs\"", saved)

    def test_get_expected_time_reuses_cached_history_store_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = str(Path(tmp) / "time_history.json")
            Path(store_path).write_text('{"schema":"ai_subtitle_studio.runtime_eta_store.v2","weights":{"fixed_overhead_sec":10.0},"variants":{},"runs":[]}', encoding="utf-8")
            with mock.patch("core.runtime_eta.request_native_core_task", return_value=None), \
                 mock.patch("core.runtime_eta.read_json_file", wraps=__import__("core.runtime_eta", fromlist=["read_json_file"]).read_json_file) as read_mock:
                get_expected_time(
                    "QUALITY:STT:test|LLM:none|DIA:X",
                    120.0,
                    settings={"stt_quality_preset": "balanced"},
                    media_info={"duration": 120.0, "fps": 30.0, "width": 1920, "height": 1080},
                    store_path=store_path,
                )
                get_expected_time(
                    "QUALITY:STT:test|LLM:none|DIA:X",
                    120.0,
                    settings={"stt_quality_preset": "balanced"},
                    media_info={"duration": 120.0, "fps": 30.0, "width": 1920, "height": 1080},
                    store_path=store_path,
                )

            self.assertEqual(read_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
