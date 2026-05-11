import unittest

from core.cut_boundary_native_plan import (
    build_follower_native_verify_settings,
    build_follower_review_scan_profile,
    build_initial_middle_segment,
    build_middle_segments_for_stage,
    build_provisional_native_settings,
    build_provisional_visual_scan_profile,
    checked_provisional_boundary_row,
    provisional_boundary_row,
    reviewed_middle_source_rows,
)


class CutBoundaryNativePlanTests(unittest.TestCase):
    def test_initial_middle_segment_is_full_range_gray_a_placeholder(self):
        rows = build_initial_middle_segment(media_duration=12.0, fps=24.0)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["major_id"], "A")
        self.assertEqual(row["display_title"], "A - 주제없음")
        self.assertTrue(bool(row["is_topicless_placeholder"]))
        self.assertEqual(row["color"], "#8E8E93")
        self.assertEqual(row["start_frame"], 0)
        self.assertEqual(row["end_frame"], 288)

    def test_provisional_boundary_rows_keep_audio_green_and_visual_blue(self):
        visual = provisional_boundary_row({"timeline_sec": 10.0})
        audio = provisional_boundary_row({"timeline_sec": 12.0, "source": "audio_gain_provisional"})
        checked = checked_provisional_boundary_row({"timeline_sec": 15.0}, verified=False)

        self.assertEqual(visual["line_color"], "#00B7FF")
        self.assertEqual(visual["line_style"], "solid")
        self.assertEqual(audio["line_color"], "#39FF14")
        self.assertEqual(audio["line_style"], "solid")
        self.assertEqual(checked["line_color"], "#8E8E93")
        self.assertEqual(checked["line_style"], "dotted")
        self.assertEqual(checked["status"], "checked")

    def test_follower_middle_segments_become_colored_a_to_c_rows_when_all_frames_are_explicitly_requested(self):
        rows = build_middle_segments_for_stage(
            [
                {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0, "status": "confirmed", "confirmed": True},
                {"timeline_sec": 30.0, "timeline_frame": 900, "fps": 30.0, "status": "confirmed", "confirmed": True},
            ],
            media_duration=60.0,
            done=True,
            prefer_all_boundary_frames=True,
        )

        self.assertEqual([row["major_id"] for row in rows], ["A", "B", "C"])
        self.assertEqual(rows[0]["display_title"], "A - 주제없음")
        self.assertFalse(bool(rows[0]["is_topicless_placeholder"]))
        self.assertEqual(rows[0]["status"], "provisional")
        self.assertNotEqual(rows[0]["color"], "#8E8E93")
        self.assertEqual(rows[2]["timeline_end_frame"], 1800)

    def test_done_middle_segments_do_not_expand_to_all_frames_without_explicit_opt_in(self):
        rows = build_middle_segments_for_stage(
            [
                {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0, "status": "confirmed", "confirmed": True},
                {"timeline_sec": 30.0, "timeline_frame": 900, "fps": 30.0, "status": "confirmed", "confirmed": True},
            ],
            media_duration=60.0,
            done=True,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["major_id"], "A")
        self.assertEqual(rows[0]["timeline_end_frame"], 1800)

    def test_provisional_native_settings_use_720p_cross4_profile(self):
        tuned, profile = build_provisional_native_settings({}, sample_step_sec=1.0)
        raw_profile = build_provisional_visual_scan_profile(sample_step_sec=1.0)

        self.assertEqual(tuned["scan_cut_compare_max_width"], 1280)
        self.assertEqual(tuned["scan_cut_compare_max_height"], 720)
        self.assertEqual(profile["grid_size"], 3)
        self.assertEqual(profile["positions"], (1, 3, 5, 7))
        self.assertEqual(profile["mask"], "cross4")
        self.assertEqual(raw_profile["positions"], profile["positions"])

    def test_follower_native_settings_use_1080_inner9_profile(self):
        tuned, profile = build_follower_native_verify_settings({})
        raw_profile = build_follower_review_scan_profile()

        self.assertEqual(tuned["scan_cut_compare_max_width"], 1920)
        self.assertEqual(tuned["scan_cut_compare_max_height"], 1080)
        self.assertEqual(profile["grid_size"], 5)
        self.assertEqual(profile["positions"], (6, 7, 8, 11, 12, 13, 16, 17, 18))
        self.assertEqual(profile["mask"], "inner9")
        self.assertEqual(raw_profile["positions"], profile["positions"])
        self.assertEqual(tuned["scan_cut_auto_verify_window_stages"], [21, 11, 5, 2, 1])
        self.assertEqual(tuned["scan_cut_auto_verify_rollback_window_sec"], 1.0)
        self.assertEqual(tuned["scan_cut_auto_verify_forward_window_sec"], 1.0)
        self.assertGreaterEqual(tuned["scan_cut_follower_strict_multiplier"], 1.20)
        self.assertGreaterEqual(tuned["scan_cut_color_avg_window_frames"], 17)
        self.assertGreaterEqual(tuned["scan_cut_dense_flow_width"], 448)
        self.assertGreaterEqual(tuned["scan_cut_dense_flow_window_radius"], 3)
        self.assertGreaterEqual(tuned["scan_cut_dense_flow_motion_votes_required"], 4)
        self.assertGreaterEqual(tuned["scan_cut_follower_gray_agreement_frames"], 3)
        self.assertGreaterEqual(tuned["scan_cut_follower_gray_color_agreement_frames"], 3)
        self.assertGreaterEqual(tuned["scan_cut_follower_local_color_confirm_frames"], 2)
        self.assertGreaterEqual(tuned["scan_cut_native_peak_bonus_scale"], 0.05)
        self.assertGreaterEqual(tuned["scan_cut_native_peak_contrast_scale"], 0.05)
        self.assertGreaterEqual(tuned["scan_cut_native_peak_sharpness_scale"], 0.02)

    def test_reviewed_middle_sources_ignore_checked_only_rows(self):
        rows = reviewed_middle_source_rows(
            [
                {"timeline_sec": 10.0, "timeline_frame": 300, "fps": 30.0, "status": "checked", "scan_checked": True},
                {"timeline_sec": 20.0, "timeline_frame": 600, "fps": 30.0, "status": "verified", "verified": True},
                {"timeline_sec": 30.0, "timeline_frame": 900, "fps": 30.0, "status": "provisional", "rollback_relocated": True},
            ]
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(int(rows[0]["timeline_frame"]), 600)
        self.assertEqual(int(rows[1]["timeline_frame"]), 900)

    def test_reviewed_middle_sources_keep_audio_checked_rows_as_middle_anchors(self):
        rows = reviewed_middle_source_rows(
            [
                {
                    "timeline_sec": 55.0,
                    "timeline_frame": 1650,
                    "fps": 30.0,
                    "status": "checked",
                    "scan_checked": True,
                    "source": "audio_gain_provisional",
                    "audio_gain_db_delta": 12.0,
                },
                {
                    "timeline_sec": 50.0,
                    "timeline_frame": 1500,
                    "fps": 30.0,
                    "status": "checked",
                    "scan_checked": True,
                    "source": "visual_provisional",
                    "score": 180.0,
                },
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["timeline_frame"]), 1650)
        self.assertEqual(rows[0]["source"], "audio_gain_provisional")

    def test_reviewed_middle_sources_keep_relocated_rows_as_snap_only_helpers(self):
        rows = reviewed_middle_source_rows(
            [
                {
                    "timeline_sec": 55.0,
                    "timeline_frame": 1650,
                    "fps": 30.0,
                    "status": "provisional",
                    "rollback_relocated": True,
                    "score": 220.0,
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(bool(rows[0].get("middle_snap_only")))


if __name__ == "__main__":
    unittest.main()
