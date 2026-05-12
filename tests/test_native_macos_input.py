import unittest
from unittest.mock import patch

import core.native_macos_input as native_input


class NativeMacOSInputTests(unittest.TestCase):
    def tearDown(self):
        native_input.clear_native_input_activity_cache()

    def test_recent_native_user_input_uses_swift_core_snapshot(self):
        payload = {
            "source": "swift_cgevent_source",
            "ok": True,
            "recent": True,
            "event_type": "mouse_moved",
            "age_sec": 0.03,
        }
        with patch("core.native_macos_input.IS_MAC", True), patch(
            "core.native_macos_input.request_native_core_task",
            return_value=payload,
        ) as request:
            detected, snapshot = native_input.recent_native_user_input_detected(threshold_sec=0.25)

        self.assertTrue(detected)
        self.assertEqual(snapshot["event_type"], "mouse_moved")
        request.assert_called_once_with("input_activity_snapshot", {"recent_threshold_sec": 0.25})

    def test_recent_native_user_input_falls_back_to_age_threshold(self):
        payload = {
            "source": "swift_cgevent_source",
            "ok": True,
            "recent": False,
            "event_type": "key_down",
            "age_sec": 0.12,
        }
        with patch("core.native_macos_input.IS_MAC", True), patch(
            "core.native_macos_input.request_native_core_task",
            return_value=payload,
        ):
            detected, snapshot = native_input.recent_native_user_input_detected(threshold_sec=0.25)

        self.assertTrue(detected)
        self.assertEqual(snapshot["event_type"], "key_down")

    def test_native_input_disabled_off_macos(self):
        with patch("core.native_macos_input.IS_MAC", False), patch(
            "core.native_macos_input.request_native_core_task",
        ) as request:
            detected, snapshot = native_input.recent_native_user_input_detected()

        self.assertFalse(detected)
        self.assertEqual(snapshot, {})
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
