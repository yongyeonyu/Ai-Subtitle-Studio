import unittest
from unittest.mock import patch

from core.audio.apple_speech_native import (
    APPLE_SPEECH_DEFAULT_LOCALE,
    apple_speech_transcribe,
    apple_speech_benchmark_only,
    apple_speech_challenger_enabled,
    apple_speech_model,
    apple_speech_probe_benchmark_row,
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

    def test_probe_benchmark_row_uses_support_payload(self):
        with patch("core.audio.apple_speech_native.IS_MAC", True), \
             patch("core.audio.apple_speech_native.native_swift_runtime_enabled", return_value=True), \
             patch("core.audio.apple_speech_native.request_native_core_task", return_value={
                 "available": True,
                 "detector_available": True,
                 "locale": "ko-KR",
                 "reason": "runtime_class_available",
             }):
            row = apple_speech_probe_benchmark_row({"stt_apple_speech_locale": "ko-KR"}, elapsed_sec=0.25)

        self.assertEqual(row["task"], "stt")
        self.assertEqual(row["backend"], "apple_speech")
        self.assertEqual(row["model"], "apple_speech:ko-KR")
        self.assertTrue(row["available"])
        self.assertTrue(row["detector_available"])
        self.assertEqual(row["elapsed_sec"], 0.25)
        self.assertTrue(row["probe_only"])

    def test_apple_speech_transcribe_returns_native_payload_when_available(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "backend": "apple_speech",
            "locale": "ko-KR",
            "segments": [{"start": 0.0, "end": 1.0, "text": "안녕하세요"}],
            "text": "안녕하세요",
        }):
            result = apple_speech_transcribe("/tmp/test.wav", {"stt_apple_speech_locale": "ko-KR"})

        self.assertTrue(result.ok)
        self.assertEqual(result.locale, "ko-KR")
        self.assertEqual(result.payload["backend"], "apple_speech")
        self.assertEqual(result.payload["chunk_path"], "/tmp/test.wav")
        self.assertFalse(result.payload["word_timestamps"])

    def test_apple_speech_transcribe_preserves_requested_word_timestamp_flag(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "backend": "apple_speech",
            "locale": "ko-KR",
            "segments": [{"start": 0.0, "end": 1.0, "text": "안녕하세요"}],
            "text": "안녕하세요",
            "word_timestamps": True,
        }):
            result = apple_speech_transcribe(
                "/tmp/test.wav",
                {"stt_apple_speech_locale": "ko-KR"},
                word_timestamps=True,
            )

        self.assertTrue(result.ok)
        self.assertTrue(result.payload["word_timestamps"])

    def test_apple_speech_transcribe_splits_single_long_punctuated_segment(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "backend": "apple_speech",
            "locale": "ko-KR",
            "segments": [{
                "start": 0.0,
                "end": 12.0,
                "text": "첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다.",
            }],
            "text": "첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다.",
        }):
            result = apple_speech_transcribe("/tmp/test.wav", {"stt_apple_speech_locale": "ko-KR"})

        self.assertTrue(result.ok)
        self.assertTrue(result.payload["synthetic_sentence_split"])
        self.assertEqual(len(result.payload["segments"]), 3)
        self.assertEqual(result.payload["segments"][0]["text"], "첫 문장입니다.")
        self.assertEqual(result.payload["segments"][1]["text"], "둘째 문장입니다.")
        self.assertEqual(result.payload["segments"][2]["text"], "셋째 문장입니다.")
        self.assertEqual(result.payload["segments"][0]["start"], 0.0)
        self.assertEqual(result.payload["segments"][-1]["end"], 12.0)

    def test_apple_speech_transcribe_keeps_decimal_text_inside_split_sentences(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "backend": "apple_speech",
            "locale": "ko-KR",
            "segments": [{
                "start": 0.0,
                "end": 15.0,
                "text": "연비가 17.8입니다. 다음은 11.4예요.",
            }],
            "text": "연비가 17.8입니다. 다음은 11.4예요.",
        }):
            result = apple_speech_transcribe("/tmp/test.wav", {"stt_apple_speech_locale": "ko-KR"})

        self.assertTrue(result.ok)
        self.assertEqual(len(result.payload["segments"]), 2)
        self.assertEqual(result.payload["segments"][0]["text"], "연비가 17.8입니다.")
        self.assertEqual(result.payload["segments"][1]["text"], "다음은 11.4예요.")

    def test_apple_speech_transcribe_splits_clause_like_segments_without_punctuation(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "backend": "apple_speech",
            "locale": "ko-KR",
            "segments": [{
                "start": 0.0,
                "end": 12.0,
                "text": "지금 에코프로를 놓은 상태고 크루즈 컨트롤 걸어볼게요",
            }],
            "text": "지금 에코프로를 놓은 상태고 크루즈 컨트롤 걸어볼게요",
        }):
            result = apple_speech_transcribe("/tmp/test.wav", {"stt_apple_speech_locale": "ko-KR"})

        self.assertTrue(result.ok)
        self.assertTrue(result.payload["synthetic_clause_split"])
        self.assertEqual(len(result.payload["segments"]), 2)
        self.assertEqual(result.payload["segments"][0]["text"], "지금 에코프로를 놓은 상태고")
        self.assertEqual(result.payload["segments"][1]["text"], "크루즈 컨트롤 걸어볼게요")

    def test_apple_speech_transcribe_surfaces_native_error(self):
        with patch("core.audio.apple_speech_native.apple_speech_support", return_value=type("Support", (), {
            "available": True,
            "detector_available": True,
            "reason": "runtime_class_available",
            "locale": "ko-KR",
        })()), patch("core.audio.apple_speech_native.request_native_core_task", return_value={
            "error": "apple_speech_transcribe_failed:test",
        }):
            result = apple_speech_transcribe("/tmp/test.wav", {"stt_apple_speech_locale": "ko-KR"})

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "apple_speech_transcribe_failed:test")


if __name__ == "__main__":
    unittest.main()
