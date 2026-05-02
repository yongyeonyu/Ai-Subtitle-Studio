# Version: 03.11.16
# Phase: PHASE2
"""Cut-boundary helpers for absolute scene splits."""
from __future__ import annotations

from copy import deepcopy
import os
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import probe_media

CUT_BOUNDARY_SCHEMA = "cut_boundaries.v1"
CUT_SEGMENT_SCHEMA = "cut_boundary_segments.v1"
MIN_SLICE_SEC = 0.02


def cut_boundary_enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(settings.get("cut_boundary_detection_enabled", settings.get("scan_cut_enabled", True)))


def normalize_cut_boundaries(
    boundaries: list[dict[str, Any]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    out: list[dict[str, Any]] = []
    seen_frames: set[int] = set()
    for idx, item in enumerate(boundaries or []):
        if not isinstance(item, dict):
            continue
        try:
            sec = float(
                item.get("timeline_sec", item.get("time", item.get("start", item.get("timeline_start", 0.0))))
                or 0.0
            )
        except Exception:
            continue
        frame = item.get("timeline_frame", item.get("frame"))
        try:
            frame = int(frame) if frame is not None else sec_to_frame(sec, fps)
        except Exception:
            frame = sec_to_frame(sec, fps)
        sec = frame_to_sec(frame, fps)
        if sec <= 0.0 or frame in seen_frames:
            continue
        seen_frames.add(frame)
        row = dict(item)
        row.update(
            {
                "schema": "cut_boundary.v1",
                "id": str(row.get("id") or f"cut_{frame:08d}"),
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps,
                "absolute": True,
                "locked": True,
                "source": str(row.get("source") or "visual"),
            }
        )
        row.setdefault("detector", "opencv-gray-pyramid60")
        row.setdefault("reason", "visual_cut_boundary")
        row.setdefault("index", idx + 1)
        out.append(row)
    out.sort(key=lambda item: (float(item.get("timeline_sec", 0.0) or 0.0), int(item.get("timeline_frame", 0) or 0)))
    for idx, item in enumerate(out, start=1):
        item["index"] = idx
    return out


def project_cut_boundaries(project: dict[str, Any] | None, *, primary_fps: float | None = None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    if primary_fps is None:
        timebase = (project.get("timeline", {}) or {}).get("timebase", {}) or project.get("frame_timebase", {}) or {}
        primary_fps = timebase.get("primary_fps", 30.0)
    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")
    if not isinstance(raw, list):
        raw = []
    return normalize_cut_boundaries(raw, primary_fps=normalize_fps(primary_fps or 30.0))


def sync_project_cut_boundaries(
    project: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    boundaries = project_cut_boundaries(project, primary_fps=primary_fps)
    analysis = project.setdefault("analysis", {})
    analysis["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
    analysis["cut_boundaries"] = boundaries
    analysis["cut_boundary_settings"] = {
        "enabled": cut_boundary_enabled(settings if settings is not None else project.get("user_settings")),
        "detector": "opencv-gray-pyramid60",
        "count": len(boundaries),
        "absolute": True,
        "locked": True,
    }
    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state.setdefault("analysis", {})
        editor_state["analysis"]["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        editor_state["analysis"]["cut_boundaries"] = list(boundaries)
        multiclip = editor_state.setdefault("multiclip", {})
        multiclip["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        multiclip["cut_boundaries"] = list(boundaries)
    return boundaries


def split_segments_by_cut_boundaries(
    segments: list[dict[str, Any]] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    enabled: bool = True,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    if not enabled:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    cuts = normalize_cut_boundaries(boundaries, primary_fps=primary_fps)
    cut_times = [float(item.get("timeline_sec", item.get("time", 0.0)) or 0.0) for item in cuts]
    if not cut_times:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    out: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        item = _fit_one_segment_to_cut(seg, cut_times, cuts, primary_fps=primary_fps)
        if item is not None:
            out.append(item)
    for idx, item in enumerate(out):
        item["line"] = idx
        item["index"] = idx + 1
    return out


def _fit_one_segment_to_cut(
    seg: dict[str, Any],
    cut_times: list[float],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> dict[str, Any] | None:
    start = _as_float(seg.get("start", seg.get("timeline_start", 0.0)))
    end = _as_float(seg.get("end", seg.get("timeline_end", start)), start)
    end = max(start, end)
    if end <= start + MIN_SLICE_SEC:
        row = dict(seg)
        _attach_cut_local_fields(row, cut_times, cuts, primary_fps=primary_fps)
        return row

    midpoint = (start + end) / 2.0
    scene_start = 0.0
    scene_end: float | None = None
    scene_index = 0
    for idx, cut in enumerate(cut_times):
        if cut <= midpoint:
            scene_start = cut
            scene_index = idx + 1
        elif cut > midpoint:
            scene_end = cut
            break
    fitted_start = max(start, scene_start)
    fitted_end = end if scene_end is None else min(end, scene_end)
    if fitted_end <= fitted_start + MIN_SLICE_SEC:
        fitted_start = scene_start
        fitted_end = scene_end if scene_end is not None else max(end, scene_start + MIN_SLICE_SEC)
    if fitted_end <= fitted_start + MIN_SLICE_SEC:
        return None

    row = deepcopy(seg)
    row["start"] = fitted_start
    row["end"] = fitted_end
    row["timeline_start"] = fitted_start
    row["timeline_end"] = fitted_end
    row["start_frame"] = sec_to_frame(fitted_start, primary_fps)
    row["end_frame"] = sec_to_frame(fitted_end, primary_fps)
    row["timeline_start_frame"] = row["start_frame"]
    row["timeline_end_frame"] = row["end_frame"]
    row["frame_rate"] = primary_fps
    row["timeline_frame_rate"] = primary_fps
    row["frame_range"] = {
        "unit": "frame",
        "start": row["start_frame"],
        "end": row["end_frame"],
        "timeline_frame_rate": primary_fps,
    }
    row["cut_boundary_fitted"] = bool(fitted_start != start or fitted_end != end)
    row["words"] = _clip_timed_items(seg.get("words"), fitted_start, fitted_end)
    if "stt_candidates" in row:
        row["stt_candidates"] = _fit_candidates_to_interval(row.get("stt_candidates"), fitted_start, fitted_end, primary_fps)
    _attach_cut_local_fields(row, cut_times, cuts, primary_fps=primary_fps)
    row["cut_scene_index"] = scene_index
    row["cut_scene_start"] = scene_start
    if scene_end is not None:
        row["cut_scene_end"] = scene_end
    return row


def _fit_candidates_to_interval(candidates: Any, start: float, end: float, primary_fps: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(candidates, list):
        return out
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        c_start = _as_float(candidate.get("start", start), start)
        c_end = _as_float(candidate.get("end", end), end)
        overlap_start = max(start, c_start)
        overlap_end = min(end, c_end)
        if overlap_end <= overlap_start + MIN_SLICE_SEC:
            continue
        row = deepcopy(candidate)
        row["start"] = overlap_start
        row["end"] = overlap_end
        row["start_frame"] = sec_to_frame(overlap_start, primary_fps)
        row["end_frame"] = sec_to_frame(overlap_end, primary_fps)
        row["timeline_start_frame"] = row["start_frame"]
        row["timeline_end_frame"] = row["end_frame"]
        row["words"] = _clip_timed_items(candidate.get("words"), overlap_start, overlap_end)
        out.append(row)
    return out


def _clip_timed_items(items: Any, start: float, end: float) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    clipped: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        w_start = _as_float(item.get("start", start), start)
        w_end = _as_float(item.get("end", w_start), w_start)
        if max(start, w_start) < min(end, w_end):
            clipped.append(dict(item))
    return clipped


def _attach_cut_local_fields(
    row: dict[str, Any],
    cut_times: list[float],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> None:
    start = _as_float(row.get("start", row.get("timeline_start", 0.0)))
    end = _as_float(row.get("end", row.get("timeline_end", start)), start)
    prev_cut = 0.0
    next_cut = None
    cut_index = 0
    for idx, cut in enumerate(cut_times):
        if cut <= start + MIN_SLICE_SEC:
            prev_cut = cut
            cut_index = idx + 1
        elif cut > start + MIN_SLICE_SEC:
            next_cut = cut
            break
    row["cut_boundary_schema"] = CUT_SEGMENT_SCHEMA
    row["cut_scene_index"] = cut_index
    row["cut_scene_start"] = prev_cut
    if next_cut is not None:
        row["cut_scene_end"] = next_cut
    row["cut_local_start"] = max(0.0, start - prev_cut)
    row["cut_local_end"] = max(row["cut_local_start"], end - prev_cut)
    row["cut_local_start_frame"] = sec_to_frame(row["cut_local_start"], primary_fps)
    row["cut_local_end_frame"] = sec_to_frame(row["cut_local_end"], primary_fps)
    if 0 <= cut_index < len(cuts):
        row["cut_boundary_prev_id"] = str(cuts[cut_index - 1].get("id", "")) if cut_index > 0 else ""
        row["cut_boundary_next_id"] = str(cuts[cut_index].get("id", "")) if cut_index < len(cuts) else ""


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "CUT_BOUNDARY_SCHEMA",
    "CUT_SEGMENT_SCHEMA",
    "cut_boundary_enabled",
    "detect_media_cut_boundaries",
    "normalize_cut_boundaries",
    "project_cut_boundaries",
    "split_segments_by_cut_boundaries",
    "sync_project_cut_boundaries",
]


def detect_media_cut_boundaries(
    filepath: str,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    sample_step_sec: float = 1.0,
    threshold: float = 18.0,
    progress_callback=None,
    found_callback=None,
) -> list[dict[str, Any]]:
    """Scan one media file and return absolute cut-boundary rows."""
    try:
        info = probe_media(filepath)
        duration = float(info.get("duration", 0.0) or 0.0)
        fps = normalize_fps(info.get("fps", 30.0) or 30.0)
    except Exception:
        duration = 0.0
        fps = 30.0
    if duration <= 0.0:
        return []

    step = max(0.25, float(sample_step_sec or 1.0))
    rows: list[dict[str, Any]] = []
    last_progress_pct = -1
    estimated_steps = max(1, int(duration / step) + 1)

    def _report_progress(timestamp: float, *, force: bool = False):
        nonlocal last_progress_pct
        if not callable(progress_callback) or duration <= 0.0:
            return
        pct = int(min(100.0, max(0.0, (float(timestamp or 0.0) / duration) * 100.0)))
        if not force and pct < 100:
            pct = (pct // 10) * 10
        if pct <= last_progress_pct:
            return
        last_progress_pct = pct
        try:
            progress_callback(
                {
                    "clip_idx": int(clip_idx),
                    "percent": pct,
                    "timestamp": float(timestamp or 0.0),
                    "duration": duration,
                    "detected": len(rows),
                    "estimated_steps": estimated_steps,
                    "sample_step_sec": step,
                }
            )
        except Exception:
            pass

    try:
        from ui.editor.editor_timeline_video import (
            _rel_capture_image_at_global,
            _rel_image_delta,
            _rel_is_candidate,
            _rel_refine_boundary,
            _rel_scan_backend_label,
            _rel_scan_coarse_stride_frames,
        )
    except Exception:
        return []

    class _AutoScanAdapter:
        def __init__(self, source_path: str, fps_value: float, settings_obj: dict):
            self.settings = dict(settings_obj or {})
            self._source_path = str(source_path)
            self._fps = float(fps_value or 30.0)
            self._scan_cv2_mod = None
            self._scan_cv2_capture = None
            self._scan_cv2_source_path = None
            self._scan_logged_relative_resolution = False
            self._scan_last_region_deltas = []
            self._scan_last_region_hits = 0

            class _VideoPlayer:
                def __init__(self, path: str):
                    self._current_source_path = path

            self.video_player = _VideoPlayer(self._source_path)

        def _current_frame_fps(self) -> float:
            return float(self._fps)

        def _resolve_active_context(self, global_sec: float = 0.0):
            sec = max(0.0, float(global_sec or 0.0))
            return {
                "global_sec": sec,
                "local_sec": sec,
                "clip_file": self._source_path,
                "source_path": self._source_path,
            }

    adapter = _AutoScanAdapter(
        filepath,
        fps,
        {
            "scan_cut_threshold": float(threshold or 18.0),
            "scan_cut_region_threshold": float(threshold or 18.0),
            "scan_cut_relative_stride_frames": max(3, int(round(step * fps))),
        },
    )

    try:
        _report_progress(0.0, force=True)
        stride = max(1, int(_rel_scan_coarse_stride_frames(adapter)))
        total_frames = max(1, int(round(duration * fps)))
        last_frame = 0
        previous_score = 0.0
        baseline = 0.0
        resume_skip_frames = max(1, int(round(1.5 * fps)))

        while last_frame < total_frames:
            next_frame = min(total_frames, last_frame + stride)
            last_sec = last_frame / fps
            next_sec = next_frame / fps

            img_a = _rel_capture_image_at_global(adapter, last_sec, region_mode="fast4")
            img_b = _rel_capture_image_at_global(adapter, next_sec, region_mode="fast4")
            if img_a is None or img_b is None:
                break

            score = float(_rel_image_delta(adapter, img_a, img_b) or 0.0)
            baseline_for_decision = baseline if baseline > 0.0 else score
            baseline = (baseline_for_decision * 0.90 + score * 0.10) if baseline_for_decision > 0.0 else score
            is_candidate, reason = _rel_is_candidate(adapter, score, baseline_for_decision, previous_score)

            if next_frame == stride or next_frame % max(stride * 2, 1) == 0 or is_candidate:
                deltas = list(getattr(adapter, "_scan_last_region_deltas", []) or [])
                delta_text = ",".join(f"{d:.1f}" for d in deltas[:4])
                print(
                    f"📊 [scan-cut-auto] frame={next_frame} "
                    f"delta={score:.2f} baseline={baseline_for_decision:.2f} "
                    f"prev={previous_score:.2f} stride={stride} "
                    f"reason={reason or '-'} "
                    f"frame {last_frame}->{next_frame} "
                    f"{last_sec:.3f}s->{next_sec:.3f}s "
                    f"img={_rel_scan_backend_label(adapter)} fast4=[{delta_text}]",
                    flush=True,
                )

            if is_candidate:
                refined = _rel_refine_boundary(adapter, last_frame, next_frame, fps, reason)
                if refined:
                    stop_frame, stop_sec, final_score, final_regions, final_reason = refined
                    timeline_sec = max(0.0, float(clip_offset or 0.0) + float(stop_sec or 0.0))
                    frame_no = sec_to_frame(timeline_sec, fps)
                    row = {
                        "schema": "cut_boundary.v1",
                        "id": f"cut_{frame_no:08d}",
                        "time": timeline_sec,
                        "timeline_sec": timeline_sec,
                        "frame": frame_no,
                        "timeline_frame": frame_no,
                        "fps": fps,
                        "clip_idx": int(clip_idx),
                        "clip_local_sec": float(stop_sec or 0.0),
                        "source_path": filepath,
                        "score": float(final_score or 0.0),
                        "regions": int(final_regions or 0),
                        "reason": f"auto_pipeline_scan:{final_reason}",
                        "detector": "opencv-gray-relative",
                        "source": "visual",
                        "absolute": True,
                        "locked": True,
                    }
                    rows.append(row)
                    if callable(found_callback):
                        try:
                            found_callback(dict(row), list(rows))
                        except Exception:
                            pass
                    last_frame = max(next_frame, int(stop_frame) + resume_skip_frames)
                    previous_score = 0.0
                    baseline = 0.0
                    _report_progress(min(duration, last_frame / fps))
                    continue

            previous_score = score
            last_frame = next_frame
            _report_progress(min(duration, next_sec))
    except Exception:
        return []
    finally:
        cap = getattr(adapter, "_scan_cv2_capture", None)
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
    _report_progress(duration, force=True)
    return normalize_cut_boundaries(rows, primary_fps=fps)


def _mean_abs_difference(frame_a: bytes | list[int], frame_b: bytes | list[int]) -> float:
    length = min(len(frame_a), len(frame_b))
    if length <= 0:
        return 0.0
    total = 0
    for index in range(length):
        total += abs(int(frame_a[index]) - int(frame_b[index]))
    return total / length
