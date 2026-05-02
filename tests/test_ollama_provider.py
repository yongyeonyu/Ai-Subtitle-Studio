# Version: 03.09.01
# Phase: PHASE2
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
        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            ollama_provider.warmup_model("exaone3.5:7.8b", logger=logger, timeout=0.01)

        self.assertIn("exaone3.5:7.8b", ollama_provider._WARMED)
        joined = "\n".join(logger.lines)
        self.assertIn("워밍업 건너뜀", joined)
        self.assertNotIn("워밍업 실패", joined)

    def test_stop_local_llm_models_unloads_candidates_and_running_models(self):
        logger = _Logger()

        def fake_post(path, payload, timeout=2.0):
            return {}

        with mock.patch("core.llm.ollama_provider._get_ollama_running_models", return_value={"gemma4:e4b"}), \
             mock.patch("core.llm.ollama_provider._post_ollama_json", side_effect=fake_post) as post_mock, \
             mock.patch("core.llm.ollama_provider.shutil.which", return_value=None):
            stopped = ollama_provider.stop_local_llm_models(["exaone3.5:7.8b", "사용 안함"], logger=logger)

        self.assertEqual(stopped, ["exaone3.5:7.8b", "gemma4:e4b"])
        payloads = [call.args[1] for call in post_mock.call_args_list]
        self.assertIn({"model": "exaone3.5:7.8b", "prompt": "", "keep_alive": 0}, payloads)
        self.assertIn({"model": "gemma4:e4b", "prompt": "", "keep_alive": 0}, payloads)
        self.assertIn("Ollama 모델 종료/언로드 완료", "\n".join(logger.lines))

    def test_stop_local_llm_models_uses_log_context(self):
        logger = _Logger()

        def fake_post(path, payload, timeout=2.0):
            return {}

        with mock.patch("core.llm.ollama_provider._get_ollama_running_models", return_value=set()), \
             mock.patch("core.llm.ollama_provider._post_ollama_json", side_effect=fake_post), \
             mock.patch("core.llm.ollama_provider.shutil.which", return_value=None):
            stopped = ollama_provider.stop_local_llm_models(["gemma4:e4b"], logger=logger, log_context="에디터 모드")

        self.assertEqual(stopped, ["gemma4:e4b"])
        joined = "\n".join(logger.lines)
        self.assertIn("에디터 모드: Ollama 모델 종료/언로드 완료", joined)
        self.assertNotIn("홈 이동: Ollama 모델 종료/언로드 완료", joined)

    def test_stop_local_llm_models_skips_cloud_model_names(self):
        with mock.patch("core.llm.ollama_provider._get_ollama_running_models", return_value=set()), \
             mock.patch("core.llm.ollama_provider._post_ollama_json") as post_mock, \
             mock.patch("core.llm.ollama_provider.shutil.which", return_value=None):
            stopped = ollama_provider.stop_local_llm_models(["Gemini 2.5 Pro (API)", "OpenAI GPT-5.2"])

        self.assertEqual(stopped, [])
        post_mock.assert_not_called()

    def test_ensure_ollama_server_logs_running_without_start(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider.is_ollama_server_running", return_value=True), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process") as start_mock:
            self.assertTrue(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=0.1))

        start_mock.assert_not_called()
        self.assertIn("AI 엔진(Ollama) 실행 중", "\n".join(logger.lines))

    def test_ensure_ollama_server_starts_when_offline(self):
        logger = _Logger()

        with mock.patch(
            "core.llm.ollama_provider.is_ollama_server_running",
            side_effect=[False, False, True],
        ), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process", return_value=True), \
             mock.patch("core.llm.ollama_provider.time.sleep"):
            self.assertTrue(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=1.0))

        joined = "\n".join(logger.lines)
        self.assertIn("자동 시작 중", joined)
        self.assertIn("자동 시작 완료", joined)

    def test_ensure_ollama_server_reports_missing_executable(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider.is_ollama_server_running", return_value=False), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process", return_value=False):
            self.assertFalse(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=0.1))

        self.assertIn("실행 파일을 찾을 수 없습니다", "\n".join(logger.lines))

    def test_warmup_auto_starts_ollama_before_request(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=False) as ensure_mock, \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen") as urlopen_mock:
            ollama_provider.warmup_model("gemma4:e4b", logger=logger, timeout=0.01)

        ensure_mock.assert_called_once()
        urlopen_mock.assert_not_called()
        self.assertIn("gemma4:e4b", ollama_provider._WARMED)


if __name__ == "__main__":
    unittest.main()
