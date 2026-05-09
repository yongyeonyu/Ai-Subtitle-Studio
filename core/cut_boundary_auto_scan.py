# Version: 03.14.29
# Phase: PHASE2
"""Pioneer/follower scan functions for auto cut-boundary detection."""

from __future__ import annotations

import math
import sys
import time

from core.cut_boundary_audio import detect_audio_gain_boundary_rows
from core.cut_boundary_ffmpeg_scene import detect_ffmpeg_scene_boundaries
from core.performance import (
    balanced_task_slices,
    current_resource_snapshot,
)
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.cut_boundary_backend_router import apply_cut_boundary_backend_settings, select_cut_boundary_backend


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "enable"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}


def _setting_bool(value, default: bool = False) -> bool:
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


def _setting_int(value, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return int(default)
    return parsed


def _setting_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _benchmark_locked_slice_count(settings: dict | None, key: str, default: int = 4) -> int:
    """Return benchmark-locked cut-boundary split counts.

    BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
    4-way CPU split was the fastest verified follower layout. 1/6, 1/8 and
    1/10 increased wall time/RSS; MPS was also slower for these tiny grids.
    """
    return max(1, min(16, _setting_int((settings or {}).get(key), default)))


def _cut_boundary_pioneer_worker_ranges(
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
        # BENCH LOCK 2026-05-09: keep 1-step overlap. It removes the candidate
        # variance seen when 6+ workers split a hard cut exactly at a range seam.
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
    """Choose the strict cut-boundary verifier backend.

    The verifier compares many tiny grid thumbnails. On Apple Silicon, moving
    those tiny tensors to MPS per candidate is far slower than OpenCV/NumPy on
    CPU, so MPS stays opt-in for this micro-kernel.
    """
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


def cut_boundary_memory_pressure_stage(settings: dict | None = None) -> str:
    try:
        snapshot = dict(current_resource_snapshot(settings) or {})
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


def build_auto_grid_scan_helpers(deps: dict):
    normalize_fps = deps["normalize_fps"]
    sec_to_frame = deps["sec_to_frame"]
    normalize_cut_boundaries = deps["normalize_cut_boundaries"]
    normalize_cut_boundary_level = deps["normalize_cut_boundary_level"]
    _selected_grid_delta = deps["_selected_grid_delta"]
    _cb_level_interval_sec = deps["_cb_level_interval_sec"]
    _cb_level_effective_threshold = deps["_cb_level_effective_threshold"]
    _cb_level_min_gap_sec = deps["_cb_level_min_gap_sec"]
    _cb_cuda_available = deps["_cb_cuda_available"]
    _auto_downscale_frame_for_compare = deps["_auto_downscale_frame_for_compare"]
    _auto_grid_v3_manual_verify_strict = deps["_auto_grid_v3_manual_verify_strict"]
    _auto_grid_v3_manual_verify_strict_mps = deps["_auto_grid_v3_manual_verify_strict_mps"]
    _mps_available = deps["_mps_available"]
    _auto_grid_v3_original_detect_media_cut_boundaries = deps["original_detect_media_cut_boundaries"]

    def detect_media_cut_boundaries(
        filepath,
        *,
        clip_offset: float = 0.0,
        clip_idx: int = 0,
        sample_step_sec: float = 2.0,
        threshold: float = 24.0,
        progress_callback=None,
        found_callback=None,
        scan_profile: dict | None = None,
        sample_positions=None,
        sample_mask: str | None = None,
        **kwargs,
    ):
        settings = dict(kwargs.pop("settings", {}) or {})
        settings_preloaded = bool(kwargs.pop("settings_preloaded", False))
        if not settings_preloaded:
            try:
                from core.settings import load_settings
                loaded = dict(load_settings() or {})
                loaded.update(settings)
                settings = loaded
            except Exception:
                pass
        fallback_kwargs = dict(kwargs)
        settings = apply_cut_boundary_backend_settings(settings)
        fallback_kwargs["settings"] = settings

        if not bool(settings.get("scan_cut_auto_strict_color_avg_enabled", True)):
            return _auto_grid_v3_original_detect_media_cut_boundaries(
                filepath,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                scan_profile=scan_profile,
                sample_positions=sample_positions,
                sample_mask=sample_mask,
                **fallback_kwargs,
            )

        try:
            import cv2
        except Exception:
            return _auto_grid_v3_original_detect_media_cut_boundaries(
                filepath,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                scan_profile=scan_profile,
                sample_positions=sample_positions,
                sample_mask=sample_mask,
                **fallback_kwargs,
            )

        original_filepath = str(filepath)
        backend_choice = select_cut_boundary_backend(original_filepath, settings)
        scan_filepath = backend_choice.scan_path
        configure_cut_boundary_cv2_threads(cv2, settings)
        cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return _auto_grid_v3_original_detect_media_cut_boundaries(
                filepath,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                scan_profile=scan_profile,
                sample_positions=sample_positions,
                sample_mask=sample_mask,
                **fallback_kwargs,
            )

        verified_rows = []
        provisional_rows = []
        saw_callback = False

        try:
            from concurrent.futures import ThreadPoolExecutor

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps <= 1.0:
                fps = 30.0
            fps = normalize_fps(fps)

            min_gap_sec = float(settings.get("scan_cut_auto_min_gap_sec", 8.0))
            min_gap_frames = max(1, int(round(min_gap_sec * fps)))
            pioneer_step_sec = max(0.25, float(sample_step_sec or 2.0))
            follower_requested = int(settings.get("scan_cut_verify_workers", 4) or 4)
            follower_workload = max(
                1,
                int((frame_count / max(1.0, fps)) / max(0.25, pioneer_step_sec)),
            )
            pressure_stage = cut_boundary_memory_pressure_stage(settings)
            follower_workers, follower_scheduler = runtime_parallel_worker_plan(
                settings=settings,
                task="cut_follower",
                requested=follower_requested,
                workload=follower_workload,
                minimum=1,
                maximum=follower_workload,
                reserve_task="cut_follower",
                accelerators=["cpu"],
            )
            follower_workers = cut_boundary_pressure_worker_cap("cut_follower", follower_workers, pressure_stage)

            def verified_progress_callback(payload):
                if not callable(progress_callback):
                    return
                try:
                    fixed = dict(payload or {})
                    fixed["detected"] = len(verified_rows)
                    fixed["verified_detected"] = len(verified_rows)
                    fixed["provisional_detected"] = len(provisional_rows)
                    fixed["visual_scan_source_path"] = str(scan_filepath)
                    fixed["visual_scan_proxy"] = bool(scan_filepath != original_filepath)
                    fixed["cut_boundary_backend"] = backend_choice.backend
                    progress_callback(fixed)
                except Exception:
                    pass

            def verify_row(row):
                if not isinstance(row, dict):
                    return None

                try:
                    local_sec = float(row.get("clip_local_sec", 0.0) or 0.0)
                except Exception:
                    local_sec = 0.0

                if local_sec <= 0.0:
                    try:
                        local_sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) - float(clip_offset or 0.0)
                    except Exception:
                        local_sec = 0.0

                coarse_frame = max(0, int(round(local_sec * fps)))

                thread_state = getattr(verify_row, "_thread_state", None)
                if thread_state is None:
                    import threading

                    thread_state = threading.local()
                    verify_row._thread_state = thread_state
                    verify_row._caps = []
                verify_cap = getattr(thread_state, "cap", None)
                if verify_cap is None or not verify_cap.isOpened():
                    verify_cap = cv2.VideoCapture(str(scan_filepath))
                    thread_state.cap = verify_cap
                    try:
                        verify_row._caps.append(verify_cap)
                    except Exception:
                        pass
                if not verify_cap.isOpened():
                    return None
                verified = _auto_grid_v3_manual_verify_strict(
                    verify_cap,
                    cv2,
                    fps=fps,
                    frame_count=frame_count,
                    coarse_frame=coarse_frame,
                    settings=settings,
                    scan_profile=scan_profile,
                    sample_positions=sample_positions,
                )

                if not verified or not verified.get("passed"):
                    return None

                refined_local_sec = float(verified.get("sec", local_sec) or local_sec)
                timeline_sec = float(clip_offset or 0.0) + refined_local_sec
                timeline_frame = sec_to_frame(timeline_sec, fps)

                for old in verified_rows:
                    try:
                        if abs(int(old.get("timeline_frame", -999999)) - timeline_frame) <= min_gap_frames:
                            return None
                    except Exception:
                        pass

                fixed = dict(row)
                fixed.update(
                    {
                        "schema": "cut_boundary.v1",
                        "id": f"cut_{timeline_frame:08d}",
                        "time": timeline_sec,
                        "timeline_sec": timeline_sec,
                        "frame": timeline_frame,
                        "timeline_frame": timeline_frame,
                        "fps": fps,
                        "frame_rate": fps,
                        "timeline_frame_rate": fps,
                        "clip_idx": int(clip_idx or 0),
                        "clip_local_sec": refined_local_sec,
                        "source_path": original_filepath,
                        "visual_scan_source_path": str(scan_filepath),
                        "visual_scan_proxy": bool(scan_filepath != original_filepath),
                        "cut_boundary_backend": backend_choice.backend,
                        "score": float(verified.get("score", fixed.get("score", 0.0)) or 0.0),
                        "regions": int(verified.get("regions", fixed.get("regions", 0)) or 0),
                        "color_score": float(verified.get("color_score", 0.0) or 0.0),
                        "color_regions": int(verified.get("color_regions", 0) or 0),
                        "dense_flow": dict(verified.get("dense_flow") or {}),
                        "grid_cells": int(verified.get("grid_cells", 0) or 0),
                        "reason": str(verified.get("reason") or "strict_color_avg"),
                        "detector": "opencv-gray-grid-v3-strict-color-avg",
                        "source": "visual",
                        "absolute": True,
                        "locked": True,
                    }
                )
                return fixed

            with ThreadPoolExecutor(max_workers=follower_workers, thread_name_prefix="cut-boundary-follower") as executor:
                future_map = {}

                def _release_verify_caps():
                    for verify_cap in list(getattr(verify_row, "_caps", []) or []):
                        try:
                            verify_cap.release()
                        except Exception:
                            pass
                    try:
                        verify_row._caps = []
                    except Exception:
                        pass

                def _drain_completed():
                    completed = []
                    for future, provisional in list(future_map.items()):
                        if future.done():
                            completed.append((future, provisional))
                    for future, provisional in completed:
                        future_map.pop(future, None)
                        try:
                            provisional_rows.remove(provisional)
                        except ValueError:
                            pass
                        try:
                            fixed = future.result()
                        except Exception:
                            fixed = None
                        if fixed is None:
                            continue
                        verified_rows.append(fixed)
                        verified_rows[:] = normalize_cut_boundaries(verified_rows, primary_fps=fps)
                        if callable(found_callback):
                            try:
                                found_callback(dict(fixed), list(verified_rows))
                            except Exception:
                                pass
                    return len(completed)

                def _submit_provisional(row):
                    provisional = dict(row) if isinstance(row, dict) else {}
                    provisional["status"] = "provisional"
                    provisional["detector_stage"] = "pioneer"
                    provisional_rows.append(provisional)
                    future_map[executor.submit(verify_row, provisional)] = provisional
                    _drain_completed()

                def verified_found_callback(row, rows):
                    nonlocal saw_callback
                    saw_callback = True
                    _submit_provisional(row)

                try:
                    raw_rows = _auto_grid_v3_original_detect_media_cut_boundaries(
                        scan_filepath,
                        clip_offset=clip_offset,
                        clip_idx=clip_idx,
                        sample_step_sec=pioneer_step_sec,
                        threshold=threshold,
                        progress_callback=verified_progress_callback,
                        found_callback=verified_found_callback,
                        scan_profile=scan_profile,
                        sample_positions=sample_positions,
                        sample_mask=sample_mask,
                        **fallback_kwargs,
                    )

                    if not saw_callback:
                        for row in raw_rows or []:
                            _submit_provisional(row)

                    while future_map:
                        if not _drain_completed():
                            time.sleep(0.002)
                finally:
                    _release_verify_caps()

            return normalize_cut_boundaries(verified_rows, primary_fps=fps)

        finally:
            try:
                cap.release()
            except Exception:
                pass


    def scan_media_cut_boundary_provisionals(
        filepath,
        *,
        clip_offset=0.0,
        clip_idx=0,
        sample_step_sec=2.0,
        threshold=24.0,
        progress_callback=None,
        found_callback=None,
        scan_profile: dict | None = None,
        sample_positions=None,
        sample_mask: str | None = None,
        **kwargs,
    ):
        completion_callback = kwargs.pop("completion_callback", None)
        settings = dict(kwargs.pop("settings", {}) or {})
        settings_preloaded = bool(kwargs.pop("settings_preloaded", False))
        if not settings_preloaded:
            try:
                from core.settings import load_settings
                loaded = dict(load_settings() or {})
                loaded.update(settings)
                settings = loaded
            except Exception:
                pass
        fallback_kwargs = dict(kwargs)
        settings = apply_cut_boundary_backend_settings(settings)
        fallback_kwargs["settings"] = settings

        try:
            import cv2
            from concurrent.futures import ThreadPoolExecutor, as_completed
        except Exception:
            rows = _auto_grid_v3_original_detect_media_cut_boundaries(
                filepath,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                scan_profile=scan_profile,
                sample_positions=sample_positions,
                sample_mask=sample_mask,
                **fallback_kwargs,
            )
            return normalize_cut_boundaries(rows or [])

        original_filepath = str(filepath)
        backend_choice = select_cut_boundary_backend(original_filepath, settings)
        scan_filepath = backend_choice.scan_path
        configure_cut_boundary_cv2_threads(cv2, settings)
        cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return []
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            frame_width = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0.0)
            frame_height = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0.0)
        finally:
            try:
                cap.release()
            except Exception:
                pass
        if fps <= 0.0 or frame_count <= 0:
            return []

        fps = normalize_fps(fps if fps > 1.0 else 30.0)
        duration = frame_count / fps
        level = normalize_cut_boundary_level((scan_profile or {}).get("level", "medium"))
        positions = tuple(int(x) for x in ((sample_positions if sample_positions is not None else (scan_profile or {}).get("positions", ())) or ()))
        if not positions:
            return []
        mask = str(sample_mask or (scan_profile or {}).get("mask", ""))
        scan_interval_sec = max(0.25, float(sample_step_sec or _cb_level_interval_sec(level) or 1.0))
        step_frames = max(1, int(round(fps * scan_interval_sec)))
        pioneer_strict_multiplier = float(settings.get("scan_cut_pioneer_strict_multiplier", 1.04) or 1.04)
        effective_threshold = _cb_level_effective_threshold(level, float(threshold or 24.0)) * pioneer_strict_multiplier
        min_gap_sec = _cb_level_min_gap_sec(level)
        pioneer_requested = int(settings.get("scan_cut_pioneer_workers", 4) or 4)
        pioneer_workload = max(1, int(duration / max(0.25, scan_interval_sec)))
        pressure_stage = cut_boundary_memory_pressure_stage(settings)
        pioneer_workers, pioneer_scheduler = runtime_parallel_worker_plan(
            settings=settings,
            task="cut_pioneer",
            requested=pioneer_requested,
            workload=pioneer_workload,
            minimum=1,
            maximum=pioneer_workload,
            reserve_task="cut_pioneer",
            accelerators=["cpu"],
        )
        pioneer_workers = cut_boundary_pressure_worker_cap("cut_pioneer", pioneer_workers, pressure_stage)
        gpu_refine_enabled = bool(settings.get("scan_cut_pioneer_gpu_refine_enabled", True))
        cuda_available = _cb_cuda_available() if gpu_refine_enabled else False
        audio_gain_enabled = _setting_bool(settings.get("scan_cut_audio_gain_enabled"), True)
        ffmpeg_scene_enabled = _setting_bool(settings.get("scan_cut_ffmpeg_scene_prepass_enabled"), False)
        ffmpeg_scene_replace_opencv = _setting_bool(
            settings.get("scan_cut_ffmpeg_scene_replace_opencv_enabled"),
            False,
        )

        def _settings_float(key: str, default: float) -> float:
            try:
                return float(settings.get(key, default) or default)
            except Exception:
                return float(default)

        def _settings_int(key: str, default: int) -> int:
            try:
                return int(settings.get(key, default) or default)
            except Exception:
                return int(default)

        audio_gain_window_sec = max(
            0.50,
            _settings_float("scan_cut_audio_gain_window_sec", max(1.0, scan_interval_sec)),
        )
        audio_gain_threshold_db = max(1.0, _settings_float("scan_cut_audio_gain_threshold_db", 10.0))
        audio_gain_min_gap_sec = max(0.0, _settings_float("scan_cut_audio_gain_min_gap_sec", min_gap_sec))
        audio_gain_sample_rate = max(1000, _settings_int("scan_cut_audio_gain_sample_rate", 4000))
        audio_gain_context_windows = max(1, _settings_int("scan_cut_audio_gain_context_windows", 2))
        audio_gain_timeout_sec = max(1.0, _settings_float("scan_cut_audio_gain_timeout_sec", 45.0))
        audio_gain_max_candidates = max(1, _settings_int("scan_cut_audio_gain_max_candidates", 240))
        ffmpeg_scene_threshold = max(
            0.01,
            min(0.95, _settings_float("scan_cut_ffmpeg_scene_threshold", 0.35)),
        )
        ffmpeg_scene_timeout_sec = max(1.0, _settings_float("scan_cut_ffmpeg_scene_timeout_sec", 90.0))
        ffmpeg_scene_max_candidates = max(1, _settings_int("scan_cut_ffmpeg_scene_max_candidates", 300))
        progress_sample_stride = max(1, _settings_int("scan_cut_progress_sample_stride", 4))

        def _scan_audio_gain_rows():
            if not audio_gain_enabled:
                return []
            try:
                return detect_audio_gain_boundary_rows(
                    str(filepath),
                    clip_offset=float(clip_offset or 0.0),
                    clip_idx=int(clip_idx or 0),
                    fps=fps,
                    duration_sec=duration,
                    threshold_db=audio_gain_threshold_db,
                    min_gap_sec=audio_gain_min_gap_sec,
                    window_sec=audio_gain_window_sec,
                    sample_rate=audio_gain_sample_rate,
                    context_windows=audio_gain_context_windows,
                    timeout_sec=audio_gain_timeout_sec,
                    max_candidates=audio_gain_max_candidates,
                )
            except Exception:
                return []

        def _scan_ffmpeg_scene_rows():
            if not ffmpeg_scene_enabled:
                return []
            try:
                return detect_ffmpeg_scene_boundaries(
                    str(scan_filepath),
                    clip_offset=float(clip_offset or 0.0),
                    clip_idx=int(clip_idx or 0),
                    fps=fps,
                    threshold=ffmpeg_scene_threshold,
                    min_gap_sec=min_gap_sec,
                    timeout_sec=ffmpeg_scene_timeout_sec,
                    max_candidates=ffmpeg_scene_max_candidates,
                    progress_callback=progress_callback,
                    visual_scan_source_path=original_filepath,
                    visual_scan_proxy=bool(scan_filepath != original_filepath),
                )
            except Exception:
                return []

        def _emit_provisional_rows(rows):
            if not callable(found_callback):
                return
            current_rows = list(rows or [])
            for row in current_rows:
                try:
                    found_callback(dict(row), current_rows)
                except Exception:
                    pass

        if ffmpeg_scene_enabled and ffmpeg_scene_replace_opencv:
            scene_rows = list(_scan_ffmpeg_scene_rows() or [])
            if scene_rows:
                audio_rows = list(_scan_audio_gain_rows() or [])
                _emit_provisional_rows(scene_rows)
                _emit_provisional_rows(audio_rows)
                combined_rows = [*scene_rows, *audio_rows]
                normalized = normalize_cut_boundaries(combined_rows, primary_fps=fps)
                payload = {
                    "clip_idx": int(clip_idx or 0),
                    "worker_total": 1,
                    "worker_completed": 1,
                    "percent": 100,
                    "timestamp": float(duration or 0.0),
                    "duration": float(duration or 0.0),
                    "detected": len(normalized),
                    "done": True,
                    "scheduler": pioneer_scheduler,
                    "visual_scan_source_path": str(scan_filepath),
                    "visual_scan_proxy": bool(scan_filepath != original_filepath),
                    "cut_boundary_backend": "ffmpeg_scene_prepass",
                    "opencv_scan_replaced": True,
                }
                if callable(progress_callback):
                    try:
                        progress_callback(dict(payload))
                    except Exception:
                        pass
                if callable(completion_callback):
                    try:
                        completion_callback(dict(payload))
                    except Exception:
                        pass
                return normalized

        high_cost_skip = high_cost_visual_scan_skip_meta(
            scan_filepath,
            width=frame_width,
            height=frame_height,
            duration_sec=duration,
            settings=settings,
        )
        if bool(high_cost_skip.get("skip")):
            audio_rows = list(_scan_audio_gain_rows() or [])
            scene_rows = list(_scan_ffmpeg_scene_rows() or []) if ffmpeg_scene_enabled else []
            _emit_provisional_rows(audio_rows)
            _emit_provisional_rows(scene_rows)
            combined_skip_rows = [*scene_rows, *audio_rows]
            normalized = normalize_cut_boundaries(combined_skip_rows, primary_fps=fps)
            payload = {
                "clip_idx": int(clip_idx or 0),
                "percent": 100,
                "timestamp": float(duration or 0.0),
                "duration": float(duration or 0.0),
                "detected": len(normalized),
                "done": True,
                "visual_scan_skipped": True,
                "skip_meta": high_cost_skip,
                "visual_scan_source_path": str(scan_filepath),
                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                "cut_boundary_backend": backend_choice.backend,
                "scheduler": pioneer_scheduler,
            }
            if callable(progress_callback):
                try:
                    progress_callback(dict(payload))
                except Exception:
                    pass
            if callable(completion_callback):
                try:
                    completion_callback(dict(payload))
                except Exception:
                    pass
            return normalized

        def _scan_range(worker_idx: int, start_frame: int, end_frame: int):
            worker_cap = cv2.VideoCapture(str(scan_filepath))
            if not worker_cap.isOpened():
                try:
                    worker_cap.release()
                except Exception:
                    pass
                return []
            rows_local = []
            prev_gray = None
            last_emit_t = -999999.0
            sequential_decode = _setting_bool(settings.get("scan_cut_pioneer_sequential_decode_enabled"), False)
            try:
                frame_no = int(start_frame)
                sample_idx = 0
                if sequential_decode:
                    try:
                        worker_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                    except Exception:
                        sequential_decode = False
                while frame_no < end_frame:
                    if not sequential_decode:
                        worker_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                    ok, frame = worker_cap.read()
                    if not ok or frame is None:
                        if sequential_decode:
                            break
                        frame_no += step_frames
                        sample_idx += 1
                        continue
                    frame = _auto_downscale_frame_for_compare(frame, cv2, settings=settings)
                    t = frame_no / fps
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if worker_idx == 0 and callable(progress_callback):
                        pass
                    if callable(progress_callback) and (sample_idx == 0 or sample_idx % progress_sample_stride == 0):
                        try:
                            local_total = max(1, int(end_frame - start_frame))
                            local_done = max(0, int(frame_no - start_frame))
                            progress_callback({
                                "clip_idx": clip_idx,
                                "percent": int(min(100, (frame_no / max(1, frame_count)) * 100)),
                                "worker_percent": int(min(100, (local_done / max(1, local_total)) * 100)),
                                "timestamp": t,
                                "duration": duration,
                                "detected": len(rows_local),
                                "worker_idx": worker_idx,
                                "worker_total": pioneer_workers,
                            })
                        except Exception:
                            pass
                    if prev_gray is not None:
                        delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)
                        # "높음"은 페이드/디졸브 같은 완만한 전환도 더 잘 집도록
                        # 더 촘촘히 샘플링하되, 셀 강도 충족 비율은 약간 완화한다.
                        required_ratio = {"low": 0.87, "medium": 0.82, "high": 0.60}.get(level, 0.82)
                        strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                        required_cells = max(1, int(round(len(positions) * required_ratio)))
                        if delta >= effective_threshold and strong_cells >= required_cells and (t - last_emit_t) >= min_gap_sec:
                            coarse_sec = round(float(t), 3)
                            row = {
                                "time": coarse_sec,
                                "timeline_sec": round(float(clip_offset or 0.0) + coarse_sec, 3),
                                "clip_idx": int(clip_idx or 0),
                                "clip_local_sec": coarse_sec,
                                "source": "grid_profile_v3_parallel",
                                "level": level,
                                "mask": mask,
                                "cell_count": len(positions),
                                "grid_positions": list(positions),
                                "delta": round(delta, 3),
                                "cell_deltas": [round(x, 3) for x in cell_deltas],
                                "threshold": float(threshold or 24.0),
                                "effective_threshold": round(effective_threshold, 3),
                                "scan_interval_sec": scan_interval_sec,
                                "min_gap_sec": min_gap_sec,
                                "worker_idx": worker_idx,
                                "coarse_time": coarse_sec,
                                "refine_pending": True,
                                "refine_backend": "gpu_preferred" if cuda_available else "async_cpu",
                                "source_path": original_filepath,
                                "visual_scan_source_path": str(scan_filepath),
                                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                            }
                            rows_local.append(row)
                            last_emit_t = coarse_sec
                            if callable(found_callback):
                                try:
                                    found_callback(dict(row), list(rows_local))
                                except Exception:
                                    pass
                    prev_gray = gray
                    next_frame_no = frame_no + step_frames
                    if sequential_decode:
                        skip_frames = max(0, min(end_frame, next_frame_no) - frame_no - 1)
                        grab = getattr(worker_cap, "grab", None)
                        skipped = 0
                        while skipped < skip_frames:
                            try:
                                if callable(grab):
                                    if not grab():
                                        break
                                else:
                                    ok_skip, _frame_skip = worker_cap.read()
                                    if not ok_skip:
                                        break
                            except Exception:
                                break
                            skipped += 1
                        if skipped < skip_frames:
                            break
                    frame_no = next_frame_no
                    sample_idx += 1
            finally:
                try:
                    worker_cap.release()
                except Exception:
                    pass
            if callable(progress_callback):
                try:
                    progress_callback({
                        "clip_idx": clip_idx,
                        "percent": int(min(100, (end_frame / max(1, frame_count)) * 100)),
                        "worker_percent": 100,
                        "timestamp": min(duration, end_frame / fps),
                        "duration": duration,
                        "detected": len(rows_local),
                        "worker_idx": worker_idx,
                        "worker_total": pioneer_workers,
                        "visual_scan_source_path": str(scan_filepath),
                        "visual_scan_proxy": bool(scan_filepath != original_filepath),
                        "cut_boundary_backend": backend_choice.backend,
                    })
                except Exception:
                    pass
            return rows_local

        if pioneer_workers <= 1 or duration <= scan_interval_sec * 2.0:
            audio_rows = list(_scan_audio_gain_rows() or [])
            scene_rows = list(_scan_ffmpeg_scene_rows() or [])
            _emit_provisional_rows(audio_rows)
            _emit_provisional_rows(scene_rows)
            rows = _scan_range(0, 0, frame_count)
            normalized = normalize_cut_boundaries([*(rows or []), *scene_rows, *audio_rows], primary_fps=fps)
            if callable(completion_callback):
                try:
                    completion_callback(
                        {
                            "clip_idx": int(clip_idx or 0),
                            "worker_total": 1,
                            "worker_completed": 1,
                            "duration": float(duration or 0.0),
                            "detected": len(normalized),
                            "done": True,
                            "scheduler": pioneer_scheduler,
                            "visual_scan_source_path": str(scan_filepath),
                            "visual_scan_proxy": bool(scan_filepath != original_filepath),
                            "cut_boundary_backend": backend_choice.backend,
                        }
                    )
                except Exception:
                    pass
            return normalized

        futures = []
        audio_future = None
        scene_future = None
        audio_rows = []
        scene_rows = []
        merged = []
        completed_workers = 0
        step_count = max(1, int(math.ceil(frame_count / max(1, step_frames))))
        worker_ranges = _cut_boundary_pioneer_worker_ranges(
            step_count=step_count,
            worker_count=pioneer_workers,
            step_frames=step_frames,
            frame_count=frame_count,
            settings=settings,
        )
        worker_count = len(worker_ranges) + (1 if audio_gain_enabled else 0) + (1 if ffmpeg_scene_enabled else 0)
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="cut-boundary-pioneer") as executor:
            if audio_gain_enabled:
                audio_future = executor.submit(_scan_audio_gain_rows)
            if ffmpeg_scene_enabled:
                scene_future = executor.submit(_scan_ffmpeg_scene_rows)
            for worker_idx, start_frame, end_frame in worker_ranges:
                futures.append(executor.submit(_scan_range, worker_idx, start_frame, end_frame))
            wait_futures = list(futures)
            if audio_future is not None:
                wait_futures.append(audio_future)
            if scene_future is not None:
                wait_futures.append(scene_future)
            for future in as_completed(wait_futures):
                if audio_future is not None and future is audio_future:
                    try:
                        audio_rows.extend(list(future.result() or []))
                    except Exception:
                        audio_rows[:] = []
                    _emit_provisional_rows(audio_rows)
                    continue
                if scene_future is not None and future is scene_future:
                    try:
                        scene_rows.extend(list(future.result() or []))
                    except Exception:
                        scene_rows[:] = []
                    _emit_provisional_rows(scene_rows)
                    continue
                completed_workers += 1
                try:
                    merged.extend(list(future.result() or []))
                except Exception:
                    pass
                if callable(completion_callback):
                    try:
                        completion_callback(
                            {
                                "clip_idx": int(clip_idx or 0),
                                "worker_total": int(len(worker_ranges)),
                                "worker_completed": int(completed_workers),
                                "duration": float(duration or 0.0),
                                "detected": len(merged),
                                "done": bool(completed_workers >= len(worker_ranges)),
                                "scheduler": pioneer_scheduler,
                                "visual_scan_source_path": str(scan_filepath),
                                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                                "cut_boundary_backend": backend_choice.backend,
                            }
                        )
                    except Exception:
                        pass

        combined_rows = [*list(merged or []), *list(scene_rows or []), *list(audio_rows or [])]
        if combined_rows:
            for row in combined_rows:
                try:
                    row["refine_pending"] = True
                    if row.get("source") != "audio_gain_provisional":
                        row["refine_backend"] = "gpu_async" if cuda_available else "async_cpu"
                except Exception:
                    pass
        if callable(progress_callback):
            try:
                progress_callback({
                    "clip_idx": clip_idx,
                    "percent": 100,
                    "timestamp": duration,
                    "duration": duration,
                    "detected": len(combined_rows),
                    "worker_idx": 0,
                    "visual_scan_source_path": str(scan_filepath),
                    "visual_scan_proxy": bool(scan_filepath != original_filepath),
                    "cut_boundary_backend": backend_choice.backend,
                })
            except Exception:
                pass
        return normalize_cut_boundaries(combined_rows or [], primary_fps=fps)


    def verify_media_cut_boundary_rows(
        filepath,
        provisional_rows,
        *,
        clip_offset=0.0,
        clip_idx=0,
        scan_profile: dict | None = None,
        sample_positions=None,
        settings: dict | None = None,
        found_callback=None,
        **kwargs,
    ):
        provisional_callback = kwargs.pop("provisional_callback", None)
        settings = dict(settings or {})
        settings_preloaded = bool(kwargs.pop("settings_preloaded", False))
        if not settings_preloaded:
            try:
                from core.settings import load_settings
                loaded = dict(load_settings() or {})
                loaded.update(settings)
                settings = loaded
            except Exception:
                pass

        try:
            import cv2
        except Exception:
            return normalize_cut_boundaries(provisional_rows or [])

        settings = apply_cut_boundary_backend_settings(settings)
        original_filepath = str(filepath)
        backend_choice = select_cut_boundary_backend(original_filepath, settings)
        scan_filepath = backend_choice.scan_path
        configure_cut_boundary_cv2_threads(cv2, settings)
        cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = cv2.VideoCapture(str(scan_filepath))
        if not cap.isOpened():
            try:
                cap.release()
            except Exception:
                pass
            return normalize_cut_boundaries(provisional_rows or [])
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            frame_width = float(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0.0)
            frame_height = float(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0.0)
            if fps <= 1.0:
                fps = 30.0
            fps = normalize_fps(fps)
            duration = frame_count / fps if fps > 0.0 else 0.0
            high_cost_skip = high_cost_visual_scan_skip_meta(
                scan_filepath,
                width=frame_width,
                height=frame_height,
                duration_sec=duration,
                settings=settings,
            )
            if bool(high_cost_skip.get("skip")):
                rows = []
                for row in list(provisional_rows or []):
                    if not isinstance(row, dict):
                        continue
                    fixed = dict(row)
                    fixed["visual_verify_skipped"] = True
                    fixed["verify_backend"] = "audio_gain_only_high_cost_skip"
                    fixed["skip_meta"] = dict(high_cost_skip)
                    fixed["visual_scan_source_path"] = str(scan_filepath)
                    fixed["visual_scan_proxy"] = bool(scan_filepath != original_filepath)
                    fixed["cut_boundary_backend"] = backend_choice.backend
                    rows.append(fixed)
                    if callable(found_callback):
                        try:
                            found_callback(dict(fixed), list(rows))
                        except Exception:
                            pass
                return normalize_cut_boundaries(rows, primary_fps=fps)
            min_gap_sec = float(settings.get("scan_cut_auto_min_gap_sec", 8.0))
            min_gap_frames = max(1, int(round(min_gap_sec * fps)))
            follower_requested = int(settings.get("scan_cut_verify_workers", 4) or 4)
            follower_workload = max(1, len(provisional_rows or []))
            pressure_stage = cut_boundary_memory_pressure_stage(settings)
            follower_backend = cut_follower_verify_backend(
                settings,
                platform_name=sys.platform,
                mps_available=_mps_available,
                pressure_stage=pressure_stage,
            )
            follower_workers, follower_scheduler = runtime_parallel_worker_plan(
                settings=settings,
                task="cut_follower",
                requested=follower_requested,
                workload=follower_workload,
                minimum=1,
                maximum=follower_workload,
                reserve_task="cut_follower",
                accelerators=[follower_backend],
            )
            follower_workers = cut_boundary_pressure_worker_cap("cut_follower", follower_workers, pressure_stage)
            verified_rows = []

            def _verify_row(row, verify_cap=None):
                if not isinstance(row, dict):
                    return None
                try:
                    local_sec = float(row.get("clip_local_sec", 0.0) or 0.0)
                except Exception:
                    local_sec = 0.0
                if local_sec <= 0.0:
                    try:
                        local_sec = float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0) - float(clip_offset or 0.0)
                    except Exception:
                        local_sec = 0.0
                coarse_frame = max(0, int(round(local_sec * fps)))
                owns_cap = verify_cap is None
                local_cap = verify_cap if verify_cap is not None else cv2.VideoCapture(str(scan_filepath))
                if local_cap is None:
                    return None
                if not local_cap.isOpened():
                    if owns_cap:
                        try:
                            local_cap.release()
                        except Exception:
                            pass
                    return None
                try:
                    if follower_backend == "mps":
                        verified = _auto_grid_v3_manual_verify_strict_mps(
                            local_cap,
                            cv2,
                            fps=fps,
                            frame_count=frame_count,
                            coarse_frame=coarse_frame,
                            settings=settings,
                            scan_profile=scan_profile,
                            sample_positions=sample_positions,
                        )
                    else:
                        verified = _auto_grid_v3_manual_verify_strict(
                            local_cap,
                            cv2,
                            fps=fps,
                            frame_count=frame_count,
                            coarse_frame=coarse_frame,
                            settings=settings,
                            scan_profile=scan_profile,
                            sample_positions=sample_positions,
                        )
                finally:
                    if owns_cap:
                        try:
                            local_cap.release()
                        except Exception:
                            pass
                if not verified or not verified.get("passed"):
                    if isinstance(verified, dict) and verified.get("rollback_relocated") and verified.get("provisional_frame") is not None:
                        provisional_frame = int(verified.get("provisional_frame") or coarse_frame)
                        provisional_local_sec = float(verified.get("provisional_sec", provisional_frame / fps) or (provisional_frame / fps))
                        timeline_sec = float(clip_offset or 0.0) + provisional_local_sec
                        timeline_frame = sec_to_frame(timeline_sec, fps)
                        hint = dict(row)
                        hint.update(
                            {
                                "schema": "cut_boundary.v1",
                                "id": f"cut_provisional_{timeline_frame:08d}",
                                "time": timeline_sec,
                                "timeline_sec": timeline_sec,
                                "frame": timeline_frame,
                                "timeline_frame": timeline_frame,
                                "fps": fps,
                                "frame_rate": fps,
                                "timeline_frame_rate": fps,
                                "clip_idx": int(clip_idx or 0),
                                "clip_local_sec": provisional_local_sec,
                                "source_path": original_filepath,
                                "visual_scan_source_path": str(scan_filepath),
                                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                                "cut_boundary_backend": backend_choice.backend,
                                "score": float(verified.get("provisional_score", hint.get("score", 0.0)) or 0.0),
                                "regions": int(verified.get("provisional_regions", hint.get("regions", 0)) or 0),
                                "reason": str(verified.get("reason") or "rollback_relocated_provisional"),
                                "detector": "rollback-largest-change-provisional",
                                "source": "visual_provisional",
                                "absolute": True,
                                "locked": False,
                                "status": "provisional",
                                "verified": False,
                                "rollback_relocated": True,
                                "provisional_mode": str(verified.get("provisional_mode") or ""),
                                "provisional_stage": int(verified.get("provisional_stage", 0) or 0),
                                "line_color": "gray",
                                "line_style": "dotted",
                            }
                        )
                        return {"provisional": hint}
                    return None
                refined_local_sec = float(verified.get("sec", local_sec) or local_sec)
                timeline_sec = float(clip_offset or 0.0) + refined_local_sec
                timeline_frame = sec_to_frame(timeline_sec, fps)
                fixed = dict(row)
                fixed.update(
                    {
                        "schema": "cut_boundary.v1",
                        "id": f"cut_{timeline_frame:08d}",
                        "time": timeline_sec,
                        "timeline_sec": timeline_sec,
                        "frame": timeline_frame,
                        "timeline_frame": timeline_frame,
                        "fps": fps,
                        "frame_rate": fps,
                        "timeline_frame_rate": fps,
                        "clip_idx": int(clip_idx or 0),
                        "clip_local_sec": refined_local_sec,
                        "source_path": original_filepath,
                        "visual_scan_source_path": str(scan_filepath),
                        "visual_scan_proxy": bool(scan_filepath != original_filepath),
                        "cut_boundary_backend": backend_choice.backend,
                        "score": float(verified.get("score", fixed.get("score", 0.0)) or 0.0),
                        "regions": int(verified.get("regions", fixed.get("regions", 0)) or 0),
                        "color_score": float(verified.get("color_score", 0.0) or 0.0),
                        "color_regions": int(verified.get("color_regions", 0) or 0),
                        "grid_cells": int(verified.get("grid_cells", 0) or 0),
                        "reason": str(verified.get("reason") or "strict_color_avg"),
                        "detector": "mps-gray-grid-v3-strict-color-avg" if follower_backend == "mps" else "opencv-gray-grid-v3-strict-color-avg",
                        "source": "visual",
                        "absolute": True,
                        "locked": True,
                        "status": "verified",
                        "verified": True,
                        "verify_backend": follower_backend,
                    }
                )
                return {"verified": fixed}

            def _apply_verify_result(result):
                fixed = None
                provisional_hint = None
                if isinstance(result, dict) and result.get("verified"):
                    fixed = result.get("verified")
                elif isinstance(result, dict) and result.get("provisional"):
                    provisional_hint = result.get("provisional")
                elif isinstance(result, dict):
                    fixed = result
                if provisional_hint is not None:
                    if callable(provisional_callback):
                        try:
                            provisional_callback(dict(provisional_hint), list(verified_rows))
                        except Exception:
                            pass
                    return
                if fixed is None:
                    return
                duplicate = False
                for old in verified_rows:
                    try:
                        if abs(int(old.get("timeline_frame", -999999)) - int(fixed.get("timeline_frame", -999998))) <= min_gap_frames:
                            duplicate = True
                            break
                    except Exception:
                        pass
                if duplicate:
                    return
                verified_rows.append(fixed)
                verified_rows[:] = normalize_cut_boundaries(verified_rows, primary_fps=fps)
                if callable(found_callback):
                    try:
                        found_callback(dict(fixed), list(verified_rows))
                    except Exception:
                        pass

            verify_rows = [dict(row) for row in list(provisional_rows or []) if isinstance(row, dict)]
            # BENCH LOCK 2026-05-09 (Apple M5, X5_시승기_후반.MP4 4K HEVC):
            # Verifying fixed candidates in 4 outer chunks won the measured
            # matrix: 1/4 = 36.579s vs 1/3 = 41.464s, 1/2 = 43.892s,
            # sequential = 58.466s, and 1/6+ regressed wall time/RSS.
            outer_splits = min(
                follower_workers,
                follower_workload,
                _benchmark_locked_slice_count(settings, "scan_cut_follower_outer_splits", 4),
            )
            batches = balanced_task_slices(len(verify_rows), outer_splits, min_batch_size=1)

            def _verify_batch(start_idx: int, end_idx: int):
                local_results = []
                verify_cap = cv2.VideoCapture(str(scan_filepath))
                try:
                    if not verify_cap.isOpened():
                        return [None for _ in verify_rows[start_idx:end_idx]]
                    for row in verify_rows[start_idx:end_idx]:
                        try:
                            local_results.append(_verify_row(row, verify_cap=verify_cap))
                        except Exception:
                            local_results.append(None)
                    return local_results
                finally:
                    try:
                        verify_cap.release()
                    except Exception:
                        pass

            with ThreadPoolExecutor(max_workers=max(1, len(batches)), thread_name_prefix="cut-boundary-follower") as executor:
                future_map = {
                    executor.submit(_verify_batch, start_idx, end_idx): (start_idx, end_idx)
                    for start_idx, end_idx in batches
                }
                for future in as_completed(future_map):
                    try:
                        batch_results = list(future.result() or [])
                    except Exception:
                        batch_results = []
                    for result in batch_results:
                        _apply_verify_result(result)
            return normalize_cut_boundaries(verified_rows, primary_fps=fps)
        finally:
            try:
                cap.release()
            except Exception:
                pass

    return {
        "detect_media_cut_boundaries": detect_media_cut_boundaries,
        "scan_media_cut_boundary_provisionals": scan_media_cut_boundary_provisionals,
        "verify_media_cut_boundary_rows": verify_media_cut_boundary_rows,
        "_auto_grid_v3_original_detect_media_cut_boundaries": _auto_grid_v3_original_detect_media_cut_boundaries,
    }
