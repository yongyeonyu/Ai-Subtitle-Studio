import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.visual_cut_jump import (
    create_visual_cut_flow_engine,
    is_visual_cut_peak,
    native_visual_cut_coarse_series,
    prepare_visual_cut_frame,
    score_visual_cut_coarse_metrics,
    score_visual_cut_metrics,
    visual_cut_pair_metrics,
)


class VisualCutJumpTests(unittest.TestCase):
    def test_hard_cut_scores_above_smooth_camera_motion(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        base = np.zeros((120, 180, 3), dtype=np.uint8)
        cv2.rectangle(base, (18, 20), (104, 88), (210, 210, 210), -1)
        cv2.line(base, (6, 108), (176, 14), (140, 140, 140), 3)
        cv2.circle(base, (145, 86), 18, (170, 170, 170), -1)

        shifted_1 = cv2.warpAffine(
            base,
            np.float32([[1, 0, 10], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        shifted_2 = cv2.warpAffine(
            base,
            np.float32([[1, 0, 20], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        hard_cut = np.zeros_like(base)
        cv2.rectangle(hard_cut, (10, 10), (172, 112), (60, 130, 230), -1)
        cv2.line(hard_cut, (0, 8), (179, 118), (250, 250, 40), 5)
        hard_cut_follow = cv2.warpAffine(
            hard_cut,
            np.float32([[1, 0, 2], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )

        prepared = [
            prepare_visual_cut_frame(frame, cv2, max_width=320)
            for frame in (base, shifted_1, shifted_2, hard_cut, hard_cut_follow)
        ]
        flow_engine, _backend = create_visual_cut_flow_engine(cv2, backend_preference="dis")
        metrics = [
            visual_cut_pair_metrics(prepared[idx], prepared[idx + 1], cv2, flow_engine=flow_engine)
            for idx in range(len(prepared) - 1)
        ]

        motion_score = score_visual_cut_metrics(metrics[1], history=[metrics[0]], settings={})
        hard_cut_score = score_visual_cut_metrics(metrics[2], history=[metrics[0], metrics[1]], settings={})
        peak = is_visual_cut_peak(
            metrics[1],
            metrics[2],
            metrics[3],
            history=[metrics[0], metrics[1]],
            settings={},
        )

        self.assertIsNotNone(motion_score)
        self.assertIsNotNone(hard_cut_score)
        self.assertGreater(hard_cut_score["score"], motion_score["score"])
        self.assertTrue(peak["passed"])
        self.assertGreaterEqual(hard_cut_score["residual_ratio"], 0.78)
        self.assertGreater(hard_cut_score["mean_motion_px"], motion_score["mean_motion_px"])

    def test_native_coarse_series_spikes_on_hard_cut_interval(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        base = np.zeros((120, 180, 3), dtype=np.uint8)
        cv2.rectangle(base, (20, 20), (100, 90), (230, 230, 230), -1)
        smooth_1 = cv2.warpAffine(
            base,
            np.float32([[1, 0, 4], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        smooth_2 = cv2.warpAffine(
            base,
            np.float32([[1, 0, 8], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        hard_cut = np.zeros_like(base)
        cv2.rectangle(hard_cut, (8, 8), (172, 112), (70, 150, 240), -1)
        cv2.line(hard_cut, (4, 114), (176, 6), (255, 240, 60), 6)

        payloads = []
        for idx, frame in enumerate((base, smooth_1, smooth_2, hard_cut)):
            prepared = prepare_visual_cut_frame(frame, cv2, max_width=320)
            prepared["global_frame"] = idx * 20
            prepared["global_sec"] = float(idx)
            prepared["source_path"] = "/tmp/test.mp4"
            payloads.append(prepared)

        series = native_visual_cut_coarse_series(payloads)
        if series is None:
            self.skipTest("native coarse series unavailable")

        scored = [
            score_visual_cut_coarse_metrics(series[idx], history=series[:idx], settings={})
            for idx in range(len(series))
        ]

        self.assertEqual(len(scored), 3)
        self.assertGreater(scored[2]["score"], scored[1]["score"])
        self.assertGreater(scored[2]["edge_diff"], scored[1]["edge_diff"])
