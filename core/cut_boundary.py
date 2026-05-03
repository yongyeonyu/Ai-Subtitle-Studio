# Version: 03.11.16
# Phase: PHASE2
"""Cut-boundary helpers for absolute scene splits."""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.media_info import probe_media

CUT_BOUNDARY_SCHEMA = "cut_boundaries.v1"
CUT_BOUNDARY_PROVISIONAL_SCHEMA = "cut_boundaries.provisional.v1"
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

    effective_fps = _boundary_primary_fps(boundaries, primary_fps)
    cuts = normalize_cut_boundaries(boundaries, primary_fps=effective_fps)
    cut_frames = [int(item.get("timeline_frame", item.get("frame", 0)) or 0) for item in cuts]
    if not cut_frames:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    out: list[dict[str, Any]] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        item = _fit_one_segment_to_cut(seg, cut_frames, cuts, primary_fps=effective_fps)
        if item is not None:
            out.append(item)
    for idx, item in enumerate(out):
        item["line"] = idx
        item["index"] = idx + 1
    return out


def snap_segments_near_cut_boundaries(
    segments: list[dict[str, Any]] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    enabled: bool = True,
    primary_fps: float = 30.0,
    snap_window_sec: float = 0.30,
    min_duration_sec: float = 0.05,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    if not enabled:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    effective_fps = _boundary_primary_fps(boundaries, primary_fps)
    cuts = normalize_cut_boundaries(boundaries, primary_fps=effective_fps)
    cut_frames = sorted(
        {
            int(item.get("timeline_frame", item.get("frame", 0)) or 0)
            for item in cuts
            if int(item.get("timeline_frame", item.get("frame", 0)) or 0) > 0
        }
    )
    if not cut_frames:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    window_frame = max(0, sec_to_frame(float(snap_window_sec or 0.0), effective_fps))
    min_duration = max(0.02, float(min_duration_sec or 0.05))
    snapped: list[dict[str, Any]] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        row = deepcopy(seg)
        start_frame, end_frame = _segment_frame_bounds(row, primary_fps)
        if end_frame < start_frame:
            end_frame = start_frame

        start_hit = _nearest_cut_frame(start_frame, cut_frames, window_frame)
        end_hit = _nearest_cut_frame(end_frame, cut_frames, window_frame)
        snapped_start_frame = start_hit if start_hit is not None else start_frame
        snapped_end_frame = end_hit if end_hit is not None else end_frame
        min_duration_frame = max(1, sec_to_frame(min_duration, effective_fps))
        if snapped_end_frame <= snapped_start_frame + min_duration_frame:
            if end_hit is not None and start_hit is None:
                snapped_start_frame = min(start_frame, max(0, snapped_end_frame - min_duration_frame))
            elif start_hit is not None and end_hit is None:
                snapped_end_frame = max(end_frame, snapped_start_frame + min_duration_frame)
            else:
                snapped_start_frame = start_frame
                snapped_end_frame = end_frame

        row["start_frame"] = snapped_start_frame
        row["end_frame"] = max(snapped_start_frame + min_duration_frame, snapped_end_frame)
        row["timeline_start_frame"] = row["start_frame"]
        row["timeline_end_frame"] = row["end_frame"]
        row["start"] = frame_to_sec(row["start_frame"], effective_fps)
        row["end"] = frame_to_sec(row["end_frame"], effective_fps)
        row["timeline_start"] = row["start"]
        row["timeline_end"] = row["end"]
        row["cut_boundary_snapped"] = bool(
            (start_hit is not None and start_hit != start_frame)
            or (end_hit is not None and end_hit != end_frame)
        )
        if start_hit is not None:
            row["cut_boundary_snap_start_frame"] = start_hit
            row["cut_boundary_snap_start"] = frame_to_sec(start_hit, effective_fps)
        if end_hit is not None:
            row["cut_boundary_snap_end_frame"] = end_hit
            row["cut_boundary_snap_end"] = frame_to_sec(end_hit, effective_fps)
        snapped.append(row)
    return snapped


def magnetize_segments_to_cut_boundaries(
    segments: list[dict[str, Any]] | None,
    *,
    confirmed_boundaries: list[dict[str, Any]] | None = None,
    provisional_boundaries: list[dict[str, Any]] | None = None,
    enabled: bool = True,
    primary_fps: float = 30.0,
    provisional_window_sec: float = 0.34,
    confirmed_window_sec: float = 0.48,
    min_duration_sec: float = 0.05,
) -> list[dict[str, Any]]:
    """Snap aggressively to provisional+confirmed cuts, then enforce confirmed hard splits."""
    if not segments:
        return []
    rows = [dict(seg) for seg in segments if isinstance(seg, dict)]
    if not enabled:
        return rows

    effective_fps = _boundary_primary_fps(confirmed_boundaries or provisional_boundaries, primary_fps)
    provisional_rows = normalize_cut_boundaries(provisional_boundaries, primary_fps=effective_fps)
    confirmed_rows = normalize_cut_boundaries(confirmed_boundaries, primary_fps=effective_fps)

    if provisional_rows:
        rows = snap_segments_near_cut_boundaries(
            rows,
            provisional_rows,
            enabled=True,
            primary_fps=effective_fps,
            snap_window_sec=provisional_window_sec,
            min_duration_sec=min_duration_sec,
        )
    if confirmed_rows:
        rows = snap_segments_near_cut_boundaries(
            rows,
            confirmed_rows,
            enabled=True,
            primary_fps=effective_fps,
            snap_window_sec=confirmed_window_sec,
            min_duration_sec=min_duration_sec,
        )
        rows = split_segments_by_cut_boundaries(
            rows,
            confirmed_rows,
            enabled=True,
            primary_fps=effective_fps,
        )
        rows = clamp_segments_to_cut_scene_edges(
            rows,
            confirmed_rows,
            enabled=True,
            primary_fps=effective_fps,
            clamp_window_sec=max(float(confirmed_window_sec or 0.0), 0.60),
            min_duration_sec=min_duration_sec,
        )

    for row in rows:
        row["cut_boundary_magnetized"] = True
        if provisional_rows:
            row["cut_boundary_magnetized_provisional"] = True
        if confirmed_rows:
            row["cut_boundary_magnetized_confirmed"] = True
    return rows


def _nearest_cut_frame(value: int, cut_frames: list[int], window_frame: int) -> int | None:
    if window_frame <= 0:
        return None
    best = None
    best_dist = None
    for cut in cut_frames:
        dist = abs(int(cut) - int(value))
        if dist > window_frame:
            continue
        if best_dist is None or dist < best_dist:
            best = int(cut)
            best_dist = int(dist)
    return best


def clamp_segments_to_cut_scene_edges(
    segments: list[dict[str, Any]] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    enabled: bool = True,
    primary_fps: float = 30.0,
    clamp_window_sec: float = 0.60,
    min_duration_sec: float = 0.05,
) -> list[dict[str, Any]]:
    """Force segment edges to their owning confirmed scene boundaries when near enough."""
    if not segments:
        return []
    if not enabled:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    effective_fps = _boundary_primary_fps(boundaries, primary_fps)
    cuts = normalize_cut_boundaries(boundaries, primary_fps=effective_fps)
    cut_frames = [int(item.get("timeline_frame", item.get("frame", 0)) or 0) for item in cuts]
    if not cut_frames:
        return [dict(seg) for seg in segments if isinstance(seg, dict)]

    window_frame = max(0, sec_to_frame(float(clamp_window_sec or 0.0), effective_fps))
    min_duration = max(0.02, float(min_duration_sec or 0.05))
    min_duration_frame = max(1, sec_to_frame(min_duration, effective_fps))
    out: list[dict[str, Any]] = []
    for seg in segments or []:
        if not isinstance(seg, dict):
            continue
        row = deepcopy(seg)
        start_frame, end_frame = _segment_frame_bounds(row, effective_fps)
        if end_frame < start_frame:
            end_frame = start_frame

        midpoint_frame = (start_frame + end_frame) // 2
        scene_start_frame = 0
        scene_end_frame: int | None = None
        for cut_frame in cut_frames:
            if cut_frame <= midpoint_frame:
                scene_start_frame = cut_frame
            elif cut_frame > midpoint_frame:
                scene_end_frame = cut_frame
                break

        clamped = False
        if abs(start_frame - scene_start_frame) <= window_frame:
            start_frame = scene_start_frame
            clamped = True
        if scene_end_frame is not None and abs(scene_end_frame - end_frame) <= window_frame:
            end_frame = scene_end_frame
            clamped = True
        if end_frame <= start_frame + min_duration_frame:
            if scene_end_frame is not None and scene_end_frame > start_frame + min_duration_frame:
                end_frame = scene_end_frame
                clamped = True
            else:
                end_frame = start_frame + min_duration_frame

        row["start_frame"] = start_frame
        row["end_frame"] = end_frame
        row["timeline_start_frame"] = start_frame
        row["timeline_end_frame"] = end_frame
        row["start"] = frame_to_sec(start_frame, effective_fps)
        row["end"] = frame_to_sec(end_frame, effective_fps)
        row["timeline_start"] = row["start"]
        row["timeline_end"] = row["end"]
        row["cut_boundary_scene_clamped"] = clamped
        if clamped:
            row["cut_boundary_hard_aligned"] = True
        _attach_cut_local_fields(row, cut_frames, cuts, primary_fps=effective_fps)
        out.append(row)
    return out


def _boundary_primary_fps(boundaries: list[dict[str, Any]] | None, fallback_fps: float) -> float:
    for item in boundaries or []:
        if not isinstance(item, dict):
            continue
        for key in ("fps", "timeline_frame_rate", "frame_rate", "source_frame_rate", "video_fps"):
            value = item.get(key)
            try:
                return normalize_fps(float(value or 0.0) or fallback_fps)
            except Exception:
                continue
    return normalize_fps(fallback_fps or 30.0)


def _fit_one_segment_to_cut(
    seg: dict[str, Any],
    cut_frames: list[int],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> dict[str, Any] | None:
    start_frame, end_frame = _segment_frame_bounds(seg, primary_fps)
    end_frame = max(start_frame, end_frame)
    if end_frame <= start_frame + 1:
        row = dict(seg)
        _attach_cut_local_fields(row, cut_frames, cuts, primary_fps=primary_fps)
        return row

    midpoint_frame = (start_frame + end_frame) // 2
    scene_start_frame = 0
    scene_end_frame: int | None = None
    scene_index = 0
    for idx, cut_frame in enumerate(cut_frames):
        if cut_frame <= midpoint_frame:
            scene_start_frame = cut_frame
            scene_index = idx + 1
        elif cut_frame > midpoint_frame:
            scene_end_frame = cut_frame
            break
    fitted_start_frame = max(start_frame, scene_start_frame)
    fitted_end_frame = end_frame if scene_end_frame is None else min(end_frame, scene_end_frame)
    edge_tolerance = max(0.06, 2.0 / max(float(primary_fps or 30.0), 1.0))
    edge_tolerance_frame = max(1, sec_to_frame(edge_tolerance, primary_fps))
    if abs(fitted_start_frame - scene_start_frame) <= edge_tolerance_frame:
        fitted_start_frame = scene_start_frame
    if scene_end_frame is not None and abs(scene_end_frame - fitted_end_frame) <= edge_tolerance_frame:
        fitted_end_frame = scene_end_frame
    if fitted_end_frame <= fitted_start_frame + 1:
        fitted_start_frame = scene_start_frame
        fitted_end_frame = scene_end_frame if scene_end_frame is not None else max(end_frame, scene_start_frame + 1)
    if fitted_end_frame <= fitted_start_frame + 1:
        return None

    row = deepcopy(seg)
    row["start_frame"] = fitted_start_frame
    row["end_frame"] = fitted_end_frame
    row["timeline_start_frame"] = fitted_start_frame
    row["timeline_end_frame"] = fitted_end_frame
    row["start"] = frame_to_sec(fitted_start_frame, primary_fps)
    row["end"] = frame_to_sec(fitted_end_frame, primary_fps)
    row["timeline_start"] = row["start"]
    row["timeline_end"] = row["end"]
    row["frame_rate"] = primary_fps
    row["timeline_frame_rate"] = primary_fps
    row["frame_range"] = {
        "unit": "frame",
        "start": row["start_frame"],
        "end": row["end_frame"],
        "timeline_frame_rate": primary_fps,
    }
    row["cut_boundary_fitted"] = bool(fitted_start_frame != start_frame or fitted_end_frame != end_frame)
    row["words"] = _clip_timed_items(seg.get("words"), row["start"], row["end"])
    if "stt_candidates" in row:
        row["stt_candidates"] = _fit_candidates_to_interval(row.get("stt_candidates"), row["start"], row["end"], primary_fps)
    _attach_cut_local_fields(row, cut_frames, cuts, primary_fps=primary_fps)
    row["cut_scene_index"] = scene_index
    row["cut_scene_start_frame"] = scene_start_frame
    row["cut_scene_start"] = frame_to_sec(scene_start_frame, primary_fps)
    if scene_end_frame is not None:
        row["cut_scene_end_frame"] = scene_end_frame
        row["cut_scene_end"] = frame_to_sec(scene_end_frame, primary_fps)
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
    cut_frames: list[int],
    cuts: list[dict[str, Any]],
    *,
    primary_fps: float,
) -> None:
    start_frame, end_frame = _segment_frame_bounds(row, primary_fps)
    prev_cut_frame = 0
    next_cut_frame = None
    cut_index = 0
    for idx, cut_frame in enumerate(cut_frames):
        if cut_frame <= start_frame:
            prev_cut_frame = cut_frame
            cut_index = idx + 1
        elif cut_frame > start_frame:
            next_cut_frame = cut_frame
            break
    row["cut_boundary_schema"] = CUT_SEGMENT_SCHEMA
    row["cut_scene_index"] = cut_index
    row["cut_scene_start_frame"] = prev_cut_frame
    row["cut_scene_start"] = frame_to_sec(prev_cut_frame, primary_fps)
    if next_cut_frame is not None:
        row["cut_scene_end_frame"] = next_cut_frame
        row["cut_scene_end"] = frame_to_sec(next_cut_frame, primary_fps)
    row["cut_local_start_frame"] = max(0, start_frame - prev_cut_frame)
    row["cut_local_end_frame"] = max(row["cut_local_start_frame"], end_frame - prev_cut_frame)
    row["cut_local_start"] = frame_to_sec(row["cut_local_start_frame"], primary_fps)
    row["cut_local_end"] = frame_to_sec(row["cut_local_end_frame"], primary_fps)
    if 0 <= cut_index < len(cuts):
        row["cut_boundary_prev_id"] = str(cuts[cut_index - 1].get("id", "")) if cut_index > 0 else ""
        row["cut_boundary_next_id"] = str(cuts[cut_index].get("id", "")) if cut_index < len(cuts) else ""


def _segment_frame_bounds(seg: dict[str, Any], primary_fps: float) -> tuple[int, int]:
    frame_range = seg.get("frame_range", {}) if isinstance(seg.get("frame_range"), dict) else {}
    start_frame = seg.get("start_frame", seg.get("timeline_start_frame", frame_range.get("start")))
    end_frame = seg.get("end_frame", seg.get("timeline_end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_frame(_as_float(seg.get("start", seg.get("timeline_start", 0.0))), primary_fps)
    else:
        start_frame = int(start_frame)
    if end_frame is None:
        end_frame = sec_to_frame(_as_float(seg.get("end", seg.get("timeline_end", frame_to_sec(start_frame, primary_fps))), frame_to_sec(start_frame, primary_fps)), primary_fps)
    else:
        end_frame = int(end_frame)
    return max(0, int(start_frame)), max(0, int(end_frame))


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
    "magnetize_segments_to_cut_boundaries",
    "normalize_cut_boundaries",
    "project_cut_boundaries",
    "split_segments_by_cut_boundaries",
    "sync_project_cut_boundaries",
]


def _legacy_detect_media_cut_boundaries(
    filepath: str,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    sample_step_sec: float = 2.0,
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



# === CUT_BOUNDARY_LEVEL_PROFILE_PATCH_V1 ===

CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "사용안함"),
    ("low", "낮음 - 9개 중 십자가 4개"),
    ("medium", "중간 - 9개 중 꽉찬 십자가 5개"),
    ("high", "높음 - 9개 전체"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    # 3x3 index:
    # 0 1 2
    # 3 4 5
    # 6 7 8
    "off": {
        "level": "off",
        "label": "사용안함",
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "낮음 - 9개 중 십자가 4개",
        "mask": "cross4",
        # 십자가 4개: 상/좌/우/하, 중앙 제외
        "positions": (1, 3, 5, 7),
        "cell_count": 4,
    },
    "medium": {
        "level": "medium",
        "label": "중간 - 9개 중 꽉찬 십자가 5개",
        "mask": "cross5",
        # X모양 5개: 네 모서리 + 중앙
        "positions": (1, 3, 4, 5, 7),
        "cell_count": 5,
    },
    "high": {
        "level": "high",
        "label": "높음 - 9개 전체",
        "mask": "grid9",
        # 9개 전체: 3x3 전체
        "positions": (0, 1, 2, 3, 4, 5, 6, 7, 8),
        "cell_count": 9,
    },
}

def normalize_cut_boundary_level(value) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "false": "off",
        "0": "off",
        "none": "off",
        "disabled": "off",
        "disable": "off",
        "off": "off",
        "사용안함": "off",
        "사용 안함": "off",

        "low": "low",
        "낮음": "low",

        "mid": "medium",
        "middle": "medium",
        "medium": "medium",
        "중간": "medium",

        "high": "medium",
        "높음": "medium",

        "true": "medium",
        "1": "medium",
        "on": "medium",
        "enabled": "medium",
        "enable": "medium",
        "사용": "medium",
    }
    return aliases.get(raw, "medium")

def cut_boundary_level(settings: dict | None = None) -> str:
    settings = settings or {}

    # 새 설정 우선
    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        if key in settings:
            return normalize_cut_boundary_level(settings.get(key))

    # 기존 boolean 호환
    for key in (
        "scan_cut_enabled",
        "scan_cut_auto_enabled",
        "cut_boundary_enabled",
    ):
        if key in settings:
            return "medium" if bool(settings.get(key)) else "off"

    return "medium"

def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
    level = cut_boundary_level(settings or {})
    profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
    step_map = {
        "low": 3.0,
        "medium": 2.0,
    }
    profile["sample_step_sec"] = float(step_map.get(level, 2.0))
    profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
    return profile

def cut_boundary_enabled(settings: dict | None = None) -> bool:
    return cut_boundary_level(settings or {}) != "off"

def _grid_cell_slices(width: int, height: int):
    xs = [0, width // 3, (width * 2) // 3, width]
    ys = [0, height // 3, (height * 2) // 3, height]
    cells = []
    for r in range(3):
        for c in range(3):
            cells.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return cells

def _selected_grid_delta(prev_gray, cur_gray, positions) -> tuple[float, list[float]]:
    try:
        import cv2
        import numpy as np

        # 계산량을 낮추기 위해 270x270으로 통일
        prev = cv2.resize(prev_gray, (270, 270), interpolation=cv2.INTER_AREA)
        cur = cv2.resize(cur_gray, (270, 270), interpolation=cv2.INTER_AREA)

        cells = _grid_cell_slices(270, 270)
        deltas = []
        for idx in positions:
            x1, y1, x2, y2 = cells[int(idx)]
            p = prev[y1:y2, x1:x2]
            c = cur[y1:y2, x1:x2]
            d = float(np.mean(cv2.absdiff(p, c)))
            deltas.append(d)

        if not deltas:
            return 0.0, []
        return float(sum(deltas) / len(deltas)), deltas
    except Exception:
        return 0.0, []

def detect_media_cut_boundaries(
    media_path,
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
    """3x3 grid-profile cut detector.

    Levels:
    - off: disabled
    - low: cross4, 4/9
    - medium: x5, 5/9
    - high: o8, 8/9

    If OpenCV scan fails, fallback to the legacy detector.
    """
    try:
        import os
        import cv2
        import time

        try:
            from logger import get_logger
        except Exception:
            get_logger = None

        if scan_profile is None:
            try:
                from core.settings import load_settings
                scan_profile = cut_boundary_scan_profile(load_settings())
            except Exception:
                scan_profile = cut_boundary_scan_profile({})

        level = str((scan_profile or {}).get("level", "medium"))
        if level == "off":
            if get_logger:
                get_logger().log("  🎬 [컷 경계] 단계=사용안함, 분석을 건너뜁니다")
            return []

        positions = sample_positions
        if positions is None:
            positions = (scan_profile or {}).get("positions", ())
        positions = tuple(int(x) for x in (positions or ()))
        if not positions:
            return []

        mask = str(sample_mask or (scan_profile or {}).get("mask", ""))
        label = str((scan_profile or {}).get("label", level))

        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise RuntimeError("video open failed")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0.0 or frame_count <= 0:
            raise RuntimeError("invalid fps/frame_count")

        duration = frame_count / fps
        step = max(0.2, float(sample_step_sec or 1.0))
        step_frames = max(1, int(round(fps * step)))
        threshold = float(threshold or 24.0)

        # ✅ grid detector 안정화:
        # 기존 threshold=24를 그대로 쓰면 카메라 움직임/노출 변화도 컷으로 잡혀
        # 2초마다 컷이 생기는 문제가 발생한다.
        level_threshold_multiplier = {
            "low": 2.40,
            "medium": 2.00,
            "high": 1.70,
        }.get(level, 2.00)
        effective_threshold = max(threshold, threshold * level_threshold_multiplier)

        # 낮음/중간/높음은 "검사 칸 수"뿐 아니라 최소 컷 간격도 다르게 둔다.
        # 중간 기본 8초: 2초/4초/6초 식 오탐을 막는다.
        level_min_gap_sec = {
            "low": 12.0,
            "medium": 8.0,
            "high": 5.0,
        }.get(level, 8.0)

        clip_offset = float(clip_offset or 0.0)
        clip_idx = int(clip_idx or 0)

        if get_logger:
            get_logger().log(
                f"🔎 [scan-cut-grid] level={level} label={label} "
                f"mask={mask} cells={len(positions)}/25 threshold={threshold:.2f} effective={effective_threshold:.2f} min_gap={cooldown_sec:.1f}s "
                f"step={step:.2f}s source={os.path.basename(str(media_path))}"
            )

        rows = []
        prev_gray = None
        prev_t = 0.0
        last_emit_t = -9999.0
        cooldown_sec = max(level_min_gap_sec, step * 2.0)

        total_steps = max(1, int(frame_count / step_frames))
        step_i = 0

        for frame_no in range(0, frame_count, step_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            t = frame_no / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if progress_callback:
                try:
                    progress_callback({
                        "clip_idx": clip_idx,
                        "percent": int(min(100, (step_i / max(1, total_steps)) * 100)),
                        "timestamp": t,
                        "duration": duration,
                        "detected": len(rows),
                    })
                except Exception:
                    pass

            if prev_gray is not None:
                delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)

                # 선택된 칸 평균 delta 기준.
                # 추가로 선택 칸 중 절반 이상이 threshold의 70%를 넘으면 유효 컷으로 인정.
                required_ratio = {
                    "low": 0.75,
                    "medium": 0.80,
                    "high": 0.70,
                }.get(level, 0.80)

                strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                required_cells = max(1, int(round(len(positions) * required_ratio)))
                enough_cells = strong_cells >= required_cells

                if delta >= effective_threshold and enough_cells and (t - last_emit_t) >= cooldown_sec:
                    sec = round(t, 3)
                    row = {
                        "time": sec,
                        "timeline_sec": round(clip_offset + sec, 3),
                        "clip_idx": clip_idx,
                        "source": "grid_profile",
                        "level": level,
                        "mask": mask,
                        "cell_count": len(positions),
                        "grid_positions": list(positions),
                        "delta": round(delta, 3),
                        "cell_deltas": [round(x, 3) for x in cell_deltas],
                        "threshold": threshold,
                        "prev_time": round(prev_t, 3),
                    }
                    rows.append(row)
                    last_emit_t = t

                    if get_logger:
                        get_logger().log(
                            f"📊 [scan-cut-grid] level={level} mask={mask} "
                            f"time={sec:.3f}s delta={delta:.2f} "
                            f"cells={strong_cells}/{len(positions)}"
                        )

                    if found_callback:
                        try:
                            found_callback(row, list(rows))
                        except Exception:
                            pass

            prev_gray = gray
            prev_t = t
            step_i += 1

        cap.release()

        if progress_callback:
            try:
                progress_callback({
                    "clip_idx": clip_idx,
                    "percent": 100,
                    "timestamp": duration,
                    "duration": duration,
                    "detected": len(rows),
                })
            except Exception:
                pass

        try:
            return normalize_cut_boundaries(rows)
        except Exception:
            return rows

    except Exception as exc:
        try:
            from logger import get_logger
            get_logger().log(f"  ⚠️ [컷 경계] grid detector 실패, legacy detector로 fallback: {exc}")
        except Exception:
            pass

        try:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                **kwargs,
            )
        except TypeError:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset,
                clip_idx,
                sample_step_sec,
                threshold,
                progress_callback,
                found_callback,
            )


# === CUT_BOUNDARY_GRID_INTERVAL_FIX_V3 ===

def _cb_level_interval_sec(level: str) -> float:
    """Requested scan interval by cut-boundary level."""
    level = normalize_cut_boundary_level(level)
    return {
        "low": 2.0,       # 동영상 프레임 * 2
        "medium": 1.0,    # 동영상 프레임 동일
        "high": 0.5,      # 동영상 프레임 / 2
    }.get(level, 1.0)


def _cb_level_pyramid_steps(level: str) -> tuple[float, ...]:
    """Regression/refinement pyramid matched to the scan interval."""
    base = _cb_level_interval_sec(level)
    return (
        round(base, 3),
        round(base / 2.0, 3),
        round(base / 4.0, 3),
    )


def _cb_level_effective_threshold(level: str, threshold: float) -> float:
    """Make lower levels less sensitive while preserving the user threshold."""
    level = normalize_cut_boundary_level(level)
    mul = {
        "low": 2.40,
        "medium": 2.00,
        "high": 1.65,
    }.get(level, 2.00)
    return max(float(threshold or 24.0), float(threshold or 24.0) * mul)


def _cb_level_min_gap_sec(level: str) -> float:
    """Debounce false positives.

    This is separate from scan interval. Scan interval controls how often we
    inspect frames; min gap controls how close accepted cuts can be.
    """
    level = normalize_cut_boundary_level(level)
    return {
        "low": 10.0,
        "medium": 6.0,
        "high": 3.0,
    }.get(level, 6.0)


def _cb_read_gray_at(cap, frame_no: int):
    try:
        import cv2
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_no)))
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    except Exception:
        return None


