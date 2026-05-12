import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runtime import config


class SettingsMaterializationTests(unittest.TestCase):
    def test_load_settings_materializes_dataset_user_settings(self):
        from core import settings as settings_module

        original_dataset_dir = config.DATASET_DIR
        original_override = settings_module.runtime_settings_override()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "custom_defaults.json").write_text(
                json.dumps({"custom_default_knob": 123, "llm_threads": 5}),
                encoding="utf-8",
            )
            Path(tmp, "user_settings.json").write_text(
                json.dumps(
                    {
                        "google_api_key": "google-secret",
                        "openai_api_key": "openai-secret",
                        "huggingface_token": "hf-secret",
                        "google_api_key_saved": True,
                        "openai_api_key_saved": True,
                        "huggingface_token_saved": True,
                    }
                ),
                encoding="utf-8",
            )
            Path(tmp, "folder_settings.json").write_text(
                json.dumps({"nas_path": "/Volumes/video", "icloud_stt_quality_preset": "balanced"}),
                encoding="utf-8",
            )
            try:
                config.DATASET_DIR = tmp
                settings_module.clear_runtime_settings_override()

                loaded = settings_module.load_settings()
                saved = json.loads(Path(tmp, "user_settings.json").read_text(encoding="utf-8"))

                self.assertEqual(saved["custom_default_knob"], 123)
                self.assertEqual(saved["llm_threads"], 5)
                self.assertIn("default_llm_prompt", saved)
                self.assertTrue(saved["default_llm_prompt"].startswith("너는 한국어 유튜브 자막 QA 편집자다"))
                self.assertEqual(saved["user_prompt"], "")
                self.assertEqual(saved["editor_roughcut_draft_prompt"], "")
                self.assertIn("selected_audio_ai", saved["_auto_managed_by_lora"])
                self.assertNotIn("google_api_key", saved)
                self.assertNotIn("openai_api_key", saved)
                self.assertNotIn("huggingface_token", saved)
                self.assertTrue(saved["google_api_key_saved"])
                self.assertTrue(saved["openai_api_key_saved"])
                self.assertTrue(saved["huggingface_token_saved"])
                self.assertEqual(saved["nas_path"], "/Volumes/video")
                self.assertEqual(saved["icloud_stt_quality_preset"], "balanced")
                self.assertEqual(loaded["custom_default_knob"], 123)
            finally:
                config.DATASET_DIR = original_dataset_dir
                settings_module.set_runtime_settings_override(original_override or None)

    def test_materialization_preserves_user_selected_subtitle_quality(self):
        from core.settings_profiles import materialize_user_settings

        materialized = materialize_user_settings(
            {
                "simple_operation_mode": "auto",
                "auto_start_mode": "precise",
                "stt_quality_preset": "precise",
            }
        )

        self.assertEqual(materialized["simple_operation_mode"], "high")
        self.assertEqual(materialized["subtitle_mode"], "high")
        self.assertEqual(materialized["auto_start_mode"], "precise")
        self.assertEqual(materialized["stt_quality_preset"], "precise")
        self.assertGreaterEqual(materialized["runtime_native_threads"], 8)
        self.assertLessEqual(materialized["runtime_native_threads"], max(8, os.cpu_count() or 8))
        self.assertTrue(materialized["runtime_native_text_similarity_enabled"])
        self.assertTrue(materialized["runtime_native_cut_boundary_enabled"])
        self.assertTrue(materialized["ollama_python_client_enabled"])
        self.assertFalse(materialized["runtime_monitor_terminal_log_enabled"])
        self.assertEqual(materialized["ffmpeg_filter_threads"], 8)
        self.assertTrue(materialized["wav_pcm_fast_chunk_extract"])
        self.assertTrue(materialized["direct_ffmpeg_chunk_extract"])
        self.assertEqual(materialized["direct_ffmpeg_chunk_min_sec"], 1.0)
        self.assertTrue(materialized["direct_ffmpeg_chunk_batch_extract"])
        self.assertEqual(materialized["direct_ffmpeg_chunk_batch_size"], 8)
        self.assertEqual(materialized["direct_ffmpeg_chunk_batch_max_span_sec"], 240.0)
        self.assertTrue(materialized["clearvoice_native_ffmpeg_enabled"])
        self.assertTrue(materialized["macos_native_fast_audio_flatten_enabled"])
        self.assertEqual(materialized["macos_native_fast_audio_flatten_volume"], 3.2)
        self.assertEqual(materialized["stt_backend_policy"], "native")
        self.assertEqual(materialized["audio_extract_backend_policy"], "native")
        self.assertEqual(materialized["cut_boundary_backend_policy"], "native")
        self.assertTrue(materialized["whisperkit_native_auto_enabled"])
        self.assertTrue(materialized["autopilot_enabled"])

    def test_materialize_user_settings_strips_plaintext_api_secrets(self):
        from core.settings_profiles import materialize_user_settings

        materialized = materialize_user_settings(
            {
                "selected_model": "unit-test-model",
                "google_api_key": "google-secret",
                "openai_api_key": "openai-secret",
                "huggingface_token": "hf-secret",
                "google_api_key_saved": True,
                "openai_api_key_saved": True,
                "huggingface_token_saved": True,
            }
        )

        self.assertNotIn("google_api_key", materialized)
        self.assertNotIn("openai_api_key", materialized)
        self.assertNotIn("huggingface_token", materialized)
        self.assertTrue(materialized["google_api_key_saved"])
        self.assertTrue(materialized["openai_api_key_saved"])
        self.assertTrue(materialized["huggingface_token_saved"])

    def test_materialize_user_settings_enables_roughcut_autorun_when_roughcut_is_enabled(self):
        from core.settings_profiles import materialize_user_settings

        materialized = materialize_user_settings(
            {
                "editor_roughcut_draft_enabled": True,
                "roughcut_llm_enabled": True,
                "roughcut_run_after_subtitle_generation": False,
            }
        )

        self.assertTrue(materialized["roughcut_run_after_subtitle_generation"])

    def test_materialize_user_settings_keeps_roughcut_autorun_off_when_llm_is_disabled(self):
        from core.settings_profiles import materialize_user_settings

        materialized = materialize_user_settings(
            {
                "editor_roughcut_draft_enabled": True,
                "roughcut_llm_enabled": False,
                "roughcut_run_after_subtitle_generation": False,
            }
        )

        self.assertFalse(materialized["roughcut_run_after_subtitle_generation"])

    def test_project_data_manager_save_writes_materialized_settings(self):
        from core.project import data_manager

        original_dataset_dir = config.DATASET_DIR
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(data_manager, "DATASET_DIR", tmp),
                patch.object(data_manager, "SETTINGS_FILE", str(Path(tmp, "user_settings.json"))),
                patch.object(data_manager, "CUSTOM_DEFAULTS_FILE", str(Path(tmp, "custom_defaults.json"))),
            ):
                try:
                    config.DATASET_DIR = tmp
                    data_manager.save_settings(
                        {
                            "selected_model": "unit-test-model",
                            "google_api_key": "google-secret",
                            "openai_api_key": "openai-secret",
                            "huggingface_token": "hf-secret",
                            "google_api_key_saved": True,
                            "openai_api_key_saved": True,
                            "huggingface_token_saved": True,
                        }
                    )
                    saved = json.loads(Path(tmp, "user_settings.json").read_text(encoding="utf-8"))

                    self.assertEqual(saved["selected_model"], "unit-test-model")
                    self.assertIn("default_llm_prompt", saved)
                    self.assertIn("selected_whisper_model", saved)
                    self.assertIn("nas_path", saved)
                    self.assertEqual(saved["_settings_storage"], "dataset/user_settings.json")
                    self.assertNotIn("google_api_key", saved)
                    self.assertNotIn("openai_api_key", saved)
                    self.assertNotIn("huggingface_token", saved)
                    self.assertTrue(saved["google_api_key_saved"])
                    self.assertTrue(saved["openai_api_key_saved"])
                    self.assertTrue(saved["huggingface_token_saved"])
                finally:
                    config.DATASET_DIR = original_dataset_dir

    def test_load_settings_recovers_from_backup_when_user_settings_is_partial_json(self):
        from core import settings as settings_module

        original_dataset_dir = config.DATASET_DIR
        original_override = settings_module.runtime_settings_override()
        with tempfile.TemporaryDirectory() as tmp:
            user_path = Path(tmp, "user_settings.json")
            user_path.write_text('{"selected_model"', encoding="utf-8")
            user_path.with_suffix(user_path.suffix + ".bak").write_text(
                json.dumps({"selected_model": "backup-model", "selected_llm_provider": "ollama", "restored_marker": True}),
                encoding="utf-8",
            )
            try:
                config.DATASET_DIR = tmp
                settings_module.clear_runtime_settings_override()

                loaded = settings_module.load_settings()
                repaired = json.loads(user_path.read_text(encoding="utf-8"))

                self.assertTrue(loaded["restored_marker"])
                self.assertEqual(repaired["selected_model"], "backup-model")
            finally:
                config.DATASET_DIR = original_dataset_dir
                settings_module.set_runtime_settings_override(original_override or None)

    def test_save_settings_writes_atomic_json_and_backup(self):
        from core import settings as settings_module

        original_dataset_dir = config.DATASET_DIR
        original_override = settings_module.runtime_settings_override()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                config.DATASET_DIR = tmp
                settings_module.clear_runtime_settings_override()

                settings_module.save_settings({"selected_model": "atomic-model", "selected_llm_provider": "ollama"})

                user_path = Path(tmp, "user_settings.json")
                backup_path = Path(tmp, "user_settings.json.bak")
                saved = json.loads(user_path.read_text(encoding="utf-8"))
                backup = json.loads(backup_path.read_text(encoding="utf-8"))

                self.assertEqual(saved["selected_model"], "atomic-model")
                self.assertEqual(backup["selected_model"], "atomic-model")
                self.assertEqual(list(Path(tmp).glob(".tmp-*.json")), [])
            finally:
                config.DATASET_DIR = original_dataset_dir
                settings_module.set_runtime_settings_override(original_override or None)

    def test_path_manager_mirrors_folder_settings_to_user_settings(self):
        from core import path_manager

        original_dataset_dir = config.DATASET_DIR
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp, "folder_settings.json")
            user_path = Path(tmp, "user_settings.json")
            with patch.object(path_manager, "SETTINGS_FILE", str(folder_path)):
                try:
                    config.DATASET_DIR = tmp
                    path_manager.save_settings({"nas_path": "/Volumes/nas", "watch_folders": ["/tmp/media"]})
                    saved = json.loads(user_path.read_text(encoding="utf-8"))

                    self.assertEqual(saved["nas_path"], "/Volumes/nas")
                    self.assertEqual(saved["watch_folders"], ["/tmp/media"])
                finally:
                    config.DATASET_DIR = original_dataset_dir


if __name__ == "__main__":
    unittest.main()
