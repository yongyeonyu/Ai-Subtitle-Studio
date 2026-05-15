import unittest

from core.project.project_model_settings import (
    build_model_settings_summary,
    build_model_settings_snapshot,
    extract_model_settings,
    merge_project_model_settings,
    project_model_settings_snapshot,
    project_model_settings_summary,
    restore_project_model_settings,
    store_project_model_settings_snapshot,
)


class ProjectModelSettingsTests(unittest.TestCase):
    def test_build_model_settings_summary_keeps_inherit_rules_without_ui_noise(self):
        summary = build_model_settings_summary(
            {
                "selected_model": "exaone",
                "selected_llm_provider": "ollama",
                "selected_whisper_model": "primary-ko",
                "stt_ensemble_enabled": True,
                "selected_whisper_model_secondary": "secondary-large",
                "roughcut_llm_enabled": True,
                "roughcut_llm_use_override": False,
                "roughcut_llm_provider": "ignored",
                "roughcut_llm_model": "ignored",
                "ui_only_key": "ignored",
            }
        )

        self.assertEqual(summary["stt1"], "primary-ko")
        self.assertTrue(summary["stt2_enabled"])
        self.assertEqual(summary["stt2"], "secondary-large")
        self.assertEqual(summary["subtitle_llm"], "exaone")
        self.assertEqual(summary["roughcut_llm_provider"], "inherit")
        self.assertEqual(summary["roughcut_llm"], "exaone")

    def test_extract_model_settings_prefers_snapshot_settings_and_filters_unknown_keys(self):
        project = {
            "model_settings": {
                "settings": {
                    "selected_model": "exaone",
                    "selected_vad": "silero",
                    "ui_only_key": "ignored",
                }
            },
            "user_settings": {
                "selected_model": "legacy",
                "selected_audio_ai": "deepfilter",
            },
        }

        extracted = extract_model_settings(project)

        self.assertEqual(extracted["selected_model"], "exaone")
        self.assertEqual(extracted["selected_vad"], "silero")
        self.assertNotIn("ui_only_key", extracted)
        self.assertNotIn("selected_audio_ai", extracted)

    def test_snapshot_and_merge_keep_model_subset_without_extra_copy_requirements(self):
        settings = {
            "selected_model": "exaone",
            "selected_llm_provider": "ollama",
            "selected_whisper_model": "primary-ko",
            "roughcut_llm_enabled": True,
            "roughcut_llm_use_override": False,
        }

        snapshot = build_model_settings_snapshot(settings)
        merged = merge_project_model_settings({"theme": "dark"}, {"model_settings": snapshot})

        self.assertEqual(snapshot["models"]["roughcut_llm"], "exaone")
        self.assertEqual(merged["selected_model"], "exaone")
        self.assertEqual(merged["theme"], "dark")

    def test_extract_model_settings_falls_back_to_legacy_user_settings_and_defaults(self):
        extracted = extract_model_settings(
            {
                "user_settings": {
                    "selected_audio_ai": "deepfilter",
                    "selected_model": "legacy-model",
                    "ui_only_key": "ignored",
                }
            }
        )

        self.assertEqual(extracted["selected_audio_ai"], "deepfilter")
        self.assertEqual(extracted["selected_model"], "legacy-model")
        self.assertEqual(extracted["preprocess_engine"], "FFMPEG")
        self.assertNotIn("ui_only_key", extracted)

    def test_store_project_model_settings_snapshot_updates_or_backfills_snapshot(self):
        project = {}

        snapshot = store_project_model_settings_snapshot(
            project,
            {"selected_model": "exaone", "selected_audio_ai": "deepfilter"},
            user_settings_provided=True,
        )
        backfilled = store_project_model_settings_snapshot(
            {"user_settings": {"selected_model": "legacy-model"}},
            user_settings_provided=False,
        )

        self.assertEqual(project["user_settings"]["selected_model"], "exaone")
        self.assertEqual(snapshot["settings"]["selected_audio_ai"], "deepfilter")
        self.assertEqual(project["model_settings"]["schema"], "ai_model_settings.v1")
        self.assertEqual(backfilled["settings"]["selected_model"], "legacy-model")

    def test_project_model_settings_snapshot_and_summary_can_build_from_legacy_project(self):
        project = {
            "user_settings": {
                "selected_audio_ai": "deepfilter",
                "selected_whisper_model": "primary-ko",
                "selected_model": "exaone",
                "selected_llm_provider": "ollama",
            }
        }

        snapshot = project_model_settings_snapshot(project, build_if_missing=True)
        summary = project_model_settings_summary(project, build_if_missing=True)

        self.assertEqual(snapshot["settings"]["selected_model"], "exaone")
        self.assertEqual(summary["stt1"], "primary-ko")
        self.assertEqual(summary["subtitle_llm"], "exaone")

    def test_project_model_settings_summary_read_does_not_materialize_snapshot(self):
        project = {
            "user_settings": {
                "selected_whisper_model": "primary-ko",
                "selected_model": "exaone",
                "selected_llm_provider": "ollama",
            }
        }

        summary = project_model_settings_summary(project, build_if_missing=True)
        extracted = extract_model_settings(project)

        self.assertEqual(summary["stt1"], "primary-ko")
        self.assertEqual(extracted["selected_model"], "exaone")
        self.assertNotIn("model_settings", project)

    def test_project_model_settings_summary_can_fallback_from_snapshot_settings_when_models_missing(self):
        project = {
            "model_settings": {
                "settings": {
                    "selected_model": "exaone",
                    "selected_llm_provider": "ollama",
                    "selected_whisper_model": "primary-ko",
                }
            }
        }

        summary = project_model_settings_summary(project)

        self.assertEqual(summary["stt1"], "primary-ko")
        self.assertEqual(summary["subtitle_llm"], "exaone")

    def test_extract_model_settings_from_snapshot_returns_independent_copy(self):
        project = {
            "model_settings": {
                "settings": {
                    "selected_model": "exaone",
                    "selected_whisper_model": "primary-ko",
                }
            }
        }

        extracted = extract_model_settings(project)
        extracted["selected_model"] = "mutated"

        self.assertEqual(project["model_settings"]["settings"]["selected_model"], "exaone")

    def test_restore_project_model_settings_returns_selected_and_merged_views(self):
        project = {
            "model_settings": {
                "settings": {
                    "selected_model": "exaone",
                    "selected_whisper_model": "primary-ko",
                }
            }
        }

        selected, merged = restore_project_model_settings({"theme": "dark"}, project)
        selected["selected_model"] = "mutated"

        self.assertEqual(merged["selected_model"], "exaone")
        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(project["model_settings"]["settings"]["selected_model"], "exaone")


if __name__ == "__main__":
    unittest.main()
