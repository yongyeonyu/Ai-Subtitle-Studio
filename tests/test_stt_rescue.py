import unittest

from core.audio import stt_rescue


class STTRescueTests(unittest.TestCase):
    def test_finds_ranges_only_when_both_tracks_are_below_threshold(self):
        primary = [
            {"start": 0.0, "end": 1.2, "text": "망고 보여 봐", "stt_score": 42},
            {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 91},
        ]
        secondary = [
            {"start": 0.05, "end": 1.25, "text": "방금 보여 봐", "stt_score": 47},
            {"start": 2.0, "end": 3.0, "text": "정상 문장", "stt_score": 48},
        ]

        ranges = stt_rescue.find_low_score_recheck_ranges(
            primary,
            secondary,
            {"stt_low_score_recheck_threshold": 50},
        )

        self.assertEqual(len(ranges), 1)
        self.assertAlmostEqual(ranges[0].start, 0.0)
        self.assertAlmostEqual(ranges[0].end, 1.25)
        self.assertEqual(ranges[0].best_original_score, 47)

    def test_replacement_requires_threshold_or_meaningful_improvement(self):
        item = stt_rescue.find_low_score_recheck_ranges(
            [{"start": 0, "end": 1, "text": "나쁜 후보", "stt_score": 42}],
            [{"start": 0, "end": 1, "text": "다른 후보", "stt_score": 45}],
            {"stt_low_score_recheck_threshold": 50},
        )[0]

        self.assertFalse(
            stt_rescue.replacement_is_better(
                [{"start": 0, "end": 1, "text": "애매", "stt_score": 46}],
                item,
                {"stt_low_score_recheck_threshold": 50, "stt_low_score_recheck_min_improvement": 3},
            )
        )
        self.assertTrue(
            stt_rescue.replacement_is_better(
                [{"start": 0, "end": 1, "text": "개선", "stt_score": 49}],
                item,
                {"stt_low_score_recheck_threshold": 50, "stt_low_score_recheck_min_improvement": 3},
            )
        )

    def test_mark_rescue_segments_preserves_original_scores(self):
        item = stt_rescue.find_low_score_recheck_ranges(
            [{"start": 0, "end": 1, "text": "원본1", "stt_score": 30}],
            [{"start": 0, "end": 1, "text": "원본2", "stt_score": 40}],
            {"stt_low_score_recheck_threshold": 50},
        )[0]

        marked = stt_rescue.mark_rescue_segments(
            [{"start": 0, "end": 1, "text": "재검사", "stt_score": 70}],
            item,
        )

        self.assertTrue(marked[0]["stt_recheck_applied"])
        self.assertEqual(marked[0]["stt_recheck_original_scores"], {"STT1": 30, "STT2": 40})
        self.assertTrue(marked[0]["asr_metadata"]["stt_low_score_recheck"]["enabled"])


if __name__ == "__main__":
    unittest.main()
