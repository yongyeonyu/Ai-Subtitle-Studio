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


if __name__ == "__main__":
    unittest.main()
