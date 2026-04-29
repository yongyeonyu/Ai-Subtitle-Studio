# Version: 03.00.21
# Phase: PHASE2
import unittest

from core.engine.llm_correction_guard import contains_timecode, safe_llm_chunks, validate_llm_chunks


class LLMCorrectionGuardTests(unittest.TestCase):
    def test_accepts_spacing_and_punctuation_changes(self):
        ok, reason = validate_llm_chunks("아니 이게 맞나", ["아니, 이게 맞나"])

        self.assertTrue(ok, reason)

    def test_rejects_word_addition(self):
        chunks = safe_llm_chunks("아니 이게 맞나", ["아니 이게 정말 맞는 것 같습니다"])

        self.assertIsNone(chunks)

    def test_rejects_word_deletion(self):
        chunks = safe_llm_chunks("현금 계산할게 감사합니다", ["현금 계산할게"])

        self.assertIsNone(chunks)

    def test_rejects_timecodes(self):
        self.assertTrue(contains_timecode("[00:01.23] 안녕"))
        chunks = safe_llm_chunks("안녕", ["[00:01.23] 안녕"])

        self.assertIsNone(chunks)

    def test_accepts_split_without_content_change(self):
        chunks = safe_llm_chunks("처음입니다 다음입니다", ["처음입니다", "다음입니다"])

        self.assertEqual(chunks, ["처음입니다", "다음입니다"])


if __name__ == "__main__":
    unittest.main()
