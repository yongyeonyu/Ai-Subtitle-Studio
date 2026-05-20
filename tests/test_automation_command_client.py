import unittest
from unittest.mock import Mock, patch

from core.automation.app_command_protocol import build_command_payload
from tools.automation_command_client import (
    result_is_waiting_for_app,
    send_app_command_with_readiness_retry,
)


class AutomationCommandClientTests(unittest.TestCase):
    def test_read_only_command_retries_until_app_ready(self):
        sender = Mock(
            side_effect=[
                OSError("timed out"),
                {"ok": True, "queued": True, "message": "queued_until_main_window_ready", "data": {}},
                {"ok": True, "queued": False, "message": "", "data": {"editor_open": True}},
            ]
        )

        with patch("tools.automation_command_client.time.sleep", return_value=None):
            result = send_app_command_with_readiness_retry(
                build_command_payload("status"),
                timeout_sec=2.0,
                retry_sleep_sec=0.0,
                sender=sender,
            )

        self.assertTrue(result["ok"])
        self.assertFalse(result.get("queued"))
        self.assertEqual(sender.call_count, 3)

    def test_state_changing_command_is_not_retried(self):
        sender = Mock(side_effect=OSError("timed out"))

        with self.assertRaises(OSError):
            send_app_command_with_readiness_retry(
                build_command_payload("editor-smart-split"),
                timeout_sec=2.0,
                sender=sender,
            )

        sender.assert_called_once()

    def test_snapshot_command_is_not_retried_after_timeout(self):
        sender = Mock(side_effect=OSError("timed out"))

        with self.assertRaises(OSError):
            send_app_command_with_readiness_retry(
                build_command_payload("capture-snapshot", path="/tmp/snap.png"),
                timeout_sec=2.0,
                sender=sender,
            )

        sender.assert_called_once()

    def test_result_is_waiting_for_app_accepts_server_startup_message(self):
        self.assertFalse(result_is_waiting_for_app({"ok": True, "queued": True, "message": "snapshot_queued"}))
        self.assertTrue(result_is_waiting_for_app({"ok": True, "message": "queued_until_main_window_ready"}))
        self.assertFalse(result_is_waiting_for_app({"ok": True, "message": ""}))


if __name__ == "__main__":
    unittest.main()
