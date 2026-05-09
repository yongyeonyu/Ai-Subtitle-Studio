# Version: 03.01.25
# Phase: PHASE2
import unittest

from core.subtitle_quality.candidate_ranker import (
    is_candidate_safe_to_apply,
    rank_overlap_candidates,
    rank_quality_candidates,
)
from core.subtitle_quality.recheck_engine import recheck_low_confidence_segments


class QualityCandidateRankerTests(unittest.TestCase):
    def test_safe_candidate_requires_threshold_and_improvement(self):
        original = {"start": 0.0, "end": 1.0, "text": "안녕 하세요 123"}
        candidate = {"segment": {"start": 0.0, "end": 1.0, "text": "안녕하세요 123"}, "score": 96}

        safe, reason = is_candidate_safe_to_apply(candidate, original_segment=original, original_score=80)

        self.assertTrue(safe)
        self.assertEqual(reason, "safe")

    def test_safe_candidate_rejects_number_change(self):
        original = {"text": "가격은 123원"}
        candidate = {"segment": {"text": "가격은 124원"}, "score": 99}

        safe, reason = is_candidate_safe_to_apply(candidate, original_segment=original, original_score=80)

        self.assertFalse(safe)
        self.assertEqual(reason, "number_changed")

    def test_rank_quality_candidates_marks_safe_state(self):
        ranked = rank_quality_candidates(
            [{"candidate_id": "c1", "segment": {"text": "안녕하세요"}, "score": 96}],
            original_segment={"text": "안녕 하세요"},
            original_score=80,
        )

        self.assertTrue(ranked[0]["safe_to_apply"])

    def test_rank_overlap_candidates_reuses_batched_vad_alignment(self):
        ranked = rank_overlap_candidates(
            [
                {"candidate_id": "speech", "segment": {"start": 0.0, "end": 1.0, "text": "음성 구간"}},
                {"candidate_id": "silent", "segment": {"start": 2.0, "end": 3.0, "text": "무음 구간"}},
            ],
            vad_segments=[{"start": 0.0, "end": 1.0}],
        )

        speech = next(item for item in ranked if item["candidate_id"] == "speech")
        silent = next(item for item in ranked if item["candidate_id"] == "silent")
        self.assertEqual(speech["segment"]["quality"]["vad_alignment_score"], 100.0)
        self.assertEqual(silent["segment"]["quality"]["vad_alignment_score"], 0.0)
        self.assertGreater(speech["score"], silent["score"])

    def test_recheck_low_confidence_clamps_to_clip_boundary(self):
        targets = recheck_low_confidence_segments(
            [
                {
                    "line": 3,
                    "start": 10.0,
                    "end": 11.0,
                    "_clip_idx": 0,
                    "quality": {"confidence_label": "red", "flags": ["high_cps"]},
                }
            ],
            buffer_sec=2.0,
            clip_boundaries=[{"start": 9.0, "end": 12.0}],
        )

        self.assertEqual(targets[0]["recheck_start"], 9.0)
        self.assertEqual(targets[0]["recheck_end"], 12.0)


if __name__ == "__main__":
    unittest.main()
