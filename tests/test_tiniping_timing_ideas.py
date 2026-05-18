import unittest

from tools.benchmark_subtitle_pipeline_variants import _base_benchmark_settings
from tools.benchmark_tiniping_timing_ideas import build_timing_ideas, _rank_rows


class TinipingTimingIdeasTests(unittest.TestCase):
    def test_build_timing_ideas_includes_expected_catalog(self):
        ideas = build_timing_ideas(_base_benchmark_settings("current"))
        by_name = {idea.name: idea for idea in ideas}

        self.assertIn("mode_auto", by_name)
        self.assertIn("timing_cut_vad_edge008_cached", by_name)
        self.assertIn("anchor_tight_cached", by_name)
        self.assertIn("word_ts_low_score_tight_shift_stt1", by_name)
        self.assertIn("audio_ffmpeg_ten_vad_balanced", by_name)

        self.assertTrue(by_name["timing_cut_vad_edge008_cached"].use_baseline_raw_cache)
        self.assertIsNotNone(by_name["audio_ffmpeg_ten_vad_balanced"].audio_profile)
        self.assertEqual(by_name["mode_auto"].variant.name, "mode_auto")

    def test_rank_rows_prefers_timing_improvement_without_large_text_regression(self):
        baseline = {
            "name": "mode_auto",
            "quality": {
                "text_score": 88.0,
                "local_text_score": 84.0,
                "timing_score": 88.0,
                "timing_mae_sec": 0.45,
                "count_score": 95.0,
                "overlap_score": 77.0,
                "segment_count_delta": -3,
                "quality_score": 86.0,
            },
        }
        better_timing = {
            "name": "anchor_tight_cached",
            "quality": {
                "text_score": 87.5,
                "local_text_score": 83.5,
                "timing_score": 92.0,
                "timing_mae_sec": 0.31,
                "count_score": 95.0,
                "overlap_score": 80.0,
                "segment_count_delta": -2,
                "quality_score": 87.0,
            },
            "error": "",
        }
        text_collapse = {
            "name": "bad_text_variant",
            "quality": {
                "text_score": 75.0,
                "local_text_score": 70.0,
                "timing_score": 93.0,
                "timing_mae_sec": 0.28,
                "count_score": 92.0,
                "overlap_score": 79.0,
                "segment_count_delta": -2,
                "quality_score": 80.0,
            },
            "error": "",
        }

        ranked = _rank_rows([better_timing, text_collapse], baseline)

        self.assertEqual(ranked[0]["name"], "anchor_tight_cached")
        self.assertTrue(ranked[0]["eligible_for_top"])
        self.assertFalse(ranked[1]["eligible_for_top"])


if __name__ == "__main__":
    unittest.main()
