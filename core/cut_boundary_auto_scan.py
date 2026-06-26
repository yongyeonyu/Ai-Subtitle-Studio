# Version: 03.14.29
# Phase: PHASE2
"""Pioneer/follower scan functions for auto cut-boundary detection."""

from __future__ import annotations

import math
import subprocess
import sys
import time
from fractions import Fraction

from core.cut_boundary_audio import detect_audio_gain_boundary_rows
from core.cut_boundary_candidate_fusion import fuse_cut_boundary_candidate_rows
from core.cut_boundary_ffmpeg_scene import detect_ffmpeg_scene_boundaries
from core.cut_boundary_scan_runtime import (
    _setting_bool,
    _setting_float,
    _setting_int,
    benchmark_locked_slice_count as _benchmark_locked_slice_count,
    configure_cut_boundary_cv2_threads,
    cut_boundary_cv2_capture_backend,
    cut_boundary_memory_pressure_stage as _runtime_cut_boundary_memory_pressure_stage,
    cut_boundary_pioneer_worker_ranges as _cut_boundary_pioneer_worker_ranges,
    cut_boundary_pressure_worker_cap,
    cut_follower_verify_backend,
    high_cost_visual_scan_skip_meta,
    open_cut_boundary_video_capture,
)
from core.performance import balanced_task_slices, current_resource_snapshot
from core.runtime.multi_process import runtime_parallel_worker_plan
from core.cut_boundary_backend_router import apply_cut_boundary_backend_settings, select_cut_boundary_backend
from core.platform_compat import ffmpeg_binary, ffprobe_binary, hidden_subprocess_kwargs
from core.visual_cut_jump import build_visual_cut_sample, score_visual_cut_pair


def resolve_pioneer_pipe_fps(settings: dict | None, *, source_fps: float, fallback_fps: float) -> float:
    data = dict(settings or {})
    try:
        source_fps = float(source_fps or 0.0)
    except Exception:
        source_fps = 0.0
    try:
        fallback_fps = float(fallback_fps or 0.0)
    except Exception:
        fallback_fps = 0.0
    if _setting_bool(data.get("scan_cut_pioneer_pipe_source_fps_enabled"), False) and source_fps > 0.0:
        max_fps = _setting_float(data.get("scan_cut_pioneer_pipe_source_max_fps"), 30.0)
        return max(0.2, min(max(1.0, float(max_fps or 30.0)), source_fps))
    return max(0.2, min(4.0, fallback_fps))


def source_fps_parts(fps: float) -> tuple[int, int]:
    try:
        ratio = Fraction(float(fps)).limit_denominator(100000)
        if ratio.numerator > 0 and ratio.denominator > 0:
            return int(ratio.numerator), int(ratio.denominator)
    except Exception:
        pass
    return 0, 0


def precise_cut_boundary_timing(local_sec: float, clip_offset: float, fps: float, sec_to_frame_fn) -> dict:
    try:
        local_raw = max(0.0, float(local_sec or 0.0))
    except Exception:
        local_raw = 0.0
    try:
        offset_raw = float(clip_offset or 0.0)
    except Exception:
        offset_raw = 0.0
    timeline_raw = max(0.0, offset_raw + local_raw)
    timeline_frame = int(sec_to_frame_fn(timeline_raw, fps))
    canonical_timeline_sec = max(0.0, timeline_frame / float(fps or 30.0))
    return {
        "clip_local_sec": max(0.0, canonical_timeline_sec - offset_raw),
        "timeline_sec": canonical_timeline_sec,
        "timeline_frame": timeline_frame,
    }


def _trace_cut_boundary_rows(rows: list[dict], *, backend_label: str, fps: float) -> None:
    try:
        from core.runtime.trace_logger import current_app_trace_logger

        logger = current_app_trace_logger()
        if logger is None:
            return
        fps_num, fps_den = source_fps_parts(float(fps or 0.0))
        if len(rows) <= 40:
            sampled_rows = list(rows)
        else:
            sampled_rows = [*rows[:20], *rows[-20:]]
        seen_trace_keys = set()
        for row in sampled_rows:
            if not isinstance(row, dict):
                continue
            trace_key = (
                int(row.get("timeline_frame", row.get("frame", 0)) or 0),
                str(row.get("detector", "") or ""),
                str(row.get("reason", "") or ""),
            )
            if trace_key in seen_trace_keys:
                continue
            seen_trace_keys.add(trace_key)
            logger.log_event(
                "cut_boundary_candidate_scored",
                stage="cut-boundary",
                level="DEBUG",
                backend=backend_label,
                frame=int(row.get("timeline_frame", row.get("frame", 0)) or 0),
                time_sec=float(row.get("timeline_sec", row.get("time", 0.0)) or 0.0),
                fps=float(row.get("fps", fps) or fps),
                fps_num=fps_num,
                fps_den=fps_den,
                score=float(row.get("score", 0.0) or 0.0),
                region_hits=int(row.get("region_hits", row.get("regions", 0)) or 0),
                pixel_ratio=float(row.get("pixel_ratio", 0.0) or 0.0),
                motion_jump=float(row.get("motion_jump", 0.0) or 0.0),
                flow_residual=float(row.get("flow_residual", 0.0) or 0.0),
                flow_mag=float(row.get("flow_mag", row.get("flow_mean", 0.0)) or 0.0),
                detector=str(row.get("detector", "") or ""),
                reason=str(row.get("reason", "") or ""),
                source=str(row.get("source", "") or ""),
            )
    except Exception:
        pass


