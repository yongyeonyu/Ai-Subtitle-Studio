import unittest

from core.audio.stt_candidate_scorer import (
    filter_scored_stt_candidates,
    score_stt_candidate,
)


class STTCandidateScorerTests(unittest.TestCase):
    def test_known_hallucination_phrase_scores_zero(self):
        result = score_stt_candidate(
            {
                "start": 0.0,
                "end": 1.2,
                "text": "시청해주셔서 감사합니다 구독 좋아요",
                "avg_logprob": -0.2,
                "no_speech_prob": 0.02,
            },
            source="STT2",
        )

        self.assertEqual(result["score"], 0.0)
        self.assertIn("known_hallucination_phrase", result["flags"])

    def test_weak_segment_without_word_confidence_is_scored_conservatively(self):
        result = score_stt_candidate(
            {
                "start": 0.0,
                "end": 0.65,
                "text": "아니 아니 아니 아니 아니 아니",
                "avg_logprob": -1.1,
                "no_speech_prob": 0.61,
                "compression_ratio": 2.7,
            },
            source="STT2",
        )

        self.assertLess(result["score"], 24.0)
        self.assertIn("repetition_hallucination_risk", result["flags"])

    def test_filter_drops_low_quality_segments_but_keeps_manual_confirmation(self):
        filtered = filter_scored_stt_candidates(
            [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "반복 반복 반복 반복 반복",
                    "stt_score": 51,
                    "stt_score_flags": ["repetition_hallucination_risk"],
                },
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "수동 확인 자막",
                    "stt_score": 12,
                    "stt_score_flags": ["manual_confirmed"],
                },
            ]
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["text"], "수동 확인 자막")


if __name__ == "__main__":
    unittest.main()
