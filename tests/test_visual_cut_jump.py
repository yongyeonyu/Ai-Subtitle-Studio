import unittest

from core.visual_cut_jump import build_visual_cut_sample, score_visual_cut_pair, visual_cut_mode_width


class VisualCutJumpTests(unittest.TestCase):
    def test_visual_cut_mode_width_defaults(self):
        self.assertEqual(visual_cut_mode_width("fast4", {}), 320)
        self.assertEqual(visual_cut_mode_width("cross5", {}), 480)
        self.assertEqual(visual_cut_mode_width("full9", {}), 960)

    def test_visual_cut_pair_scores_hard_cut_higher_than_camera_motion(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        base = np.zeros((180, 320, 3), dtype=np.uint8)
        cv2.rectangle(base, (42, 38), (168, 128), (228, 228, 228), -1)
        cv2.line(base, (24, 148), (292, 32), (120, 120, 120), 3)
        cv2.circle(base, (244, 124), 26, (186, 186, 186), -1)

        shifted = cv2.warpAffine(
            base,
            np.float32([[1, 0, 18], [0, 1, 0]]),
            (320, 180),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        hard_cut = np.zeros_like(base)
        cv2.rectangle(hard_cut, (16, 18), (304, 160), (72, 138, 232), -1)
        cv2.line(hard_cut, (0, 0), (319, 179), (252, 252, 48), 4)

        motion_score = score_visual_cut_pair(
            build_visual_cut_sample(base, cv2, mode="fast4", width=320),
            build_visual_cut_sample(shifted, cv2, mode="fast4", width=320),
            cv2,
            region_threshold=18.0,
        )
        cut_score = score_visual_cut_pair(
            build_visual_cut_sample(base, cv2, mode="fast4", width=320),
            build_visual_cut_sample(hard_cut, cv2, mode="fast4", width=320),
            cv2,
            region_threshold=18.0,
        )

        self.assertGreater(float(cut_score["score"]), float(motion_score["score"]) * 2.0)
        self.assertGreater(float(cut_score["pixel_ratio"]), float(motion_score["pixel_ratio"]))
        self.assertGreater(float(cut_score["hist_delta"]), float(motion_score["hist_delta"]))
        self.assertGreater(float(cut_score["ssim_delta"]), float(motion_score["ssim_delta"]))
        self.assertGreater(float(cut_score["hash_delta"]), float(motion_score["hash_delta"]))
        self.assertGreaterEqual(int(cut_score["region_hits"]), int(motion_score["region_hits"]))

    def test_visual_cut_pair_skips_flow_for_low_change_fast4_pairs(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        frame = np.full((120, 200, 3), 32, dtype=np.uint8)
        score = score_visual_cut_pair(
            build_visual_cut_sample(frame, cv2, mode="fast4", width=320),
            build_visual_cut_sample(frame.copy(), cv2, mode="fast4", width=320),
            cv2,
            region_threshold=18.0,
        )

        self.assertEqual(score["backend"], "edge_gray_fast_gate")
        self.assertEqual(score["flow_mean"], 0.0)
