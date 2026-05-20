import os
import unittest

from core.audio.stt_lattice_service import (
    candidate_score_100,
    find_best_word_match,
    lattice_selection_thresholds,
)
from core import native_stt_lattice as native


class STTLatticeServiceTests(unittest.TestCase):
    def test_lattice_selection_thresholds_clamp_values(self):
        thresholds = lattice_selection_thresholds(
            {
                "stt_lattice_min_match_score": 2.0,
                "stt_lattice_replace_margin": -1.0,
                "stt_lattice_min_confidence": 9.0,
            }
        )

        self.assertEqual(thresholds.min_match_score, 0.95)
        self.assertEqual(thresholds.replace_margin, 0.0)
        self.assertEqual(thresholds.min_confidence, 1.0)

    def test_candidate_score_100_normalizes_zero_to_one_scale(self):
        score = candidate_score_100(
            {"score": 0.83},
            score_fn=lambda _candidate: {"score": 11.0},
        )

        self.assertEqual(score, 83.0)

    def test_find_best_word_match_prefers_overlap_plus_text_similarity(self):
        anchor = {"word": "방금", "start": 0.0, "end": 0.5}
        words = [
            {"word": "망고", "start": 0.0, "end": 0.5},
            {"word": "방금", "start": 0.02, "end": 0.52},
            {"word": "보여", "start": 0.55, "end": 1.0},
        ]

        index, score = find_best_word_match(
            anchor,
            words,
            {0},
            min_match_score=0.42,
            similarity_scores=[0.15, 1.0, 0.05],
        )

        self.assertEqual(index, 1)
        self.assertGreater(score, 0.9)

    def test_native_best_word_match_matches_python_fallback_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_STT_LATTICE")
        try:
            os.environ["AI_SUBTITLE_NATIVE_STT_LATTICE"] = "1"
            if not native.native_stt_lattice_enabled():
                self.skipTest("native stt lattice extension unavailable")
            result = find_best_word_match(
                {"word": "방금", "start": 0.0, "end": 0.5},
                [
                    {"word": "망고", "start": 0.0, "end": 0.5},
                    {"word": "방금", "start": 0.02, "end": 0.52},
                ],
                set(),
                min_match_score=0.42,
                similarity_scores=[0.15, 1.0],
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_STT_LATTICE", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_STT_LATTICE"] = previous

        self.assertEqual(result[0], 1)
        self.assertGreater(result[1], 0.9)


if __name__ == "__main__":
    unittest.main()
