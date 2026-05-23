import unittest
from unittest.mock import patch

from core.native_swift_vad import vad_flags_to_segments_via_swift


class NativeSwiftVadTests(unittest.TestCase):
    def test_vad_flags_to_segments_via_swift_coerces_native_rows(self):
        with patch("core.native_swift_vad.IS_MAC", True), \
             patch("core.native_swift_vad.native_swift_runtime_enabled", return_value=True), \
             patch("core.native_swift_vad.request_native_core_task", return_value={
                 "segments": [
                     {
                         "start": 0.05,
                         "end": 0.35,
                         "source": "ten_vad",
                         "post_stt_align": True,
                         "vad_word_filter": False,
                         "speech_pad_sec": 0.05,
                         "min_silence_sec": 0.1,
                     }
                 ]
             }) as request:
            rows = vad_flags_to_segments_via_swift(
                [0, 1, 1, 0],
                hop_sec=0.1,
                min_speech_sec=0.1,
                min_silence_sec=0.1,
                speech_pad_sec=0.05,
                source="ten_vad",
                for_post_stt_align=True,
            )

        self.assertEqual(rows, [{
            "start": 0.05,
            "end": 0.35,
            "source": "ten_vad",
            "post_stt_align": True,
            "vad_word_filter": False,
            "speech_pad_sec": 0.05,
            "min_silence_sec": 0.1,
        }])
        payload = request.call_args.args[1]
        self.assertEqual(payload["flags"], [0, 1, 1, 0])
        self.assertEqual(payload["for_post_stt_align"], True)

    def test_vad_flags_to_segments_via_swift_respects_disable_setting(self):
        with patch("core.native_swift_vad.IS_MAC", True), \
             patch("core.native_swift_vad.native_swift_runtime_enabled", return_value=True), \
             patch("core.native_swift_vad.request_native_core_task") as request:
            rows = vad_flags_to_segments_via_swift(
                [1, 1],
                hop_sec=0.1,
                min_speech_sec=0.1,
                min_silence_sec=0.1,
                speech_pad_sec=0.0,
                source="silero",
                settings={"native_swift_vad_segments_enabled": False},
            )

        self.assertIsNone(rows)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
