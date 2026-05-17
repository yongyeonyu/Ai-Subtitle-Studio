# Version: 03.09.25
# Phase: PHASE2

import json
import unittest
from pathlib import Path

from ui.settings.settings_ai import stt2_whisper_model_candidates
from ui.settings.settings_common import (
    MAC_WHISPER_MODELS,
    REMOVED_WHISPER_MODELS,
    WINDOWS_WHISPER_MODELS,
    filter_available_whisper_models,
    whisper_model_display_name,
)


ROOT = Path(__file__).resolve().parents[1]

REMOVED_REGISTRY_IDS = {
    "whisper-large-v3-coreml",
    "whisper-medium-en-mlx",
    "whisper-small-mlx",
    "whisper-small-en-mlx",
    "whisper-base-mlx",
    "whisper-base-en-mlx",
    "whisper-tiny-mlx",
    "whisper-tiny-en-mlx",
    "whisper-medium-en-faster",
    "whisper-small-faster",
    "whisper-small-en-faster",
    "whisper-base-faster",
    "whisper-base-en-faster",
    "whisper-tiny-faster",
    "whisper-tiny-en-faster",
}


class WhisperModelCatalogTest(unittest.TestCase):
    def test_unused_models_are_not_selectable(self):
        selectable = set(MAC_WHISPER_MODELS + WINDOWS_WHISPER_MODELS)
        self.assertFalse(selectable & REMOVED_WHISPER_MODELS)

    def test_cache_filter_removes_unused_models(self):
        mixed = ["mlx-community/whisper-large-v3-mlx", "small", "mlx-community/whisper-base-mlx"]
        self.assertEqual(filter_available_whisper_models(mixed), ["mlx-community/whisper-large-v3-mlx"])

    def test_mac_native_stt1_candidates_are_curated(self):
        self.assertIn("whisperkit-persistent:large-v3-v20240930_626MB", MAC_WHISPER_MODELS)
        self.assertIn("whisperkit-persistent:large-v3-v20240930_turbo_632MB", MAC_WHISPER_MODELS)
        self.assertIn("youngouk/whisper-medium-komixv2-mlx", MAC_WHISPER_MODELS)
        self.assertNotIn("whisper-medium-komixv2", MAC_WHISPER_MODELS)
        self.assertNotIn("seastar105/whisper-medium-komixv2", MAC_WHISPER_MODELS)
        self.assertNotIn("Systran/faster-whisper-large-v3", MAC_WHISPER_MODELS)
        self.assertEqual(WINDOWS_WHISPER_MODELS, [])

    def test_curated_candidates_are_selectable_for_stt2(self):
        mac_stt2 = stt2_whisper_model_candidates(MAC_WHISPER_MODELS)

        self.assertIn("whisperkit-persistent:large-v3-v20240930_626MB", mac_stt2)
        self.assertIn("youngouk/whisper-medium-komixv2-mlx", mac_stt2)
        self.assertNotIn("seastar105/whisper-medium-komixv2", mac_stt2)

    def test_native_model_labels_are_user_facing(self):
        self.assertEqual(
            whisper_model_display_name("whisperkit-persistent:large-v3-v20240930_626MB"),
            "WhisperKit Large V3 · 정밀",
        )
        self.assertEqual(
            whisper_model_display_name("youngouk/whisper-medium-komixv2-mlx"),
            "KomixV2 MLX · 한국어 특화",
        )

    def test_native_model_labels_can_include_benchmark_recommendations(self):
        self.assertEqual(
            whisper_model_display_name(
                "whisperkit-persistent:large-v3-v20240930_626MB",
                include_recommendations=True,
            ),
            "WhisperKit Large V3 · 정밀 [Fast] [Auto] [High]",
        )
        self.assertEqual(
            whisper_model_display_name(
                "youngouk/whisper-medium-komixv2-mlx",
                include_recommendations=True,
            ),
            "KomixV2 MLX · 한국어 특화 [Fast]",
        )

    def test_unused_models_are_not_in_default_settings(self):
        defaults = json.loads((ROOT / "dataset" / "custom_defaults.json").read_text(encoding="utf-8"))
        models = set(defaults.get("whisper_models", []))
        self.assertFalse(models & REMOVED_WHISPER_MODELS)

    def test_unused_models_are_not_install_targets(self):
        registry = json.loads((ROOT / "dataset" / "model_registry.json").read_text(encoding="utf-8"))
        ids = {model.get("id") for model in registry.get("models", [])}
        self.assertFalse(ids & REMOVED_REGISTRY_IDS)


if __name__ == "__main__":
    unittest.main()
