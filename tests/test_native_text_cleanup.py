import os
import unittest

from core import native_text_cleanup as native
from core.engine.subtitle_text_policy import clean_subtitle_text, enforce_final_subtitle_text_policy


def _python_sequential_replace(text: str, corrections: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    applied: list[tuple[str, str]] = []
    for old, new in corrections.items():
        if old and old in text:
            text = text.replace(old, new)
            applied.append((old, new))
    return text, applied


class NativeTextCleanupTests(unittest.TestCase):
    def test_correction_index_token_tracks_content_changes(self):
        self.assertNotEqual(
            native.correction_index_token({"틴니핑": "티니핑"}),
            native.correction_index_token({"틴니핑": "티니핑!"}),
        )

    def test_single_clean_keeps_sequential_correction_semantics(self):
        corrections = {
            "소설과 유무시입니다": "소설기유모씨입니다",
            "티니핑": "티니핑.",
            "티니핑.": "티니핑",
        }

        cleaned = clean_subtitle_text("소설과 유무시입니다 티니핑", corrections)

        self.assertEqual(cleaned, "소설기유모씨입니다 티니핑")

    def test_batch_policy_matches_python_sequential_replace_reference(self):
        corrections = {
            "ab": "x",
            "x": "xy",
            "xyxy": "z",
            "소설가 유무씨": "소설가유모씨",
        }
        texts = ["ab", "xyxy", "소설가 유무씨", "변경 없음"]
        expected = [_python_sequential_replace(text, corrections)[0] for text in texts]

        result = enforce_final_subtitle_text_policy(
            [
                {"start": float(idx), "end": float(idx) + 1.0, "text": text}
                for idx, text in enumerate(texts)
            ],
            corrections,
        )

        self.assertEqual([row["text"] for row in result], expected)

    def test_final_policy_flattens_non_speaker_linebreaks(self):
        result = enforce_final_subtitle_text_policy(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "어\n유스 어드벤처 2026",
                    "speaker_list": ["00"],
                }
            ],
            None,
        )

        self.assertEqual(result[0]["text"], "어 유스 어드벤처 2026")

    def test_final_policy_preserves_two_speaker_linebreaks(self):
        result = enforce_final_subtitle_text_policy(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "안녕하세요\n반갑습니다",
                    "speaker_list": ["00", "01"],
                }
            ],
            None,
        )

        self.assertEqual(result[0]["text"], "안녕하세요\n반갑습니다")

    def test_final_policy_strips_quote_marks_but_keeps_inner_apostrophes(self):
        result = enforce_final_subtitle_text_policy(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "\"왜?\" ‘단독’ I’ll don't",
                }
            ],
            None,
        )

        self.assertEqual(result[0]["text"], "왜? 단독 I’ll don't")

    def test_native_indexed_batch_keeps_matches_introduced_inside_replacement_text(self):
        corrections = {
            "ab": "pqx",
            "x요": "X요",
            "pqX요": "완료",
            "없는규칙": "미사용",
        }
        texts = ["ab요", "변경 없음"]
        expected = [_python_sequential_replace(text, corrections) for text in texts]

        result = enforce_final_subtitle_text_policy(
            [
                {"start": float(idx), "end": float(idx) + 1.0, "text": text}
                for idx, text in enumerate(texts)
            ],
            corrections,
        )

        self.assertEqual([row["text"] for row in result], [item[0] for item in expected])

    def test_native_batch_helper_matches_python_reference_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_TEXT_CLEANUP")
        try:
            os.environ["AI_SUBTITLE_NATIVE_TEXT_CLEANUP"] = "1"
            if not native.native_text_cleanup_enabled():
                self.skipTest("native text cleanup extension unavailable")
            corrections = {
                "하추핑": "하츄핑",
                "하츄핑": "하츄핑.",
                "하츄핑.": "하츄핑",
                "틴니핑": "티니핑",
            }
            texts = ["하추핑 틴니핑", "하츄핑", "없는 문장"]
            expected = [_python_sequential_replace(text, corrections) for text in texts]

            native_out = native.apply_corrections_batch(texts, corrections)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_TEXT_CLEANUP", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_TEXT_CLEANUP"] = previous

        self.assertIsNotNone(native_out)
        out_texts, applied_batches = native_out or ([], [])
        self.assertEqual(out_texts, [item[0] for item in expected])
        self.assertEqual(applied_batches, [item[1] for item in expected])

    def test_native_compiled_db_helper_matches_python_reference_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_TEXT_CLEANUP")
        try:
            os.environ["AI_SUBTITLE_NATIVE_TEXT_CLEANUP"] = "1"
            if native.correction_backend() != "cpp-db":
                self.skipTest("native compiled correction DB unavailable")
            native.clear_correction_index_cache()
            corrections = {
                "핫쇼핑이다": "하츄핑이다",
                "하츄핑이다": "하츄핑",
                "틴니핑": "티니핑",
            }
            texts = ["핫쇼핑이다", "틴니핑", "변경 없음"]
            expected = [_python_sequential_replace(text, corrections) for text in texts]

            first = native.apply_corrections_batch(texts, corrections)
            second = native.apply_corrections_batch(texts, corrections)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_TEXT_CLEANUP", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_TEXT_CLEANUP"] = previous

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual((first or ([], []))[0], [item[0] for item in expected])
        self.assertEqual((second or ([], []))[1], [item[1] for item in expected])


if __name__ == "__main__":
    unittest.main()
