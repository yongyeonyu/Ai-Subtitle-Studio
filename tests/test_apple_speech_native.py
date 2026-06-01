import unittest
from unittest.mock import patch

from core.audio.apple_speech_native import (
    APPLE_SPEECH_DEFAULT_LOCALE,
    apple_speech_benchmark_only,
    apple_speech_challenger_enabled,
    apple_speech_model,
    apple_speech_support,
    apple_speech_vad_coupled_enabled,
)


class AppleSpeechNativeTests(unittest.TestCase):
    def test_apple_speech_support_reads_native_probe_payload(self):
        with patch("core.audio.apple_speech_native.IS_MAC", True), \
             patch("core.audio.apple_speech_native.native_swift_runtime_enabled", return_value=True), \
             patch("core.audio.apple_speech_native.request_native_core_task", return_value={
                 "available": True,
                 "detector_available": True,
                 "locale": "ko-KR",
                 "reason": "runtime_class_available",
             }):
            support = apple_speech_support({"stt_apple_speech_locale": "ko-KR"})

        self.assertTrue(support.available)
        self.assertTrue(support.detector_available)
        self.assertEqual(support.locale, "ko-KR")
        self.assertEqual(support.reason, "runtime_class_available")

    def test_apple_speech_challenger_gate_requires_mac_and_hidden_flag(self):
        with patch("core.audio.apple_speech_native.IS_MAC", True), \
             patch("core.audio.apple_speech_native.native_swift_runtime_enabled", return_value=True):
            self.assertTrue(apple_speech_challenger_enabled({"stt_apple_speech_challenger_enabled": True}))
            self.assertFalse(apple_speech_challenger_enabled({"stt_apple_speech_challenger_enabled": False}))

    def test_apple_speech_vad_remains_coupled_to_challenger(self):
        with patch("core.audio.apple_speech_native.IS_MAC", True), \
             patch("core.audio.apple_speech_native.native_swift_runtime_enabled", return_value=True):
            enabled = apple_speech_vad_coupled_enabled(
                {
                    "stt_apple_speech_challenger_enabled": True,
                    "stt_apple_speech_vad_coupled_enabled": True,
                }
            )
            disabled = apple_speech_vad_coupled_enabled(
                {
                    "stt_apple_speech_challenger_enabled": True,
                    "stt_apple_speech_vad_coupled_enabled": False,
                }
            )

        self.assertTrue(enabled)
        self.assertFalse(disabled)
        self.assertTrue(apple_speech_benchmark_only({}))
        self.assertEqual(apple_speech_model(None), f"apple_speech:{APPLE_SPEECH_DEFAULT_LOCALE}")


if __name__ == "__main__":
    unittest.main()
