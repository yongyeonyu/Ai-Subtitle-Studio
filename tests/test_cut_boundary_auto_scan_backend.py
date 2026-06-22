import os
import sys
import unittest
from unittest.mock import patch

from core import native_cut_boundary as native
from core.cut_boundary_auto_scan import (
    _cut_boundary_pioneer_worker_ranges,
    build_auto_grid_scan_helpers,
    cut_boundary_cv2_capture_backend,
    cut_boundary_memory_pressure_stage,
    cut_boundary_pressure_worker_cap,
    configure_cut_boundary_cv2_threads,
    cut_follower_verify_backend,
    high_cost_visual_scan_skip_meta,
    open_cut_boundary_video_capture,
)
from core.cut_boundary_auto_verify import build_strict_verify_helpers
from core.cut_boundary_backend_router import CutBoundaryBackendChoice


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


class _BackendCapture:
    def __init__(self, opened=True):
        self.opened = bool(opened)
        self.released = False

    def isOpened(self):
        return self.opened

    def release(self):
        self.released = True


class _BackendCaptureCv2(_FakeCv2):
    CAP_AVFOUNDATION = 1200
    CAP_FFMPEG = 1900

    def __init__(self):
        super().__init__()
        self.calls = []

    def VideoCapture(self, *args):
        self.calls.append(tuple(args))
        return _BackendCapture(opened=True)


class _OneArgCaptureCv2(_FakeCv2):
    CAP_AVFOUNDATION = 1200

    def __init__(self):
        super().__init__()
        self.calls = []

    def VideoCapture(self, path, *args):
        if args:
            raise TypeError("one-arg test capture")
        self.calls.append((path,))
        return _BackendCapture(opened=True)


class _SequentialCapture:
    def __init__(self, cv2_mod):
        self._cv2 = cv2_mod
        self.pos = 0
        self.released = False
        self.set_calls = []
        self.grab_calls = 0

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == self._cv2.CAP_PROP_FPS:
            return 10.0
        if prop == self._cv2.CAP_PROP_FRAME_COUNT:
            return 45
        if prop == self._cv2.CAP_PROP_FRAME_WIDTH:
            return 1280
        if prop == self._cv2.CAP_PROP_FRAME_HEIGHT:
            return 720
        return 0

    def set(self, prop, value):
        if prop == self._cv2.CAP_PROP_POS_FRAMES:
            self.set_calls.append(int(value))
            self.pos = int(value)
        return True

    def read(self):
        if self.pos >= 45:
            return False, None
        frame = {"frame": self.pos}
        self.pos += 1
        return True, frame

    def grab(self):
        if self.pos >= 45:
            return False
        self.grab_calls += 1
        self.pos += 1
        return True

    def release(self):
        self.released = True


class _SequentialCaptureCv2(_FakeCv2):
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_POS_FRAMES = 5
    COLOR_BGR2GRAY = 6

    def __init__(self):
        super().__init__()
        self.captures = []
        self.paths = []

    def VideoCapture(self, path):
        self.paths.append(str(path))
        capture = _SequentialCapture(self)
        self.captures.append(capture)
        return capture

    def cvtColor(self, frame, _code):
        return frame


class _ArrayCapture:
    def __init__(self, frames):
        self.frames = list(frames)
        self.pos = 0

    def set(self, _prop, value):
        self.pos = max(0, min(len(self.frames) - 1, int(value)))
        return True

    def read(self):
        frame = self.frames[self.pos].copy()
        self.pos = min(len(self.frames) - 1, self.pos + 1)
        return True, frame


