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


def _visual_boundary_strength(row: dict[str, Any]) -> float:
    return max(
        _row_float(row, ("fusion_score",), 0.0),
        _row_float(row, ("score",), 0.0),
        _row_float(row, ("color_score",), 0.0),
        _row_float(row, ("delta",), 0.0),
        _row_float(row, ("window_score",), 0.0),
    )


def _is_middle_snap_only(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if bool(row.get("middle_snap_only")):
        return True
    if bool(row.get("verified") or row.get("confirmed") or row.get("visual_verify_skipped")):
        return False
    status = str(row.get("status", "") or "").strip().lower()
    if status in {"verified", "confirmed", "accepted", "done"}:
        return False
    return bool(row.get("follower_relocated") or row.get("rollback_relocated"))


def _boundary_priority_score(row: dict[str, Any], *, audio_supported: bool, hard: bool) -> float:
    score = max(
        _row_float(row, ("fusion_score",), 0.0),
        _row_float(row, ("score",), 0.0),
        _row_float(row, ("color_score",), 0.0),
        _row_float(row, ("delta",), 0.0),
        _row_float(row, ("window_score",), 0.0),
        _row_float(row, ("audio_gain_db_delta",), 0.0),
    )
    if audio_supported:
        score += 10_000.0
    if hard:
        score += 1_000.0
    return float(score)


def _candidate_is_better(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = (
        1 if bool(left.get("audio_supported")) else 0,
        1 if bool(left.get("hard")) else 0,
        float(left.get("priority_score", 0.0) or 0.0),
        int(left.get("frame", 0) or 0),
    )
    right_key = (
        1 if bool(right.get("audio_supported")) else 0,
        1 if bool(right.get("hard")) else 0,
        float(right.get("priority_score", 0.0) or 0.0),
        int(right.get("frame", 0) or 0),
    )
    return left_key > right_key


def _snap_audio_anchor_to_visual_boundary(
    candidate: dict[str, Any],
    *,
    candidates: list[dict[str, Any]],
    snap_window_frame: int,
) -> tuple[int, bool]:
    frame = int(candidate.get("frame", 0) or 0)
    hard = bool(candidate.get("hard"))
    if not bool(candidate.get("audio_supported")) or snap_window_frame <= 0:
        return frame, hard

    best_visual: dict[str, Any] | None = None
    best_key: tuple[float, float, float, float] | None = None
    for other in list(candidates or []):
        other_frame = int(other.get("frame", 0) or 0)
        if other_frame <= 0 or abs(other_frame - frame) > int(snap_window_frame):
            continue
        visual_strength = _visual_boundary_strength(dict(other.get("row") or {}))
        if visual_strength <= 0.0:
            continue
        compare_key = (
            1.0 if not bool(other.get("audio_supported")) else 0.0,
            float(visual_strength),
            1.0 if bool(other.get("hard")) else 0.0,
            -abs(other_frame - frame),
        )
        if best_key is None or compare_key > best_key:
            best_key = compare_key
            best_visual = other

    if best_visual is None:
        return frame, hard
    return int(best_visual.get("frame", frame) or frame), bool(hard or best_visual.get("hard"))


def _candidate_meets_middle_gap(
    candidate: dict[str, Any],
    *,
    last_frame: int,
    min_frame: int,
    hard_min_frame: int,
    audio_min_frame: int,
) -> bool:
    distance = int(candidate.get("frame", 0) or 0) - int(last_frame or 0)
    if distance >= int(min_frame):
        return True
    if bool(candidate.get("audio_supported")) and distance >= int(audio_min_frame):
        return True
    if bool(candidate.get("hard")) and distance >= int(hard_min_frame):
        return True
    return False


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
        audio_priority_min_segment_sec = float(
            settings.get("scan_cut_topicless_audio_priority_min_segment_sec", 24.0) or 24.0
        )
    except Exception:
        audio_priority_min_segment_sec = 24.0
    try:
        audio_priority_window_sec = float(
            settings.get("scan_cut_topicless_audio_priority_window_sec", 12.0) or 12.0
        )
    except Exception:
        audio_priority_window_sec = 12.0
    try:
        audio_snap_visual_window_sec = float(
            settings.get("scan_cut_topicless_audio_snap_visual_window_sec", 8.0) or 8.0
        )
    except Exception:
        audio_snap_visual_window_sec = 8.0
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
    audio_min_frame = max(1, sec_to_frame(max(0.0, audio_priority_min_segment_sec), fps_value))
    audio_priority_window_frame = max(0, sec_to_frame(max(0.0, audio_priority_window_sec), fps_value))
    audio_snap_visual_window_frame = max(0, sec_to_frame(max(0.0, audio_snap_visual_window_sec), fps_value))
    duration_frame = max(0, int(duration_frame or 0))

    candidates: list[dict[str, Any]] = []
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
        audio_supported = _is_audio_supported_middle_boundary(item, audio_delta_db=audio_delta_db)
        hard = (
            audio_supported
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
        candidates.append(
            {
                "frame": int(frame),
                "row": row,
                "hard": bool(hard),
                "audio_supported": bool(audio_supported),
                "snap_only": bool(_is_middle_snap_only(row)),
                "priority_score": _boundary_priority_score(
                    row,
                    audio_supported=bool(audio_supported),
                    hard=bool(hard),
                ),
            }
        )
    candidates.sort(key=lambda item: int(item.get("frame", 0) or 0))
    selectable_candidates = [item for item in candidates if not bool(item.get("snap_only"))]

    selected: list[tuple[int, bool]] = []
    last_frame = 0
    index = 0
    while index < len(selectable_candidates):
        candidate = selectable_candidates[index]
        if not _candidate_meets_middle_gap(
            candidate,
            last_frame=last_frame,
            min_frame=min_frame,
            hard_min_frame=hard_min_frame,
            audio_min_frame=audio_min_frame,
        ):
            index += 1
            continue

        best = candidate
        lookahead = index + 1
        while lookahead < len(selectable_candidates):
            next_candidate = selectable_candidates[lookahead]
            if int(next_candidate.get("frame", 0) or 0) - int(candidate.get("frame", 0) or 0) > audio_priority_window_frame:
                break
            if _candidate_meets_middle_gap(
                next_candidate,
                last_frame=last_frame,
                min_frame=min_frame,
                hard_min_frame=hard_min_frame,
                audio_min_frame=audio_min_frame,
            ) and _candidate_is_better(next_candidate, best):
                best = next_candidate
            lookahead += 1

        selected_frame, selected_hard = _snap_audio_anchor_to_visual_boundary(
            best,
            candidates=candidates,
            snap_window_frame=audio_snap_visual_window_frame,
        )
        selected_frame = max(last_frame + 1, int(selected_frame or 0))
        selected.append(
            (
                selected_frame,
                bool(selected_hard) or bool(best.get("audio_supported")),
            )
        )
        last_frame = selected_frame
        index = max(lookahead, index + 1)

    if duration_frame > 0:
        while selected and (duration_frame - selected[-1][0]) < min_frame and not selected[-1][1]:
            selected.pop()

    return [frame for frame, _hard in selected]


__all__ = ["coalesce_topicless_middle_boundary_frames"]
