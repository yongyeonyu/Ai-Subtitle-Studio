"""Coarse middle-segment boundary selection from fine cut boundaries."""
from __future__ import annotations

from typing import Any

from core.cut_boundary_audio import is_audio_gain_boundary
from core.cut_boundary_fusion import score_fused_boundary_row
from core.frame_time import normalize_fps, sec_to_frame
from core.personalization.deep_subtitle_policy import score_cut_boundary


def _row_float(row: dict[str, Any], keys: tuple[str, ...], default: float = 0.0) -> float:
    for key in keys:
        try:
            value = row.get(key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return float(default)


def _row_frame(row: dict[str, Any], fps: float) -> int | None:
    for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
        try:
            value = row.get(key)
            if value is not None:
                frame = int(value)
                if frame > 0:
                    return frame
        except Exception:
            pass
    for key in ("timeline_sec", "time", "start", "timeline_start"):
        try:
            sec = float(row.get(key) or 0.0)
            if sec > 0.0:
                return sec_to_frame(sec, fps)
        except Exception:
            pass
    return None


def _is_audio_supported_middle_boundary(row: dict[str, Any], *, audio_delta_db: float) -> bool:
    if is_audio_gain_boundary(row):
        return True
    return abs(_row_float(row, ("audio_gain_db_delta",), 0.0)) >= float(audio_delta_db or 0.0)


def _is_visual_hard_middle_boundary(row: dict[str, Any], *, visual_score: float) -> bool:
    score = max(
        _row_float(row, ("score",), 0.0),
        _row_float(row, ("color_score",), 0.0),
        _row_float(row, ("delta",), 0.0),
        _row_float(row, ("window_score",), 0.0),
    )
    return score >= float(visual_score or 0.0)


def coalesce_topicless_middle_boundary_frames(
    cut_boundaries,
    *,
    fps: float = 30.0,
    duration_frame: int = 0,
    settings: dict | None = None,
) -> list[int]:
    """Return coarse boundaries for middle placeholders.

    Fine visual cuts are still kept elsewhere. This selector prevents every
    camera/rollback cut from becoming a separate roughcut middle segment.
    """
    settings = dict(settings or {})
    fps_value = normalize_fps(fps or 30.0)
    try:
        min_segment_sec = float(settings.get("scan_cut_topicless_min_segment_sec", 120.0) or 120.0)
    except Exception:
        min_segment_sec = 120.0
    try:
        hard_min_segment_sec = float(settings.get("scan_cut_topicless_hard_min_segment_sec", 45.0) or 45.0)
    except Exception:
        hard_min_segment_sec = 45.0
    try:
        audio_delta_db = float(settings.get("scan_cut_topicless_audio_hard_delta_db", 8.0) or 8.0)
    except Exception:
        audio_delta_db = 8.0
    try:
        visual_score = float(settings.get("scan_cut_topicless_visual_hard_score", 140.0) or 140.0)
    except Exception:
        visual_score = 140.0

    min_frame = max(1, sec_to_frame(max(0.0, min_segment_sec), fps_value))
    hard_min_frame = max(1, sec_to_frame(max(0.0, hard_min_segment_sec), fps_value))
    duration_frame = max(0, int(duration_frame or 0))

    candidates: list[tuple[int, dict[str, Any], bool]] = []
    seen: set[int] = set()
    for item in list(cut_boundaries or []):
        if not isinstance(item, dict):
            continue
        frame = _row_frame(item, fps_value)
        if frame is None or frame <= 0:
            continue
        if duration_frame > 0 and frame >= duration_frame:
            continue
        if frame in seen:
            continue
        seen.add(frame)
        deep_boundary = score_cut_boundary(item, settings)
        fusion_boundary = score_fused_boundary_row(item, settings)
        hard = (
            _is_audio_supported_middle_boundary(item, audio_delta_db=audio_delta_db)
            or _is_visual_hard_middle_boundary(item, visual_score=visual_score)
            or str(deep_boundary.get("decision") or "") in {"keep", "verify"}
            or str(fusion_boundary.get("decision") or "") in {"keep", "verify", "roughcut_boundary"}
        )
        row = dict(item)
        if fusion_boundary:
            row["_cut_boundary_fusion"] = fusion_boundary
            row["fusion_score"] = fusion_boundary.get("score", 0.0)
            row["fusion_decision"] = fusion_boundary.get("decision", "")
            row["fusion_sources"] = fusion_boundary.get("sources", [])
        candidates.append((int(frame), row, bool(hard)))
    candidates.sort(key=lambda item: item[0])

    selected: list[tuple[int, bool]] = []
    last_frame = 0
    for frame, _row, hard in candidates:
        distance = int(frame) - int(last_frame)
        if distance >= min_frame or (hard and distance >= hard_min_frame):
            selected.append((int(frame), bool(hard)))
            last_frame = int(frame)

    if duration_frame > 0:
        while selected and (duration_frame - selected[-1][0]) < min_frame and not selected[-1][1]:
            selected.pop()

    return [frame for frame, _hard in selected]


__all__ = ["coalesce_topicless_middle_boundary_frames"]