def _cb_refine_cut_time_with_pyramid(
    cap,
    *,
    fps: float,
    coarse_time: float,
    positions,
    effective_threshold: float,
    level: str,
):
    """Refine candidate time using a backward pyramid.

    Example:
    - low:    2.0s -> 1.0s -> 0.5s
    - medium: 1.0s -> 0.5s -> 0.25s
    - high:   0.5s -> 0.25s -> 0.125s
    """
    try:
        import cv2

        steps = _cb_level_pyramid_steps(level)
        best_time = float(coarse_time)

        # Search only the previous base interval.
        window = max(steps[0], 0.25)
        start_t = max(0.0, best_time - window)
        end_t = best_time

        for step in steps:
            if step <= 0:
                continue

            t = start_t
            prev_gray = None
            local_best = best_time

            while t <= end_t + 1e-6:
                gray = _cb_read_gray_at(cap, int(round(t * fps)))
                if gray is not None and prev_gray is not None:
                    delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)
                    strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                    required_cells = max(1, int(round(len(positions) * 0.80)))
                    if delta >= effective_threshold and strong_cells >= required_cells:
                        local_best = round(t, 3)
                        break
                if gray is not None:
                    prev_gray = gray
                t += step

            best_time = local_best

            # Narrow next search window around the current best.
            start_t = max(0.0, best_time - step)
            end_t = min(float(coarse_time), best_time + step)

        return round(float(best_time), 3)
    except Exception:
        return round(float(coarse_time), 3)


