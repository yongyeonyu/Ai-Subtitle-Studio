# Version: 03.08.07
# Phase: PHASE2
import unittest
from unittest.mock import Mock, patch

from core.audio import whisper_coreml


class WhisperCoreMLTests(unittest.TestCase):
    def test_coreml_model_detection_requires_mac_and_prefix(self):
        with patch("core.audio.whisper_coreml.config.IS_MAC", True):
            self.assertTrue(whisper_coreml.is_coreml_whisper_model("coreml:large-v3-v20240930_626MB"))
            self.assertTrue(whisper_coreml.is_coreml_whisper_model("COREML:large-v3"))
            self.assertFalse(whisper_coreml.is_coreml_whisper_model("mlx-community/whisper-large-v3-mlx"))

        with patch("core.audio.whisper_coreml.config.IS_MAC", False):
            self.assertFalse(whisper_coreml.is_coreml_whisper_model("coreml:large-v3-v20240930_626MB"))

    def test_coreml_model_selector_strips_prefix(self):
        self.assertEqual(
            whisper_coreml.coreml_model_selector("coreml:large-v3-v20240930_626MB"),
            "large-v3-v20240930_626MB",
        )
        self.assertEqual(
            whisper_coreml.coreml_model_selector(""),
            whisper_coreml.DEFAULT_COREML_MODEL,
        )

    def test_run_whisper_returns_none_without_cli(self):
        with patch("core.audio.whisper_coreml.config.IS_MAC", True), \
                patch("core.audio.whisper_coreml.find_whisperkit_cli", return_value=""), \
                patch("core.audio.whisper_coreml.get_logger") as logger:
            proc = whisper_coreml.run_whisper(["/tmp/chunk.wav"], "coreml:large-v3", "ko", log_label="STT2")

        self.assertIsNone(proc)
        self.assertTrue(logger.return_value.log.called)

    def test_run_whisper_starts_worker_with_cli_env(self):
        proc = Mock()
        proc.stdin = Mock()
        proc.stderr = []
        with patch("core.audio.whisper_coreml.config.IS_MAC", True), \
                patch("core.audio.whisper_coreml.find_whisperkit_cli", return_value="/opt/homebrew/bin/whisperkit-cli"), \
                patch("core.audio.whisper_coreml.subprocess.Popen", return_value=proc) as popen:
            started = whisper_coreml.run_whisper(["/tmp/chunk.wav"], "coreml:large-v3", "ko", log_label="STT2")

        self.assertIs(started, proc)
        self.assertEqual(
            popen.call_args.kwargs["env"]["WHISPERKIT_CLI"],
            "/opt/homebrew/bin/whisperkit-cli",
        )

    def test_coreml_stderr_log_includes_stt_label(self):
        line = whisper_coreml._format_stderr_log("warning", log_label="STT2")

        self.assertEqual(line, "[STT2] [coreml] warning")


if __name__ == "__main__":
    unittest.main()
