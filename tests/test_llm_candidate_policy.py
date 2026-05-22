import unittest

from core.engine.llm_candidate_policy import (
    build_llm_candidate_options,
    format_candidate_options_for_prompt,
    validate_candidate_locked_chunks,
)


class LlmCandidatePolicyTests(unittest.TestCase):
    def test_builds_deduped_candidate_options_from_source_text(self):
        candidates = build_llm_candidate_options(
            "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다",
            threshold=8,
            rules={"end_words": ["습니다"]},
            settings={"llm_candidate_policy_enabled": True, "llm_candidate_policy_max_candidates": 4},
        )

        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["strategy"], "source")
        self.assertTrue(any(item["chunk_count"] > 1 for item in candidates))

    def test_builds_lora_target_line_count_candidate(self):
        candidates = build_llm_candidate_options(
            "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다",
            threshold=20,
            settings={
                "llm_candidate_policy_enabled": True,
                "subtitle_target_line_count": 2,
                "llm_candidate_policy_max_candidates": 5,
            },
        )

        lora_line = next(item for item in candidates if item["strategy"] == "lora_line_count")
        self.assertEqual(lora_line["chunk_count"], 2)

    def test_lora_ground_truth_line_break_pattern_is_primary_candidate(self):
        candidates = build_llm_candidate_options(
            "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다",
            threshold=20,
            settings={
                "llm_candidate_policy_enabled": True,
                "llm_candidate_policy_max_candidates": 5,
                "linebreak_lora_policy_enabled": True,
                "_lora_generation_profile": {
                    "examples": [{"text": "오늘은 행사장에 왔습니다\n그리고 촬영을 시작합니다", "line_break_pattern": "10|11", "score": 94.0}],
                    "learned_rules": [{"kind": "learned_line_break_rules", "rule_text": "10|11", "score": 90.0}],
                },
            },
        )

        lora_candidate = next(item for item in candidates if item["strategy"] == "lora_ground_truth_line_break")
        self.assertEqual(lora_candidate["id"], "L1")
        self.assertTrue(lora_candidate["lora_primary"])
        self.assertEqual(lora_candidate["chunk_count"], 2)

    def test_prompt_formats_locked_candidates_as_json_block(self):
        candidates = build_llm_candidate_options("오늘은 행사장에 왔습니다 그리고 시작합니다", threshold=8)

        prompt = format_candidate_options_for_prompt(candidates)

        self.assertIn("[후보 잠금 모드]", prompt)
        self.assertIn("LoRA ground truth", prompt)
        self.assertIn('"id": "A"', prompt)
        self.assertIn('"result"', prompt)

    def test_accepts_exact_candidate_match(self):
        source = "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다"
        candidates = build_llm_candidate_options(source, threshold=8)

        chunks, decision = validate_candidate_locked_chunks(source, candidates[0]["chunks"], candidates)

        self.assertEqual(chunks, candidates[0]["chunks"])
        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["reason"], "candidate_match")

    def test_rejects_output_outside_candidates_and_minimal_edit_budget(self):
        source = "오늘은 행사장에 왔습니다 그리고 촬영을 시작합니다"
        candidates = build_llm_candidate_options(source, threshold=8)

        chunks, decision = validate_candidate_locked_chunks(
            source,
            ["완전히 다른 설명을 새로 추가했습니다"],
            candidates,
            {"llm_candidate_policy_max_edit_ratio": 0.08},
        )

        self.assertIsNone(chunks)
        self.assertFalse(decision["accepted"])
        self.assertTrue(decision["reason"].startswith("not_candidate_or_minimal_edit:"))

    def test_rejects_semantic_rewrite_when_stt_candidate_contains_ground_truth(self):
        source = "아까 뭐래? 커피준데? 어"
        candidates = [
            {"id": "A", "label": "원문 유지", "chunks": [source]},
            {"id": "B", "label": "구어 호흡 분리", "chunks": ["아까 뭐래?", "커피준데?", "어"]},
        ]

        chunks, decision = validate_candidate_locked_chunks(
            source,
            ["커피즈가 같이 여기 맞은거예요"],
            candidates,
        )

        self.assertIsNone(chunks)
        self.assertFalse(decision["accepted"])
        self.assertEqual(decision["reason"].split(":", 1)[0], "not_candidate_or_minimal_edit")

    def test_accepts_locked_stt_candidate_line_break_without_rewrite(self):
        source = "아까 뭐래? 커피준데? 어"
        candidates = [
            {"id": "A", "label": "원문 유지", "chunks": [source]},
            {"id": "B", "label": "구어 호흡 분리", "chunks": ["아까 뭐래?", "커피준데?", "어"]},
        ]

        chunks, decision = validate_candidate_locked_chunks(
            source,
            ["아까 뭐래?", "커피준데?", "어"],
            candidates,
        )

        self.assertEqual(chunks, ["아까 뭐래?", "커피준데?", "어"])
        self.assertTrue(decision["accepted"])
        self.assertEqual(decision["selected_candidate_id"], "B")


if __name__ == "__main__":
    unittest.main()