def _cb_cuda_available() -> bool:
    try:
        import cv2
        cuda_mod = getattr(cv2, "cuda", None)
        if cuda_mod is None:
            return False
        count_fn = getattr(cuda_mod, "getCudaEnabledDeviceCount", None)
        if not callable(count_fn):
            return False
        return int(count_fn() or 0) > 0
    except Exception:
        return False


def detect_media_cut_boundaries(
    media_path,
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
    """Stable 3x3 grid-profile cut detector.

    Levels:
    - off: disabled
    - low:    cross4, 4/9, scan every 2.0s
    - medium: x5,     5/9, scan every 1.0s
    - high:   o8,     8/9, scan every 0.5s

    Regression pyramid follows the same interval ratio:
    - low:    2.0 -> 1.0 -> 0.5
    - medium: 1.0 -> 0.5 -> 0.25
    - high:   0.5 -> 0.25 -> 0.125
    """
    try:
        import os
        import cv2

        try:
            from logger import get_logger
        except Exception:
            get_logger = None

        if scan_profile is None:
            try:
                from core.settings import load_settings
                scan_profile = cut_boundary_scan_profile(load_settings())
            except Exception:
                scan_profile = cut_boundary_scan_profile({})

        level = normalize_cut_boundary_level((scan_profile or {}).get("level", "medium"))

        if level == "off":
            if get_logger:
                get_logger().log("  🎬 [컷 경계] 단계=사용안함, 분석을 건너뜁니다")
            return []

        positions = sample_positions
        if positions is None:
            positions = (scan_profile or {}).get("positions", ())
        positions = tuple(int(x) for x in (positions or ()))
        if not positions:
            return []

        mask = str(sample_mask or (scan_profile or {}).get("mask", ""))
        label = str((scan_profile or {}).get("label", level))

        cap = cv2.VideoCapture(str(media_path))
        if not cap.isOpened():
            raise RuntimeError("video open failed")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if fps <= 0.0 or frame_count <= 0:
            raise RuntimeError("invalid fps/frame_count")

        duration = frame_count / fps

        # ✅ 요청 기준 강제 적용
        scan_interval_sec = _cb_level_interval_sec(level)
        step_frames = max(1, int(round(fps * scan_interval_sec)))

        threshold = float(threshold or 24.0)
        effective_threshold = _cb_level_effective_threshold(level, threshold)
        min_gap_sec = _cb_level_min_gap_sec(level)
        pyramid_steps = _cb_level_pyramid_steps(level)

        clip_offset = float(clip_offset or 0.0)
        clip_idx = int(clip_idx or 0)

        if get_logger:
            get_logger().log(
                f"🔎 [scan-cut-grid-v3] level={level} label={label} "
                f"mask={mask} cells={len(positions)}/25 "
                f"interval={scan_interval_sec:.3f}s pyramid={pyramid_steps} "
                f"threshold={threshold:.2f} effective={effective_threshold:.2f} "
                f"min_gap={min_gap_sec:.1f}s source={os.path.basename(str(media_path))}"
            )

        rows = []
        prev_gray = None
        prev_t = 0.0
        last_emit_t = -999999.0

        total_steps = max(1, int(frame_count / step_frames))
        step_i = 0

        for frame_no in range(0, frame_count, step_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            t = frame_no / fps
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if progress_callback:
                try:
                    progress_callback({
                        "clip_idx": clip_idx,
                        "percent": int(min(100, (step_i / max(1, total_steps)) * 100)),
                        "timestamp": t,
                        "duration": duration,
                        "detected": len(rows),
                    })
                except Exception:
                    pass

            if prev_gray is not None:
                delta, cell_deltas = _selected_grid_delta(prev_gray, gray, positions)

                required_ratio = {
                    "low": 0.85,
                    "medium": 0.80,
                    "high": 0.70,
                }.get(level, 0.80)

                strong_cells = sum(1 for d in cell_deltas if d >= effective_threshold * 0.70)
                required_cells = max(1, int(round(len(positions) * required_ratio)))
                enough_cells = strong_cells >= required_cells

                if (
                    delta >= effective_threshold
                    and enough_cells
                    and (t - last_emit_t) >= min_gap_sec
                ):
                    refined_sec = _cb_refine_cut_time_with_pyramid(
                        cap,
                        fps=fps,
                        coarse_time=t,
                        positions=positions,
                        effective_threshold=effective_threshold,
                        level=level,
                    )

                    # refine 결과도 min_gap 안쪽이면 버림
                    if refined_sec - last_emit_t < min_gap_sec:
                        prev_gray = gray
                        prev_t = t
                        step_i += 1
                        continue

                    row = {
                        "time": round(refined_sec, 3),
                        "timeline_sec": round(clip_offset + refined_sec, 3),
                        "clip_idx": clip_idx,
                        "source": "grid_profile_v3",
                        "level": level,
                        "mask": mask,
                        "cell_count": len(positions),
                        "grid_positions": list(positions),
                        "delta": round(delta, 3),
                        "cell_deltas": [round(x, 3) for x in cell_deltas],
                        "threshold": threshold,
                        "effective_threshold": round(effective_threshold, 3),
                        "scan_interval_sec": scan_interval_sec,
                        "pyramid_steps": list(pyramid_steps),
                        "min_gap_sec": min_gap_sec,
                        "prev_time": round(prev_t, 3),
                        "coarse_time": round(t, 3),
                    }

                    rows.append(row)
                    last_emit_t = refined_sec

                    if get_logger:
                        get_logger().log(
                            f"📊 [scan-cut-grid-v3] level={level} mask={mask} "
                            f"coarse={t:.3f}s refined={refined_sec:.3f}s "
                            f"delta={delta:.2f} cells={strong_cells}/{len(positions)}"
                        )

                    if found_callback:
                        try:
                            found_callback(row, list(rows))
                        except Exception:
                            pass

            prev_gray = gray
            prev_t = t
            step_i += 1

        cap.release()

        if progress_callback:
            try:
                progress_callback({
                    "clip_idx": clip_idx,
                    "percent": 100,
                    "timestamp": duration,
                    "duration": duration,
                    "detected": len(rows),
                })
            except Exception:
                pass

        try:
            return normalize_cut_boundaries(rows)
        except Exception:
            return rows

    except Exception as exc:
        try:
            from logger import get_logger
            get_logger().log(
                f"  ⚠️ [컷 경계] grid-v3 detector 실패, legacy detector로 fallback: {exc}"
            )
        except Exception:
            pass

        try:
            return _legacy_detect_media_cut_boundaries(
                media_path,
                clip_offset=clip_offset,
                clip_idx=clip_idx,
                sample_step_sec=sample_step_sec,
                threshold=threshold,
                progress_callback=progress_callback,
                found_callback=found_callback,
                **kwargs,
            )
        except Exception:
            return []


# === CUT_BOUNDARY_CROSS5_LEVEL_OVERRIDE ===

CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "사용안함"),
    ("low", "낮음"),
    ("medium", "중간"),
    ("high", "높음"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    # 3x3 index:
    # 0 1 2
    # 3 4 5
    # 6 7 8
    "off": {
        "level": "off",
        "label": "사용안함",
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "낮음 - 9개 중 십자가 4개",
        "mask": "cross4",
        "positions": (1, 3, 5, 7),
        "cell_count": 4,
    },
    "medium": {
        "level": "medium",
        "label": "중간 - 9개 중 꽉찬 십자가 5개",
        "mask": "cross5",
        "positions": (1, 3, 4, 5, 7),
        "cell_count": 5,
    },
    "high": {
        "level": "high",
        "label": "높음 - 9개 전체",
        "mask": "grid9",
        "positions": (0, 1, 2, 3, 4, 5, 6, 7, 8),
        "cell_count": 9,
    },
}

def normalize_cut_boundary_level(value) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "사용안함": "off",
        "사용 안함": "off",
        "미사용": "off",
        "off": "off",
        "false": "off",
        "0": "off",
        "disabled": "off",
        "disable": "off",
        "none": "off",

        "낮음": "low",
        "low": "low",

        "중간": "medium",
        "medium": "medium",
        "mid": "medium",
        "middle": "medium",
        "사용": "medium",
        "on": "medium",
        "true": "medium",
        "1": "medium",
        "enabled": "medium",

        "높음": "medium",
        "high": "medium",
    }
    return aliases.get(raw, "medium")

