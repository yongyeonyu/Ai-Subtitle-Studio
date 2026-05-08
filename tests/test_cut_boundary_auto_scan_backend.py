import sys
import unittest
from unittest.mock import patch

from core.cut_boundary_auto_scan import (
    build_auto_grid_scan_helpers,
    configure_cut_boundary_cv2_threads,
    cut_follower_verify_backend,
    high_cost_visual_scan_skip_meta,
)


class _FakeCv2:
    def __init__(self):
        self.threads = 8

    def getNumThreads(self):
        return self.threads

    def setNumThreads(self, value):
        self.threads = int(value)


class _ClosedCapture:
    def __init__(self):
        self.released = False

    def isOpened(self):
        return False

    def release(self):
        self.released = True


class _ClosedCaptureCv2(_FakeCv2):
    def __init__(self):
        super().__init__()
        self.captures = []

    def VideoCapture(self, _path):
        capture = _ClosedCapture()
        self.captures.append(capture)
        return capture


class CutBoundaryAutoScanBackendTests(unittest.TestCase):
    def test_cut_follower_uses_cpu_by_default_without_touching_mps(self):
        def fail_if_called():
            raise AssertionError("MPS availability should not be checked when disabled")

        self.assertEqual(
            cut_follower_verify_backend({}, platform_name="darwin", mps_available=fail_if_called),
            "cpu",
        )

    def test_cut_follower_mps_is_explicit_opt_in(self):
        self.assertEqual(
            cut_follower_verify_backend(
                {"scan_cut_follower_mps_enabled": True},
                platform_name="darwin",
                mps_available=lambda: True,
            ),
            "mps",
        )

    def test_cut_follower_mps_string_false_keeps_cpu(self):
        self.assertEqual(
            cut_follower_verify_backend(
                {"scan_cut_follower_mps_enabled": "false"},
                platform_name="darwin",
                mps_available=lambda: True,
            ),
            "cpu",
        )

    def test_cut_cv2_threads_are_limited_inside_worker_pools(self):
        fake_cv2 = _FakeCv2()

        meta = configure_cut_boundary_cv2_threads(fake_cv2, {"scan_cut_cv2_threads_per_worker": 2})

        self.assertTrue(meta["applied"])
        self.assertEqual(meta["previous_threads"], 8)
        self.assertEqual(fake_cv2.threads, 2)

    def test_cut_cv2_threads_keep_opencv_auto_by_default(self):
        fake_cv2 = _FakeCv2()

        meta = configure_cut_boundary_cv2_threads(fake_cv2, {})

        self.assertFalse(meta["applied"])
        self.assertEqual(meta["reason"], "opencv_auto")
        self.assertEqual(fake_cv2.threads, 8)

    def test_high_cost_4k_video_skips_visual_scan(self):
        class FakePath:
            def stat(self):
                return type("Stat", (), {"st_size": 8_000_000_000})()

        meta = high_cost_visual_scan_skip_meta(
            FakePath(),
            width=3840,
            height=2160,
            duration_sec=404.0,
            settings={},
        )

        self.assertTrue(meta["skip"])
        self.assertEqual(meta["reason"], "high_cost_4k_hevc_like_media")

    def test_high_cost_visual_scan_skip_can_be_disabled(self):
        class FakePath:
            def stat(self):
                return type("Stat", (), {"st_size": 8_000_000_000})()

        meta = high_cost_visual_scan_skip_meta(
            FakePath(),
            width=3840,
            height=2160,
            duration_sec=404.0,
            settings={"scan_cut_high_cost_visual_skip_enabled": False},
        )

        self.assertFalse(meta["skip"])

    def test_preloaded_pioneer_settings_skip_disk_reload(self):
        helpers = build_auto_grid_scan_helpers(
            {
                "normalize_fps": lambda fps: fps,
                "sec_to_frame": lambda sec, fps: int(round(sec * fps)),
                "normalize_cut_boundaries": lambda rows, primary_fps=None: list(rows or []),
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "_selected_grid_delta": lambda prev, gray, positions: (0.0, []),
                "_cb_level_interval_sec": lambda level: 2.0,
                "_cb_level_effective_threshold": lambda level, threshold: float(threshold or 0.0),
                "_cb_level_min_gap_sec": lambda level: 8.0,
                "_cb_cuda_available": lambda: False,
                "_auto_downscale_frame_for_compare": lambda frame, cv2, settings=None: frame,
                "_auto_grid_v3_manual_verify_strict": lambda *args, **kwargs: {"passed": False},
                "_auto_grid_v3_manual_verify_strict_mps": lambda *args, **kwargs: {"passed": False},
                "_mps_available": lambda: False,
                "original_detect_media_cut_boundaries": lambda *args, **kwargs: [],
            }
        )

        with patch("core.settings.load_settings", side_effect=AssertionError("unexpected reload")):
            rows = helpers["scan_media_cut_boundary_provisionals"](
                "/definitely/missing/video.mp4",
                settings={"scan_cut_audio_gain_enabled": False},
                settings_preloaded=True,
                scan_profile={"level": "low"},
                sample_positions=(0,),
                sample_mask="single",
            )

        self.assertEqual(rows, [])

    def test_unopened_pioneer_capture_is_released(self):
        fake_cv2 = _ClosedCaptureCv2()
        helpers = build_auto_grid_scan_helpers(
            {
                "normalize_fps": lambda fps: fps,
                "sec_to_frame": lambda sec, fps: int(round(sec * fps)),
                "normalize_cut_boundaries": lambda rows, primary_fps=None: list(rows or []),
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "_selected_grid_delta": lambda prev, gray, positions: (0.0, []),
                "_cb_level_interval_sec": lambda level: 2.0,
                "_cb_level_effective_threshold": lambda level, threshold: float(threshold or 0.0),
                "_cb_level_min_gap_sec": lambda level: 8.0,
                "_cb_cuda_available": lambda: False,
                "_auto_downscale_frame_for_compare": lambda frame, cv2, settings=None: frame,
                "_auto_grid_v3_manual_verify_strict": lambda *args, **kwargs: {"passed": False},
                "_auto_grid_v3_manual_verify_strict_mps": lambda *args, **kwargs: {"passed": False},
                "_mps_available": lambda: False,
                "original_detect_media_cut_boundaries": lambda *args, **kwargs: [],
            }
        )

        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            rows = helpers["scan_media_cut_boundary_provisionals"](
                "/missing/video.mp4",
                settings={"scan_cut_audio_gain_enabled": False},
                settings_preloaded=True,
                scan_profile={"level": "low"},
                sample_positions=(0,),
                sample_mask="single",
            )

        self.assertEqual(rows, [])
        self.assertTrue(fake_cv2.captures)
        self.assertTrue(fake_cv2.captures[0].released)


if __name__ == "__main__":
    unittest.main()
