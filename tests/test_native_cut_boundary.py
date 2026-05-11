import os
import unittest

from core import native_cut_boundary as native
from core.cut_boundary_auto_utils import build_auto_grid_verify_utils


class NativeCutBoundaryTests(unittest.TestCase):
    def test_wrapper_reports_python_backend_when_disabled(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "0"
            self.assertEqual(native.cut_boundary_backend(), "python")
            self.assertIsNone(native.delta_bytes(b"abc", b"abd", target_samples=16))
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

    def test_cut_boundary_helpers_match_reference_values(self):
        helpers = build_auto_grid_verify_utils(lambda width, height: [(0, 0, width, height)] * 25)
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        left = (bytes((i * 5 + j) % 256 for j in range(256)) for i in range(4))
        right = (bytes((i * 7 + j * 3) % 256 for j in range(256)) for i in range(4))
        prev_thumb = tuple(left)
        next_thumb = tuple(right)
        prev_avg = ((10.0, 20.0, 30.0), (22.0, 31.0, 43.0))
        next_avg = ((16.0, 25.0, 36.0), (20.0, 45.0, 40.0))
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "0"
            gray_reference = helpers["_auto_gray_delta"](
                prev_thumb,
                next_thumb,
                region_threshold=12.0,
                target_samples=64,
            )
            color_reference = helpers["_auto_color_avg_delta"](
                prev_avg,
                next_avg,
                threshold=8.0,
                weight_luma=0.65,
                weight_chroma=0.35,
            )

            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            gray_out = helpers["_auto_gray_delta"](
                prev_thumb,
                next_thumb,
                region_threshold=12.0,
                target_samples=64,
            )
            color_out = helpers["_auto_color_avg_delta"](
                prev_avg,
                next_avg,
                threshold=8.0,
                weight_luma=0.65,
                weight_chroma=0.35,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertAlmostEqual(gray_out[0], gray_reference[0], places=6)
        self.assertEqual(gray_out[1], gray_reference[1])
        self.assertEqual(len(gray_out[2]), len(gray_reference[2]))
        self.assertAlmostEqual(color_out[0], color_reference[0], places=6)
        self.assertEqual(color_out[1], color_reference[1])
        self.assertEqual(color_out[2], color_reference[2])

    def test_native_interval_overlaps_match_reference_values(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            native_out = native.interval_overlaps(
                [2.0, 0.0, 5.0],
                [4.0, 1.0, 7.0],
                [0.5, 3.0, 6.0],
                [2.5, 4.5, 8.0],
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertIsNotNone(native_out)
        self.assertEqual([round(value, 3) for value in native_out or []], [1.5, 0.5, 1.0])

    def test_dense_flow_pair_metrics_runs_in_native_extension(self):
        import numpy as np

        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            prev = np.zeros((4, 5), dtype=np.uint8)
            next_ = np.zeros((4, 5), dtype=np.uint8)
            flow = np.zeros((4, 5, 2), dtype=np.float32)
            flow[:, :, 0] = 2.0

            metrics = native.dense_flow_pair_metrics(prev, next_, flow, diff_threshold=18.0)
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertIsNotNone(metrics)
        self.assertAlmostEqual(metrics["diff"], 0.0, places=6)
        self.assertAlmostEqual(metrics["residual"], 0.0, places=6)
        self.assertAlmostEqual(metrics["coverage"], 0.0, places=6)
        self.assertAlmostEqual(metrics["mean_motion_px"], 2.0, places=6)
        self.assertAlmostEqual(metrics["mean_fx"], 2.0, places=6)
        self.assertAlmostEqual(metrics["mean_fy"], 0.0, places=6)
        self.assertAlmostEqual(metrics["coherence"], 1.0, places=6)

    def test_native_gray_rollback_search_refines_to_adjacent_peak(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")

        def thumb(value: int):
            return tuple(bytes([value]) * 64 for _ in range(4))

        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            if not native.native_cut_boundary_enabled():
                self.skipTest("native cut-boundary extension unavailable")
            rollback = native.gray_rollback_search(
                [
                    thumb(0),
                    thumb(0),
                    thumb(0),
                    thumb(96),
                    thumb(96),
                    thumb(96),
                    thumb(96),
                ],
                start_frame=0,
                hi_frame=4,
                stages=[4, 3],
                region_threshold=10.0,
                target_samples=64,
                gray_required_regions=2,
                gray_1f_threshold=20.0,
                gray_2f_threshold=24.0,
                gray_window_required=2,
                gray_window_threshold=40.0,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertIsNotNone(rollback)
        self.assertEqual(int(rollback["best_adj"]["frame"]), 2)
        self.assertEqual(int(rollback["best_win"]["frame"]), 2)
        self.assertGreaterEqual(float(rollback["best_win"]["score"]), 40.0)

    def test_waveform_peaks_f32le_matches_reference_downsample(self):
        import numpy as np

        from ui.timeline.timeline_waveform import _downsample_waveform_samples

        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        samples = np.zeros(2000, dtype=np.float32)
        samples[100:110] = 0.5
        samples[1000:1010] = -1.0
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            native_out = native.waveform_peaks_f32le(
                samples.tobytes(),
                sample_rate=2000,
                points_per_second=100,
                duration=None,
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        reference = _downsample_waveform_samples(samples)
        self.assertIsNotNone(native_out)
        np.testing.assert_allclose(native_out[0], reference[0], rtol=0, atol=1e-6)
        self.assertAlmostEqual(native_out[1], reference[1], places=6)


if __name__ == "__main__":
    unittest.main()
