import os
import unittest

from core import native_cut_boundary as native
from core.cut_boundary_verify_strategy import StrictVerifyCandidateStrategy


class StrictVerifyCandidateStrategyTests(unittest.TestCase):
    def setUp(self):
        self.strategy = StrictVerifyCandidateStrategy()

    def test_color_window_candidate_prefers_closer_local_frame(self):
        color_map = {frame_no: frame_no for frame_no in range(10, 18)}

        def color_delta(left, right, **_kwargs):
            pair = (int(left), int(right))
            if pair == (12, 13):
                return 24.0, 5, [24.0]
            if pair == (13, 14):
                return 24.0, 5, [24.0]
            return 0.0, 0, []

        result = self.strategy.best_local_color_candidate(
            color_map,
            center_frame=13,
            lo=10,
            hi=15,
            radius_frames=2,
            color_threshold=20.0,
            color_required_regions=4,
            weight_luma=0.25,
            weight_chroma=0.75,
            delta_fn=color_delta,
        )

        self.assertEqual(result["frame"], 13)
        self.assertEqual(result["mode"], "color_local_1f")

    def test_frame_mean_color_similarity_reports_weighted_average(self):
        result = self.strategy.frame_mean_color_similarity(
            {
                10: [(40.0, 90.0, 110.0), (42.0, 94.0, 112.0)],
                11: [(44.0, 98.0, 111.0), (43.0, 96.0, 115.0)],
            },
            frame=10,
        )

        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["luma_delta"], 2.5)
        self.assertAlmostEqual(result["chroma_delta"], 3.5)
        self.assertAlmostEqual(result["score"], (2.5 * 0.25) + (3.5 * 0.75))

    def test_native_color_window_candidate_matches_python_result_when_available(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            if not native.native_cut_boundary_enabled():
                self.skipTest("native cut-boundary extension unavailable")
            native_result = self.strategy.color_window_candidate(
                {
                    10: [(0.0, 0.0, 0.0)] * 5,
                    11: [(30.0, 30.0, 30.0)] * 5,
                    12: [(60.0, 60.0, 60.0)] * 5,
                    13: [(61.0, 61.0, 61.0)] * 5,
                    14: [(62.0, 62.0, 62.0)] * 5,
                },
                start_frame=10,
                stop_frame=12,
                window_frames=1,
                step=1,
                threshold=18.0,
                required_regions=3,
                weight_luma=0.25,
                weight_chroma=0.75,
                delta_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("native path should win when available")),
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertIn(native_result["frame"], {10, 11})
        self.assertEqual(native_result["mode"], "color_window")


if __name__ == "__main__":
    unittest.main()
