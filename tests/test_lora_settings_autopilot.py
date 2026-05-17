import json
import tempfile
import unittest
from pathlib import Path

from core.personalization.lora_storage import append_multimodal_lora_context_rows, initialize_lora_personalization_store, load_best_settings, store_paths
from core.personalization.lora_optimizer import optimize_settings_for_media
from core.personalization.settings_autopilot import AUTOPILOT_METADATA_KEY, apply_lora_user_settings_autopilot


class LoraSettingsAutopilotTests(unittest.TestCase):
    def test_autopilot_smoothly_promotes_safe_lora_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            user_settings = Path(tmpdir, "user_settings.json")
            user_settings.write_text(
                json.dumps(
                    {
                        "selected_audio_ai": "deepfilter",
                        "continuous_threshold": 2.0,
                        "split_length_threshold": 20,
                        "user_prompt": "사용자 프롬프트는 저장하지 않는다",
                        "lora_user_settings_auto_apply_min_score": 80.0,
                        "lora_user_settings_auto_apply_categorical_min_score": 80.0,
                        "lora_user_settings_auto_apply_blend": 0.5,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = apply_lora_user_settings_autopilot(
                {
                    "selected_audio_ai": "clearvoice",
                    "continuous_threshold": 3.0,
                    "split_length_threshold": 14,
                    "user_prompt": "LoRA가 프롬프트를 덮으면 안 됨",
                },
                score=91.0,
                media_id="media-001",
                media_path="/tmp/a.mp4",
                store_dir=tmpdir,
            )
            saved = json.loads(user_settings.read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "applied")
            self.assertEqual(saved["selected_audio_ai"], "none")
            self.assertEqual(saved["continuous_threshold"], 2.5)
            self.assertEqual(saved["split_length_threshold"], 17)
            self.assertEqual(saved["user_prompt"], "")
            self.assertIn("continuous_threshold", saved[AUTOPILOT_METADATA_KEY]["applied_keys"])
            self.assertNotIn("selected_audio_ai", saved[AUTOPILOT_METADATA_KEY]["applied_keys"])
            self.assertEqual(saved[AUTOPILOT_METADATA_KEY]["skipped_keys"]["selected_audio_ai"], "mode_managed")
            self.assertNotIn("user_prompt", saved[AUTOPILOT_METADATA_KEY]["applied_keys"])

    def test_optimizer_records_exploration_and_updates_user_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            initialize_lora_personalization_store(tmpdir)
            paths = store_paths(tmpdir)
            Path(tmpdir, "user_settings.json").write_text(
                json.dumps(
                    {
                        "selected_audio_ai": "deepfilter",
                        "continuous_threshold": 2.0,
                        "split_length_threshold": 20,
                        "lora_user_settings_auto_apply_min_score": 80.0,
                        "lora_user_settings_auto_apply_categorical_min_score": 80.0,
                        "lora_user_settings_auto_apply_blend": 0.5,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            append_multimodal_lora_context_rows(
                [
                    {
                        "media_id": "media-001",
                        "media_path": "/tmp/a.mp4",
                        "context_classification": {
                            "scene_environment": {"label": "car"},
                            "topic": {"primary": "vehicle_review"},
                            "microphone_environment": {"mic_type": "builtin", "noise_sources": ["engine"]},
                        },
                        "media_profile": {"has_audio": True, "audio": {"sample_rate": 48000, "channels": 2}},
                        "candidate_context": {"candidate_disagreement_ratio": 0.2},
                    }
                ],
                tmpdir,
            )
            rows = [
                {
                    "start_sec": float(index * 2),
                    "end_sec": float(index * 2 + 1.2),
                    "duration_sec": 1.2,
                    "char_count": 18,
                    "cps": 15.0,
                    "line_break_pattern": "9|9",
                    "punctuation_pattern": ".",
                }
                for index in range(6)
            ]

            result = optimize_settings_for_media(
                "media-001",
                rows,
                media_path="/tmp/a.mp4",
                subtitle_path="/tmp/a.srt",
                store_dir=tmpdir,
                base_settings={
                    "selected_audio_ai": "deepfilter",
                    "continuous_threshold": 2.0,
                    "split_length_threshold": 20,
                    "lora_user_settings_auto_apply_min_score": 80.0,
                    "lora_user_settings_auto_apply_categorical_min_score": 80.0,
                    "lora_user_settings_auto_apply_blend": 0.5,
                    "lora_user_settings_exploration_rate": 1.0,
                    "lora_user_settings_exploration_min_truth_rows": 0,
                },
            )
            saved = json.loads(Path(tmpdir, "user_settings.json").read_text(encoding="utf-8"))
            trials = [
                json.loads(line)
                for line in paths["setting_trials"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            best_settings = load_best_settings(tmpdir)

            self.assertGreaterEqual(result["trial_count"], 5)
            self.assertTrue(any((row.get("metrics") or {}).get("lora_exploration_candidate") for row in trials))
            self.assertEqual(saved[AUTOPILOT_METADATA_KEY]["media_id"], "media-001")
            self.assertIn("media-001", dict(best_settings.get("by_media_id") or {}))
            self.assertTrue(dict(best_settings.get("by_style_cluster") or {}))
            self.assertTrue(dict(best_settings.get("by_audio_profile") or {}))


if __name__ == "__main__":
    unittest.main()