def cut_boundary_level(settings: dict | None = None) -> str:
    settings = settings or {}

    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        if key in settings:
            return normalize_cut_boundary_level(settings.get(key))

    for key in (
        "cut_boundary_detection_enabled",
        "scan_cut_enabled",
        "scan_cut_auto_enabled",
        "cut_boundary_enabled",
    ):
        if key in settings:
            return "medium" if bool(settings.get(key)) else "off"

    return "medium"

def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
    level = cut_boundary_level(settings or {})
    profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
    profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
    return profile

def cut_boundary_enabled(settings: dict | None = None) -> bool:
    return cut_boundary_level(settings or {}) != "off"






# === FRAME FPS NORMALIZE PATCH START ===

def _cut_boundary_row_fps(row, fallback: float = 30.0) -> float:
    """
    컷 경계 row의 fps를 우선 사용한다.
    중요:
    - frame=1950, fps=59.94이면 32.532초가 맞다.
    - frame=1950을 fallback 30fps로 계산하면 65초가 되어 시간이 2배로 밀린다.
    """
    try:
        fallback = normalize_fps(float(fallback or 30.0))
    except Exception:
        fallback = 30.0

    if isinstance(row, dict):
        for key in ("fps", "frame_rate", "timeline_frame_rate"):
            try:
                value = float(row.get(key) or 0.0)
                if value > 1.0:
                    return normalize_fps(value)
            except Exception:
                pass

    return fallback


