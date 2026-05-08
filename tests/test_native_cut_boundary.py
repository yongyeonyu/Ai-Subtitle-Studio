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


if __name__ == "__main__":
    unittest.main()
