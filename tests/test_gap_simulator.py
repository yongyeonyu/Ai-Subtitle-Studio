import unittest

from ui.settings.gap_simulator import simulate_gap_pipeline


class GapSimulatorTests(unittest.TestCase):
    def test_simulator_reports_delete_split_and_gap_adjustment(self):
        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.7,
                "single_subtitle_end": 0.2,
                "split_length_threshold": 10,
                "sub_min_duration": 0.3,
                "sub_max_duration": 2.0,
                "sub_max_cps": 12,
                "sub_dedup_window": 0.5,
                "sub_gap_break_sec": 0.5,
            }
        )

        self.assertGreaterEqual(result["summary"]["deleted"], 2)
        self.assertGreaterEqual(result["summary"]["split"], 1)
        self.assertGreaterEqual(result["summary"]["gap_adjusted"], 1)

    def test_continuous_gap_push_rate_moves_both_edges(self):
        blocks = [
            {"id": 1, "start": 0.0, "end": 1.0, "text": "앞 자막"},
            {"id": 2, "start": 2.0, "end": 3.0, "text": "뒤 자막"},
        ]

        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.8,
                "single_subtitle_end": 0.0,
                "split_length_threshold": 20,
                "sub_min_duration": 0.1,
                "sub_max_duration": 6.0,
                "sub_max_cps": 30,
                "sub_dedup_window": 0.1,
                "sub_gap_break_sec": 0.5,
            },
            blocks=blocks,
        )

        first, second = result["tuned"]
        self.assertEqual(first["end"], 1.8)
        self.assertEqual(second["start"], 1.8)
        self.assertIn("앞 80%", first["gap_action"])

    def test_large_gap_uses_single_subtitle_extension(self):
        blocks = [
            {"id": 1, "start": 0.0, "end": 1.0, "text": "앞 자막"},
            {"id": 2, "start": 3.0, "end": 4.0, "text": "뒤 자막"},
        ]

        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 0.5,
                "gap_push_rate": 0.8,
                "single_subtitle_end": 0.2,
                "split_length_threshold": 20,
                "sub_min_duration": 0.1,
                "sub_max_duration": 6.0,
                "sub_max_cps": 30,
                "sub_dedup_window": 0.1,
                "sub_gap_break_sec": 1.5,
            },
            blocks=blocks,
        )

        first, second = result["tuned"]
        self.assertEqual(first["end"], 1.2)
        self.assertEqual(second["start"], 2.8)
        self.assertIn("단일 유지", first["gap_action"])

    def test_confirmed_cut_boundary_splits_crossing_subtitle(self):
        blocks = [
            {
                "id": 1,
                "start": 0.0,
                "end": 10.0,
                "text": "정식 컷 경계를 기준으로 자막이 두 개로 나뉩니다",
            },
        ]

        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.7,
                "single_subtitle_end": 0.0,
                "split_length_threshold": 80,
                "sub_min_duration": 0.1,
                "sub_max_duration": 20.0,
                "sub_max_cps": 30,
                "sub_dedup_window": 0.1,
                "sub_gap_break_sec": 0.1,
            },
            blocks=blocks,
            confirmed_cut_boundaries=[5.0],
            provisional_cut_boundaries=[],
        )

        self.assertEqual(len(result["cut_aligned"]), 2)
        self.assertEqual(result["cut_aligned"][0]["end"], 5.0)
        self.assertEqual(result["cut_aligned"][1]["start"], 5.0)
        self.assertGreaterEqual(result["summary"]["confirmed_cuts"], 1)

    def test_confirmed_cut_boundary_stays_locked_after_gap_tuning(self):
        blocks = [
            {"id": 1, "start": 0.0, "end": 4.82, "text": "정식 경계 앞 자막"},
            {"id": 2, "start": 5.22, "end": 7.0, "text": "정식 경계 뒤 자막"},
        ]

        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 2.0,
                "gap_push_rate": 0.8,
                "single_subtitle_end": 0.2,
                "split_length_threshold": 80,
                "sub_min_duration": 0.1,
                "sub_max_duration": 20.0,
                "sub_max_cps": 30,
                "sub_dedup_window": 0.1,
                "sub_gap_break_sec": 0.1,
            },
            blocks=blocks,
            confirmed_cut_boundaries=[5.0],
            provisional_cut_boundaries=[],
        )

        first, second = result["tuned"]
        self.assertEqual(first["end"], 5.0)
        self.assertEqual(second["start"], 5.0)
        self.assertIn("정식 컷 보호", first["gap_action"])

    def test_provisional_cut_boundary_snaps_nearby_edges_only(self):
        blocks = [
            {"id": 1, "start": 0.0, "end": 4.82, "text": "임시 경계 앞 자막"},
            {"id": 2, "start": 5.22, "end": 7.0, "text": "임시 경계 뒤 자막"},
        ]

        result = simulate_gap_pipeline(
            {
                "continuous_threshold": 0.1,
                "gap_push_rate": 0.5,
                "single_subtitle_end": 0.0,
                "split_length_threshold": 80,
                "sub_min_duration": 0.1,
                "sub_max_duration": 20.0,
                "sub_max_cps": 30,
                "sub_dedup_window": 0.1,
                "sub_gap_break_sec": 0.1,
                "provisional_cut_snap_window": 0.35,
            },
            blocks=blocks,
            confirmed_cut_boundaries=[],
            provisional_cut_boundaries=[5.0],
        )

        first, second = result["cut_aligned"]
        self.assertEqual(first["end"], 5.0)
        self.assertEqual(second["start"], 5.0)
        self.assertGreaterEqual(result["summary"]["provisional_snaps"], 2)


if __name__ == "__main__":
    unittest.main()
