# Version: 03.01.16
# Phase: PHASE1-B
import socket
import unittest
from unittest import mock

from core.llm import ollama_provider


class _Logger:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(str(message))


class OllamaWarmupTest(unittest.TestCase):
    def setUp(self):
        ollama_provider._WARMED.clear()

    def test_warmup_timeout_is_skipped_without_failure_log(self):
        logger = _Logger()
        with mock.patch("core.llm.ollama_provider.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            ollama_provider.warmup_model("exaone3.5:7.8b", logger=logger, timeout=0.01)

        self.assertIn("exaone3.5:7.8b", ollama_provider._WARMED)
        joined = "\n".join(logger.lines)
        self.assertIn("워밍업 건너뜀", joined)
        self.assertNotIn("워밍업 실패", joined)


if __name__ == "__main__":
    unittest.main()
