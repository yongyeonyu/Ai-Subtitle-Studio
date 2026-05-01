# Version: 03.01.23
# Phase: PHASE2

import unittest
from unittest.mock import patch

from core import platform_compat
from core.audio.whisper_faster import _convert_model_name, _fallback_model_name
from core.audio.whisper_transformers import is_transformers_whisper_model


class WindowsPlatformCompatTest(unittest.TestCase):
    def test_windows_missing_executable_falls_back_to_exe_name(self):
        with patch("core.platform_compat.config.IS_WINDOWS", True):
            resolved = platform_compat.resolve_executable("definitely_missing_ai_subtitle_tool")
        self.assertEqual(resolved, "definitely_missing_ai_subtitle_tool.exe")

    def test_worker_env_strips_qt_variables(self):
        with patch.dict(
            "os.environ",
            {
                "QT_PLUGIN_PATH": "bad",
                "QT_QPA_PLATFORM_PLUGIN_PATH": "bad",
                "QML2_IMPORT_PATH": "bad",
            },
            clear=False,
        ):
            env = platform_compat.subprocess_env(strip_qt=True)
        self.assertNotIn("QT_PLUGIN_PATH", env)
        self.assertNotIn("QT_QPA_PLATFORM_PLUGIN_PATH", env)
        self.assertNotIn("QML2_IMPORT_PATH", env)
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")

    def test_faster_whisper_model_name_converts_mlx_to_windows_model(self):
        self.assertEqual(
            _convert_model_name("mlx-community/whisper-large-v3-turbo"),
            "large-v3-turbo",
        )
        self.assertEqual(_convert_model_name("large-v3-turbo"), "large-v3-turbo")

    def test_korean_experimental_model_maps_to_windows_repo_with_fallback(self):
        model = _convert_model_name("youngouk/ghost613-turbo-korean-4bit-mlx")

        self.assertEqual(model, "ghost613/faster-whisper-large-v3-turbo-korean")
        self.assertEqual(_fallback_model_name(model), "large-v3")

    def test_faster_whisper_accepts_full_standard_model_list(self):
        for model in (
            "tiny.en", "tiny", "base.en", "base", "small.en", "small",
            "medium.en", "large-v1", "large-v2",
            "large", "distil-large-v2", "distil-medium.en", "distil-small.en",
            "distil-large-v3", "large-v3-turbo", "turbo",
        ):
            self.assertEqual(_convert_model_name(model), model)

    def test_mlx_whisper_names_convert_to_faster_whisper_equivalents(self):
        cases = {
            "mlx-community/whisper-large-v2-mlx": "large-v2",
            "mlx-community/whisper-medium.en-mlx": "medium.en",
            "mlx-community/whisper-small.en-mlx": "small.en",
            "mlx-community/whisper-base.en-mlx": "base.en",
            "mlx-community/whisper-tiny.en-mlx": "tiny.en",
            "mlx-community/distil-whisper-large-v3": "distil-large-v3",
        }
        for source, expected in cases.items():
            self.assertEqual(_convert_model_name(source), expected)

    def test_korean_zeroth_model_uses_transformers_backend(self):
        self.assertTrue(
            is_transformers_whisper_model("o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2")
        )
        self.assertFalse(is_transformers_whisper_model("large-v3"))


if __name__ == "__main__":
    unittest.main()
