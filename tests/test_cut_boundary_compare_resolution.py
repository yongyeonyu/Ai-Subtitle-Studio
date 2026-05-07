import unittest

import numpy as np

from core.cut_boundary_auto_utils import build_auto_grid_verify_utils


class _FakeCv2:
    INTER_AREA = 3

    def __init__(self):
        self.resize_calls = []

    def resize(self, frame, size, interpolation=None):
        self.resize_calls.append((size, interpolation))
        width, height = size
        channels = frame.shape[2] if len(frame.shape) > 2 else 1
        return np.zeros((height, width, channels), dtype=frame.dtype)


class CutBoundaryCompareResolutionTests(unittest.TestCase):
    def test_compare_frame_downscales_4k_to_1080p_before_pixel_comparison(self):
        helpers = build_auto_grid_verify_utils(lambda width, height: [(0, 0, width, height)] * 25)
        fake_cv2 = _FakeCv2()
        frame = np.zeros((2160, 3840, 3), dtype=np.uint8)

        out = helpers["_auto_downscale_frame_for_compare"](frame, fake_cv2)

        self.assertEqual(out.shape[:2], (1080, 1920))
        self.assertEqual(fake_cv2.resize_calls[-1][0], (1920, 1080))

    def test_compare_frame_keeps_1080p_or_smaller_without_resize(self):
        helpers = build_auto_grid_verify_utils(lambda width, height: [(0, 0, width, height)] * 25)
        fake_cv2 = _FakeCv2()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        out = helpers["_auto_downscale_frame_for_compare"](frame, fake_cv2)

        self.assertIs(out, frame)
        self.assertEqual(fake_cv2.resize_calls, [])


if __name__ == "__main__":
    unittest.main()