class CutBoundaryAutoScanBackendTests(unittest.TestCase):
    def _dense_flow_helper(self):
        return build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0,)),
                "_auto_capture_verify_maps": lambda *args, **kwargs: ({}, {}),
                "_auto_gray_delta": lambda *args, **kwargs: (0.0, 0, []),
                "_auto_color_avg_delta": lambda *args, **kwargs: (0.0, 0, []),
                "_auto_gray_delta_mps": lambda *args, **kwargs: (0.0, 0, []),
                "_auto_color_avg_delta_mps": lambda *args, **kwargs: (0.0, 0, []),
                "_mps_available": lambda: False,
            }
        )["_auto_dense_flow_cut_check"]

    def test_cut_follower_uses_native_mps_by_default_when_runtime_native_is_enabled(self):
        self.assertEqual(
            cut_follower_verify_backend(
                {"runtime_native_cut_boundary_enabled": True},
                platform_name="darwin",
                mps_available=lambda: True,
            ),
            "mps",
        )

    def test_cut_follower_keeps_cpu_when_runtime_native_is_disabled(self):
        def fail_if_called():
            raise AssertionError("MPS availability should not be checked when runtime native is disabled")

        self.assertEqual(
            cut_follower_verify_backend(
                {"runtime_native_cut_boundary_enabled": False},
                platform_name="darwin",
                mps_available=fail_if_called,
            ),
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

    def test_cut_follower_memory_pressure_forces_cpu_even_when_mps_is_enabled(self):
        self.assertEqual(
            cut_follower_verify_backend(
                {"scan_cut_follower_mps_enabled": True},
                platform_name="darwin",
                mps_available=lambda: True,
                pressure_stage="critical",
            ),
            "cpu",
        )

    def test_cut_boundary_memory_pressure_stage_uses_runtime_snapshot(self):
        with patch(
            "core.cut_boundary_auto_scan.current_resource_snapshot",
            return_value={"memory_pressure_stage": "warning"},
        ):
            self.assertEqual(cut_boundary_memory_pressure_stage({}), "warning")

    def test_cut_boundary_pressure_worker_cap_reduces_cut_workers_under_pressure(self):
        self.assertEqual(cut_boundary_pressure_worker_cap("cut_pioneer", 8, "warning"), 4)
        self.assertEqual(cut_boundary_pressure_worker_cap("cut_pioneer", 8, "critical"), 2)
        self.assertEqual(cut_boundary_pressure_worker_cap("cut_follower", 6, "warning"), 2)
        self.assertEqual(cut_boundary_pressure_worker_cap("cut_follower", 6, "critical"), 1)
        self.assertEqual(cut_boundary_pressure_worker_cap("cut_follower", 2, "normal"), 2)

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

    def test_cut_cv2_capture_prefers_avfoundation_on_macos(self):
        fake_cv2 = _BackendCaptureCv2()
        with patch("core.cut_boundary_auto_scan.sys.platform", "darwin"):
            backend = cut_boundary_cv2_capture_backend(fake_cv2, {"scan_cut_cv2_video_backend": "auto"})
            cap = open_cut_boundary_video_capture(fake_cv2, "/tmp/clip.mp4", {"scan_cut_cv2_video_backend": "auto"})

        self.assertEqual(backend, fake_cv2.CAP_AVFOUNDATION)
        self.assertTrue(cap.isOpened())
        self.assertEqual(fake_cv2.calls, [("/tmp/clip.mp4", fake_cv2.CAP_AVFOUNDATION)])

    def test_cut_cv2_capture_prefers_ffmpeg_for_lrf_when_avfoundation_is_requested(self):
        fake_cv2 = _BackendCaptureCv2()
        with patch("core.cut_boundary_auto_scan.sys.platform", "darwin"):
            backend = cut_boundary_cv2_capture_backend(
                fake_cv2,
                {"scan_cut_cv2_video_backend": "avfoundation"},
                "/tmp/clip.LRF",
            )
            cap = open_cut_boundary_video_capture(
                fake_cv2,
                "/tmp/clip.LRF",
                {"scan_cut_cv2_video_backend": "avfoundation"},
            )

        self.assertEqual(backend, fake_cv2.CAP_FFMPEG)
        self.assertTrue(cap.isOpened())
        self.assertEqual(fake_cv2.calls, [("/tmp/clip.LRF", fake_cv2.CAP_FFMPEG)])

    def test_cut_cv2_capture_falls_back_for_one_arg_capture(self):
        fake_cv2 = _OneArgCaptureCv2()
        with patch("core.cut_boundary_auto_scan.sys.platform", "darwin"):
            cap = open_cut_boundary_video_capture(fake_cv2, "/tmp/clip.mp4", {"scan_cut_cv2_video_backend": "auto"})

        self.assertTrue(cap.isOpened())
        self.assertEqual(fake_cv2.calls, [("/tmp/clip.mp4",)])

    def test_pioneer_worker_ranges_overlap_one_step_to_protect_seams(self):
        ranges = _cut_boundary_pioneer_worker_ranges(
            step_count=12,
            worker_count=4,
            step_frames=10,
            frame_count=120,
            settings={"scan_cut_pioneer_worker_overlap_steps": 1},
        )

        self.assertEqual(ranges, [(0, 0, 40), (1, 20, 70), (2, 50, 100), (3, 80, 120)])

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

    def test_pioneer_uses_sequential_grab_instead_of_random_seek_per_sample(self):
        fake_cv2 = _SequentialCaptureCv2()
        seen_frames = []
        helpers = build_auto_grid_scan_helpers(
            {
                "normalize_fps": lambda fps: fps,
                "sec_to_frame": lambda sec, fps: int(round(sec * fps)),
                "normalize_cut_boundaries": lambda rows, primary_fps=None: list(rows or []),
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "_selected_grid_delta": lambda prev, gray, positions: (seen_frames.append(gray["frame"]) or 0.0, [0.0]),
                "_cb_level_interval_sec": lambda level: 1.0,
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
                "/fake/video.mp4",
                sample_step_sec=1.0,
                settings={
                    "scan_cut_audio_gain_enabled": False,
                    "scan_cut_pioneer_workers": 1,
                    "scan_cut_pioneer_sequential_decode_enabled": True,
                },
                settings_preloaded=True,
                scan_profile={"level": "low"},
                sample_positions=(0,),
                sample_mask="single",
            )

        self.assertEqual(rows, [])
        self.assertGreaterEqual(len(fake_cv2.captures), 2)
        worker_capture = fake_cv2.captures[1]
        self.assertEqual(worker_capture.set_calls, [0])
        self.assertGreater(worker_capture.grab_calls, 0)
        self.assertEqual(seen_frames[:4], [10, 20, 30, 40])

    def test_pioneer_scans_existing_preview_proxy_when_available(self):
        fake_cv2 = _SequentialCaptureCv2()
        helpers = build_auto_grid_scan_helpers(
            {
                "normalize_fps": lambda fps: fps,
                "sec_to_frame": lambda sec, fps: int(round(sec * fps)),
                "normalize_cut_boundaries": lambda rows, primary_fps=None: list(rows or []),
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "_selected_grid_delta": lambda prev, gray, positions: (0.0, [0.0]),
                "_cb_level_interval_sec": lambda level: 1.0,
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

        with patch.dict(sys.modules, {"cv2": fake_cv2}), patch(
            "core.cut_boundary_auto_scan.select_cut_boundary_backend",
            return_value=CutBoundaryBackendChoice("opencv_proxy_fast", "/fake/proxy_720p.mp4", "test", True),
        ):
            rows = helpers["scan_media_cut_boundary_provisionals"](
                "/fake/original_4k.mov",
                sample_step_sec=1.0,
                settings={
                    "scan_cut_audio_gain_enabled": False,
                    "scan_cut_pioneer_workers": 1,
                    "scan_cut_use_preview_proxy_enabled": True,
                },
                settings_preloaded=True,
                scan_profile={"level": "low"},
                sample_positions=(0,),
                sample_mask="single",
            )

        self.assertEqual(rows, [])
        self.assertTrue(fake_cv2.paths)
        self.assertTrue(all(path == "/fake/proxy_720p.mp4" for path in fake_cv2.paths))

    def test_ffmpeg_scene_prepass_can_replace_opencv_pioneer(self):
        fake_cv2 = _SequentialCaptureCv2()

        def fail_if_opencv_grid_runs(*_args, **_kwargs):
            raise AssertionError("OpenCV grid scan should be skipped after scene prepass candidates")

        helpers = build_auto_grid_scan_helpers(
            {
                "normalize_fps": lambda fps: fps,
                "sec_to_frame": lambda sec, fps: int(round(sec * fps)),
                "normalize_cut_boundaries": lambda rows, primary_fps=None: list(rows or []),
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "_selected_grid_delta": fail_if_opencv_grid_runs,
                "_cb_level_interval_sec": lambda level: 1.0,
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
        scene_row = {
            "time": 12.0,
            "timeline_sec": 12.0,
            "source": "ffmpeg_scene_provisional",
            "refine_pending": True,
        }

        with patch.dict(sys.modules, {"cv2": fake_cv2}), patch(
            "core.cut_boundary_auto_scan.detect_ffmpeg_scene_boundaries",
            return_value=[scene_row],
        ):
            rows = helpers["scan_media_cut_boundary_provisionals"](
                "/fake/video.mp4",
                sample_step_sec=1.0,
                settings={
                    "scan_cut_audio_gain_enabled": False,
                    "scan_cut_ffmpeg_scene_prepass_enabled": True,
                    "scan_cut_ffmpeg_scene_replace_opencv_enabled": True,
                    "scan_cut_pioneer_workers": 1,
                },
                settings_preloaded=True,
                scan_profile={"level": "low"},
                sample_positions=(0,),
                sample_mask="single",
            )

        self.assertEqual(rows, [scene_row])

    def test_dense_flow_rejects_camera_motion_but_keeps_hard_cut(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        helper = self._dense_flow_helper()

        base = np.zeros((120, 180, 3), dtype=np.uint8)
        cv2.rectangle(base, (30, 30), (100, 85), (220, 220, 220), -1)
        cv2.line(base, (10, 100), (170, 20), (130, 130, 130), 2)
        cv2.circle(base, (140, 85), 18, (180, 180, 180), -1)

        shifted = cv2.warpAffine(
            base,
            np.float32([[1, 0, 20], [0, 1, 0]]),
            (180, 120),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        hard_cut = np.zeros_like(base)
        cv2.rectangle(hard_cut, (10, 10), (170, 110), (70, 140, 230), -1)
        cv2.line(hard_cut, (0, 0), (179, 119), (250, 250, 50), 4)

        motion_result = helper(_ArrayCapture([base, base, shifted]), cv2, frame=1, frame_count=3, settings={})
        hard_cut_result = helper(_ArrayCapture([base, base, hard_cut]), cv2, frame=1, frame_count=3, settings={})

        self.assertFalse(motion_result["passed"])
        self.assertEqual(motion_result["reason"], "dense_flow_motion_reject")
        self.assertTrue(hard_cut_result["passed"])

    def test_dense_flow_uses_five_frame_window_and_preserves_fades(self):
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            self.skipTest(f"OpenCV/numpy unavailable: {exc}")

        helper = self._dense_flow_helper()
        base = np.zeros((120, 180, 3), dtype=np.uint8)
        cv2.rectangle(base, (20, 28), (92, 84), (230, 230, 230), -1)
        cv2.line(base, (10, 108), (170, 18), (150, 150, 150), 2)
        shifted = [
            cv2.warpAffine(
                base,
                np.float32([[1, 0, shift], [0, 1, 0]]),
                (180, 120),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            )
            for shift in (0, 8, 16, 24, 32)
        ]
        fade = [
            np.full((120, 180, 3), value, dtype=np.uint8)
            for value in (20, 55, 90, 125, 160)
        ]

        motion_result = helper(_ArrayCapture(shifted), cv2, frame=2, frame_count=5, settings={})
        fade_result = helper(_ArrayCapture(fade), cv2, frame=2, frame_count=5, settings={})

        self.assertEqual(motion_result["window"], [0, 4])
        self.assertGreaterEqual(motion_result["pair_count"], 4)
        self.assertFalse(motion_result["passed"])
        self.assertTrue(fade_result["passed"])
        self.assertTrue(fade_result["brightness_monotonic"])

    def test_dense_flow_feature_flag_accepts_string_false(self):
        helper = self._dense_flow_helper()

        result = helper(None, object(), frame=1, frame_count=10, settings={"scan_cut_follower_dense_flow_enabled": "false"})

        self.assertTrue(result["passed"])
        self.assertEqual(result["reason"], "disabled")

    def test_strict_verify_skips_color_capture_when_gray_fails(self):
        capture_calls = []

        def capture_maps(_cap, _cv2, **kwargs):
            capture_calls.append(
                {
                    "start_frame": int(kwargs["start_frame"]),
                    "end_frame": int(kwargs["end_frame"]),
                    "capture_gray": bool(kwargs.get("capture_gray", True)),
                    "capture_color": bool(kwargs.get("capture_color", True)),
                }
            )
            start_frame = int(kwargs["start_frame"])
            end_frame = int(kwargs["end_frame"])
            gray_map = {frame: frame for frame in range(start_frame, end_frame + 1)} if kwargs.get("capture_gray", True) else {}
            color_map = {frame: frame for frame in range(start_frame, end_frame + 1)} if kwargs.get("capture_color", True) else {}
            return gray_map, color_map

        strict_verify = build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                "_auto_capture_verify_maps": capture_maps,
                "_auto_gray_delta": lambda *args, **kwargs: (0.0, 0, []),
                "_auto_color_avg_delta": lambda *args, **kwargs: (999.0, 5, [999.0]),
                "_auto_gray_delta_mps": lambda *args, **kwargs: (0.0, 0, []),
                "_auto_color_avg_delta_mps": lambda *args, **kwargs: (999.0, 5, [999.0]),
                "_mps_available": lambda: False,
            }
        )["_auto_grid_v3_manual_verify_strict"]

        result = strict_verify(
            object(),
            object(),
            fps=10.0,
            frame_count=45,
            coarse_frame=10,
            settings={
                "scan_cut_auto_verify_rollback_frames": 5,
                "scan_cut_auto_verify_forward_frames": 5,
                "scan_cut_color_avg_window_frames": 3,
                "scan_cut_auto_verify_window_stages": [4, 2, 1],
            },
            sample_positions=(0, 1, 2, 3, 4),
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "gray_failed")
        self.assertEqual(len(capture_calls), 1)
        self.assertEqual(
            capture_calls[0],
            {
                "start_frame": 5,
                "end_frame": 20,
                "capture_gray": True,
                "capture_color": False,
            },
        )

    def test_strict_verify_limits_color_capture_to_local_window_after_gray_pass(self):
        capture_calls = []

        def capture_maps(_cap, _cv2, **kwargs):
            capture_calls.append(
                {
                    "start_frame": int(kwargs["start_frame"]),
                    "end_frame": int(kwargs["end_frame"]),
                    "capture_gray": bool(kwargs.get("capture_gray", True)),
                    "capture_color": bool(kwargs.get("capture_color", True)),
                }
            )
            start_frame = int(kwargs["start_frame"])
            end_frame = int(kwargs["end_frame"])
            gray_map = {frame: frame for frame in range(start_frame, end_frame + 1)} if kwargs.get("capture_gray", True) else {}
            color_map = {frame: frame for frame in range(start_frame, end_frame + 1)} if kwargs.get("capture_color", True) else {}
            return gray_map, color_map

        def gray_delta(a, b, **_kwargs):
            gap = abs(int(b) - int(a))
            return float(gap * 40.0), 5, [float(gap)]

        strict_verify = build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                "_auto_capture_verify_maps": capture_maps,
                "_auto_gray_delta": gray_delta,
                "_auto_color_avg_delta": lambda *args, **kwargs: (25.0, 5, [25.0]),
                "_auto_gray_delta_mps": gray_delta,
                "_auto_color_avg_delta_mps": lambda *args, **kwargs: (25.0, 5, [25.0]),
                "_mps_available": lambda: False,
            }
        )["_auto_grid_v3_manual_verify_strict"]

        result = strict_verify(
            object(),
            object(),
            fps=10.0,
            frame_count=45,
            coarse_frame=10,
            settings={
                "scan_cut_auto_verify_rollback_frames": 5,
                "scan_cut_auto_verify_forward_frames": 5,
                "scan_cut_color_avg_window_frames": 3,
                "scan_cut_auto_verify_window_stages": [4, 2, 1],
                "scan_cut_follower_dense_flow_enabled": False,
            },
            sample_positions=(0, 1, 2, 3, 4),
        )

        self.assertTrue(result["passed"])
        self.assertEqual(len(capture_calls), 2)
        self.assertEqual(
            capture_calls[0],
            {
                "start_frame": 5,
                "end_frame": 20,
                "capture_gray": True,
                "capture_color": False,
            },
        )
        self.assertEqual(
            capture_calls[1],
            {
                "start_frame": 5,
                "end_frame": 12,
                "capture_gray": False,
                "capture_color": True,
            },
        )

    def test_strict_verify_uses_native_gray_rollback_search_for_precise_frame(self):
        previous = os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY")
        try:
            os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = "1"
            if not native.native_cut_boundary_enabled():
                self.skipTest("native cut-boundary extension unavailable")

            def thumb(value: int):
                return tuple(bytes([value]) * 64 for _ in range(5))

            def capture_maps(_cap, _cv2, **kwargs):
                start_frame = int(kwargs["start_frame"])
                end_frame = int(kwargs["end_frame"])
                if kwargs.get("capture_gray", True):
                    gray_map = {}
                    for frame_no in range(start_frame, end_frame + 1):
                        gray_map[frame_no] = thumb(0 if frame_no <= 7 else 120)
                    return gray_map, {}
                color_map = {frame_no: frame_no for frame_no in range(start_frame, end_frame + 1)}
                return {}, color_map

            def should_not_run(*_args, **_kwargs):
                raise AssertionError("python gray delta fallback should not run when native rollback search is enabled")

            strict_verify = build_strict_verify_helpers(
                {
                    "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                    "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                    "_auto_capture_verify_maps": capture_maps,
                    "_auto_gray_delta": should_not_run,
                    "_auto_color_avg_delta": lambda *args, **kwargs: (25.0, 5, [25.0]),
                    "_auto_gray_delta_mps": should_not_run,
                    "_auto_color_avg_delta_mps": lambda *args, **kwargs: (25.0, 5, [25.0]),
                    "_mps_available": lambda: False,
                }
            )["_auto_grid_v3_manual_verify_strict"]

            result = strict_verify(
                object(),
                object(),
                fps=10.0,
                frame_count=45,
                coarse_frame=10,
                settings={
                    "scan_cut_auto_verify_rollback_frames": 5,
                    "scan_cut_auto_verify_forward_frames": 5,
                    "scan_cut_color_avg_window_frames": 3,
                    "scan_cut_auto_verify_window_stages": [4, 2, 1],
                    "scan_cut_follower_dense_flow_enabled": False,
                },
                sample_positions=(0, 1, 2, 3, 4),
            )
        finally:
            if previous is None:
                os.environ.pop("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", None)
            else:
                os.environ["AI_SUBTITLE_NATIVE_CUT_BOUNDARY"] = previous

        self.assertTrue(result["passed"])
        self.assertEqual(result["frame"], 7)
        self.assertEqual(result["mode"], "gray_window_color_avg")

    def test_strict_verify_uses_one_second_window_independent_of_fps(self):
        capture_calls = []

        def capture_maps(_cap, _cv2, **kwargs):
            capture_calls.append(
                {
                    "start_frame": int(kwargs["start_frame"]),
                    "end_frame": int(kwargs["end_frame"]),
                    "capture_gray": bool(kwargs.get("capture_gray")),
                    "capture_color": bool(kwargs.get("capture_color")),
                }
            )
            start_frame = int(kwargs["start_frame"])
            end_frame = int(kwargs["end_frame"])
            if kwargs.get("capture_gray", True):
                return ({frame_no: frame_no for frame_no in range(start_frame, end_frame + 1)}, {})
            return ({}, {frame_no: frame_no for frame_no in range(start_frame, end_frame + 1)})

        strict_verify = build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                "_auto_capture_verify_maps": capture_maps,
                "_auto_gray_delta": lambda *_args, **_kwargs: (120.0, 5, [120.0]),
                "_auto_color_avg_delta": lambda *_args, **_kwargs: (25.0, 5, [25.0]),
                "_auto_gray_delta_mps": lambda *_args, **_kwargs: (120.0, 5, [120.0]),
                "_auto_color_avg_delta_mps": lambda *_args, **_kwargs: (25.0, 5, [25.0]),
                "_mps_available": lambda: False,
            }
        )["_auto_grid_v3_manual_verify_strict"]

        result = strict_verify(
            object(),
            object(),
            fps=60.0,
            frame_count=500,
            coarse_frame=240,
            settings={
                "scan_cut_auto_verify_rollback_window_sec": 1.0,
                "scan_cut_auto_verify_forward_window_sec": 1.0,
                "scan_cut_color_avg_window_frames": 3,
                "scan_cut_auto_verify_window_stages": [4, 2, 1],
                "scan_cut_follower_dense_flow_enabled": False,
            },
            sample_positions=(0, 1, 2, 3, 4),
        )

        self.assertTrue(result["passed"])
        self.assertEqual(
            capture_calls[0],
            {
                "start_frame": 180,
                "end_frame": 305,
                "capture_gray": True,
                "capture_color": False,
            },
        )

    def test_strict_verify_uses_local_color_consensus_to_resolve_gray_conflict(self):
        def capture_maps(_cap, _cv2, **kwargs):
            start_frame = int(kwargs["start_frame"])
            end_frame = int(kwargs["end_frame"])
            frame_map = {frame_no: frame_no for frame_no in range(start_frame, end_frame + 1)}
            if kwargs.get("capture_gray", True):
                return frame_map, {}
            return {}, frame_map

        def gray_delta(a, b, **_kwargs):
            pair = (int(a), int(b))
            if pair == (8, 9):
                return 85.0, 5, [85.0]
            if pair == (14, 18):
                return 150.0, 5, [150.0]
            return 0.0, 0, []

        def color_delta(a, b, **_kwargs):
            pair = (int(a), int(b))
            if pair == (14, 15):
                return 28.0, 5, [28.0]
            if pair == (13, 15):
                return 26.0, 5, [26.0]
            if pair == (8, 9):
                return 10.0, 1, [10.0]
            return 0.0, 0, []

        strict_verify = build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                "_auto_capture_verify_maps": capture_maps,
                "_auto_gray_delta": gray_delta,
                "_auto_color_avg_delta": color_delta,
                "_auto_gray_delta_mps": gray_delta,
                "_auto_color_avg_delta_mps": color_delta,
                "_mps_available": lambda: False,
            }
        )["_auto_grid_v3_manual_verify_strict"]

        result = strict_verify(
            object(),
            object(),
            fps=10.0,
            frame_count=60,
            coarse_frame=14,
            settings={
                "scan_cut_auto_verify_rollback_frames": 8,
                "scan_cut_auto_verify_forward_frames": 8,
                "scan_cut_color_avg_window_frames": 3,
                "scan_cut_auto_verify_window_stages": [4, 1],
                "scan_cut_follower_gray_agreement_frames": 3,
                "scan_cut_follower_gray_color_agreement_frames": 4,
                "scan_cut_follower_local_color_confirm_frames": 4,
                "scan_cut_follower_dense_flow_enabled": False,
            },
            sample_positions=(0, 1, 2, 3, 4),
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["frame"], 14)
        self.assertEqual(result["mode"], "gray_window_color_avg")

    def test_strict_verify_rejects_same_scene_when_frame_colors_are_too_similar(self):
        def capture_maps(_cap, _cv2, **kwargs):
            start_frame = int(kwargs["start_frame"])
            end_frame = int(kwargs["end_frame"])
            if kwargs.get("capture_gray", True):
                return ({frame_no: frame_no for frame_no in range(start_frame, end_frame + 1)}, {})
            color_map = {}
            for frame_no in range(start_frame, end_frame + 1):
                if frame_no <= 10:
                    color_map[frame_no] = [(40.0, 90.0, 120.0)] * 5
                else:
                    color_map[frame_no] = [(42.0, 92.0, 121.0)] * 5
            return ({}, color_map)

        def gray_delta(a, b, **_kwargs):
            pair = (int(a), int(b))
            if pair == (10, 11):
                return 130.0, 5, [130.0]
            if pair == (9, 13):
                return 155.0, 5, [155.0]
            return 0.0, 0, []

        strict_verify = build_strict_verify_helpers(
            {
                "normalize_cut_boundary_level": lambda level: str(level or "medium"),
                "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0, 1, 2, 3, 4)),
                "_auto_capture_verify_maps": capture_maps,
                "_auto_gray_delta": gray_delta,
                "_auto_color_avg_delta": lambda *_args, **_kwargs: (24.0, 5, [24.0]),
                "_auto_gray_delta_mps": gray_delta,
                "_auto_color_avg_delta_mps": lambda *_args, **_kwargs: (24.0, 5, [24.0]),
                "_mps_available": lambda: False,
            }
        )["_auto_grid_v3_manual_verify_strict"]

        result = strict_verify(
            object(),
            object(),
            fps=10.0,
            frame_count=60,
            coarse_frame=10,
            settings={
                "scan_cut_auto_verify_rollback_frames": 8,
                "scan_cut_auto_verify_forward_frames": 8,
                "scan_cut_color_avg_window_frames": 3,
                "scan_cut_auto_verify_window_stages": [4, 1],
                "scan_cut_follower_local_color_confirm_frames": 4,
                "scan_cut_follower_dense_flow_enabled": False,
                "scan_cut_follower_same_scene_color_enabled": True,
                "scan_cut_follower_same_scene_color_max_score": 6.0,
                "scan_cut_follower_same_scene_color_max_luma_delta": 4.0,
                "scan_cut_follower_same_scene_color_max_chroma_delta": 3.0,
            },
            sample_positions=(0, 1, 2, 3, 4),
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "same_scene_color_similarity")
        self.assertTrue(result["same_scene_color_similarity"])


if __name__ == "__main__":
    unittest.main()
