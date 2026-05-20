# Version: 03.09.01
# Phase: PHASE2
import http.client
import json
import os
import socket
import unittest
from unittest import mock
import urllib.error

from core.llm import ollama_provider
from core.llm.provider_router import normalize_llm_provider


class _Logger:
    def __init__(self):
        self.lines = []

    def log(self, message):
        self.lines.append(str(message))


class OllamaWarmupTest(unittest.TestCase):
    def setUp(self):
        ollama_provider._WARMED.clear()
        ollama_provider._PROBE_OK_UNTIL.clear()
        ollama_provider._PROBE_FAILED_UNTIL.clear()
        ollama_provider._APP_STARTED_RUNTIME = False
        ollama_provider._SERVER_READY_UNTIL = 0.0
        ollama_provider._START_IN_PROGRESS_UNTIL = 0.0
        ollama_provider._SERVER_READY_LOGGED_UNTIL = 0.0
        self._previous_py_client = os.environ.get("AI_SUBTITLE_OLLAMA_PY_CLIENT")
        os.environ["AI_SUBTITLE_OLLAMA_PY_CLIENT"] = "0"

    def tearDown(self):
        if self._previous_py_client is None:
            os.environ.pop("AI_SUBTITLE_OLLAMA_PY_CLIENT", None)
        else:
            os.environ["AI_SUBTITLE_OLLAMA_PY_CLIENT"] = self._previous_py_client

    def test_warmup_timeout_is_skipped_without_failure_log(self):
        logger = _Logger()
        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            ollama_provider.warmup_model("exaone3.5:7.8b", logger=logger, timeout=0.01)

        self.assertIn("exaone3.5:7.8b", ollama_provider._WARMED)
        joined = "\n".join(logger.lines)
        self.assertIn("워밍업 건너뜀", joined)
        self.assertNotIn("워밍업 실패", joined)

    def test_provider_router_recognizes_llama_cpp_gguf_models(self):
        self.assertEqual(normalize_llm_provider("llama.cpp", "/models/korean.gguf"), "llama_cpp")
        self.assertEqual(normalize_llm_provider("", "/models/korean.gguf"), "llama_cpp")

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

    def test_shutdown_local_ollama_runtime_unloads_models_and_kills_server(self):
        logger = _Logger()
        ollama_provider._WARMED.add("gemma4:e4b")
        ollama_provider._SERVER_READY_UNTIL = 9.0
        ollama_provider._START_IN_PROGRESS_UNTIL = 8.0
        ollama_provider._SERVER_READY_LOGGED_UNTIL = 7.0

        with mock.patch(
            "core.llm.ollama_provider.stop_local_llm_models",
            return_value=["gemma4:e4b"],
        ) as stop_mock, mock.patch(
            "core.platform_compat.cleanup_ollama_runtime_processes",
            return_value=2,
        ) as cleanup_mock, mock.patch(
            "core.llm.ollama_provider._is_ollama_api_ready",
            return_value=False,
        ):
            result = ollama_provider.shutdown_local_ollama_runtime(
                ["gemma4:e4b"],
                logger=logger,
                log_context="생성 완료",
                timeout_sec=0.7,
            )

        stop_mock.assert_called_once_with(["gemma4:e4b"], logger=logger, log_context="생성 완료")
        cleanup_mock.assert_called_once_with(timeout_sec=0.7)
        self.assertEqual(result, {"models": ["gemma4:e4b"], "processes": 2})
        self.assertEqual(ollama_provider._SERVER_READY_UNTIL, 0.0)
        self.assertEqual(ollama_provider._START_IN_PROGRESS_UNTIL, 0.0)
        self.assertEqual(ollama_provider._SERVER_READY_LOGGED_UNTIL, 0.0)
        self.assertEqual(ollama_provider._WARMED, set())
        self.assertIn("Ollama 서버/러너 종료 완료", "\n".join(logger.lines))

    def test_stop_local_llm_models_skips_cloud_model_names(self):
        with mock.patch("core.llm.ollama_provider._get_ollama_running_models", return_value=set()), \
             mock.patch("core.llm.ollama_provider._post_ollama_json") as post_mock, \
             mock.patch("core.llm.ollama_provider.shutil.which", return_value=None):
            stopped = ollama_provider.stop_local_llm_models(["Gemini 2.5 Pro (API)", "OpenAI GPT-5.2"])

        self.assertEqual(stopped, [])
        post_mock.assert_not_called()

    def test_ensure_ollama_server_logs_running_without_start(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider._is_ollama_api_ready", return_value=True), \
             mock.patch("core.llm.ollama_provider.is_ollama_server_running", return_value=True), \
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
             mock.patch("core.llm.ollama_provider._is_ollama_api_ready", side_effect=[False, False, True]), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process", return_value=True), \
             mock.patch("core.llm.ollama_provider.time.sleep"):
            self.assertTrue(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=1.0))

        joined = "\n".join(logger.lines)
        self.assertIn("자동 시작 중", joined)
        self.assertIn("자동 시작 완료", joined)

    def test_ensure_ollama_server_reports_missing_executable(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider._is_ollama_api_ready", return_value=False), \
             mock.patch("core.llm.ollama_provider.is_ollama_server_running", return_value=False), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process", return_value=False):
            self.assertFalse(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=0.1))

        self.assertIn("실행 파일을 찾을 수 없습니다", "\n".join(logger.lines))

    def test_iter_ollama_bins_includes_macos_app_bundle_binary(self):
        app_bin = "/Applications/Ollama.app/Contents/MacOS/ollama"

        def fake_exists(path):
            return path == app_bin

        with mock.patch("core.llm.ollama_provider.shutil.which", return_value=None), \
             mock.patch("core.llm.ollama_provider.os.path.exists", side_effect=fake_exists):
            bins = ollama_provider._iter_ollama_bins()

        self.assertEqual(bins, [app_bin])

    def test_start_ollama_server_process_marks_app_managed_runtime(self):
        with mock.patch("core.llm.ollama_provider._iter_ollama_bins", return_value=["/Applications/Ollama.app/Contents/MacOS/ollama"]), \
             mock.patch("core.llm.ollama_provider.subprocess.Popen") as popen_mock:
            self.assertTrue(ollama_provider._start_ollama_server_process())

        popen_mock.assert_called_once()
        self.assertTrue(ollama_provider.app_started_ollama_runtime())

    def test_restart_ollama_server_restarts_runtime_before_skip(self):
        logger = _Logger()

        with mock.patch("core.platform_compat.cleanup_ollama_runtime_processes", return_value=2) as cleanup_mock, \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process", return_value=True) as start_mock, \
             mock.patch("core.llm.ollama_provider._is_ollama_api_ready", side_effect=[False, True]), \
             mock.patch("core.llm.ollama_provider.time.sleep"):
            self.assertTrue(ollama_provider.restart_ollama_server(logger=logger, wait_sec=1.0))

        cleanup_mock.assert_called_once()
        start_mock.assert_called_once()
        joined = "\n".join(logger.lines)
        self.assertIn("재시작 중", joined)
        self.assertIn("재시작 완료", joined)

    def test_warmup_auto_starts_ollama_before_request(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=False) as ensure_mock, \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen") as urlopen_mock:
            ollama_provider.warmup_model("gemma4:e4b", logger=logger, timeout=0.01)

        ensure_mock.assert_called_once()
        urlopen_mock.assert_not_called()
        self.assertIn("gemma4:e4b", ollama_provider._WARMED)

    def test_split_text_retries_once_after_http_500(self):
        success_payload = mock.Mock()
        success_payload.__enter__ = mock.Mock(return_value=success_payload)
        success_payload.__exit__ = mock.Mock(return_value=False)
        success_payload.read.return_value = b'{"response":"[\\"A\\"]"}'

        first_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True) as ensure_mock, \
             mock.patch(
                 "core.llm.ollama_provider.urllib.request.urlopen",
                 side_effect=[first_error, success_payload],
             ) as urlopen_mock, \
             mock.patch("core.llm.ollama_provider.time.sleep") as sleep_mock:
            chunks = ollama_provider.split_text("gemma4:e4b", "prompt", timeout=1)

        self.assertEqual(chunks, ["A"])
        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertGreaterEqual(ensure_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_split_text_uses_python_client_when_enabled(self):
        os.environ["AI_SUBTITLE_OLLAMA_PY_CLIENT"] = "1"

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch("core.llm.ollama_provider._ollama_client_generate", return_value='["A"]') as client_mock, \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen") as urlopen_mock:
            chunks = ollama_provider.split_text("gemma4:e4b", "prompt", timeout=1)

        self.assertEqual(chunks, ["A"])
        client_mock.assert_called_once()
        urlopen_mock.assert_not_called()

    def test_ollama_connection_backend_reports_python_client_when_enabled(self):
        os.environ["AI_SUBTITLE_OLLAMA_PY_CLIENT"] = "1"
        expected = "python-client" if ollama_provider._ollama_py is not None else "http"

        self.assertEqual(ollama_provider.ollama_connection_backend(), expected)

    def test_negative_keep_alive_uses_ollama_duration_unit(self):
        self.assertEqual(ollama_provider._ollama_keep_alive(-1), "-1m")
        self.assertEqual(ollama_provider._ollama_keep_alive("-1"), "-1m")
        self.assertEqual(ollama_provider._ollama_keep_alive(-0.5), "-1m")
        self.assertEqual(ollama_provider._ollama_keep_alive("15m"), "15m")

    def test_http_generate_request_normalizes_negative_keep_alive(self):
        with mock.patch(
            "core.performance.current_resource_snapshot",
            return_value={"memory_pressure_stage": "normal"},
        ):
            request = ollama_provider._build_generate_request("gemma4:e4b", "ping", keep_alive=-1)
        payload = json.loads(request.data.decode("utf-8"))

        self.assertEqual(payload["keep_alive"], "-1m")

    def test_http_generate_request_unloads_model_under_critical_memory(self):
        with mock.patch(
            "core.performance.current_resource_snapshot",
            return_value={"memory_pressure_stage": "critical"},
        ):
            request = ollama_provider._build_generate_request("gemma4:e4b", "ping", keep_alive=-1)

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["keep_alive"], 0)

    def test_warmup_model_skips_residency_under_critical_memory(self):
        logger = _Logger()

        with mock.patch(
            "core.performance.current_resource_snapshot",
            return_value={"memory_pressure_stage": "critical"},
        ), \
             mock.patch("core.llm.ollama_provider.ensure_ollama_server") as ensure_mock, \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen") as urlopen_mock:
            ollama_provider.warmup_model("gemma4:e4b", logger=logger, timeout=0.01)

        ensure_mock.assert_not_called()
        urlopen_mock.assert_not_called()
        self.assertIn("gemma4:e4b", ollama_provider._WARMED)
        self.assertIn("메모리 critical", "\n".join(logger.lines))

    def test_split_text_raises_after_repeated_http_500(self):
        repeated_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=None,
        )

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch(
                 "core.llm.ollama_provider.urllib.request.urlopen",
                 side_effect=[repeated_error, repeated_error, repeated_error],
             ) as urlopen_mock, \
             mock.patch("core.llm.ollama_provider.time.sleep") as sleep_mock:
            with self.assertRaises(urllib.error.HTTPError):
                ollama_provider.split_text("gemma4:e4b", "prompt", timeout=1)

        self.assertEqual(urlopen_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_resolve_ollama_model_for_request_falls_back_after_model_load_failure(self):
        logger = _Logger()

        first_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=mock.Mock(read=mock.Mock(return_value=b'{"error":"unable to load model: broken-blob"}')),
        )
        success_payload = mock.Mock()
        success_payload.__enter__ = mock.Mock(return_value=success_payload)
        success_payload.__exit__ = mock.Mock(return_value=False)
        success_payload.read.return_value = b'{"response":"ok"}'

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch("core.llm.ollama_provider._get_ollama_installed_models", return_value=["gemma4:e4b", "exaone3.5:7.8b"]), \
             mock.patch(
                 "core.llm.ollama_provider.urllib.request.urlopen",
                 side_effect=[first_error, success_payload],
             ):
            resolved = ollama_provider.resolve_ollama_model_for_request("gemma4:e4b", logger=logger, context="자막 LLM", timeout=1.0)

        self.assertEqual(resolved, "exaone3.5:7.8b")
        joined = "\n".join(logger.lines)
        self.assertIn("모델 로드 실패", joined)
        self.assertIn("자동 대체", joined)

    def test_resolve_ollama_model_for_request_skips_probe_when_recently_confirmed(self):
        logger = _Logger()
        ollama_provider._mark_model_probe_ok("exaone3.5:7.8b", ttl_sec=30.0)

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server") as ensure_mock, \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen") as urlopen_mock:
            resolved = ollama_provider.resolve_ollama_model_for_request("exaone3.5:7.8b", logger=logger, context="자막 LLM", timeout=1.0)

        self.assertEqual(resolved, "exaone3.5:7.8b")
        ensure_mock.assert_not_called()
        urlopen_mock.assert_not_called()
        self.assertEqual(logger.lines, [])

    def test_resolve_ollama_model_for_request_skips_repeated_failed_probe(self):
        logger = _Logger()
        first_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=mock.Mock(read=mock.Mock(return_value=b'{"error":"unable to load model: broken-blob"}')),
        )

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True) as ensure_mock, \
             mock.patch("core.llm.ollama_provider._get_ollama_installed_models", return_value=[]), \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen", side_effect=[first_error]) as urlopen_mock:
            first = ollama_provider.resolve_ollama_model_for_request("gemma4:e4b", logger=logger, context="STT 앙상블 LLM", timeout=1.0)
            second = ollama_provider.resolve_ollama_model_for_request("gemma4:e4b", logger=logger, context="STT 앙상블 LLM", timeout=1.0)

        self.assertEqual(first, "gemma4:e4b")
        self.assertEqual(second, "gemma4:e4b")
        ensure_mock.assert_called_once()
        urlopen_mock.assert_called_once()
        self.assertEqual(sum("사용 가능한 대체 Ollama 모델" in line for line in logger.lines), 1)

    def test_resolve_ollama_model_for_request_can_disable_fallback(self):
        logger = _Logger()
        first_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=mock.Mock(read=mock.Mock(return_value=b'{"error":"unable to load model: broken-blob"}')),
        )

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True), \
             mock.patch("core.llm.ollama_provider.urllib.request.urlopen", side_effect=[first_error]) as urlopen_mock:
            resolved = ollama_provider.resolve_ollama_model_for_request(
                "gemma4:e4b",
                logger=logger,
                context="자막 LLM",
                timeout=1.0,
                allow_fallback=False,
            )

        self.assertEqual(resolved, "gemma4:e4b")
        self.assertEqual(urlopen_mock.call_count, 1)
        self.assertNotIn("자동 대체", "\n".join(logger.lines))

    def test_ensure_ollama_server_waits_for_api_ready_when_root_is_up(self):
        logger = _Logger()

        with mock.patch("core.llm.ollama_provider._is_ollama_api_ready", side_effect=[False, False, True]), \
             mock.patch("core.llm.ollama_provider.is_ollama_server_running", return_value=True), \
             mock.patch("core.llm.ollama_provider._start_ollama_server_process") as start_mock, \
             mock.patch("core.llm.ollama_provider.time.sleep"):
            self.assertTrue(ollama_provider.ensure_ollama_server(logger=logger, wait_sec=1.0))

        start_mock.assert_not_called()
        self.assertIn("AI 엔진(Ollama) 실행 중", "\n".join(logger.lines))

    def test_resolve_ollama_model_retries_remote_disconnected_probe(self):
        logger = _Logger()
        success_payload = mock.Mock()
        success_payload.__enter__ = mock.Mock(return_value=success_payload)
        success_payload.__exit__ = mock.Mock(return_value=False)
        success_payload.read.return_value = b'{"response":"ok"}'

        with mock.patch("core.llm.ollama_provider.ensure_ollama_server", return_value=True) as ensure_mock, \
             mock.patch(
                 "core.llm.ollama_provider.urllib.request.urlopen",
                 side_effect=[http.client.RemoteDisconnected("Remote end closed connection without response"), success_payload],
             ) as urlopen_mock, \
             mock.patch("core.llm.ollama_provider.time.sleep") as sleep_mock:
            resolved = ollama_provider.resolve_ollama_model_for_request(
                "gemma4:e4b",
                logger=logger,
                context="자막 LLM",
                timeout=1.0,
                allow_fallback=False,
            )

        self.assertEqual(resolved, "gemma4:e4b")
        self.assertEqual(urlopen_mock.call_count, 2)
        self.assertGreaterEqual(ensure_mock.call_count, 2)
        sleep_mock.assert_called_once()
        self.assertEqual(logger.lines, [])


if __name__ == "__main__":
    unittest.main()
