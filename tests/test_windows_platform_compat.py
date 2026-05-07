# Version: 03.08.12
# Phase: PHASE2

import signal
import unittest
from unittest.mock import call, patch

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

    def test_worker_env_strips_macos_malloc_logging_variables(self):
        with patch.dict(
            "os.environ",
            {
                "MallocStackLogging": "0",
                "MallocStackLoggingNoCompact": "1",
                "MallocScribble": "1",
            },
            clear=False,
        ):
            env = platform_compat.subprocess_env()

        self.assertNotIn("MallocStackLogging", env)
        self.assertNotIn("MallocStackLoggingNoCompact", env)
        self.assertNotIn("MallocScribble", env)

    def test_preview_proxy_match_is_limited_to_legacy_cache_encoder(self):
        cache = str(platform_compat.PROJECT_ROOT / "dataset" / "video_preview_cache")
        self.assertTrue(platform_compat._is_preview_proxy_ffmpeg_command(
            f"ffmpeg -y -i sample.mp4 {cache}/abc_preview_720p.mp4.tmp.mp4"
        ))
        self.assertTrue(platform_compat._is_preview_proxy_ffmpeg_command(
            f"ffmpeg -y -i sample.mp4 {cache}/abc_preview_720p_hevc.mp4.tmp.mp4"
        ))
        self.assertFalse(platform_compat._is_preview_proxy_ffmpeg_command(
            "ffmpeg -y -i sample.mp4 /tmp/render_output.mp4"
        ))

    def test_cleanup_stale_preview_proxy_processes_terminates_matching_ffmpeg_only(self):
        cache = str(platform_compat.PROJECT_ROOT / "dataset" / "video_preview_cache")
        ps_output = "\n".join([
            f"123 1 ffmpeg -y -i sample.mp4 {cache}/abc_preview_720p.mp4.tmp.mp4",
            "456 1 ffmpeg -y -i sample.mp4 /tmp/render_output.mp4",
            "789 1 python main.py",
        ])

        with patch("core.platform_compat.is_windows", return_value=False), \
                patch("core.platform_compat.subprocess.check_output", return_value=ps_output), \
                patch("core.platform_compat.os.kill") as kill:
            stopped = platform_compat.cleanup_stale_preview_proxy_processes(timeout_sec=0.0)

        self.assertEqual(stopped, 1)
        kill.assert_has_calls([call(123, signal.SIGTERM)])
        self.assertEqual(kill.call_count, 1)

    def test_cleanup_app_child_processes_terminates_heavy_descendants_only(self):
        root = 100
        project = str(platform_compat.PROJECT_ROOT)
        ps_output = "\n".join([
            f"{root} 1 python main.py",
            f"101 {root} ffmpeg -y -i input.mp4 {project}/output/tmp.wav",
            f"102 {root} python {project}/core/audio/whisper_transformers.py",
            f"103 {root} ffmpeg -y -i input.mp4 /tmp/other.mp4",
            f"104 {root} /Applications/Ollama.app/Contents/Resources/ollama runner --model x",
            "105 1 ffmpeg -y -i unrelated.mp4 /tmp/other.mp4",
        ])

        with patch("core.platform_compat.is_windows", return_value=False), \
                patch("core.platform_compat.subprocess.check_output", return_value=ps_output), \
                patch("core.platform_compat.os.kill") as kill:
            stopped = platform_compat.cleanup_app_child_processes(root_pid=root, timeout_sec=0.0)

        self.assertEqual(stopped, 4)
        killed = [args.args[0] for args in kill.call_args_list]
        self.assertEqual(killed, [101, 102, 103, 104])

    def test_cleanup_ollama_runtime_processes_stops_server_and_runners(self):
        ps_output = "\n".join([
            "201 1 /Applications/Ollama.app/Contents/MacOS/Ollama",
            "202 201 /Applications/Ollama.app/Contents/Resources/ollama serve",
            "203 202 /Applications/Ollama.app/Contents/Resources/ollama runner --model gemma",
            "204 1 python main.py",
        ])

        with patch("core.platform_compat.is_windows", return_value=False), \
                patch("core.platform_compat.subprocess.check_output", return_value=ps_output), \
                patch("core.platform_compat.os.kill") as kill:
            stopped = platform_compat.cleanup_ollama_runtime_processes(timeout_sec=0.0)

        self.assertEqual(stopped, 3)
        killed = [args.args[0] for args in kill.call_args_list]
        self.assertEqual(killed, [201, 202, 203])

    def test_cleanup_ollama_runtime_processes_stops_homebrew_service_before_kill(self):
        ps_output = "301 1 /opt/homebrew/opt/ollama/bin/ollama serve"
        launchctl_output = "-\t0\thomebrew.mxcl.ollama"

        with patch("core.platform_compat.is_windows", return_value=False), \
                patch(
                    "core.platform_compat.subprocess.check_output",
                    side_effect=[launchctl_output, ps_output],
                ), \
                patch("core.platform_compat.shutil.which", return_value="/opt/homebrew/bin/brew"), \
                patch(
                    "core.platform_compat.subprocess.run",
                    return_value=unittest.mock.Mock(returncode=0),
                ) as run_mock, \
                patch("core.platform_compat.os.kill") as kill:
            stopped = platform_compat.cleanup_ollama_runtime_processes(timeout_sec=0.0)

        self.assertEqual(stopped, 1)
        brew_calls = [
            entry
            for entry in run_mock.call_args_list
            if entry.args and entry.args[0] == ["/opt/homebrew/bin/brew", "services", "stop", "ollama"]
        ]
        self.assertEqual(len(brew_calls), 1)
        self.assertTrue(brew_calls[0].kwargs.get("capture_output"))
        self.assertTrue(brew_calls[0].kwargs.get("text"))
        self.assertIn("env", brew_calls[0].kwargs)
        kill.assert_has_calls([call(301, signal.SIGTERM)])

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
