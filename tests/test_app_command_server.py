import socket
import threading
import unittest

from core.automation.app_command_protocol import (
    APP_COMMAND_BUFFER_SIZE,
    build_command_payload,
    build_command_result,
    decode_command_result,
    encode_command_payload,
)
from core.automation.app_command_server import LocalAppCommandServer


class LocalAppCommandServerTests(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