def cut_boundary_memory_pressure_stage(settings: dict | None = None) -> str:
    """Compatibility wrapper that preserves the historical test patch hook."""
    return _runtime_cut_boundary_memory_pressure_stage(settings, snapshot_fn=current_resource_snapshot)


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
        cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
                    verify_cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
                fps_num, fps_den = source_fps_parts(fps)

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
                        "source_fps": fps,
                        "source_fps_num": fps_num,
                        "source_fps_den": fps_den,
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
        cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
        try:
            min_gap_sec = float(settings.get("scan_cut_pioneer_min_gap_sec", _cb_level_min_gap_sec(level)) or _cb_level_min_gap_sec(level))
        except Exception:
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

        packet_bucket_sec = max(
            0.10,
            min(1.0, _settings_float("scan_cut_pioneer_packet_bucket_sec", 0.25)),
        )

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
        audio_spectral_flux_enabled = _setting_bool(settings.get("scan_cut_audio_spectral_flux_enabled"), True)
        audio_spectral_flux_window_sec = max(
            0.10,
            _settings_float("scan_cut_audio_spectral_flux_window_sec", 0.50),
        )
        audio_spectral_flux_multiplier = max(
            1.0,
            _settings_float("scan_cut_audio_spectral_flux_threshold_multiplier", 3.0),
        )
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
                    spectral_flux_enabled=audio_spectral_flux_enabled,
                    spectral_flux_window_sec=audio_spectral_flux_window_sec,
                    spectral_flux_threshold_multiplier=audio_spectral_flux_multiplier,
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

        def _scan_pioneer_pipe_rows():
            if not _setting_bool(settings.get("scan_cut_pioneer_pipe_enabled"), True):
                return None
            try:
                import cv2
                import numpy as np
            except Exception:
                return None

            width = max(64, min(960, _settings_int("scan_cut_pioneer_pipe_width", 320)))
            height = max(36, min(540, _settings_int("scan_cut_pioneer_pipe_height", 180)))
            pipe_fps = resolve_pioneer_pipe_fps(
                settings,
                source_fps=fps,
                fallback_fps=_settings_float("scan_cut_pioneer_pipe_fps", 1.0 / max(0.25, scan_interval_sec)),
            )
            pipe_step_sec = 1.0 / pipe_fps if pipe_fps > 0.0 else max(1.0, scan_interval_sec)
            score_threshold = max(8.0, _settings_float("scan_cut_pioneer_pipe_score_threshold", 40.0))
            region_threshold = max(4.0, _settings_float("scan_cut_pioneer_pipe_region_threshold", 18.0))
            regions_required = max(1, _settings_int("scan_cut_pioneer_pipe_regions_required", 2))
            pixel_ratio_threshold = max(0.04, _settings_float("scan_cut_pioneer_pipe_pixel_ratio_threshold", 0.18))
            motion_threshold = max(1.0, _settings_float("scan_cut_pioneer_pipe_motion_threshold", 6.0))
            timeout_sec = max(5.0, _settings_float("scan_cut_pioneer_pipe_timeout_sec", max(30.0, duration * 0.08)))
            max_candidates = max(1, _settings_int("scan_cut_pioneer_pipe_max_candidates", 360))
            min_gap = max(0.5, float(min_gap_sec or 1.0))

            scale_filter = f"fps={pipe_fps:.6f},scale={width}:{height}:flags=fast_bilinear,format=gray"
            cmd = [
                ffmpeg_binary(),
                "-hide_banner",
                "-nostdin",
                "-v",
                "error",
            ]
            if sys.platform == "darwin" and _setting_bool(settings.get("scan_cut_pioneer_pipe_hwaccel_enabled"), True):
                cmd.extend(["-hwaccel", "videotoolbox"])
            cmd.extend([
                "-threads",
                "1",
                "-i",
                str(scan_filepath),
                "-an",
                "-vf",
                scale_filter,
                "-pix_fmt",
                "gray",
                "-f",
                "rawvideo",
                "pipe:1",
            ])

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **hidden_subprocess_kwargs(strip_qt=True),
                )
            except Exception:
                return None

            frame_size = int(width * height)
            rows_local: list[dict] = []
            prev_gray = None
            prev_sample = None
            last_emit_t = -999999.0
            frame_idx = 0
            started = time.monotonic()
            try:
                while True:
                    if time.monotonic() - started > timeout_sec:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        break
                    if proc.stdout is None:
                        break
                    chunk = proc.stdout.read(frame_size)
                    if not chunk or len(chunk) < frame_size:
                        break
                    gray = np.frombuffer(chunk, dtype=np.uint8).reshape((height, width))
                    t = frame_idx * pipe_step_sec
                    frame_idx += 1
                    if prev_gray is None:
                        prev_gray = gray.copy()
                        prev_sample = build_visual_cut_sample(prev_gray, cv2, mode="fast4", width=width, settings=settings)
                        continue

                    gray_sample = build_visual_cut_sample(gray, cv2, mode="fast4", width=width, settings=settings)
                    metrics = score_visual_cut_pair(
                        prev_sample,
                        gray_sample,
                        cv2,
                        settings=settings,
                        region_threshold=region_threshold,
                    )
                    score = float(metrics.get("score", 0.0) or 0.0)
                    region_hits = int(metrics.get("region_hits", 0) or 0)
                    pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
                    edge_ratio = float(metrics.get("edge_ratio", 0.0) or 0.0)
                    motion_jump = float(metrics.get("motion_jump", 0.0) or 0.0)
                    flow_residual = float(metrics.get("flow_residual", 0.0) or 0.0)
                    flow_mag = float(metrics.get("flow_mean", 0.0) or 0.0)
                    strong_visual_cut = (
                        score >= score_threshold
                        and region_hits >= regions_required
                        and (pixel_ratio >= pixel_ratio_threshold or motion_jump >= motion_threshold)
                    )
                    if strong_visual_cut and (t - last_emit_t) >= min_gap:
                        timing = precise_cut_boundary_timing(float(t), float(clip_offset or 0.0), fps, sec_to_frame)
                        timeline_sec = timing["timeline_sec"]
                        timeline_frame = timing["timeline_frame"]
                        clip_local_sec = timing["clip_local_sec"]
                        fps_num, fps_den = source_fps_parts(fps)
                        row = {
                            "schema": "cut_boundary.v1",
                            "id": f"pipe_cut_{int(clip_idx or 0):02d}_{timeline_frame:08d}",
                            "time": timeline_sec,
                            "timeline_sec": timeline_sec,
                            "clip_idx": int(clip_idx or 0),
                            "clip_local_sec": clip_local_sec,
                            "coarse_time": round(float(t), 3),
                            "frame": timeline_frame,
                            "timeline_frame": timeline_frame,
                            "fps": fps,
                            "frame_rate": fps,
                            "timeline_frame_rate": fps,
                            "source_fps": fps,
                            "source_fps_num": fps_num,
                            "source_fps_den": fps_den,
                            "pipe_fps": pipe_fps,
                            "source": "visual_provisional",
                            "detector": "ffmpeg-pipe-visual-cut-jump-v2",
                            "reason": "gray_pixel_edge_flow_scout",
                            "score": round(float(score), 3),
                            "pixel_ratio": round(pixel_ratio, 6),
                            "edge_ratio": round(edge_ratio, 6),
                            "region_hits": int(region_hits),
                            "motion_jump": round(motion_jump, 3),
                            "flow_residual": round(flow_residual, 3),
                            "flow_mag": round(flow_mag, 3),
                            "scan_interval_sec": round(pipe_step_sec, 3),
                            "min_gap_sec": min_gap,
                            "refine_pending": True,
                            "refine_backend": "strict_visual_verify",
                            "source_path": original_filepath,
                            "visual_scan_source_path": str(scan_filepath),
                            "visual_scan_proxy": bool(scan_filepath != original_filepath),
                            "cut_boundary_backend": "ffmpeg_pipe_pixel_flow",
                        }
                        rows_local.append(row)
                        last_emit_t = float(t)
                        if callable(found_callback):
                            try:
                                found_callback(dict(row), list(rows_local))
                            except Exception:
                                pass
                        if len(rows_local) >= max_candidates:
                            break

                    prev_gray = gray.copy()
                    prev_sample = gray_sample
                    if callable(progress_callback) and (frame_idx <= 2 or frame_idx % max(1, int(round(pipe_fps * 8))) == 0):
                        try:
                            progress_callback({
                                "clip_idx": clip_idx,
                                "percent": int(min(100, (t / max(1.0, duration)) * 100)),
                                "worker_percent": int(min(100, (t / max(1.0, duration)) * 100)),
                                "timestamp": t,
                                "duration": duration,
                                "detected": len(rows_local),
                                "worker_idx": 0,
                                "worker_total": 1,
                                "cut_boundary_backend": "ffmpeg_pipe_pixel_flow",
                            })
                        except Exception:
                            pass
                try:
                    if proc.stdout is not None:
                        proc.stdout.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                if frame_idx <= 1:
                    return None
                if callable(progress_callback):
                    try:
                        progress_callback({
                            "clip_idx": clip_idx,
                            "percent": 100,
                            "worker_percent": 100,
                            "timestamp": duration,
                            "duration": duration,
                            "detected": len(rows_local),
                            "worker_idx": 0,
                            "worker_total": 1,
                            "cut_boundary_backend": "ffmpeg_pipe_pixel_flow",
                        })
                    except Exception:
                        pass
                return rows_local
            finally:
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
                try:
                    if proc.stderr is not None:
                        proc.stderr.close()
                except Exception:
                    pass

        def _pixel_flow_confirm_row(
            local_sec: float,
            *,
            packet_score: float = 0.0,
            packet_delta: float = 0.0,
            cap_local=None,
        ):
            try:
                import cv2
            except Exception:
                return None
            own_capture = cap_local is None
            if own_capture:
                cap_local = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
            if cap_local is None or not cap_local.isOpened():
                try:
                    if cap_local is not None:
                        cap_local.release()
                except Exception:
                    pass
                return None
            try:
                width = max(64, min(960, _settings_int("scan_cut_pioneer_pipe_width", 320)))
                height = max(36, min(540, _settings_int("scan_cut_pioneer_pipe_height", 180)))
                region_threshold = max(4.0, _settings_float("scan_cut_pioneer_pipe_region_threshold", 18.0))
                score_threshold = max(8.0, _settings_float("scan_cut_pioneer_pipe_score_threshold", 40.0))
                pixel_ratio_threshold = max(0.04, _settings_float("scan_cut_pioneer_pipe_pixel_ratio_threshold", 0.18))
                motion_threshold = max(1.0, _settings_float("scan_cut_pioneer_pipe_motion_threshold", 6.0))
                before_sec = max(0.0, float(local_sec) - 0.50)
                after_sec = min(duration, float(local_sec) + 0.50)

                def _read_gray(sec_value: float):
                    try:
                        cap_local.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(round(sec_value * fps))))
                        ok, frame = cap_local.read()
                    except Exception:
                        return None
                    if not ok or frame is None:
                        return None
                    try:
                        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    except Exception:
                        return None

                prev_gray = _read_gray(before_sec)
                gray = _read_gray(after_sec)
                if prev_gray is None or gray is None:
                    return None
                prev_sample = build_visual_cut_sample(
                    prev_gray,
                    cv2,
                    mode="full9",
                    width=min(960, width * 3),
                    settings=settings,
                )
                next_sample = build_visual_cut_sample(
                    gray,
                    cv2,
                    mode="full9",
                    width=min(960, width * 3),
                    settings=settings,
                )
                metrics = score_visual_cut_pair(
                    prev_sample,
                    next_sample,
                    cv2,
                    settings=settings,
                    region_threshold=region_threshold,
                )
                score = float(metrics.get("score", 0.0) or 0.0)
                pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
                edge_ratio = float(metrics.get("edge_ratio", 0.0) or 0.0)
                region_hits = int(metrics.get("region_hits", 0) or 0)
                motion_jump = float(metrics.get("motion_jump", 0.0) or 0.0)
                flow_residual = float(metrics.get("flow_residual", 0.0) or 0.0)
                flow_mag = float(metrics.get("flow_mean", 0.0) or 0.0)
                if not (
                    score >= score_threshold
                    and region_hits >= 1
                    and (pixel_ratio >= pixel_ratio_threshold or motion_jump >= motion_threshold)
                ):
                    return None
                verified = None
                try:
                    verified = _auto_grid_v3_manual_verify_strict(
                        cap_local,
                        cv2,
                        fps=fps,
                        frame_count=frame_count,
                        coarse_frame=max(0, int(round(float(local_sec) * fps))),
                        settings=settings,
                        scan_profile=scan_profile,
                        sample_positions=sample_positions,
                    )
                except Exception:
                    verified = None

                verified_passed = bool(isinstance(verified, dict) and verified.get("passed"))
                refined_local_sec = float((verified or {}).get("sec", local_sec) if verified_passed else local_sec)
                timing = precise_cut_boundary_timing(refined_local_sec, float(clip_offset or 0.0), fps, sec_to_frame)
                timeline_sec = timing["timeline_sec"]
                timeline_frame = timing["timeline_frame"]
                refined_local_sec = timing["clip_local_sec"]
                fps_num, fps_den = source_fps_parts(fps)
                score = max(
                    score,
                    float(packet_score or 0.0),
                    float((verified or {}).get("score", 0.0) if verified_passed else 0.0),
                )
                return {
                    "schema": "cut_boundary.v1",
                    "id": f"packet_cut_{int(clip_idx or 0):02d}_{timeline_frame:08d}",
                    "time": timeline_sec,
                    "timeline_sec": timeline_sec,
                    "clip_idx": int(clip_idx or 0),
                    "clip_local_sec": refined_local_sec,
                    "coarse_time": round(float(local_sec), 3),
                    "frame": timeline_frame,
                    "timeline_frame": timeline_frame,
                    "fps": fps,
                    "frame_rate": fps,
                    "timeline_frame_rate": fps,
                    "source_fps": fps,
                    "source_fps_num": fps_num,
                    "source_fps_den": fps_den,
                    "source": "visual_provisional",
                    "detector": "packet-energy-visual-cut-jump-v2",
                    "reason": str(
                        (verified or {}).get("reason", "packet_energy_gray_pixel_edge_flow_scout")
                        if verified_passed
                        else "packet_energy_gray_pixel_edge_flow_scout"
                    ),
                    "score": round(float(score), 3),
                    "packet_score": round(float(packet_score), 3),
                    "packet_delta": round(float(packet_delta), 3),
                    "pixel_ratio": round(pixel_ratio, 6),
                    "edge_ratio": round(edge_ratio, 6),
                    "region_hits": int((verified or {}).get("regions", region_hits) if verified_passed else region_hits),
                    "motion_jump": round(motion_jump, 3),
                    "flow_residual": round(flow_residual, 3),
                    "flow_mag": round(flow_mag, 3),
                    "color_score": round(float((verified or {}).get("color_score", 0.0) if verified_passed else 0.0), 3),
                    "color_regions": int((verified or {}).get("color_regions", 0) if verified_passed else 0),
                    "dense_flow": dict((verified or {}).get("dense_flow") or {}) if verified_passed else {},
                    "grid_cells": int((verified or {}).get("grid_cells", 0) if verified_passed else 0),
                    "scan_interval_sec": 1.0,
                    "min_gap_sec": float(min_gap_sec or 1.0),
                    "refine_pending": True,
                    "refine_backend": "strict_visual_verify",
                    "source_path": original_filepath,
                    "visual_scan_source_path": str(scan_filepath),
                    "visual_scan_proxy": bool(scan_filepath != original_filepath),
                    "cut_boundary_backend": "packet_energy_pixel_flow",
                }
            finally:
                try:
                    if own_capture and cap_local is not None:
                        cap_local.release()
                except Exception:
                    pass

        def _scan_packet_energy_rows():
            if not _setting_bool(settings.get("scan_cut_pioneer_packet_scout_enabled"), True):
                return None
            try:
                import numpy as np
            except Exception:
                return None
            timeout_sec = max(5.0, _settings_float("scan_cut_pioneer_packet_scout_timeout_sec", max(20.0, duration * 0.03)))
            max_raw_candidates = max(20, _settings_int("scan_cut_pioneer_packet_scout_raw_candidates", 180))
            max_candidates = max(1, _settings_int("scan_cut_pioneer_pipe_max_candidates", 360))
            cmd = [
                ffprobe_binary(),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "packet=pts_time,size,flags",
                "-of",
                "csv=p=0",
                str(scan_filepath),
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_sec,
                    **hidden_subprocess_kwargs(strip_qt=True),
                )
            except Exception:
                return None
            lines = str(proc.stdout or "").splitlines()
            if not lines:
                return None
            bucket_span_sec = max(0.10, float(packet_bucket_sec or 0.25))
            bucket_count = max(1, int(math.ceil(duration / bucket_span_sec)) + 2)
            energy = np.zeros(bucket_count, dtype=np.float32)
            keyframes = np.zeros(bucket_count, dtype=np.float32)
            for line in lines:
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 2:
                    continue
                try:
                    sec = float(parts[0])
                    size = float(parts[1])
                except Exception:
                    continue
                idx = int(max(0, min(bucket_count - 1, round(sec / bucket_span_sec))))
                energy[idx] += size
                if len(parts) >= 3 and "K" in parts[2]:
                    keyframes[idx] += 1.0
            if float(np.max(energy)) <= 0.0:
                return None
            log_energy = np.log1p(energy)
            prev = np.roll(log_energy, 1)
            prev[0] = log_energy[0]
            delta = np.abs(log_energy - prev)
            nonzero = delta[delta > 0.0]
            if nonzero.size <= 0:
                return []
            median = float(np.median(nonzero))
            mad = float(np.median(np.abs(nonzero - median))) or 0.001
            adaptive_threshold = max(
                _settings_float("scan_cut_pioneer_packet_delta_threshold", 1.4),
                median + (mad * _settings_float("scan_cut_pioneer_packet_mad_multiplier", 3.0)),
            )
            scored = []
            max_bucket_idx = min(bucket_count - 1, int(math.ceil(duration / bucket_span_sec)) + 1)
            for idx in range(1, max_bucket_idx):
                score = float(delta[idx]) + (0.18 if keyframes[idx] > 0 else 0.0)
                if score < adaptive_threshold:
                    continue
                if score < float(delta[idx - 1]) or score < float(delta[idx + 1]):
                    continue
                scored.append((score, float(delta[idx]), float(idx) * bucket_span_sec))
            scored.sort(key=lambda item: item[0], reverse=True)
            selected = sorted(scored[:max_raw_candidates], key=lambda item: item[2])
            rows_local = []
            last_sec = -999999.0
            min_gap = max(
                0.10,
                float(_settings_float("scan_cut_pioneer_packet_min_gap_sec", min_gap_sec or 0.20)),
            )
            cap_local = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
            if cap_local is not None and not cap_local.isOpened():
                try:
                    cap_local.release()
                except Exception:
                    pass
                cap_local = None
            try:
                for score, packet_delta, sec in selected:
                    if sec - last_sec < min_gap:
                        continue
                    row = _pixel_flow_confirm_row(
                        sec,
                        packet_score=score,
                        packet_delta=packet_delta,
                        cap_local=cap_local,
                    )
                    if not row:
                        continue
                    rows_local.append(row)
                    candidate_sec = float(row.get("clip_local_sec", sec) or sec)
                    last_sec = candidate_sec
                    if callable(found_callback):
                        try:
                            found_callback(dict(row), list(rows_local))
                        except Exception:
                            pass
                    if callable(progress_callback):
                        try:
                            progress_callback({
                                "clip_idx": clip_idx,
                                "percent": int(min(100, (candidate_sec / max(1.0, duration)) * 100)),
                                "worker_percent": int(min(100, (candidate_sec / max(1.0, duration)) * 100)),
                                "timestamp": candidate_sec,
                                "duration": duration,
                                "detected": len(rows_local),
                                "worker_idx": 0,
                                "worker_total": 1,
                                "cut_boundary_backend": "packet_energy_pixel_flow",
                            })
                        except Exception:
                            pass
                    if len(rows_local) >= max_candidates:
                        break
                return rows_local
            finally:
                try:
                    if cap_local is not None:
                        cap_local.release()
                except Exception:
                    pass

        def _emit_provisional_rows(rows):
            if not callable(found_callback):
                return
            current_rows = list(rows or [])
            for row in current_rows:
                try:
                    found_callback(dict(row), current_rows)
                except Exception:
                    pass

        def _fuse_pioneer_rows(rows, *, backend_label: str):
            raw_rows = list(rows or [])
            if not raw_rows:
                return []
            fps_num, fps_den = source_fps_parts(fps)
            if not _setting_bool(settings.get("scan_cut_pioneer_candidate_fusion_enabled"), True):
                normalized_rows = normalize_cut_boundaries(raw_rows, primary_fps=fps)
                for row in normalized_rows:
                    row.setdefault("source_fps", fps)
                    row.setdefault("source_fps_num", fps_num)
                    row.setdefault("source_fps_den", fps_den)
                _trace_cut_boundary_rows(normalized_rows, backend_label=backend_label, fps=fps)
                return normalized_rows
            fused_rows = fuse_cut_boundary_candidate_rows(
                raw_rows,
                fps=fps,
                window_sec=max(
                    0.02,
                    _settings_float(
                        "scan_cut_pioneer_fusion_window_sec",
                        _settings_float("cut_boundary_fusion_window_sec", 0.35),
                    ),
                ),
                keep_threshold=max(0.0, min(1.0, _settings_float("cut_boundary_fusion_keep_threshold", 0.68))),
                verify_threshold=max(0.0, min(1.0, _settings_float("cut_boundary_fusion_verify_threshold", 0.43))),
                max_candidates=_settings_int("scan_cut_pioneer_fusion_max_candidates", len(raw_rows) or 1),
            )
            for row in fused_rows:
                try:
                    row.setdefault("cut_boundary_backend", backend_label)
                    row.setdefault("visual_scan_source_path", str(scan_filepath))
                    row.setdefault("visual_scan_proxy", bool(scan_filepath != original_filepath))
                    row.setdefault("source_fps", fps)
                    row.setdefault("source_fps_num", fps_num)
                    row.setdefault("source_fps_den", fps_den)
                except Exception:
                    pass
            normalized_rows = normalize_cut_boundaries(fused_rows, primary_fps=fps)
            _trace_cut_boundary_rows(normalized_rows, backend_label=backend_label, fps=fps)
            return normalized_rows

        if ffmpeg_scene_enabled and ffmpeg_scene_replace_opencv:
            scene_rows = list(_scan_ffmpeg_scene_rows() or [])
            if scene_rows:
                audio_rows = list(_scan_audio_gain_rows() or [])
                _emit_provisional_rows(scene_rows)
                _emit_provisional_rows(audio_rows)
                combined_rows = [*scene_rows, *audio_rows]
                normalized = _fuse_pioneer_rows(combined_rows, backend_label="ffmpeg_scene_prepass")
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

        if _setting_bool(settings.get("scan_cut_pioneer_packet_scout_enabled"), True):
            packet_rows = None
            audio_rows = []
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cut-boundary-packet-scout") as executor:
                packet_future = executor.submit(_scan_packet_energy_rows)
                audio_future = executor.submit(_scan_audio_gain_rows) if audio_gain_enabled else None
                try:
                    packet_rows = packet_future.result()
                except Exception:
                    packet_rows = None
                if audio_future is not None:
                    try:
                        audio_rows = list(audio_future.result() or [])
                    except Exception:
                        audio_rows = []
            if packet_rows is not None:
                _emit_provisional_rows(audio_rows)
                combined_rows = [*list(packet_rows or []), *list(audio_rows or [])]
                normalized = _fuse_pioneer_rows(combined_rows, backend_label="packet_energy_pixel_flow")
                if callable(completion_callback):
                    try:
                        completion_callback(
                            {
                                "clip_idx": int(clip_idx or 0),
                                "worker_total": 1 + (1 if audio_gain_enabled else 0),
                                "worker_completed": 1 + (1 if audio_gain_enabled else 0),
                                "duration": float(duration or 0.0),
                                "detected": len(normalized),
                                "done": True,
                                "scheduler": "packet_energy_pixel_flow",
                                "visual_scan_source_path": str(scan_filepath),
                                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                                "cut_boundary_backend": "packet_energy_pixel_flow",
                            }
                        )
                    except Exception:
                        pass
                return normalized

        if _setting_bool(settings.get("scan_cut_pioneer_pipe_enabled"), False):
            pipe_rows = None
            audio_rows = []
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cut-boundary-pipe-scout") as executor:
                pipe_future = executor.submit(_scan_pioneer_pipe_rows)
                audio_future = executor.submit(_scan_audio_gain_rows) if audio_gain_enabled else None
                try:
                    pipe_rows = pipe_future.result()
                except Exception:
                    pipe_rows = None
                if audio_future is not None:
                    try:
                        audio_rows = list(audio_future.result() or [])
                    except Exception:
                        audio_rows = []
            if pipe_rows is not None:
                _emit_provisional_rows(audio_rows)
                combined_rows = [*list(pipe_rows or []), *list(audio_rows or [])]
                normalized = _fuse_pioneer_rows(combined_rows, backend_label="ffmpeg_pipe_pixel_flow")
                if callable(completion_callback):
                    try:
                        completion_callback(
                            {
                                "clip_idx": int(clip_idx or 0),
                                "worker_total": 1 + (1 if audio_gain_enabled else 0),
                                "worker_completed": 1 + (1 if audio_gain_enabled else 0),
                                "duration": float(duration or 0.0),
                                "detected": len(normalized),
                                "done": True,
                                "scheduler": "ffmpeg_pipe_pixel_flow",
                                "visual_scan_source_path": str(scan_filepath),
                                "visual_scan_proxy": bool(scan_filepath != original_filepath),
                                "cut_boundary_backend": "ffmpeg_pipe_pixel_flow",
                            }
                        )
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
            normalized = _fuse_pioneer_rows(combined_skip_rows, backend_label=backend_choice.backend)
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
            worker_cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
                        flow_residual = 0.0
                        flow_mag = 0.0
                        if (
                            delta >= effective_threshold * 0.80
                            and _setting_bool(settings.get("scan_cut_pioneer_dense_flow_confirm_enabled"), True)
                        ):
                            try:
                                import numpy as np

                                h, w = gray.shape[:2]
                                flow_width = max(64, min(w, _settings_int("scan_cut_pioneer_pipe_flow_width", 160)))
                                flow_h = max(36, int(round(h * (flow_width / float(max(1, w))))))
                                prev_small = cv2.resize(prev_gray, (flow_width, flow_h), interpolation=cv2.INTER_AREA)
                                gray_small = cv2.resize(gray, (flow_width, flow_h), interpolation=cv2.INTER_AREA)
                                flow = cv2.calcOpticalFlowFarneback(prev_small, gray_small, None, 0.5, 1, 15, 1, 5, 1.1, 0)
                                yy, xx = np.mgrid[0:flow_h, 0:flow_width].astype(np.float32)
                                warped = cv2.remap(
                                    prev_small,
                                    xx + flow[..., 0],
                                    yy + flow[..., 1],
                                    cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REPLICATE,
                                )
                                flow_residual = float(np.mean(cv2.absdiff(gray_small, warped)))
                                flow_mag = float(np.mean(np.sqrt(flow[..., 0] * flow[..., 0] + flow[..., 1] * flow[..., 1])))
                            except Exception:
                                flow_residual = 0.0
                                flow_mag = 0.0
                        flow_ok = (
                            flow_residual >= _settings_float("scan_cut_pioneer_pipe_flow_residual_threshold", 10.0)
                            or delta >= effective_threshold * 1.25
                            or not _setting_bool(settings.get("scan_cut_pioneer_dense_flow_confirm_enabled"), True)
                        )
                        if delta >= effective_threshold and strong_cells >= required_cells and flow_ok and (t - last_emit_t) >= min_gap_sec:
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
                                "flow_residual": round(flow_residual, 3),
                                "flow_mag": round(flow_mag, 3),
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
            normalized = _fuse_pioneer_rows([*(rows or []), *scene_rows, *audio_rows], backend_label=backend_choice.backend)
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
                    if row.get("source") not in {"audio_gain_provisional", "audio_spectral_flux_provisional"}:
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
        return _fuse_pioneer_rows(combined_rows or [], backend_label=backend_choice.backend)


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
        checked_callback = kwargs.pop("checked_callback", None)
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
        cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
        if not cap.isOpened() and scan_filepath != original_filepath:
            try:
                cap.release()
            except Exception:
                pass
            scan_filepath = original_filepath
            cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
                local_cap = verify_cap if verify_cap is not None else open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
                    if isinstance(verified, dict) and bool(verified.get("same_scene_color_similarity")):
                        checked = dict(row)
                        checked["same_scene_color_similarity"] = True
                        checked["middle_merge_preferred"] = True
                        if isinstance(verified.get("color_similarity"), dict):
                            checked["color_similarity"] = dict(verified.get("color_similarity") or {})
                        checked["reason"] = str(verified.get("reason") or "same_scene_color_similarity")
                        return {"checked": checked}
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
                fps_num, fps_den = source_fps_parts(fps)
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
                        "source_fps": fps,
                        "source_fps_num": fps_num,
                        "source_fps_den": fps_den,
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
                fixed["boundary_kind"] = "visual"
                fixed.pop("line_color", None)
                fixed.pop("line_style", None)
                fixed.pop("provisional_type", None)
                fixed.pop("ui_label", None)
                return {"verified": fixed}

            def _apply_verify_result(result):
                fixed = None
                provisional_hint = None
                checked_hint = None
                if isinstance(result, dict) and result.get("verified"):
                    fixed = result.get("verified")
                elif isinstance(result, dict) and result.get("checked"):
                    checked_hint = result.get("checked")
                elif isinstance(result, dict) and result.get("provisional"):
                    provisional_hint = result.get("provisional")
                elif isinstance(result, dict):
                    fixed = result
                if checked_hint is not None:
                    if callable(checked_callback):
                        try:
                            checked_callback(dict(checked_hint), list(verified_rows))
                        except Exception:
                            pass
                    return
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
                verify_cap = open_cut_boundary_video_capture(cv2, scan_filepath, settings)
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
