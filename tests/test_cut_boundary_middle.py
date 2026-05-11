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

    def test_audio_boundary_can_snap_to_nearby_strongest_visual_boundary_for_middle_split(self):
        frames = coalesce_topicless_middle_boundary_frames(
            [
                {
                    "timeline_sec": 50.0,
                    "timeline_frame": 1500,
                    "fps": 30.0,
                    "source": "visual",
                    "score": 190.0,
                },
                {
                    "timeline_sec": 55.0,
                    "timeline_frame": 1650,
                    "fps": 30.0,
                    "source": "audio_gain_provisional",
                    "audio_gain_db_delta": 14.0,
                },
                {
                    "timeline_sec": 180.0,
                    "timeline_frame": 5400,
                    "fps": 30.0,
                    "source": "visual",
                    "score": 180.0,
                },
            ],
            fps=30.0,
            duration_frame=30 * 420,
            settings={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
                "scan_cut_topicless_audio_priority_min_segment_sec": 24.0,
                "scan_cut_topicless_audio_priority_window_sec": 12.0,
                "scan_cut_topicless_audio_snap_visual_window_sec": 8.0,
                "scan_cut_topicless_audio_hard_delta_db": 8.0,
                "scan_cut_topicless_visual_hard_score": 140.0,
            },
        )

        self.assertEqual(frames, [1500, 5400])

    def test_audio_boundary_can_create_middle_segment_earlier_than_generic_hard_min_gap(self):
        frames = coalesce_topicless_middle_boundary_frames(
            [
                {
                    "timeline_sec": 30.0,
                    "timeline_frame": 900,
                    "fps": 30.0,
                    "source": "audio_gain_provisional",
                    "audio_gain_db_delta": 12.0,
                },
                {
                    "timeline_sec": 180.0,
                    "timeline_frame": 5400,
                    "fps": 30.0,
                    "source": "visual",
                    "score": 170.0,
                },
            ],
            fps=30.0,
            duration_frame=30 * 420,
            settings={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
                "scan_cut_topicless_audio_priority_min_segment_sec": 24.0,
                "scan_cut_topicless_audio_priority_window_sec": 12.0,
                "scan_cut_topicless_audio_snap_visual_window_sec": 8.0,
                "scan_cut_topicless_audio_hard_delta_db": 8.0,
                "scan_cut_topicless_visual_hard_score": 140.0,
            },
        )

        self.assertEqual(frames, [900, 5400])

    def test_relocated_visual_rows_snap_audio_boundary_without_creating_extra_middle_split(self):
        frames = coalesce_topicless_middle_boundary_frames(
            [
                {
                    "timeline_sec": 40.0,
                    "timeline_frame": 1200,
                    "fps": 30.0,
                    "source": "audio_gain_provisional",
                    "status": "checked",
                    "scan_checked": True,
                    "audio_gain_db_delta": 13.0,
                },
                {
                    "timeline_sec": 44.0,
                    "timeline_frame": 1320,
                    "fps": 30.0,
                    "status": "provisional",
                    "rollback_relocated": True,
                    "middle_snap_only": True,
                    "score": 240.0,
                },
                {
                    "timeline_sec": 70.0,
                    "timeline_frame": 2100,
                    "fps": 30.0,
                    "status": "provisional",
                    "rollback_relocated": True,
                    "middle_snap_only": True,
                    "score": 260.0,
                },
            ],
            fps=30.0,
            duration_frame=30 * 120,
            settings={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
                "scan_cut_topicless_audio_priority_min_segment_sec": 24.0,
                "scan_cut_topicless_audio_priority_window_sec": 12.0,
                "scan_cut_topicless_audio_snap_visual_window_sec": 8.0,
                "scan_cut_topicless_audio_hard_delta_db": 8.0,
                "scan_cut_topicless_visual_hard_score": 140.0,
            },
        )

        self.assertEqual(frames, [1320])

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

    def test_confirmed_cut_boundaries_still_flow_through_coalesce_for_middle_segments(self):
        with patch(
            "core.settings.load_settings",
            return_value={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
            },
        ), patch(
            "core.cut_boundary_middle.coalesce_topicless_middle_boundary_frames",
            return_value=[900],
        ) as coalesce_mock:
            rows = build_topicless_middle_segments(
                [
                    {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0, "status": "confirmed", "confirmed": True},
                    {"timeline_sec": 30.0, "timeline_frame": 900, "fps": 30.0, "status": "confirmed", "confirmed": True},
                ],
                media_duration=120.0,
                include_trailing=True,
            )

        self.assertTrue(coalesce_mock.called)
        bounds = [(round(row["start"], 3), round(row["end"], 3)) for row in rows]
        self.assertEqual(bounds, [(0.0, 30.0), (30.0, 120.0)])

    def test_topicless_middle_can_use_all_boundary_frames_for_follower_preview(self):
        with patch(
            "core.settings.load_settings",
            return_value={
                "scan_cut_topicless_min_segment_sec": 120.0,
                "scan_cut_topicless_hard_min_segment_sec": 45.0,
            },
        ), patch(
            "core.cut_boundary_middle.coalesce_topicless_middle_boundary_frames",
            return_value=[900],
        ) as coalesce_mock:
            rows = build_topicless_middle_segments(
                [
                    {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0, "status": "checked", "scan_checked": True},
                    {"timeline_sec": 30.0, "timeline_frame": 900, "fps": 30.0, "status": "checked", "scan_checked": True},
                ],
                media_duration=120.0,
                include_trailing=True,
                prefer_all_boundary_frames=True,
            )

        self.assertFalse(coalesce_mock.called)
        bounds = [(round(row["start"], 3), round(row["end"], 3)) for row in rows]
        self.assertEqual(bounds, [(0.0, 10.0), (10.0, 30.0), (30.0, 120.0)])


if __name__ == "__main__":
    unittest.main()
