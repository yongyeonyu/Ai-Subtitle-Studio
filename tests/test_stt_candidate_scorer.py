import unittest
from unittest.mock import patch

from core.audio import stt_candidate_scorer
from core.audio.stt_candidate_scorer import filter_scored_stt_candidates, score_stt_candidate


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

    def test_annotate_candidates_batches_vad_overlap_with_native_cpp(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "첫 문장", "avg_logprob": -0.1, "no_speech_prob": 0.01},
            {"start": 2.0, "end": 3.0, "text": "두 번째", "avg_logprob": -0.1, "no_speech_prob": 0.01},
        ]
        vad = [{"start": 0.0, "end": 1.0}, {"start": 2.9, "end": 3.0}]

        with patch.object(stt_candidate_scorer, "_native_interval_overlaps", return_value=[1.0, 0.1]) as native:
            annotated = stt_candidate_scorer.annotate_stt_candidates(
                segments,
                source="STT1",
                vad_segments=vad,
            )

        native.assert_called_once()
        self.assertEqual(annotated[0]["quality"]["vad_alignment_score"], 100.0)
        self.assertEqual(annotated[0]["asr_metadata"]["vad_alignment"]["native_backend"], "cpp")
        self.assertEqual(annotated[1]["quality"]["vad_alignment_score"], 10.0)
        self.assertIn("outside_vad_speech", annotated[1]["quality"]["flags"])

    def test_annotate_candidates_peer_window_matches_full_scan(self):
        segments = [
            {"start": 0.0, "end": 1.0, "text": "같은 말", "avg_logprob": -0.1, "no_speech_prob": 0.01},
            {"start": 3.0, "end": 4.0, "text": "다른 말", "avg_logprob": -0.1, "no_speech_prob": 0.01},
            {"start": 8.0, "end": 9.0, "text": "혼자 말", "avg_logprob": -0.1, "no_speech_prob": 0.01},
        ]
        peers = [
            {"start": 0.2, "end": 0.9, "text": "같은 말"},
            {"start": 3.1, "end": 3.8, "text": "전혀 다름"},
            {"start": 30.0, "end": 31.0, "text": "먼 후보"},
        ]

        optimized = stt_candidate_scorer.annotate_stt_candidates(
            segments,
            source="STT1",
            peer_segments=peers,
        )
        with patch.object(stt_candidate_scorer, "_peer_overlap_windows", return_value=None):
            full_scan = stt_candidate_scorer.annotate_stt_candidates(
                segments,
                source="STT1",
                peer_segments=peers,
            )

        self.assertEqual([row["stt_score"] for row in optimized], [row["stt_score"] for row in full_scan])
        self.assertEqual([row["stt_score_flags"] for row in optimized], [row["stt_score_flags"] for row in full_scan])


if __name__ == "__main__":
    unittest.main()
