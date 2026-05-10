"""Runtime policy helpers for cut-boundary pioneer/follower scans."""

from __future__ import annotations

import sys
from typing import Any

from core.performance import balanced_task_slices, current_resource_snapshot


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "enable"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}


def _setting_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


def _setting_int(value: Any, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return int(default)
    return parsed


def _setting_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def benchmark_locked_slice_count(settings: dict | None, key: str, default: int = 4) -> int:
    """Return benchmark-locked cut-boundary split counts.

    BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
    4-way CPU split was the fastest verified follower layout. 1/6, 1/8 and
    1/10 increased wall time/RSS; MPS was also slower for these tiny grids.
    """
    return max(1, min(16, _setting_int((settings or {}).get(key), default)))


def cut_boundary_pioneer_worker_ranges(
    *,
    step_count: int,
    worker_count: int,
    step_frames: int,
    frame_count: int,
    settings: dict | None = None,
) -> list[tuple[int, int, int]]:
    """Build overlapped pioneer frame ranges so worker seams cannot hide cuts."""
    step_slices = balanced_task_slices(step_count, worker_count, min_batch_size=1)
    overlap_steps = max(0, min(4, _setting_int((settings or {}).get("scan_cut_pioneer_worker_overlap_steps"), 1)))
    ranges: list[tuple[int, int, int]] = []
    last_idx = len(step_slices) - 1
    for idx, (start_step, end_step) in enumerate(step_slices):
        if end_step <= start_step:
            continue
        # BENCH LOCK 2026-05-09: keep 1-step overlap. It removes candidate
        # variance when a hard cut lands exactly on a worker range seam.
        overlapped_start = max(0, start_step - (overlap_steps if idx > 0 else 0))
        overlapped_end = min(step_count, end_step + (overlap_steps if idx < last_idx else 0))
        start_frame = min(frame_count, overlapped_start * step_frames)
        end_frame = min(frame_count, overlapped_end * step_frames)
        if end_frame > start_frame:
            ranges.append((idx, start_frame, end_frame))
    return ranges


def high_cost_visual_scan_skip_meta(
    filepath,
    *,
    width: float,
    height: float,
    duration_sec: float,
    settings: dict | None = None,
) -> dict:
    data = dict(settings or {})
    if not _setting_bool(data.get("scan_cut_high_cost_visual_skip_enabled"), True):
        return {"skip": False, "reason": "disabled"}
    pixels = max(0.0, float(width or 0.0)) * max(0.0, float(height or 0.0))
    duration = max(0.0, float(duration_sec or 0.0))
    try:
        size_bytes = float(getattr(filepath, "stat", lambda: None)().st_size)  # type: ignore[union-attr]
    except Exception:
        try:
            import os

            size_bytes = float(os.path.getsize(str(filepath)))
        except Exception:
            size_bytes = 0.0
    bitrate = (size_bytes * 8.0 / duration) if duration > 0.0 else 0.0
    min_pixels = max(1.0, _setting_float(data.get("scan_cut_high_cost_min_pixels"), 8_000_000.0))
    min_bitrate = max(1.0, _setting_float(data.get("scan_cut_high_cost_min_bitrate"), 80_000_000.0))
    skip = pixels >= min_pixels and bitrate >= min_bitrate
    return {
        "skip": bool(skip),
        "reason": "high_cost_4k_hevc_like_media" if skip else "below_threshold",
        "pixels": int(pixels),
        "bitrate": int(bitrate),
        "min_pixels": int(min_pixels),
        "min_bitrate": int(min_bitrate),
    }


def cut_boundary_cv2_capture_backend(cv2_mod, settings: dict | None = None) -> int | None:
    """Return the preferred OpenCV capture backend for cut-boundary scans."""
    data = dict(settings or {})
    requested = str(data.get("scan_cut_cv2_video_backend", "auto") or "auto").strip().lower()
    if requested in {"", "0", "false", "off", "none", "default", "opencv", "any"}:
        return None
    if requested in {"ffmpeg", "cap_ffmpeg"}:
        backend = getattr(cv2_mod, "CAP_FFMPEG", None)
        return int(backend) if backend is not None else None
    if requested in {"auto", "avfoundation", "avf", "mac", "macos", "videotoolbox"}:
        if sys.platform != "darwin" and requested == "auto":
            return None
        backend = getattr(cv2_mod, "CAP_AVFOUNDATION", None)
        return int(backend) if backend is not None else None
    return None


def open_cut_boundary_video_capture(cv2_mod, path, settings: dict | None = None):
    """Open a VideoCapture with the fastest safe backend, falling back silently."""
    backend = cut_boundary_cv2_capture_backend(cv2_mod, settings)
    if backend is not None:
        try:
            cap = cv2_mod.VideoCapture(str(path), backend)
            if cap is not None and cap.isOpened():
                return cap
            try:
                cap.release()
            except Exception:
                pass
        except TypeError:
            # Test doubles and older OpenCV builds may only accept one arg.
            pass
        except Exception:
            pass
    return cv2_mod.VideoCapture(str(path))


def configure_cut_boundary_cv2_threads(cv2_mod, settings: dict | None = None) -> dict:
    """Keep OpenCV from multiplying threads inside Python worker pools."""
    data = dict(settings or {})
    threads = _setting_int(data.get("scan_cut_cv2_threads_per_worker"), 0)
    meta = {"requested_threads": threads, "applied": False}
    if threads <= 0:
        meta["reason"] = "opencv_auto"
        return meta
    threads = max(1, min(8, threads))
    meta["requested_threads"] = threads
    try:
        get_threads = getattr(cv2_mod, "getNumThreads", None)
        if callable(get_threads):
            meta["previous_threads"] = int(get_threads() or 0)
    except Exception:
        pass
    try:
        set_threads = getattr(cv2_mod, "setNumThreads", None)
        if callable(set_threads):
            set_threads(threads)
            meta["applied"] = True
    except Exception:
        meta["applied"] = False
    return meta


def cut_follower_verify_backend(
    settings: dict | None = None,
    *,
    platform_name: str | None = None,
    mps_available=None,
    pressure_stage: str | None = None,
) -> str:
    """Choose the strict cut-boundary verifier backend."""
    data = dict(settings or {})
    if str(pressure_stage or "").strip().lower() in {"warning", "critical"}:
        return "cpu"
    if not _setting_bool(data.get("scan_cut_follower_mps_enabled"), False):
        return "cpu"
    if str(platform_name or sys.platform).strip().lower() != "darwin":
        return "cpu"
    try:
        available = mps_available() if callable(mps_available) else bool(mps_available)
    except Exception:
        available = False
    return "mps" if available else "cpu"


def cut_boundary_memory_pressure_stage(settings: dict | None = None, *, snapshot_fn=None) -> str:
    try:
        getter = snapshot_fn if callable(snapshot_fn) else current_resource_snapshot
        snapshot = dict(getter(settings) or {})
    except Exception:
        snapshot = {}
    stage = str(snapshot.get("memory_pressure_stage", "") or "").strip().lower()
    if stage in {"warning", "critical"}:
        return stage
    available_ratio = _setting_float(snapshot.get("available_memory_ratio"), 1.0)
    available_gb = _setting_float(snapshot.get("available_memory_bytes"), 0.0) / float(1024 ** 3)
    if available_ratio <= 0.12 or (available_gb > 0.0 and available_gb <= 1.5):
        return "critical"
    if available_ratio <= 0.20 or (available_gb > 0.0 and available_gb <= 3.0):
        return "warning"
    return "normal"


def cut_boundary_pressure_worker_cap(task: str, workers: int, pressure_stage: str | None) -> int:
    task_key = str(task or "").strip().lower()
    stage = str(pressure_stage or "").strip().lower()
    count = max(1, _setting_int(workers, 1))
    if task_key == "cut_follower":
        if stage == "critical":
            return 1
        if stage == "warning":
            return min(count, 2)
        return count
    if task_key == "cut_pioneer":
        if stage == "critical":
            return min(count, 2)
        if stage == "warning":
            return min(count, 4)
    return count


__all__ = [
    "_setting_bool",
    "_setting_float",
    "_setting_int",
    "benchmark_locked_slice_count",
    "configure_cut_boundary_cv2_threads",
    "cut_boundary_cv2_capture_backend",
    "cut_boundary_memory_pressure_stage",
    "cut_boundary_pioneer_worker_ranges",
    "cut_boundary_pressure_worker_cap",
    "cut_follower_verify_backend",
    "high_cost_visual_scan_skip_meta",
    "open_cut_boundary_video_capture",
]
