# Version: 03.01.23
# Phase: PHASE2
import unittest

from core.engine.llm_correction_guard import contains_timecode, safe_llm_chunks, validate_llm_chunks
from core.subtitle_quality.llm_guarded_corrector import build_conservative_prompt, limited_negative_hints


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

    def test_conservative_prompt_adds_guard_rules_and_limited_negative_hints(self):
        prompt = build_conservative_prompt("기본 프롬프트", ["오답1", "오답2", "오답3", "오답4", "오답5", "오답6"])

        self.assertIn("검사/자동교정 보수 profile", prompt)
        self.assertIn("원문에 없는 단어", prompt)
        self.assertIn("오답1", prompt)
        self.assertNotIn("오답6", prompt)

    def test_negative_hints_are_deduplicated(self):
        hints = limited_negative_hints(["중복", "중복", "새"], limit=3)

        self.assertEqual(hints, ["중복", "새"])


if __name__ == "__main__":
    unittest.main()
