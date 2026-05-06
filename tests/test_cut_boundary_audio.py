import unittest

from core.cut_boundary_audio import (
    AUDIO_GAIN_BOUNDARY_SOURCE,
    AUDIO_GAIN_LINE_COLOR,
    build_audio_gain_boundary_rows,
    detect_audio_gain_changes,
)


class CutBoundaryAudioTests(unittest.TestCase):
    def test_detect_audio_gain_changes_finds_sustained_volume_shift(self):
        levels = [(idx + 0.5, -36.0 if idx < 8 else -18.0) for idx in range(16)]

        candidates = detect_audio_gain_changes(
            levels,
            threshold_db=10.0,
            min_gap_sec=4.0,
            context_windows=2,
            duration_sec=16.0,
        )

        self.assertGreaterEqual(len(candidates), 1)
        self.assertGreaterEqual(candidates[0]["local_sec"], 6.0)
        self.assertLessEqual(candidates[0]["local_sec"], 9.0)
        self.assertGreaterEqual(candidates[0]["score"], 10.0)

    def test_audio_gain_rows_are_neon_green_provisional_hints(self):
        rows = build_audio_gain_boundary_rows(
            [
                {
                    "local_sec": 8.0,
                    "score": 18.0,
                    "before_db": -36.0,
                    "after_db": -18.0,
                    "delta_db": 18.0,
                }
            ],
            clip_offset=100.0,
            clip_idx=2,
            fps=60.0,
            source_path="/tmp/sample.mp4",
            threshold_db=10.0,
            window_sec=2.0,
            sample_rate=4000,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], AUDIO_GAIN_BOUNDARY_SOURCE)
        self.assertEqual(rows[0]["status"], "provisional")
        self.assertFalse(rows[0]["verified"])
        self.assertEqual(rows[0]["line_color"], AUDIO_GAIN_LINE_COLOR)
        self.assertEqual(rows[0]["line_style"], "dash")
        self.assertIn(rows[0]["deep_boundary_decision"], {"verify", "keep"})
        self.assertGreater(rows[0]["deep_boundary_score"], 0.0)
        self.assertAlmostEqual(rows[0]["timeline_sec"], 108.0, places=3)


if __name__ == "__main__":
    unittest.main()
