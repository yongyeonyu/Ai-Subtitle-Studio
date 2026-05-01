# Version: 03.01.23
# Phase: PHASE2

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.model_manager import ModelManager


class ModelManagerTest(unittest.TestCase):
    def _registry(self, models):
        tmp = tempfile.TemporaryDirectory()
        registry_path = Path(tmp.name) / "model_registry.json"
        registry_path.write_text(json.dumps({"models": models}), encoding="utf-8")
        self.addCleanup(tmp.cleanup)
        return registry_path, Path(tmp.name)

    def test_available_models_filters_by_os_and_hidden(self):
        registry_path, root = self._registry([
            {"id": "mac-only", "name": "Mac", "os": ["mac"], "hidden": False},
            {"id": "win-only", "name": "Windows", "os": ["windows"], "hidden": False},
            {"id": "hidden", "name": "Hidden", "os": ["mac"], "hidden": True},
        ])
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="mac")

        visible = manager.available_models()
        self.assertEqual([m["id"] for m in visible], ["mac-only"])

        all_models = manager.available_models(include_hidden=True)
        self.assertEqual([m["id"] for m in all_models], ["mac-only", "hidden"])

    def test_required_models_uses_install_status(self):
        registry_path, root = self._registry([
            {
                "id": "ready",
                "name": "Ready",
                "os": ["mac"],
                "required": True,
                "pip_packages": ["ready-pkg"],
                "import_names": ["ready_pkg"],
            },
            {
                "id": "missing",
                "name": "Missing",
                "os": ["mac"],
                "required": True,
                "pip_packages": ["missing-pkg"],
                "import_names": ["missing_pkg"],
            },
        ])
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="mac")

        def fake_find_spec(name):
            return object() if name == "ready_pkg" else None

        with patch("core.model_manager.importlib.util.find_spec", side_effect=fake_find_spec):
            missing = manager.required_models()

        self.assertEqual([m["id"] for m in missing], ["missing"])

    def test_model_path_accepts_windows_style_registry_metadata(self):
        registry_path, root = self._registry([
            {
                "id": "hf-model",
                "name": "HF",
                "os": ["windows"],
                "model_path": "models/hf-model",
                "model_files": ["config.json"],
            }
        ])
        model_dir = root / "models" / "hf-model"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="windows")

        models = manager.available_models()

        self.assertEqual(len(models), 1)
        self.assertTrue(models[0]["installed"])

    def test_experimental_models_are_visible_but_not_required(self):
        registry_path, root = self._registry([
            {
                "id": "whisper-korean-ghost613-mlx",
                "name": "Whisper Korean Turbo (MLX, 실험)",
                "os": ["mac"],
                "required": False,
                "experimental": True,
            }
        ])
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="mac")

        models = manager.available_models()
        required = manager.required_models()

        self.assertEqual(models[0]["id"], "whisper-korean-ghost613-mlx")
        self.assertTrue(models[0]["experimental"])
        self.assertEqual(required, [])

    def test_korean_transformers_model_is_visible_on_mac_and_windows(self):
        row = {
            "id": "whisper-korean-zeroth-ko-v2-transformers",
            "name": "Whisper Korean Zeroth KO v2 (Transformers, 실험)",
            "os": ["mac", "windows"],
            "required": False,
            "experimental": True,
            "pip_packages": ["transformers", "accelerate"],
            "import_names": ["transformers", "accelerate", "torch"],
        }
        registry_path, root = self._registry([row])

        with patch("core.model_manager.importlib.util.find_spec", return_value=object()):
            mac_models = ModelManager(registry_path=registry_path, project_root=root, current_os="mac").available_models()
            win_models = ModelManager(registry_path=registry_path, project_root=root, current_os="windows").available_models()

        self.assertEqual(mac_models[0]["id"], "whisper-korean-zeroth-ko-v2-transformers")
        self.assertEqual(win_models[0]["id"], "whisper-korean-zeroth-ko-v2-transformers")
        self.assertTrue(mac_models[0]["installed"])

    def test_rnnoise_model_uses_binary_check(self):
        registry_path, root = self._registry([
            {
                "id": "rnnoise",
                "name": "RNNoise",
                "category": "Audio",
                "os": ["mac"],
                "binary_check": "rnnoise",
            }
        ])
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="mac")

        with patch("core.platform_compat.rnnoise_binary", return_value="rnnoise_demo"), \
                patch("core.model_manager.shutil.which", return_value=None):
            models = manager.available_models()
        self.assertFalse(models[0]["installed"])

        with patch("core.platform_compat.rnnoise_binary", return_value="rnnoise_demo"), \
                patch("core.model_manager.shutil.which", return_value="/usr/local/bin/rnnoise_demo"):
            models = manager.available_models()
        self.assertTrue(models[0]["installed"])

    def test_audio_filter_candidate_models_are_optional(self):
        rows = [
            {
                "id": "ten-vad",
                "name": "TEN VAD",
                "category": "VAD",
                "os": ["mac", "windows"],
                "required": False,
                "experimental": True,
                "pip_packages": ["ten-vad"],
                "import_names": ["ten_vad"],
            },
            {
                "id": "resemble-enhance",
                "name": "Resemble Enhance",
                "category": "Audio",
                "os": ["mac", "windows"],
                "required": False,
                "experimental": True,
                "pip_packages": ["resemble-enhance"],
                "import_names": ["resemble_enhance"],
            },
            {
                "id": "clearvoice",
                "name": "ClearVoice",
                "category": "Audio",
                "os": ["mac", "windows"],
                "required": False,
                "experimental": True,
                "pip_packages": ["clearvoice"],
                "import_names": ["clearvoice"],
            },
        ]
        registry_path, root = self._registry(rows)
        manager = ModelManager(registry_path=registry_path, project_root=root, current_os="mac")

        models = manager.available_models()
        required = manager.required_models()

        self.assertEqual([model["id"] for model in models], ["ten-vad", "resemble-enhance", "clearvoice"])
        self.assertTrue(all(model.get("experimental") for model in models))
        self.assertEqual(required, [])


if __name__ == "__main__":
    unittest.main()
