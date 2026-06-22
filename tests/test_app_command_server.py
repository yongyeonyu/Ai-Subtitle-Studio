import socket
import threading
import unittest
from unittest import mock

from core.automation.app_command_protocol import (
    APP_COMMAND_BUFFER_SIZE,
    build_command_payload,
    build_command_result,
    decode_command_result,
    encode_command_payload,
    encode_command_result,
)
from core.automation.app_command_server import LocalAppCommandServer
from core.runtime.stage_metrics import reset_stage_metrics, snapshot_stage_metrics


class LocalAppCommandServerTests(unittest.TestCase):
    def setUp(self):
        reset_stage_metrics()
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._server_socket.bind(("127.0.0.1", 0))
        self._server = LocalAppCommandServer(self._server_socket)
        self._server.start()
        self._server_addr = self._server_socket.getsockname()
        self._client_sockets: list[socket.socket] = []

    def tearDown(self):
        self._server.close()
        for sock in self._client_sockets:
            try:
                sock.close()
            except OSError:
                pass
        reset_stage_metrics()

    def _client(self, *, timeout_sec: float) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_sec)
        self._client_sockets.append(sock)
        return sock

    def _send(self, sock: socket.socket, command: str, **fields):
        sock.sendto(encode_command_payload(build_command_payload(command, **fields)), self._server_addr)

    def _recv(self, sock: socket.socket) -> dict:
        raw, _addr = sock.recvfrom(APP_COMMAND_BUFFER_SIZE)
        return decode_command_result(raw)

    def test_status_command_is_not_blocked_by_slow_stateful_command(self):
        slow_entered = threading.Event()
        release_slow = threading.Event()

        def handler(payload: dict) -> dict:
            command = str(payload.get("command", ""))
            if command == "guided-subtitle-run":
                slow_entered.set()
                self.assertTrue(release_slow.wait(1.0))
                return build_command_result(command, ok=True, message="guided_done")
            return build_command_result(command, ok=True, data={"command": command})

        self._server.set_handler(handler)
        slow_client = self._client(timeout_sec=1.0)
        status_client = self._client(timeout_sec=0.4)

        self._send(slow_client, "guided-subtitle-run", path="/tmp/media.mp4")
        self.assertTrue(slow_entered.wait(0.5))

        self._send(status_client, "guided-subtitle-status")
        status_result = self._recv(status_client)
        self.assertTrue(status_result["ok"])
        self.assertEqual(status_result["command"], "guided-subtitle-status")
        self.assertEqual(status_result["data"]["command"], "guided-subtitle-status")

        release_slow.set()
        slow_result = self._recv(slow_client)
        self.assertTrue(slow_result["ok"])
        self.assertEqual(slow_result["message"], "guided_done")

    def test_stateful_commands_remain_serialized(self):
        first_entered = threading.Event()
        release_first = threading.Event()
        active_lock = threading.Lock()
        active_calls = 0
        overlapped = threading.Event()
        call_count = 0

        def handler(payload: dict) -> dict:
            nonlocal active_calls, call_count
            command = str(payload.get("command", ""))
            with active_lock:
                active_calls += 1
                call_count += 1
                current_call = call_count
                if active_calls > 1:
                    overlapped.set()
            if command == "editor-smart-split" and current_call == 1:
                first_entered.set()
                self.assertTrue(release_first.wait(1.0))
            with active_lock:
                active_calls -= 1
            return build_command_result(command, ok=True, message=f"done_{current_call}")

        self._server.set_handler(handler)
        first_client = self._client(timeout_sec=1.0)
        second_client = self._client(timeout_sec=0.2)

        self._send(first_client, "editor-smart-split")
        self.assertTrue(first_entered.wait(0.5))

        self._send(second_client, "editor-smart-split")
        with self.assertRaises(socket.timeout):
            self._recv(second_client)
        self.assertFalse(overlapped.is_set())

        release_first.set()
        first_result = self._recv(first_client)
        second_client.settimeout(1.0)
        second_result = self._recv(second_client)
        self.assertTrue(first_result["ok"])
        self.assertTrue(second_result["ok"])
        self.assertFalse(overlapped.is_set())

    def test_command_server_records_wait_busy_and_queue_metrics(self):
        release_first = threading.Event()
        first_entered = threading.Event()

        def handler(payload: dict) -> dict:
            command = str(payload.get("command", ""))
            if command == "editor-smart-split":
                first_entered.set()
                release_first.wait(1.0)
            return build_command_result(command, ok=True)

        self._server.set_handler(handler)
        first_client = self._client(timeout_sec=1.0)
        status_client = self._client(timeout_sec=1.0)

        self._send(first_client, "editor-smart-split")
        self.assertTrue(first_entered.wait(0.5))
        self._send(status_client, "guided-subtitle-status")
        self.assertTrue(self._recv(status_client)["ok"])
        release_first.set()
        self.assertTrue(self._recv(first_client)["ok"])

        metrics = snapshot_stage_metrics(max_events=20)
        self.assertIn("automation", metrics["resources"])
        self.assertGreaterEqual(metrics["resources"]["automation"]["stage_ready_count"], 2)
        self.assertGreaterEqual(metrics["resources"]["automation"]["stage_done_count"], 2)
        self.assertGreaterEqual(metrics["resources"]["automation"]["max_queue_depth"], 1)

    def test_oversized_status_payload_is_compacted_before_udp_send(self):
        huge_logs = ["상태 로그 " + ("x" * 2000) for _ in range(80)]

        def handler(payload: dict) -> dict:
            command = str(payload.get("command", ""))
            return build_command_result(
                command,
                ok=True,
                data={
                    "editor_open": True,
                    "editor_state": "ST_EDITING",
                    "editor_runtime": {"segment_count": 3},
                    "runtime_resource": {"pressure_stage": "normal", "rss_gb": 0.42},
                    "recent_logs": huge_logs,
                    "recent_stage_logs": huge_logs,
                },
            )

        self._server.set_handler(handler)
        status_client = self._client(timeout_sec=1.0)

        self._send(status_client, "status")
        result = self._recv(status_client)

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_response_truncated"])
        self.assertEqual(result["data"]["editor_state"], "ST_EDITING")
        self.assertLess(len(result["data"]["recent_logs"]), len(huge_logs))

    def test_medium_status_payload_is_compacted_before_send(self):
        medium_logs = ["상태 로그 " + ("x" * 700) for _ in range(16)]

        def handler(payload: dict) -> dict:
            command = str(payload.get("command", ""))
            return build_command_result(
                command,
                ok=True,
                data={
                    "editor_open": True,
                    "editor_state": "ST_PROC",
                    "editor_runtime": {
                        "segment_count": 413,
                        "playhead_sec": 1450.2,
                        "start_button_text": "시작",
                        "start_button_enabled": True,
                        "geometry": {
                            "video_frame": {
                                "x": 12,
                                "y": 24,
                                "width": 640,
                                "height": 360,
                                "right": 651,
                                "bottom": 383,
                                "visible": True,
                                "debug": "x" * 2000,
                            },
                            "timeline_frame": {"x": 12, "y": 400, "width": 640, "height": 180},
                            "editor_splitter_sizes": [220, 640],
                        },
                    },
                    "generation_stage": "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중",
                    "last_stage_key": "subtitle-generation",
                    "subtitle_count": 413,
                    "roughcut_state": {"status": "queued", "pending": True, "running": True, "debug": "x" * 600},
                    "roughcut_runtime": {
                        "selected_candidate_id": "candidate_current",
                        "candidate_count": 3,
                        "selected_chapter_id": "A_0000",
                        "selected_segment_id": "A",
                        "sequence_preview_active": True,
                        "order_summary": "카드 1/4 · A > C > B > D",
                    },
                    "runtime_timestamp": 1234.5,
                    "runtime_resource": {"pressure_stage": "warning", "rss_gb": 0.42},
                    "recent_logs": medium_logs,
                },
            )

        self._server.set_handler(handler)
        status_client = self._client(timeout_sec=1.0)

        self._send(status_client, "status")
        result = self._recv(status_client)

        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_response_truncated"])
        self.assertEqual(result["data"]["editor_state"], "ST_PROC")
        self.assertEqual(result["data"]["editor_runtime"]["segment_count"], 413)
        self.assertEqual(result["data"]["editor_runtime"]["start_button_text"], "시작")
        self.assertTrue(result["data"]["editor_runtime"]["start_button_enabled"])
        geometry = result["data"]["editor_runtime"]["geometry"]
        self.assertEqual(geometry["video_frame"]["width"], 640)
        self.assertEqual(geometry["timeline_frame"]["y"], 400)
        self.assertEqual(geometry["editor_splitter_sizes"], [220, 640])
        self.assertNotIn("debug", geometry["video_frame"])
        self.assertEqual(result["data"]["generation_stage"], "⏳ [STT+자막 LLM] 인식 결과 교정/분리 중")
        self.assertEqual(result["data"]["last_stage_key"], "subtitle-generation")
        self.assertEqual(result["data"]["subtitle_count"], 413)
        self.assertEqual(result["data"]["roughcut_state"]["status"], "queued")
        self.assertNotIn("debug", result["data"]["roughcut_state"])
        self.assertEqual(result["data"]["roughcut_runtime"]["selected_candidate_id"], "candidate_current")
        self.assertEqual(result["data"]["roughcut_runtime"]["candidate_count"], 3)
        self.assertTrue(result["data"]["roughcut_runtime"]["sequence_preview_active"])
        self.assertEqual(result["data"]["runtime_timestamp"], 1234.5)
        self.assertLess(len(encode_command_result(result)), 8192)

    def test_stateful_guided_run_payload_is_compacted_before_send(self):
        large_rows = [{"status": "처리 중", "info": "x" * 800} for _ in range(20)]

        def handler(payload: dict) -> dict:
            command = str(payload.get("command", ""))
            return build_command_result(
                command,
                ok=True,
                accepted=True,
                message="guided_subtitle_started",
                data={"rows": large_rows, "snapshot": "x" * 12000},
            )

        self._server.set_handler(handler)
        client = self._client(timeout_sec=1.0)

        self._send(client, "guided-subtitle-run", path="/tmp/media.mp4")
        result = self._recv(client)

        self.assertTrue(result["ok"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["message"], "guided_subtitle_started")
        self.assertTrue(result["data"]["response_truncated"])
        self.assertNotIn("response_send_fallback", result["data"])
        self.assertLess(len(encode_command_result(result)), 8192)

    def test_status_handler_timeout_returns_cached_result(self):
        release_second = threading.Event()
        call_count = 0

        def handler(payload: dict) -> dict:
            nonlocal call_count
            call_count += 1
            command = str(payload.get("command", ""))
            if call_count == 1:
                return build_command_result(
                    command,
                    ok=True,
                    data={"editor_state": "ST_PROC", "runtime_resource": {"pressure_stage": "warning"}},
                )
            release_second.wait(1.0)
            return build_command_result(command, ok=True, data={"editor_state": "late"})

        self._server.set_handler(handler)
        first_client = self._client(timeout_sec=1.0)
        second_client = self._client(timeout_sec=1.0)

        self._send(first_client, "status")
        first = self._recv(first_client)
        self.assertEqual(first["data"]["editor_state"], "ST_PROC")

        with mock.patch("core.automation.app_command_server._READ_HANDLER_TIMEOUT_SEC", 0.05):
            self._send(second_client, "status")
            second = self._recv(second_client)

        release_second.set()
        self.assertTrue(second["ok"])
        self.assertTrue(second["data"]["status_handler_timeout"])
        self.assertTrue(second["data"]["status_response_cached"])
        self.assertEqual(second["data"]["editor_state"], "ST_PROC")

    def test_status_send_failure_falls_back_to_compact_packet(self):
        class _FakeSocket:
            def __init__(self):
                self.sent: list[bytes] = []

            def sendto(self, payload: bytes, _addr):
                if not self.sent:
                    self.sent.append(payload)
                    raise OSError("message too long")
                self.sent.append(payload)
                return len(payload)

        fake_socket = _FakeSocket()
        server = LocalAppCommandServer(fake_socket)  # type: ignore[arg-type]
        oversized = {"recent_logs": ["x" * 4000 for _ in range(100)]}
        server.set_handler(lambda payload: build_command_result(str(payload.get("command", "")), ok=True, data=oversized))

        server._handle_request(encode_command_payload(build_command_payload("status")), ("127.0.0.1", 12345))

        self.assertEqual(len(fake_socket.sent), 2)
        result = decode_command_result(fake_socket.sent[-1])
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["status_response_send_fallback"])
        self.assertTrue(result["data"]["status_response_truncated"])
        self.assertLess(len(encode_command_result(result)), 4096)

    def test_start_recreates_dead_server_thread(self):
        fake_socket = mock.Mock()
        first_thread = mock.Mock()
        first_thread.is_alive.return_value = False
        second_thread = mock.Mock()
        second_thread.is_alive.return_value = True

        with mock.patch("core.automation.app_command_server.threading.Thread", side_effect=[first_thread, second_thread]) as thread_ctor:
            server = LocalAppCommandServer(fake_socket)
            server.start()
            server.start()

        self.assertEqual(thread_ctor.call_count, 2)
        first_thread.start.assert_called_once()
        second_thread.start.assert_called_once()


if __name__ == "__main__":
    unittest.main()
