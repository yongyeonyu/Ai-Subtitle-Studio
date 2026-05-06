import unittest
from unittest.mock import patch

from core.cut_boundary_middle import coalesce_topicless_middle_boundary_frames
from core.roughcut.cut_boundary_placeholder import build_topicless_middle_segments


class CutBoundaryMiddleTests(unittest.TestCase):
    def test_topicless_middle_boundaries_coalesce_short_visual_splits(self):
        frames = coalesce_topicless_middle_boundary_frames(
            [
                {"timeline_sec": 150.0, "fps": 30.0, "score": 72.0},
                {"timeline_sec": 210.0, "fps": 30.0, "score": 75.0},
                {"timeline_sec": 360.0, "fps": 30.0, "score": 80.0},
            ],
            fps=30.0,
            duration_frame=30 * 600,
            settings={"scan_cut_topicless_min_segment_sec": 120.0},
        )

        self.assertEqual(frames, [4500, 10800])

    def test_audio_supported_boundary_can_start_a_short_middle_segment(self):
        frames = coalesce_topicless_middle_boundary_frames(
            [
                {
                    "timeline_sec": 60.0,
                    "fps": 30.0,
                    "source": "visual",
                    "audio_gain_db_delta": 11.0,
                },
                {"timeline_sec": 180.0, "fps": 30.0, "source": "visual"},
            ],
            fps=30.0,
            duration_frame=30 * 420,
            settings={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
                "scan_cut_topicless_audio_hard_delta_db": 8.0,
            },
        )

        self.assertEqual(frames, [1800, 5400])

    def test_topicless_placeholder_builds_one_middle_for_red_box_like_span(self):
        with patch(
            "core.settings.load_settings",
            return_value={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_visual_hard_score": 140.0,
            },
        ):
            rows = build_topicless_middle_segments(
                [
                    {"timeline_sec": 780.0, "fps": 30.0, "score": 72.0},
                    {"timeline_sec": 850.0, "fps": 30.0, "score": 75.0},
                    {"timeline_sec": 970.0, "fps": 30.0, "score": 80.0},
                ],
                media_duration=1200.0,
            )

        bounds = [(round(row["start"], 3), round(row["end"], 3)) for row in rows]
        self.assertEqual(bounds, [(0.0, 780.0), (780.0, 970.0), (970.0, 1200.0)])


if __name__ == "__main__":
    unittest.main()
