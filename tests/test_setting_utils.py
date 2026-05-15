import unittest
from unittest.mock import patch

from core.runtime.setting_utils import env_bool, positive_int, setting_bool


class SettingUtilsTests(unittest.TestCase):
    def test_setting_bool_handles_defaulted_tokens(self):
        self.assertTrue(setting_bool("enabled", False))
        self.assertFalse(setting_bool("disabled", True))
        self.assertFalse(setting_bool("사용 안함", True, false_values={"0", "false", "off", "no", "사용 안함", "끔"}))
        self.assertTrue(setting_bool("", True))
        self.assertFalse(setting_bool("", False))

    def test_setting_bool_supports_false_only_string_mode(self):
        kwargs = {
            "false_values": {"0", "false", "off", "no", "사용 안함", "끔"},
            "false_only_strings": True,
            "empty_is_default": False,
        }
        self.assertTrue(setting_bool("", True, **kwargs))
        self.assertTrue(setting_bool("maybe", False, **kwargs))
        self.assertFalse(setting_bool("0", True, **kwargs))
        self.assertTrue(setting_bool(1, False, **kwargs))
        self.assertFalse(setting_bool(0, True, **kwargs))

    def test_setting_bool_supports_true_only_string_mode(self):
        kwargs = {
            "true_values": {"1", "true", "yes", "on", "사용", "켜짐"},
            "true_only_strings": True,
            "empty_is_default": False,
        }
        self.assertTrue(setting_bool("yes", False, **kwargs))
        self.assertFalse(setting_bool("maybe", True, **kwargs))
        self.assertFalse(setting_bool("", True, **kwargs))
        self.assertTrue(setting_bool(1, False, **kwargs))
        self.assertFalse(setting_bool(0, True, **kwargs))

    def test_env_bool_ignores_unknown_values(self):
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_TEST_BOOL": "1"}, clear=False):
            self.assertTrue(env_bool("AI_SUBTITLE_STUDIO_TEST_BOOL"))
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_TEST_BOOL": "0"}, clear=False):
            self.assertFalse(env_bool("AI_SUBTITLE_STUDIO_TEST_BOOL"))
        with patch.dict("os.environ", {"AI_SUBTITLE_STUDIO_TEST_BOOL": "maybe"}, clear=False):
            self.assertIsNone(env_bool("AI_SUBTITLE_STUDIO_TEST_BOOL"))

    def test_positive_int_clamps_invalid_or_non_positive_values(self):
        self.assertEqual(positive_int("12.8", 3), 12)
        self.assertEqual(positive_int("0", 3), 3)
        self.assertEqual(positive_int("-4", 3), 3)
        self.assertEqual(positive_int("bad", 3), 3)


if __name__ == "__main__":
    unittest.main()
