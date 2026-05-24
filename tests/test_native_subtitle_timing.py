import unittest

from core import native_subtitle_timing as native
from tools.benchmark_subtitle_pipeline_variants import _best_ref_for, _overlap


class NativeSubtitleTimingTests(unittest.TestCase):
    def test_cpp_timing_metrics_match_python_reference_pairing(self):
        if not native.native_subtitle_timing_enabled():
            self.skipTest("native subtitle timing extension unavailable")
        hypothesis = [
            {"start": 0.1, "end": 1.1, "text": "첫 문장"},
            {"start": 2.2, "end": 3.1, "text": "두 번째"},
        ]
        reference = [
            {"start": 0.0, "end": 1.0, "text": "첫 문장"},
            {"start": 2.0, "end": 3.0, "text": "두 번째"},
        ]

        metrics = native.timing_metrics(hypothesis, reference)

        timing_errors = []
        overlaps = []
        for row in hypothesis:
            ref = _best_ref_for(row, reference)
            timing_errors.append((abs(row["start"] - ref["start"]) + abs(row["end"] - ref["end"])) / 2.0)
            span = max(row["end"] - row["start"], ref["end"] - ref["start"], 0.001)
            overlaps.append(min(1.0, _overlap(row, ref) / span))

        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(metrics["timing_mae_sec"], sum(timing_errors) / len(timing_errors), places=9)
        self.assertAlmostEqual(metrics["overlap_score"], sum(overlaps) / len(overlaps) * 100.0, places=9)
        self.assertEqual(metrics["matched_reference_indices"], [0, 1])
        self.assertAlmostEqual(metrics["max_start_error_sec"], 0.2, places=9)
        self.assertAlmostEqual(metrics["max_end_error_sec"], 0.1, places=9)
        self.assertAlmostEqual(metrics["max_pair_timing_error_sec"], 0.15, places=9)
        self.assertEqual(metrics["worst_match_hypothesis_index"], 1)
        self.assertEqual(metrics["worst_match_reference_index"], 1)
        self.assertEqual(metrics["native_backend"], "cpp")


if __name__ == "__main__":
    unittest.main()
