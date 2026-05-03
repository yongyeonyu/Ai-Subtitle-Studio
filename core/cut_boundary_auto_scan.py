# Version: 03.13.07
# Phase: PHASE2
"""Pioneer/follower scan functions for auto cut-boundary detection."""

from __future__ import annotations

import sys


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
        settings = dict(kwargs.get("settings") or {})
        try:
            from core.settings import load_settings
            loaded = dict(load_settings() or {})
            loaded.update(settings)
            settings = loaded
        except Exception:
            pass

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
                **kwargs,
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
                **kwargs,
            )

        cap = cv2.VideoCapture(str(filepath))
        if not cap.isOpened():
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
                **kwargs,
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
            follower_workers = max(1, min(4, int(settings.get("scan_cut_verify_workers", 4) or 4)))

            def verified_progress_callback(payload):
                if not callable(progress_callback):
                    return
                try:
                    fixed = dict(payload or {})
                    fixed["detected"] = len(verified_rows)
                    fixed["verified_detected"] = len(verified_rows)
                    fixed["provisional_detected"] = len(provisional_rows)
                    progress_callback(fixed)
                except Exception:
                    pass

            def row_raw_score(row):
                for key in ("score", "delta", "window_score"):
                    try:
                        value = row.get(key)
                        if value is not None:
                            return float(value)
                    except Exception:
                        pass
                return 0.0

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

                verify_cap = cv2.VideoCapture(str(filepath))
                if not verify_cap.isOpened():
                    return None
                try:
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
                finally:
                    try:
                        verify_cap.release()
                    except Exception:
                        pass

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
                        "source_path": str(filepath),
                        "score": float(verified.get("score", fixed.get("score", 0.0)) or 0.0),
                        "regions": int(verified.get("regions", fixed.get("regions", 0)) or 0),
                        "color_score": float(verified.get("color_score", 0.0) or 0.0),
                        "color_regions": int(verified.get("color_regions", 0) or 0),
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

                raw_rows = _auto_grid_v3_original_detect_media_cut_boundaries(
                    filepath,
                    clip_offset=clip_offset,
                    clip_idx=clip_idx,
                    sample_step_sec=pioneer_step_sec,
                    threshold=threshold,
                    progress_callback=verified_progress_callback,
                    found_callback=verified_found_callback,
                    scan_profile=scan_profile,
                    sample_positions=sample_positions,
                    sample_mask=sample_mask,
                    **kwargs,
                )

                if not saw_callback:
                    for row in raw_rows or []:
                        _submit_provisional(row)

                while future_map:
                    _drain_completed()

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
        settings = dict(kwargs.get("settings") or {})
        try:
            from core.settings import load_settings
            loaded = dict(load_settings() or {})
            loaded.update(settings)
            settings = loaded
        except Exception:
            pass

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
                **kwargs,
            )
            return normalize_cut_boundaries(rows or [])

        cap = cv2.VideoCapture(str(filepath))
        if not cap.isOpened():
            return []
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
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
        pioneer_workers = max(1, min(4, int(settings.get("scan_cut_pioneer_workers", 4) or 4)))
        pioneer_refine_workers = max(1, min(4, int(settings.get("scan_cut_pioneer_refine_workers", 4) or 4)))
        gpu_refine_enabled = bool(settings.get("scan_cut_pioneer_gpu_refine_enabled", True))
        cuda_available = _cb_cuda_available() if gpu_refine_enabled else False

        def _scan_range(worker_idx: int, start_frame: int, end_frame: int):
            worker_cap = cv2.VideoCapture(str(filepath))
            if not worker_cap.isOpened():
                return []
            rows_local = []
            prev_gray = None
            prev_t = max(0.0, float(start_frame) / fps)
            last_emit_t = -999999.0
            total_frames = max(1, end_frame - start_frame)
            try:
                frame_no = int(start_frame)
                while frame_no < end_frame:
                    worker_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                    ok, frame = worker_cap.read()
                    if not ok or frame is None:
                        frame_no += step_frames
                        continue
                    t = frame_no / fps
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if worker_idx == 0 and callable(progress_callback):
                        pass
                    if callable(progress_callback):
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
                            }
                            rows_local.append(row)
                            last_emit_t = coarse_sec
                            if callable(found_callback):
                                try:
                                    found_callback(dict(row), list(rows_local))
                                except Exception:
                                    pass
                    prev_gray = gray
                    prev_t = t
                    frame_no += step_frames
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
                    })
                except Exception:
                    pass
            return rows_local

        if pioneer_workers <= 1 or duration <= scan_interval_sec * 2.0:
            rows = _scan_range(0, 0, frame_count)
            normalized = normalize_cut_boundaries(rows or [], primary_fps=fps)
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
                        }
                    )
                except Exception:
                    pass
            return normalized

        shard_size = max(step_frames, int(frame_count / pioneer_workers))
        futures = []
        merged = []
        completed_workers = 0
        with ThreadPoolExecutor(max_workers=pioneer_workers, thread_name_prefix="cut-boundary-pioneer") as executor:
            for worker_idx in range(pioneer_workers):
                start_frame = worker_idx * shard_size
                end_frame = frame_count if worker_idx == pioneer_workers - 1 else min(frame_count, (worker_idx + 1) * shard_size)
                futures.append(executor.submit(_scan_range, worker_idx, start_frame, end_frame))
            for future in as_completed(futures):
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
                                "worker_total": int(pioneer_workers),
                                "worker_completed": int(completed_workers),
                                "duration": float(duration or 0.0),
                                "detected": len(merged),
                                "done": bool(completed_workers >= pioneer_workers),
                            }
                        )
                    except Exception:
                        pass

        if merged:
            for row in merged:
                try:
                    row["refine_pending"] = True
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
                    "detected": len(merged),
                    "worker_idx": 0,
                })
            except Exception:
                pass
        return normalize_cut_boundaries(merged or [], primary_fps=fps)


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
        settings = dict(settings or {})
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

        cap = cv2.VideoCapture(str(filepath))
        if not cap.isOpened():
            return normalize_cut_boundaries(provisional_rows or [])
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps <= 1.0:
                fps = 30.0
            fps = normalize_fps(fps)
            min_gap_sec = float(settings.get("scan_cut_auto_min_gap_sec", 8.0))
            min_gap_frames = max(1, int(round(min_gap_sec * fps)))
            follower_workers = max(1, min(4, int(settings.get("scan_cut_verify_workers", 4) or 4)))
            follower_backend = "mps" if sys.platform == "darwin" and _mps_available() else "cpu"
            verified_rows = []

            def _verify_row(row):
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
                verify_cap = cv2.VideoCapture(str(filepath))
                if not verify_cap.isOpened():
                    return None
                try:
                    if follower_backend == "mps":
                        verified = _auto_grid_v3_manual_verify_strict_mps(
                            verify_cap,
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
                            verify_cap,
                            cv2,
                            fps=fps,
                            frame_count=frame_count,
                            coarse_frame=coarse_frame,
                            settings=settings,
                            scan_profile=scan_profile,
                            sample_positions=sample_positions,
                        )
                finally:
                    try:
                        verify_cap.release()
                    except Exception:
                        pass
                if not verified or not verified.get("passed"):
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
                        "source_path": str(filepath),
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
                return fixed

            with ThreadPoolExecutor(max_workers=follower_workers, thread_name_prefix="cut-boundary-follower") as executor:
                future_map = {
                    executor.submit(_verify_row, dict(row)): dict(row)
                    for row in list(provisional_rows or [])
                    if isinstance(row, dict)
                }
                for future in as_completed(future_map):
                    fixed = None
                    try:
                        fixed = future.result()
                    except Exception:
                        fixed = None
                    if fixed is None:
                        continue
                    duplicate = False
                    for old in verified_rows:
                        try:
                            if abs(int(old.get("timeline_frame", -999999)) - int(fixed.get("timeline_frame", -999998))) <= min_gap_frames:
                                duplicate = True
                                break
                        except Exception:
                            pass
                    if duplicate:
                        continue
                    verified_rows.append(fixed)
                    verified_rows[:] = normalize_cut_boundaries(verified_rows, primary_fps=fps)
                    if callable(found_callback):
                        try:
                            found_callback(dict(fixed), list(verified_rows))
                        except Exception:
                            pass
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
