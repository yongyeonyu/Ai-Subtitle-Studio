import unittest

from core.engine.subtitle_context_refiner import refine_high_contextual_boundaries


def _word(text, start, end):
    return {"word": text, "start": start, "end": end}


class SubtitleContextRefinerTests(unittest.TestCase):
    def test_high_context_refiner_moves_boundary_to_word_timestamp_and_corrects_word(self):
        segments = [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "음요를 한 사람씩",
                "words": [
                    _word("음요를", 0.0, 0.30),
                    _word("한", 0.32, 0.45),
                    _word("사람씩", 0.47, 0.90),
                ],
            },
            {
                "start": 1.05,
                "end": 1.8,
                "text": "시켰다 그리고",
                "words": [
                    _word("시켰다", 1.05, 1.35),
                    _word("그리고", 1.40, 1.80),
                ],
            },
        ]

        def decide(_left, _right, _context):
            return {
                "action": "move_boundary",
                "boundary_after_word_index": 3,
                "corrections": [{"word_index": 0, "from": "음요를", "to": "음료를"}],
                "reason": "contextual noun correction and natural sentence boundary",
            }

        refined = refine_high_contextual_boundaries(
            segments,
            settings={
                "subtitle_mode": "high",
                "subtitle_llm_context_boundary_refine_enabled": True,
                "subtitle_llm_context_word_correction_enabled": True,
                "subtitle_llm_context_max_pairs": 4,
                "subtitle_llm_context_require_risk_signal": False,
                "subtitle_llm_context_max_pair_gap_sec": 0.5,
                "split_length_threshold": 20,
            },
            model="exaone3.5:7.8b",
            decision_func=decide,
        )

        self.assertEqual(len(refined), 2)
        self.assertEqual(refined[0]["text"], "음료를 한 사람씩 시켰다")
        self.assertEqual(refined[1]["text"], "그리고")
        self.assertAlmostEqual(refined[0]["end"], 1.35)
        self.assertAlmostEqual(refined[1]["start"], 1.40)
        self.assertEqual(refined[0]["words"][0]["word"], "음료를")
        self.assertEqual(refined[0]["_llm_context_boundary_policy"]["action"], "move_boundary")
        self.assertEqual(refined[0]["_llm_context_word_corrections"][0]["to"], "음료를")

    def test_context_refiner_is_disabled_outside_high_mode(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "문장 하나", "words": [_word("문장", 0.0, 0.4), _word("하나", 0.5, 1.0)]},
            {"start": 1.1, "end": 2.0, "text": "문장 둘", "words": [_word("문장", 1.1, 1.5), _word("둘", 1.6, 2.0)]},
        ]

        def fail_decision(_left, _right, _context):
            raise AssertionError("decision function should not be called outside High mode")

        refined = refine_high_contextual_boundaries(
            segments,
            settings={
                "subtitle_mode": "auto",
                "subtitle_llm_context_boundary_refine_enabled": True,
            },
            model="exaone3.5:7.8b",
            decision_func=fail_decision,
        )

        self.assertEqual(refined, segments)

    def test_high_context_refiner_can_merge_short_context_pair(self):
        segments = [
            {"start": 0.0, "end": 0.4, "text": "음료를", "words": [_word("음료를", 0.0, 0.4)]},
            {"start": 0.45, "end": 1.1, "text": "시켰다", "words": [_word("시켰다", 0.45, 1.1)]},
        ]

        refined = refine_high_contextual_boundaries(
            segments,
            settings={
                "subtitle_mode": "high",
                "subtitle_llm_context_boundary_refine_enabled": True,
                "subtitle_llm_context_allow_merge": True,
                "subtitle_llm_context_merge_max_chars": 16,
                "subtitle_llm_context_max_pair_gap_sec": 0.5,
            },
            model="exaone3.5:7.8b",
            decision_func=lambda _left, _right, _context: {"action": "merge", "reason": "short phrase"},
        )

        self.assertEqual(len(refined), 1)
        self.assertEqual(refined[0]["text"], "음료를 시켰다")
        self.assertAlmostEqual(refined[0]["start"], 0.0)
        self.assertAlmostEqual(refined[0]["end"], 1.1)


if __name__ == "__main__":
    unittest.main()