def normalize_cut_boundaries(
    boundaries: list[dict[str, Any]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    """
    컷 경계 정규화.

    Canonical rule:
    - frame/timeline_frame이 있으면 그것이 기준이다.
    - seconds는 frame / row_fps로만 재계산한다.
    - row에 fps가 있으면 primary_fps보다 row fps를 우선한다.
    """
    try:
        base_fps = normalize_fps(primary_fps or 30.0)
    except Exception:
        base_fps = 30.0

    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for idx, item in enumerate(boundaries or []):
        if not isinstance(item, dict):
            continue

        row = dict(item)
        fps = _cut_boundary_row_fps(row, base_fps)

        frame = None
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            try:
                value = row.get(key)
                if value is not None:
                    frame = int(round(float(value)))
                    break
            except Exception:
                pass

        if frame is None:
            sec = None
            for key in ("timeline_sec", "time", "start", "timeline_start"):
                try:
                    value = row.get(key)
                    if value is not None:
                        sec = float(value)
                        break
                except Exception:
                    pass
            if sec is None:
                continue
            try:
                frame = sec_to_frame(sec, fps)
            except Exception:
                continue

        frame = int(frame)
        if frame <= 0:
            continue

        try:
            sec = frame_to_sec(frame, fps)
        except Exception:
            sec = frame / float(fps or 30.0)

        if sec <= 0.0:
            continue

        key = (frame, int(round(float(fps) * 1000)))
        if key in seen:
            continue
        seen.add(key)

        row.update(
            {
                "schema": "cut_boundary.v1",
                "id": str(row.get("id") or f"cut_{frame:08d}"),
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps,
                "frame_rate": fps,
                "timeline_frame_rate": fps,
                "absolute": True,
                "locked": True,
                "source": str(row.get("source") or "visual"),
            }
        )
        row.setdefault("detector", "opencv-gray-pyramid60")
        row.setdefault("reason", "visual_cut_boundary")
        row.setdefault("index", idx + 1)
        out.append(row)

    out.sort(
        key=lambda item: (
            int(item.get("timeline_frame", item.get("frame", 0)) or 0),
            float(item.get("timeline_sec", 0.0) or 0.0),
        )
    )

    for idx, item in enumerate(out, start=1):
        item["index"] = idx

    return out

# === FRAME FPS NORMALIZE PATCH END ===


# === VIDEO FPS NORMALIZE OVERRIDE START ===

def _cut_boundary_video_paths_from_obj(obj) -> list[str]:
    paths: list[str] = []
    video_exts = (".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm")

    def walk(x):
        if isinstance(x, dict):
            for value in x.values():
                walk(value)
        elif isinstance(x, list):
            for value in x:
                walk(value)
        elif isinstance(x, str):
            raw = x.strip()
            if raw.lower().endswith(video_exts) and os.path.exists(raw):
                paths.append(raw)

    walk(obj)
    return paths


def _cut_boundary_probe_fps(path: str) -> float | None:
    try:
        if not path or not os.path.exists(path):
            return None
        info = probe_media(path)
        fps = float(info.get("fps", 0.0) or 0.0)
        if fps > 1.0:
            return normalize_fps(fps)
    except Exception:
        pass
    return None


def _cut_boundary_fps_from_row(row, fallback: float = 30.0) -> float:
    try:
        fallback = normalize_fps(float(fallback or 30.0))
    except Exception:
        fallback = 30.0

    if not isinstance(row, dict):
        return fallback

    # 1) row 자체 fps 우선
    for key in ("fps", "frame_rate", "timeline_frame_rate", "source_fps", "video_fps"):
        try:
            value = float(row.get(key) or 0.0)
            if value > 1.0:
                return normalize_fps(value)
        except Exception:
            pass

    # 2) row의 source_path 실제 영상 fps
    for key in ("source_path", "clip_file", "file", "media_path", "path"):
        try:
            path = str(row.get(key) or "")
        except Exception:
            path = ""
        fps = _cut_boundary_probe_fps(path)
        if fps:
            return fps

    return fallback


def _cut_boundary_infer_fps(rows=None, project=None, fallback: float = 30.0) -> float:
    try:
        fallback = normalize_fps(float(fallback or 30.0))
    except Exception:
        fallback = 30.0

    rows = list(rows or [])

    # 1) row fps/source_path
    for row in rows:
        fps = _cut_boundary_fps_from_row(row, fallback)
        if abs(float(fps) - float(fallback)) > 0.001 or fps > 30.1:
            return normalize_fps(fps)

    # 2) project timebase
    if isinstance(project, dict):
        for path in (
            ("timeline", "timebase", "primary_fps"),
            ("frame_timebase", "primary_fps"),
            ("timebase", "primary_fps"),
            ("timeline", "fps"),
            ("fps",),
            ("video_fps",),
        ):
            cur = project
            try:
                for key in path:
                    cur = cur.get(key, {})
                value = float(cur or 0.0)
                if value > 1.0:
                    return normalize_fps(value)
            except Exception:
                pass

        # 3) project 내부 영상 파일 probe
        for video_path in _cut_boundary_video_paths_from_obj(project):
            fps = _cut_boundary_probe_fps(video_path)
            if fps:
                return fps

    return fallback


def normalize_cut_boundaries(
    boundaries: list[dict[str, Any]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    """
    컷 경계 정규화.

    Canonical:
    - frame/timeline_frame이 있으면 frame이 기준.
    - seconds는 frame / fps에서 파생.
    - fps는 row.fps 또는 실제 source_path 영상 fps를 우선.
    """
    try:
        base_fps = normalize_fps(primary_fps or 30.0)
    except Exception:
        base_fps = 30.0

    out: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    for idx, item in enumerate(boundaries or []):
        if not isinstance(item, dict):
            continue

        row = dict(item)
        fps = _cut_boundary_fps_from_row(row, base_fps)

        frame = None
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            try:
                value = row.get(key)
                if value is not None:
                    frame = int(round(float(value)))
                    break
            except Exception:
                pass

        if frame is None:
            sec = None
            for key in ("timeline_sec", "time", "start", "timeline_start"):
                try:
                    value = row.get(key)
                    if value is not None:
                        sec = float(value)
                        break
                except Exception:
                    pass

            if sec is None:
                continue

            try:
                frame = sec_to_frame(sec, fps)
            except Exception:
                continue

        frame = int(frame)
        if frame <= 0:
            continue

        try:
            sec = frame_to_sec(frame, fps)
        except Exception:
            sec = frame / float(fps or 30.0)

        if sec <= 0.0:
            continue

        seen_key = (frame, int(round(float(fps) * 1000)))
        if seen_key in seen:
            continue
        seen.add(seen_key)

        row.update(
            {
                "schema": "cut_boundary.v1",
                "id": str(row.get("id") or f"cut_{frame:08d}"),
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps,
                "frame_rate": fps,
                "timeline_frame_rate": fps,
                "absolute": True,
                "locked": True,
                "source": str(row.get("source") or "visual"),
            }
        )
        row.setdefault("detector", "opencv-gray-pyramid60")
        row.setdefault("reason", "visual_cut_boundary")
        row.setdefault("index", idx + 1)

        out.append(row)

    out.sort(
        key=lambda item: (
            int(item.get("timeline_frame", item.get("frame", 0)) or 0),
            float(item.get("timeline_sec", 0.0) or 0.0),
        )
    )

    for idx, item in enumerate(out, start=1):
        item["index"] = idx

    return out


def project_cut_boundaries(project: dict[str, Any] | None, *, primary_fps: float | None = None) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []

    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundaries")

    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundaries")

    if not isinstance(raw, list):
        raw = []

    fps = _cut_boundary_infer_fps(raw, project, primary_fps or 30.0)
    return normalize_cut_boundaries(raw, primary_fps=fps)


def project_cut_provisional_boundaries(
    project: dict[str, Any] | None,
    *,
    primary_fps: float | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []

    analysis = project.get("analysis", {}) or {}
    raw = analysis.get("cut_boundary_provisional_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("analysis", {}) or {}).get("cut_boundary_provisional_boundaries")
    if not isinstance(raw, list):
        raw = ((project.get("editor_state", {}) or {}).get("multiclip", {}) or {}).get("cut_boundary_provisional_boundaries")
    if not isinstance(raw, list):
        raw = []

    fps = _cut_boundary_infer_fps(raw, project, primary_fps or 30.0)
    rows = normalize_cut_boundaries(raw, primary_fps=fps)
    for idx, row in enumerate(rows, start=1):
        row.setdefault("status", "provisional")
        row.setdefault("detector_stage", "pioneer")
        row["index"] = idx
    return rows


def sync_project_cut_boundaries(
    project: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    primary_fps: float = 30.0,
    provisional_boundaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []

    analysis = project.setdefault("analysis", {})
    raw = analysis.get("cut_boundaries", [])

    fps = _cut_boundary_infer_fps(raw if isinstance(raw, list) else [], project, primary_fps or 30.0)
    boundaries = project_cut_boundaries(project, primary_fps=fps)
    if provisional_boundaries is None:
        provisional_rows = project_cut_provisional_boundaries(project, primary_fps=fps)
    else:
        provisional_rows = normalize_cut_boundaries(provisional_boundaries, primary_fps=fps)
        for idx, row in enumerate(provisional_rows, start=1):
            row.setdefault("status", "provisional")
            row.setdefault("detector_stage", "pioneer")
            row["index"] = idx

    analysis["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
    analysis["cut_boundaries"] = boundaries
    analysis["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
    analysis["cut_boundary_provisional_boundaries"] = list(provisional_rows)
    analysis["cut_boundary_settings"] = {
        "enabled": cut_boundary_enabled(settings if settings is not None else project.get("user_settings")),
        "detector": "opencv-gray-pyramid60",
        "count": len(boundaries),
        "provisional_count": len(provisional_rows),
        "absolute": True,
        "locked": True,
        "fps": fps,
    }

    editor_state = project.get("editor_state")
    if isinstance(editor_state, dict):
        editor_state.setdefault("analysis", {})
        editor_state["analysis"]["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        editor_state["analysis"]["cut_boundaries"] = list(boundaries)
        editor_state["analysis"]["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
        editor_state["analysis"]["cut_boundary_provisional_boundaries"] = list(provisional_rows)
        multiclip = editor_state.setdefault("multiclip", {})
        multiclip["cut_boundary_schema"] = CUT_BOUNDARY_SCHEMA
        multiclip["cut_boundaries"] = list(boundaries)
        multiclip["cut_boundary_provisional_schema"] = CUT_BOUNDARY_PROVISIONAL_SCHEMA
        multiclip["cut_boundary_provisional_boundaries"] = list(provisional_rows)

    return boundaries

# === VIDEO FPS NORMALIZE OVERRIDE END ===


# === AUTO GRID V3 VERIFY WRAPPER START ===

def _auto_level_positions(scan_profile=None, sample_positions=None):
    """
    최종 색상 평균 검증에 사용할 grid 위치.
    낮음: 4칸, 중간: 5칸, 높음: 8칸.
    """
    if sample_positions:
        try:
            return tuple(int(x) for x in sample_positions)
        except Exception:
            pass

    profile = scan_profile or {}
    positions = profile.get("positions") if isinstance(profile, dict) else None
    if positions:
        try:
            return tuple(int(x) for x in positions)
        except Exception:
            pass

    level = ""
    if isinstance(profile, dict):
        level = str(profile.get("level", "") or "").lower()

    if level == "low":
        return (1, 3, 5, 7)              # 4칸: 상/좌/우/하
    if level == "high":
        return (0, 1, 2, 3, 4, 5, 6, 7, 8) # 9칸: 3x3 전체

    return (1, 3, 4, 5, 7)              # 5칸: cross5


def _auto_grid_cells(width: int, height: int):
    xs = [0, int(width / 3), int(width * 2 / 3), width]
    ys = [0, int(height / 3), int(height * 2 / 3), height]
    cells = []
    for r in range(3):
        for c in range(3):
            cells.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return cells


def _auto_gray_thumb_from_frame(frame, cv2_mod, *, positions, scale_w: int, scale_h: int):
    try:
        h, w = frame.shape[:2]
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None

    cells = _auto_grid_cells(w, h)
    out = []
    for idx in positions:
        try:
            x1, y1, x2, y2 = cells[int(idx)]
        except Exception:
            continue
        roi = frame[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            continue
        gray = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2GRAY)
        small = cv2_mod.resize(gray, (int(scale_w), int(scale_h)), interpolation=cv2_mod.INTER_AREA)
        out.append(small.tobytes())

    return tuple(out) if out else None


def _auto_color_avg_from_frame(frame, cv2_mod, *, positions, color_space: str = "ycrcb"):
    """
    선택 grid 칸별 평균 색상 벡터를 만든다.
    YCrCb 기준:
      Y는 밝기, Cr/Cb는 색상 성분.
    """
    try:
        h, w = frame.shape[:2]
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None

    color_space = str(color_space or "ycrcb").lower()
    cells = _auto_grid_cells(w, h)
    out = []

    for idx in positions:
        try:
            x1, y1, x2, y2 = cells[int(idx)]
        except Exception:
            continue

        roi = frame[y1:y2, x1:x2]
        if roi is None or roi.size == 0:
            continue

        try:
            if color_space == "hsv":
                converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2HSV)
            elif color_space == "lab":
                converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2LAB)
            else:
                converted = cv2_mod.cvtColor(roi, cv2_mod.COLOR_BGR2YCrCb)

            mean = converted.reshape(-1, 3).mean(axis=0)
            out.append(tuple(float(x) for x in mean))
        except Exception:
            continue

    return tuple(out) if out else None


def _auto_delta_bytes(a: bytes, b: bytes, *, target_samples: int = 64) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0

    target_samples = max(16, min(256, int(target_samples or 64)))
    step = max(1, n // target_samples)

    total = 0
    count = 0
    for i in range(0, n, step):
        total += abs(a[i] - b[i])
        count += 1

    return total / float(count or 1)


def _auto_gray_delta(prev_thumb, next_thumb, *, region_threshold: float, target_samples: int):
    if not prev_thumb or not next_thumb:
        return 0.0, 0, []

    n = min(len(prev_thumb), len(next_thumb))
    deltas = [
        _auto_delta_bytes(prev_thumb[i], next_thumb[i], target_samples=target_samples)
        for i in range(n)
    ]

    hits = sum(1 for d in deltas if d >= region_threshold)
    ranked = sorted(deltas, reverse=True)
    top_n = ranked[: min(3, len(ranked))]
    score = sum(top_n) / float(len(top_n) or 1)
    return float(score), int(hits), deltas


def _auto_color_avg_delta(
    prev_avg,
    next_avg,
    *,
    threshold: float,
    weight_luma: float,
    weight_chroma: float,
):
    if not prev_avg or not next_avg:
        return 0.0, 0, []

    n = min(len(prev_avg), len(next_avg))
    deltas = []

    for i in range(n):
        try:
            a0, a1, a2 = prev_avg[i]
            b0, b1, b2 = next_avg[i]
            luma = abs(float(a0) - float(b0))
            chroma = (abs(float(a1) - float(b1)) + abs(float(a2) - float(b2))) / 2.0
            score = float(weight_luma) * luma + float(weight_chroma) * chroma
            deltas.append(score)
        except Exception:
            continue

    if not deltas:
        return 0.0, 0, []

    hits = sum(1 for d in deltas if d >= threshold)
    score = sum(deltas) / float(len(deltas))
    return float(score), int(hits), deltas


def _mps_available() -> bool:
    try:
        import torch
        return bool(getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available())
    except Exception:
        return False


def _auto_gray_delta_mps(prev_thumb, next_thumb, *, region_threshold: float, target_samples: int):
    try:
        import torch
        if not prev_thumb or not next_thumb:
            return 0.0, 0, []
        n = min(len(prev_thumb), len(next_thumb))
        deltas = []
        target_samples = max(16, min(256, int(target_samples or 64)))
        device = torch.device("mps")
        for i in range(n):
            a = prev_thumb[i]
            b = next_thumb[i]
            if not a or not b:
                continue
            ta = torch.tensor(list(a), dtype=torch.float32, device=device)
            tb = torch.tensor(list(b), dtype=torch.float32, device=device)
            step = max(1, int(min(ta.numel(), tb.numel()) // target_samples))
            diff = torch.abs(ta[::step] - tb[::step])
            deltas.append(float(diff.mean().item()))
        if not deltas:
            return 0.0, 0, []
        hits = sum(1 for d in deltas if d >= region_threshold)
        ranked = sorted(deltas, reverse=True)
        top_n = ranked[: min(3, len(ranked))]
        score = sum(top_n) / float(len(top_n) or 1)
        return float(score), int(hits), deltas
    except Exception:
        return _auto_gray_delta(prev_thumb, next_thumb, region_threshold=region_threshold, target_samples=target_samples)


def _auto_color_avg_delta_mps(
    prev_avg,
    next_avg,
    *,
    threshold: float,
    weight_luma: float,
    weight_chroma: float,
):
    try:
        import torch
        if not prev_avg or not next_avg:
            return 0.0, 0, []
        n = min(len(prev_avg), len(next_avg))
        if n <= 0:
            return 0.0, 0, []
        device = torch.device("mps")
        a = torch.tensor([list(prev_avg[i]) for i in range(n)], dtype=torch.float32, device=device)
        b = torch.tensor([list(next_avg[i]) for i in range(n)], dtype=torch.float32, device=device)
        luma = torch.abs(a[:, 0] - b[:, 0])
        chroma = (torch.abs(a[:, 1] - b[:, 1]) + torch.abs(a[:, 2] - b[:, 2])) / 2.0
        scores = (float(weight_luma) * luma) + (float(weight_chroma) * chroma)
        deltas = [float(x) for x in scores.detach().cpu().tolist()]
        hits = sum(1 for d in deltas if d >= threshold)
        score = sum(deltas) / float(len(deltas) or 1)
        return float(score), int(hits), deltas
    except Exception:
        return _auto_color_avg_delta(
            prev_avg,
            next_avg,
            threshold=threshold,
            weight_luma=weight_luma,
            weight_chroma=weight_chroma,
        )


def _auto_capture_verify_maps(
    cap,
    cv2_mod,
    *,
    start_frame: int,
    end_frame: int,
    frame_count: int,
    positions,
    scale_w: int,
    scale_h: int,
    color_space: str,
):
    start_frame = max(0, int(start_frame))
    end_frame = min(int(frame_count) - 1, int(end_frame))
    if end_frame < start_frame:
        return {}, {}

    gray_map = {}
    color_map = {}

    try:
        cap.set(cv2_mod.CAP_PROP_POS_FRAMES, start_frame)
    except Exception:
        return gray_map, color_map

    f = start_frame
    while f <= end_frame:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        gray_map[f] = _auto_gray_thumb_from_frame(
            frame,
            cv2_mod,
            positions=positions,
            scale_w=scale_w,
            scale_h=scale_h,
        )
        color_map[f] = _auto_color_avg_from_frame(
            frame,
            cv2_mod,
            positions=positions,
            color_space=color_space,
        )
        f += 1

    return gray_map, color_map


def _auto_grid_v3_manual_verify_strict(
    cap,
    cv2_mod,
    *,
    fps: float,
    frame_count: int,
    coarse_frame: int,
    settings: dict | None = None,
    scan_profile=None,
    sample_positions=None,
):
    """
    최종 검증:
    1. gray 1f/2f/window로 후보 위치 확인
    2. 선택 grid 칸의 색상 평균 변화량으로 최종 탈락/통과 결정
    """
    settings = settings or {}

    try:
        fps = float(fps or 30.0)
        frame_count = int(frame_count or 0)
        coarse_frame = int(coarse_frame)
    except Exception:
        return None

    if fps <= 0.0 or frame_count <= 1:
        return None

    positions = _auto_level_positions(scan_profile, sample_positions)
    selected_count = len(positions)

    rollback_frames = int(settings.get("scan_cut_auto_verify_rollback_frames", round(fps * 1.0)))
    forward_frames = int(settings.get("scan_cut_auto_verify_forward_frames", round(fps * 1.0)))
    rollback_frames = max(2, min(240, rollback_frames))
    forward_frames = max(2, min(240, forward_frames))

    strict_multiplier = float(settings.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08)
    gray_1f_threshold = float(settings.get("scan_cut_auto_verify_threshold", 30.0)) * strict_multiplier
    gray_2f_threshold = gray_1f_threshold * float(settings.get("scan_cut_auto_verify_two_frame_threshold_multiplier", 1.15))
    gray_window_threshold = float(settings.get("scan_cut_auto_verify_window_threshold", 90.0)) * strict_multiplier
    gray_region_threshold = float(settings.get("scan_cut_region_threshold", 20.0))

    gray_region_bonus = int(settings.get("scan_cut_follower_strict_region_bonus", 1) or 1)
    gray_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_regions_required", max(3, round(selected_count * 0.6)))) + gray_region_bonus))
    gray_window_required = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_window_regions_required", max(3, round(selected_count * 0.7)))) + gray_region_bonus))

    color_space = str(settings.get("scan_cut_color_verify_space", "ycrcb") or "ycrcb")
    color_threshold = float(settings.get("scan_cut_color_avg_threshold", 18.0)) * strict_multiplier
    color_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_color_avg_regions_required", max(2, round(selected_count * 0.45)))) + gray_region_bonus))
    color_weight_luma = float(settings.get("scan_cut_color_verify_weight_luma", 0.25))
    color_weight_chroma = float(settings.get("scan_cut_color_verify_weight_chroma", 0.75))
    color_window_frames = max(3, int(settings.get("scan_cut_color_avg_window_frames", 30)))

    scale_w = max(8, min(48, int(settings.get("scan_cut_sample_width", 18))))
    scale_h = max(6, min(27, int(settings.get("scan_cut_sample_height", 10))))
    target_samples = max(16, min(256, int(settings.get("scan_cut_target_samples", 64))))

    try:
        stages_raw = settings.get("scan_cut_auto_verify_window_stages", [30, 15, 6, 3, 1])
        if isinstance(stages_raw, str):
            stages = [max(1, int(x.strip())) for x in stages_raw.split(",") if x.strip()]
        else:
            stages = [max(1, int(x)) for x in list(stages_raw or [30, 15, 6, 3, 1])]
    except Exception:
        stages = [30, 15, 6, 3, 1]

    if 1 not in stages:
        stages.append(1)

    max_stage = max(max(stages or [1]), color_window_frames)

    lo = max(0, coarse_frame - rollback_frames)
    hi = min(frame_count - 2, coarse_frame + forward_frames)
    read_hi = min(frame_count - 1, hi + max_stage + 1)

    gray_map, color_map = _auto_capture_verify_maps(
        cap,
        cv2_mod,
        start_frame=lo,
        end_frame=read_hi,
        frame_count=frame_count,
        positions=positions,
        scale_w=scale_w,
        scale_h=scale_h,
        color_space=color_space,
    )

    if not gray_map:
        return None

    # gray 1f/2f
    best_adj = {
        "frame": None,
        "score": -1.0,
        "regions": 0,
        "deltas": [],
        "mode": "1f",
        "threshold": gray_1f_threshold,
    }

    def consider_adj(mode, frame_no, score, regions, deltas, threshold):
        norm = (float(score) / float(threshold or 1.0)) + min(int(regions), gray_required_regions) * 0.03
        old_norm = (float(best_adj["score"]) / float(best_adj["threshold"] or 1.0)) + min(int(best_adj["regions"]), gray_required_regions) * 0.03
        if best_adj["frame"] is None or norm > old_norm:
            best_adj.update({
                "frame": int(frame_no),
                "score": float(score),
                "regions": int(regions),
                "deltas": list(deltas or []),
                "mode": str(mode),
                "threshold": float(threshold),
            })

    for f in range(lo, hi + 1):
        a1 = gray_map.get(f)
        b1 = gray_map.get(f + 1)
        if a1 is not None and b1 is not None:
            score, regions, deltas = _auto_gray_delta(
                a1,
                b1,
                region_threshold=gray_region_threshold,
                target_samples=target_samples,
            )
            consider_adj("1f", f, score, regions, deltas, gray_1f_threshold)

        a2 = gray_map.get(f)
        b2 = gray_map.get(f + 2)
        if a2 is not None and b2 is not None:
            score, regions, deltas = _auto_gray_delta(
                a2,
                b2,
                region_threshold=gray_region_threshold,
                target_samples=target_samples,
            )
            consider_adj("2f", f + 1, score, regions, deltas, gray_2f_threshold)

    # gray window rollback
    best_win = {
        "frame": None,
        "score": -1.0,
        "regions": 0,
        "deltas": [],
        "stage": 0,
    }

    cur_lo = lo
    cur_hi = hi

    for stage in stages:
        stage = max(1, int(stage))
        step = max(1, stage // 2)

        local_frame = None
        local_score = -1.0
        local_regions = 0
        local_deltas = []

        f = int(cur_lo)
        while f <= int(cur_hi):
            a = gray_map.get(f)
            b = gray_map.get(f + stage)
            if a is not None and b is not None:
                score, regions, deltas = _auto_gray_delta(
                    a,
                    b,
                    region_threshold=gray_region_threshold,
                    target_samples=target_samples,
                )
                if score > local_score:
                    local_frame = int(f)
                    local_score = float(score)
                    local_regions = int(regions)
                    local_deltas = list(deltas or [])
            f += step

        if local_frame is None:
            continue

        if local_score > best_win["score"]:
            best_win.update({
                "frame": int(local_frame),
                "score": float(local_score),
                "regions": int(local_regions),
                "deltas": list(local_deltas),
                "stage": int(stage),
            })

        cur_lo = max(lo, local_frame - stage)
        cur_hi = min(hi, local_frame + stage)

    gray_adj_pass = (
        best_adj["frame"] is not None
        and best_adj["score"] >= best_adj["threshold"]
        and best_adj["regions"] >= gray_required_regions
    )

    gray_window_pass = (
        best_win["frame"] is not None
        and best_win["score"] >= gray_window_threshold
        and best_win["regions"] >= gray_window_required
    )

    # color average final gate
    color_center = best_win["frame"] if best_win["frame"] is not None else best_adj["frame"]
    if color_center is None:
        color_center = coarse_frame

    color_lo = max(lo, int(color_center) - color_window_frames)
    color_hi = min(hi, int(color_center) + color_window_frames)

    best_color = {
        "frame": None,
        "score": -1.0,
        "regions": 0,
        "deltas": [],
    }

    step = max(1, color_window_frames // 2)
    f = color_lo
    while f <= color_hi:
        a = color_map.get(f)
        b = color_map.get(f + color_window_frames)
        if a is not None and b is not None:
            score, regions, deltas = _auto_color_avg_delta(
                a,
                b,
                threshold=color_threshold,
                weight_luma=color_weight_luma,
                weight_chroma=color_weight_chroma,
            )
            if score > best_color["score"]:
                best_color.update({
                    "frame": int(f),
                    "score": float(score),
                    "regions": int(regions),
                    "deltas": list(deltas or []),
                })
        f += step

    gray_super_strong_for_color = (
        best_win["frame"] is not None
        and best_win["score"] >= float(settings.get("scan_cut_auto_gray_super_strong_threshold", 110.0))
        and best_win["regions"] >= max(1, min(selected_count, int(round(selected_count * 0.85))))
    )

    relaxed_color_required_regions = color_required_regions
    if gray_super_strong_for_color:
        relaxed_color_required_regions = max(1, color_required_regions - int(settings.get("scan_cut_color_avg_super_strong_relax_regions", 2)))

    color_pass = (
        best_color["frame"] is not None
        and best_color["score"] >= color_threshold
        and best_color["regions"] >= relaxed_color_required_regions
    )

    # gray 통과 조건
    gray_pass = gray_adj_pass or gray_window_pass

    if not gray_pass:
        return {"passed": False, "reason": "gray_failed"}

    if not color_pass:
        return {"passed": False, "reason": "color_avg_failed"}

    # 통과 위치 선택
    if gray_window_pass:
        selected_frame = int(best_win["frame"])
        selected_score = float(best_win["score"])
        selected_regions = int(best_win["regions"])
        selected_mode = "gray_window_color_avg"
        selected_deltas = list(best_win["deltas"])
    else:
        selected_frame = int(best_adj["frame"])
        selected_score = float(best_adj["score"])
        selected_regions = int(best_adj["regions"])
        selected_mode = "gray_adj_color_avg"
        selected_deltas = list(best_adj["deltas"])

    return {
        "passed": True,
        "mode": selected_mode,
        "reason": selected_mode,
        "frame": selected_frame,
        "sec": float(selected_frame / fps),
        "score": selected_score,
        "regions": selected_regions,
        "deltas": selected_deltas,
        "color_score": float(best_color["score"]),
        "color_regions": int(best_color["regions"]),
        "color_deltas": list(best_color["deltas"]),
        "grid_cells": selected_count,
    }


def _auto_grid_v3_manual_verify_strict_mps(
    cap,
    cv2_mod,
    *,
    fps: float,
    frame_count: int,
    coarse_frame: int,
    settings: dict | None = None,
    scan_profile=None,
    sample_positions=None,
):
    if not _mps_available():
        return _auto_grid_v3_manual_verify_strict(
            cap,
            cv2_mod,
            fps=fps,
            frame_count=frame_count,
            coarse_frame=coarse_frame,
            settings=settings,
            scan_profile=scan_profile,
            sample_positions=sample_positions,
        )

    settings = settings or {}
    try:
        fps = float(fps or 30.0)
        frame_count = int(frame_count or 0)
        coarse_frame = int(coarse_frame)
    except Exception:
        return None
    if fps <= 0.0 or frame_count <= 1:
        return None

    positions = _auto_level_positions(scan_profile, sample_positions)
    selected_count = len(positions)
    rollback_frames = max(2, min(240, int(settings.get("scan_cut_auto_verify_rollback_frames", round(fps * 1.0)))))
    forward_frames = max(2, min(240, int(settings.get("scan_cut_auto_verify_forward_frames", round(fps * 1.0)))))
    strict_multiplier = float(settings.get("scan_cut_follower_strict_multiplier", 1.08) or 1.08)
    gray_1f_threshold = float(settings.get("scan_cut_auto_verify_threshold", 30.0)) * strict_multiplier
    gray_2f_threshold = gray_1f_threshold * float(settings.get("scan_cut_auto_verify_two_frame_threshold_multiplier", 1.15))
    gray_window_threshold = float(settings.get("scan_cut_auto_verify_window_threshold", 90.0)) * strict_multiplier
    gray_region_threshold = float(settings.get("scan_cut_region_threshold", 20.0))
    gray_region_bonus = int(settings.get("scan_cut_follower_strict_region_bonus", 1) or 1)
    gray_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_regions_required", max(3, round(selected_count * 0.6)))) + gray_region_bonus))
    gray_window_required = max(1, min(selected_count, int(settings.get("scan_cut_auto_verify_window_regions_required", max(3, round(selected_count * 0.7)))) + gray_region_bonus))
    color_space = str(settings.get("scan_cut_color_verify_space", "ycrcb") or "ycrcb")
    color_threshold = float(settings.get("scan_cut_color_avg_threshold", 18.0)) * strict_multiplier
    color_required_regions = max(1, min(selected_count, int(settings.get("scan_cut_color_avg_regions_required", max(2, round(selected_count * 0.45)))) + gray_region_bonus))
    color_weight_luma = float(settings.get("scan_cut_color_verify_weight_luma", 0.25))
    color_weight_chroma = float(settings.get("scan_cut_color_verify_weight_chroma", 0.75))
    color_window_frames = max(3, int(settings.get("scan_cut_color_avg_window_frames", 30)))
    scale_w = max(8, min(48, int(settings.get("scan_cut_sample_width", 18))))
    scale_h = max(6, min(27, int(settings.get("scan_cut_sample_height", 10))))
    target_samples = max(16, min(256, int(settings.get("scan_cut_target_samples", 64))))
    try:
        stages_raw = settings.get("scan_cut_auto_verify_window_stages", [30, 15, 6, 3, 1])
        stages = [max(1, int(x.strip())) for x in stages_raw.split(",") if x.strip()] if isinstance(stages_raw, str) else [max(1, int(x)) for x in list(stages_raw or [30, 15, 6, 3, 1])]
    except Exception:
        stages = [30, 15, 6, 3, 1]
    if 1 not in stages:
        stages.append(1)
    max_stage = max(max(stages or [1]), color_window_frames)
    lo = max(0, coarse_frame - rollback_frames)
    hi = min(frame_count - 2, coarse_frame + forward_frames)
    read_hi = min(frame_count - 1, hi + max_stage + 1)
    gray_map, color_map = _auto_capture_verify_maps(
        cap,
        cv2_mod,
        start_frame=lo,
        end_frame=read_hi,
        frame_count=frame_count,
        positions=positions,
        scale_w=scale_w,
        scale_h=scale_h,
        color_space=color_space,
    )
    if not gray_map:
        return None
    best_adj = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "mode": "1f", "threshold": gray_1f_threshold}
    def consider_adj(mode, frame_no, score, regions, deltas, threshold):
        norm = (float(score) / float(threshold or 1.0)) + min(int(regions), gray_required_regions) * 0.03
        old_norm = (float(best_adj["score"]) / float(best_adj["threshold"] or 1.0)) + min(int(best_adj["regions"]), gray_required_regions) * 0.03
        if best_adj["frame"] is None or norm > old_norm:
            best_adj.update({"frame": int(frame_no), "score": float(score), "regions": int(regions), "deltas": list(deltas or []), "mode": str(mode), "threshold": float(threshold)})
    for f in range(lo, hi + 1):
        a1 = gray_map.get(f); b1 = gray_map.get(f + 1)
        if a1 is not None and b1 is not None:
            score, regions, deltas = _auto_gray_delta_mps(a1, b1, region_threshold=gray_region_threshold, target_samples=target_samples)
            consider_adj("1f", f, score, regions, deltas, gray_1f_threshold)
        a2 = gray_map.get(f); b2 = gray_map.get(f + 2)
        if a2 is not None and b2 is not None:
            score, regions, deltas = _auto_gray_delta_mps(a2, b2, region_threshold=gray_region_threshold, target_samples=target_samples)
            consider_adj("2f", f + 1, score, regions, deltas, gray_2f_threshold)
    best_win = {"frame": None, "score": -1.0, "regions": 0, "deltas": [], "stage": 0}
    cur_lo = lo; cur_hi = hi
    for stage in stages:
        stage = max(1, int(stage)); step = max(1, stage // 2)
        local_frame = None; local_score = -1.0; local_regions = 0; local_deltas = []
        f = int(cur_lo)
        while f <= int(cur_hi):
            a = gray_map.get(f); b = gray_map.get(f + stage)
            if a is not None and b is not None:
                score, regions, deltas = _auto_gray_delta_mps(a, b, region_threshold=gray_region_threshold, target_samples=target_samples)
                if score > local_score:
                    local_frame = int(f); local_score = float(score); local_regions = int(regions); local_deltas = list(deltas or [])
            f += step
        if local_frame is None:
            continue
        if local_score > best_win["score"]:
            best_win.update({"frame": int(local_frame), "score": float(local_score), "regions": int(local_regions), "deltas": list(local_deltas), "stage": int(stage)})
        cur_lo = max(lo, local_frame - stage); cur_hi = min(hi, local_frame + stage)
    gray_adj_pass = best_adj["frame"] is not None and best_adj["score"] >= best_adj["threshold"] and best_adj["regions"] >= gray_required_regions
    gray_window_pass = best_win["frame"] is not None and best_win["score"] >= gray_window_threshold and best_win["regions"] >= gray_window_required
    color_center = best_win["frame"] if best_win["frame"] is not None else best_adj["frame"]
    if color_center is None:
        color_center = coarse_frame
    color_lo = max(lo, int(color_center) - color_window_frames)
    color_hi = min(hi, int(color_center) + color_window_frames)
    best_color = {"frame": None, "score": -1.0, "regions": 0, "deltas": []}
    step = max(1, color_window_frames // 2)
    f = color_lo
    while f <= color_hi:
        a = color_map.get(f); b = color_map.get(f + color_window_frames)
        if a is not None and b is not None:
            score, regions, deltas = _auto_color_avg_delta_mps(a, b, threshold=color_threshold, weight_luma=color_weight_luma, weight_chroma=color_weight_chroma)
            if score > best_color["score"]:
                best_color.update({"frame": int(f), "score": float(score), "regions": int(regions), "deltas": list(deltas or [])})
        f += step
    gray_super_strong_for_color = best_win["frame"] is not None and best_win["score"] >= float(settings.get("scan_cut_auto_gray_super_strong_threshold", 110.0)) and best_win["regions"] >= max(1, min(selected_count, int(round(selected_count * 0.85))))
    relaxed_color_required_regions = max(1, color_required_regions - int(settings.get("scan_cut_color_avg_super_strong_relax_regions", 2))) if gray_super_strong_for_color else color_required_regions
    gray_pass = gray_adj_pass or gray_window_pass
    color_pass = best_color["frame"] is not None and best_color["score"] >= color_threshold and best_color["regions"] >= relaxed_color_required_regions
    if not gray_pass:
        return {"passed": False, "reason": "gray_failed"}
    if not color_pass:
        return {"passed": False, "reason": "color_avg_failed"}
    if gray_window_pass:
        selected_frame = int(best_win["frame"]); selected_score = float(best_win["score"]); selected_regions = int(best_win["regions"]); selected_mode = "gray_window_color_avg_mps"; selected_deltas = list(best_win["deltas"])
    else:
        selected_frame = int(best_adj["frame"]); selected_score = float(best_adj["score"]); selected_regions = int(best_adj["regions"]); selected_mode = "gray_adj_color_avg_mps"; selected_deltas = list(best_adj["deltas"])
    return {
        "passed": True,
        "mode": selected_mode,
        "reason": selected_mode,
        "frame": selected_frame,
        "sec": float(selected_frame / fps),
        "score": selected_score,
        "regions": selected_regions,
        "deltas": selected_deltas,
        "color_score": float(best_color["score"]),
        "color_regions": int(best_color["regions"]),
        "color_deltas": list(best_color["deltas"]),
        "grid_cells": selected_count,
    }


_auto_grid_v3_original_detect_media_cut_boundaries = detect_media_cut_boundaries


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
                    required_ratio = {"low": 0.87, "medium": 0.82, "high": 0.72}.get(level, 0.82)
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

# === AUTO GRID V3 STRICT COLOR AVG VERIFY END ===


# === CUT BOUNDARY 5X5 CUSTOM PROFILE START ===

# 5×5 index:
#  0  1  2  3  4
#  5  6  7  8  9
# 10 11 12 13 14
# 15 16 17 18 19
# 20 21 22 23 24

CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "사용안함"),
    ("low", "중간 - 5×5 선택 9칸"),
    ("medium", "높음 - 5×5 선택 13칸"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    "off": {
        "level": "off",
        "label": "사용안함",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "중간 - 5×5 선택 9칸",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "custom9",
        "positions": (1, 3, 7, 10, 12, 14, 17, 21, 23),
        "cell_count": 9,
    },
    "medium": {
        "level": "medium",
        "label": "높음 - 5×5 선택 13칸",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "custom13",
        "positions": (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24),
        "cell_count": 13,
    },
}


def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
    level = cut_boundary_level(settings or {})
    profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
    profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
    return profile


def _grid_cell_slices(width: int, height: int):
    """
    5×5 grid cell slices.
    index:
      0  1  2  3  4
      5  6  7  8  9
     10 11 12 13 14
     15 16 17 18 19
     20 21 22 23 24
    """
    xs = [
        0,
        width // 5,
        (width * 2) // 5,
        (width * 3) // 5,
        (width * 4) // 5,
        width,
    ]
    ys = [
        0,
        height // 5,
        (height * 2) // 5,
        (height * 3) // 5,
        (height * 4) // 5,
        height,
    ]

    cells = []
    for r in range(5):
        for c in range(5):
            cells.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return cells


def _auto_5x5_positions_for_level(level: str):
    level = str(level or "medium").lower()
    if level == "low":
        return (1, 3, 7, 10, 12, 14, 17, 21, 23)
    return (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24)


def _auto_level_positions(scan_profile=None, sample_positions=None):
    """
    strict color avg 검증에서 사용할 5×5 grid 위치.
    기존 3×3 sample_positions가 들어와도 level 기준 5×5로 재해석한다.
    """
    profile = scan_profile or {}
    level = ""
    if isinstance(profile, dict):
        level = str(profile.get("level", "") or "").lower()

    if isinstance(profile, dict) and int(profile.get("grid_size", 5) or 5) == 5:
        positions = profile.get("positions")
        if positions:
            try:
                return tuple(int(x) for x in positions)
            except Exception:
                pass

    return _auto_5x5_positions_for_level(level or "medium")


def _auto_grid_cells(width: int, height: int):
    """
    strict color avg 검증용 5×5 grid cells.
    """
    return _grid_cell_slices(width, height)

# === CUT BOUNDARY 5X5 CUSTOM PROFILE END ===
