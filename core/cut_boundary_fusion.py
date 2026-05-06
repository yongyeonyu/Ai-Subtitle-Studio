"""Cut-boundary fusion for roughcut segmentation.

Visual cuts remain the only default hard cut source. Audio, silence, and STT
context shifts are treated as rough boundary evidence that can help major/minor
roughcut grouping without pretending to be frame-accurate scene cuts.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from core.cut_boundary_audio import AUDIO_GAIN_LINE_COLOR, is_audio_gain_boundary
from core.frame_time import normalize_fps, sec_to_frame
from core.personalization.deep_subtitle_policy import score_cut_boundary


CUT_BOUNDARY_FUSION_SCHEMA = "ai_subtitle_studio.cut_boundary_fusion.v1"
SILENCE_BOUNDARY_SOURCE = "silence_gap_boundary"
STT_CONTEXT_BOUNDARY_SOURCE = "stt_context_shift_boundary"
FUSED_BOUNDARY_SOURCE = "cut_boundary_fusion"
SILENCE_LINE_COLOR = "#B6FF00"
STT_CONTEXT_LINE_COLOR = "#00E5FF"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return number


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "keep", "confirmed"}:
            return True
        if lowered in {"0", "false", "no", "off", "drop", "provisional"}:
            return False
    if value is None:
        return bool(default)
    return bool(value)


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    return max(float(low), min(float(high), _safe_float(value, default)))


def boundary_time_sec(row: Any, *, fps: float = 30.0) -> float | None:
    """Return an absolute boundary time from a row, SceneChange, or number."""
    if row is None:
        return None
    if isinstance(row, (int, float)):
        value = _safe_float(row, -1.0)
        return value if value > 0.0 else None
    if isinstance(row, dict):
        for key in ("time", "timeline_sec", "sec", "seconds", "timestamp", "start", "pos"):
            if key in row:
                value = _safe_float(row.get(key), -1.0)
                if value > 0.0:
                    return value
        for key in ("timeline_frame", "frame", "start_frame", "timeline_start_frame"):
            if key in row:
                frame = _safe_float(row.get(key), -1.0)
                if frame > 0.0:
                    return frame / normalize_fps(row.get("fps") or row.get("frame_rate") or fps or 30.0)
        return None
    start = getattr(row, "start", None)
    end = getattr(row, "end", None)
    if start is not None and end is not None:
        left = _safe_float(start, -1.0)
        right = _safe_float(end, left)
        if right >= left > 0.0:
            return (left + right) * 0.5
        if right > 0.0:
            return right
    for key in ("time", "sec", "seconds", "timestamp", "pos"):
        if hasattr(row, key):
            value = _safe_float(getattr(row, key), -1.0)
            if value > 0.0:
                return value
    return None


def _normalize_scene_boundary_row(item: Any, *, fps: float = 30.0) -> dict[str, Any] | None:
    fps_value = normalize_fps(fps or 30.0)
    sec = boundary_time_sec(item, fps=fps_value)
    if sec is None or sec <= 0.0:
        return None
    frame = sec_to_frame(sec, fps_value)

    if isinstance(item, dict):
        row = dict(item)
        if str(row.get("fusion_decision") or "").strip().lower() == "drop_hint":
            return None
        row.setdefault("source", "visual_cut")
        row.setdefault("detector", "visual-scene-change")
    else:
        is_cut = _safe_bool(getattr(item, "is_cut", True), True)
        if not is_cut:
            return None
        score = _safe_float(getattr(item, "score", 0.0), 0.0)
        row = {
            "source": "visual_cut",
            "detector": "visual-scene-change",
            "score": score,
            "is_cut": True,
        }
    row.setdefault("schema", "cut_boundary.v1")
    row.setdefault("time", round(sec, 3))
    row.setdefault("timeline_sec", round(sec, 3))
    row.setdefault("frame", frame)
    row.setdefault("timeline_frame", frame)
    row.setdefault("fps", fps_value)
    row.setdefault("status", "confirmed")
    row.setdefault("verified", True)
    row.setdefault("boundary_role", "hard_cut")
    row.setdefault("hard_cut_allowed", True)
    return row


def boundary_rows_from_scene_changes(scene_changes: Iterable[Any] | None, *, fps: float = 30.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list(scene_changes or []):
        row = _normalize_scene_boundary_row(item, fps=fps)
        if row is not None:
            rows.append(row)
    return rows


def _segment_start(segment: Any) -> float:
    if isinstance(segment, dict):
        return _safe_float(segment.get("start"), 0.0)
    return _safe_float(getattr(segment, "start", 0.0), 0.0)


def _segment_end(segment: Any) -> float:
    if isinstance(segment, dict):
        return _safe_float(segment.get("end"), _segment_start(segment))
    return _safe_float(getattr(segment, "end", _segment_start(segment)), _segment_start(segment))


def _segment_text(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("text") or "").strip()
    return str(getattr(segment, "text", "") or "").strip()


def _ordered_segments(segments: Iterable[Any] | None) -> list[Any]:
    rows = [row for row in list(segments or []) if _segment_end(row) > _segment_start(row)]
    return sorted(rows, key=lambda row: (_segment_start(row), _segment_end(row)))


def build_silence_boundary_rows(
    segments: Iterable[Any] | None,
    *,
    fps: float = 30.0,
    min_silence_sec: float = 1.0,
    media_duration: float | None = None,
) -> list[dict[str, Any]]:
    """Build roughcut boundary hints at long no-speech gaps."""
    rows: list[dict[str, Any]] = []
    ordered = _ordered_segments(segments)
    if len(ordered) < 2:
        return rows
    fps_value = normalize_fps(fps or 30.0)
    threshold = max(0.05, float(min_silence_sec or 1.0))
    duration_value = _safe_float(media_duration, 0.0)
    for index, (previous, current) in enumerate(zip(ordered, ordered[1:]), start=1):
        prev_end = _segment_end(previous)
        next_start = _segment_start(current)
        gap = next_start - prev_end
        if gap < threshold:
            continue
        sec = round((prev_end + next_start) * 0.5, 3)
        if sec <= 0.0 or (duration_value > 0.0 and sec >= duration_value):
            continue
        frame = sec_to_frame(sec, fps_value)
        rows.append(
            {
                "schema": "cut_boundary.v1",
                "id": f"silence_cut_{frame:08d}",
                "source": SILENCE_BOUNDARY_SOURCE,
                "detector": "subtitle-silence-gap-v1",
                "detector_stage": "roughcut_boundary_fusion",
                "reason": "long_silence_gap",
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps_value,
                "status": "confirmed",
                "verified": True,
                "boundary_role": "roughcut",
                "hard_cut_allowed": False,
                "line_color": SILENCE_LINE_COLOR,
                "line_style": "dot",
                "score": round(min(1.0, gap / max(threshold * 2.0, threshold)), 4),
                "silence_gap_sec": round(gap, 3),
                "silence_threshold_sec": round(threshold, 3),
                "boundary_index": index,
            }
        )
    return rows


def build_stt_context_shift_boundary_rows(
    segments: Iterable[Any] | None,
    *,
    fps: float = 30.0,
    threshold: float = 0.65,
    min_gap_sec: float = 0.0,
) -> list[dict[str, Any]]:
    """Build roughcut boundary hints from subtitle/STT topic drift."""
    rows: list[dict[str, Any]] = []
    ordered = _ordered_segments(segments)
    if len(ordered) < 2:
        return rows
    fps_value = normalize_fps(fps or 30.0)
    min_score = _clamp(threshold, 0.0, 1.0, 0.65)
    gap_floor = max(0.0, float(min_gap_sec or 0.0))
    from core.roughcut.topic_detector import topic_shift_score

    for index, (previous, current) in enumerate(zip(ordered, ordered[1:]), start=1):
        prev_text = _segment_text(previous)
        next_text = _segment_text(current)
        if not prev_text or not next_text:
            continue
        score = topic_shift_score(prev_text, next_text)
        gap = max(0.0, _segment_start(current) - _segment_end(previous))
        if score < min_score and not (gap >= max(1.2, gap_floor) and score >= min_score * 0.82):
            continue
        sec = round((_segment_end(previous) + _segment_start(current)) * 0.5, 3)
        if sec <= 0.0:
            continue
        frame = sec_to_frame(sec, fps_value)
        rows.append(
            {
                "schema": "cut_boundary.v1",
                "id": f"stt_context_cut_{frame:08d}",
                "source": STT_CONTEXT_BOUNDARY_SOURCE,
                "detector": "stt-context-shift-v1",
                "detector_stage": "roughcut_boundary_fusion",
                "reason": "stt_topic_context_shift",
                "time": sec,
                "timeline_sec": sec,
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps_value,
                "status": "confirmed",
                "verified": True,
                "boundary_role": "roughcut",
                "hard_cut_allowed": False,
                "line_color": STT_CONTEXT_LINE_COLOR,
                "line_style": "dot",
                "score": round(score, 4),
                "topic_shift_score": round(score, 4),
                "context_gap_sec": round(gap, 3),
                "previous_text": prev_text[:160],
                "current_text": next_text[:160],
                "boundary_index": index,
            }
        )
    return rows


def boundary_source_kind(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return "visual"
    source = str(row.get("source") or row.get("provisional_source") or "").lower()
    detector = str(row.get("detector") or "").lower()
    reason = str(row.get("reason") or "").lower()
    payload = " ".join((source, detector, reason))
    if is_audio_gain_boundary(row) or "audio" in payload or "gain" in payload:
        return "audio"
    if "silence" in payload or "gap" in payload:
        return "silence"
    if "stt" in payload or "context" in payload or "topic" in payload:
        return "stt_context"
    return "visual"


def _visual_score(row: dict[str, Any]) -> float:
    raw = max(
        _safe_float(row.get("score"), 0.0),
        _safe_float(row.get("color_score"), 0.0),
        _safe_float(row.get("delta"), 0.0),
        _safe_float(row.get("window_score"), 0.0),
        _safe_float(row.get("deep_boundary_score"), 0.0) * 120.0,
        _safe_float(row.get("fusion_score"), 0.0) * 120.0,
    )
    if raw <= 1.0:
        return max(0.0, min(1.0, raw))
    return 1.0 - math.exp(-(max(0.0, raw) / 120.0))


def _component_scores(row: dict[str, Any], settings: dict[str, Any]) -> dict[str, float]:
    kind = boundary_source_kind(row)
    visual = _visual_score(row) if kind == "visual" else 0.0
    audio_delta = abs(_safe_float(row.get("audio_gain_db_delta", row.get("delta_db", row.get("gain_delta_db"))), 0.0))
    audio_threshold = max(1.0, _safe_float(settings.get("scan_cut_audio_gain_threshold_db"), 10.0))
    audio = min(1.0, audio_delta / (audio_threshold * 1.4)) if kind == "audio" else 0.0
    silence = min(1.0, _safe_float(row.get("silence_gap_sec"), 0.0) / max(1.0, _safe_float(row.get("silence_threshold_sec"), 1.0) * 2.0))
    stt = max(_safe_float(row.get("topic_shift_score"), 0.0), _safe_float(row.get("context_shift_score"), 0.0))
    if kind == "silence":
        silence = max(silence, _safe_float(row.get("score"), 0.0))
    if kind == "stt_context":
        stt = max(stt, _safe_float(row.get("score"), 0.0))
    return {
        "visual": round(max(0.0, min(1.0, visual)), 4),
        "audio": round(max(0.0, min(1.0, audio)), 4),
        "silence": round(max(0.0, min(1.0, silence)), 4),
        "stt_context": round(max(0.0, min(1.0, stt)), 4),
    }


def score_fused_boundary_row(row: dict[str, Any], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a single boundary row with the same feature weights as fusion."""
    settings = dict(settings or {})
    components = _component_scores(row, settings)
    kinds = {boundary_source_kind(row)}
    combined = _fusion_score_from_components(components, kinds)
    return _fusion_decision(components, kinds, combined, settings)


def _fusion_score_from_components(components: dict[str, float], kinds: set[str]) -> float:
    combined = (
        components.get("visual", 0.0) * 0.42
        + components.get("audio", 0.0) * 0.23
        + components.get("silence", 0.0) * 0.18
        + components.get("stt_context", 0.0) * 0.17
    )
    if len(kinds) > 1:
        combined += min(0.12, (len(kinds) - 1) * 0.04)
    return max(0.0, min(1.0, combined))


def _fusion_decision(
    components: dict[str, float],
    kinds: set[str],
    combined: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    keep_threshold = _clamp(settings.get("cut_boundary_fusion_keep_threshold"), 0.0, 1.0, 0.68)
    verify_threshold = _clamp(settings.get("cut_boundary_fusion_verify_threshold"), 0.0, 1.0, 0.43)
    has_visual = "visual" in kinds
    has_audio = "audio" in kinds
    has_rough = bool(kinds & {"silence", "stt_context"})
    if has_visual and combined >= keep_threshold and components.get("visual", 0.0) >= 0.35:
        decision = "keep"
    elif combined >= verify_threshold or (has_audio and components.get("audio", 0.0) >= 0.72):
        decision = "verify"
    elif has_rough and max(components.get("silence", 0.0), components.get("stt_context", 0.0)) >= 0.62:
        decision = "roughcut_boundary"
    else:
        decision = "drop_hint"
    return {
        "schema": CUT_BOUNDARY_FUSION_SCHEMA,
        "score": round(combined, 4),
        "decision": decision,
        "sources": sorted(kinds),
        "components": {key: round(value, 4) for key, value in components.items()},
        "hard_cut_allowed": bool(has_visual and decision in {"keep", "verify"}),
    }


def _merge_group(group: list[dict[str, Any]], *, fps: float, settings: dict[str, Any]) -> dict[str, Any] | None:
    if not group:
        return None
    fps_value = normalize_fps(fps or 30.0)
    kinds = {boundary_source_kind(row) for row in group}
    component_max = {"visual": 0.0, "audio": 0.0, "silence": 0.0, "stt_context": 0.0}
    for row in group:
        scores = _component_scores(row, settings)
        for key, value in scores.items():
            component_max[key] = max(component_max[key], float(value))
    combined = _fusion_score_from_components(component_max, kinds)
    decision = _fusion_decision(component_max, kinds, combined, settings)

    def anchor_key(row: dict[str, Any]) -> tuple[int, float]:
        kind = boundary_source_kind(row)
        verified = _safe_bool(row.get("verified"), False) or str(row.get("status") or "").lower() == "confirmed"
        rank = 3 if kind == "visual" and verified else (2 if kind == "visual" else 1)
        return rank, max(_component_scores(row, settings).values())

    anchor = max(group, key=anchor_key)
    sec = boundary_time_sec(anchor, fps=fps_value)
    if sec is None:
        weighted = []
        for row in group:
            row_sec = boundary_time_sec(row, fps=fps_value)
            if row_sec is None:
                continue
            weight = max(_component_scores(row, settings).values(), 0.1)
            weighted.append((row_sec, weight))
        if not weighted:
            return None
        sec = sum(value * weight for value, weight in weighted) / sum(weight for _value, weight in weighted)
    sec = round(float(sec), 3)
    frame = sec_to_frame(sec, fps_value)

    out = dict(anchor)
    if len(group) > 1:
        out["source"] = FUSED_BOUNDARY_SOURCE
        out["detector"] = "visual-audio-silence-stt-fusion-v1"
    out["schema"] = "cut_boundary.v1"
    out["time"] = sec
    out["timeline_sec"] = sec
    out["frame"] = frame
    out["timeline_frame"] = frame
    out["fps"] = fps_value
    out["fusion_schema"] = CUT_BOUNDARY_FUSION_SCHEMA
    out["fusion_score"] = decision["score"]
    out["fusion_decision"] = decision["decision"]
    out["fusion_sources"] = decision["sources"]
    out["fusion_components"] = decision["components"]
    out["_cut_boundary_fusion"] = decision
    out["deep_boundary_score"] = max(_safe_float(out.get("deep_boundary_score"), 0.0), _safe_float(decision["score"], 0.0))
    out["deep_boundary_decision"] = decision["decision"]
    out["hard_cut_allowed"] = bool(decision["hard_cut_allowed"])
    out["is_cut"] = bool(decision["hard_cut_allowed"] or decision["decision"] in {"verify", "roughcut_boundary"})

    if "visual" in kinds and decision["hard_cut_allowed"]:
        out["status"] = "confirmed"
        out["verified"] = True
        out["boundary_role"] = "hard_cut"
    elif "audio" in kinds and "visual" not in kinds:
        out["status"] = "provisional"
        out["verified"] = False
        out["boundary_role"] = "roughcut"
        out["hard_cut_allowed"] = False
        out["refine_pending"] = True
        out["refine_backend"] = "visual_rollback"
        out["line_color"] = AUDIO_GAIN_LINE_COLOR
        out["line_style"] = "dash"
    else:
        out["status"] = str(out.get("status") or "confirmed")
        out["verified"] = _safe_bool(out.get("verified"), True)
        out["boundary_role"] = "roughcut"
        out["hard_cut_allowed"] = False
    out["fusion_component_rows"] = [
        {
            "source": str(row.get("source") or ""),
            "detector": str(row.get("detector") or ""),
            "time": round(boundary_time_sec(row, fps=fps_value) or 0.0, 3),
            "kind": boundary_source_kind(row),
            "score": round(max(_component_scores(row, settings).values()), 4),
        }
        for row in group[:8]
    ]
    return out


def fuse_cut_boundary_rows(
    rows: Iterable[dict[str, Any]] | None,
    *,
    fps: float = 30.0,
    settings: dict[str, Any] | None = None,
    merge_window_sec: float | None = None,
    media_duration: float | None = None,
) -> list[dict[str, Any]]:
    settings = dict(settings or {})
    fps_value = normalize_fps(fps or 30.0)
    window = max(0.0, _safe_float(merge_window_sec, _safe_float(settings.get("cut_boundary_fusion_window_sec"), 1.0)))
    duration_value = _safe_float(media_duration, 0.0)
    prepared: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        sec = boundary_time_sec(row, fps=fps_value)
        if sec is None or sec <= 0.0:
            continue
        if duration_value > 0.0 and sec >= duration_value:
            continue
        out = dict(row)
        out.setdefault("time", round(sec, 3))
        out.setdefault("timeline_sec", round(sec, 3))
        out.setdefault("frame", sec_to_frame(sec, fps_value))
        out.setdefault("timeline_frame", sec_to_frame(sec, fps_value))
        out.setdefault("fps", fps_value)
        prepared.append(out)
    prepared.sort(key=lambda row: boundary_time_sec(row, fps=fps_value) or 0.0)

    groups: list[list[dict[str, Any]]] = []
    for row in prepared:
        sec = boundary_time_sec(row, fps=fps_value) or 0.0
        if not groups:
            groups.append([row])
            continue
        previous_sec = boundary_time_sec(groups[-1][-1], fps=fps_value) or 0.0
        if abs(sec - previous_sec) <= window:
            groups[-1].append(row)
        else:
            groups.append([row])

    fused: list[dict[str, Any]] = []
    for group in groups:
        out = _merge_group(group, fps=fps_value, settings=settings)
        if out is None:
            continue
        if str(out.get("fusion_decision") or "") == "drop_hint":
            continue
        fused.append(out)
    return fused


def build_roughcut_fusion_boundary_rows(
    subtitle_segments: Iterable[Any] | None,
    scene_changes: Iterable[Any] | None,
    *,
    media_duration: float | None = None,
    settings: dict[str, Any] | None = None,
    fps: float = 30.0,
) -> list[dict[str, Any]]:
    """Build fused roughcut boundaries from video, audio, silence, and STT rows."""
    settings = dict(settings or {})
    if not _safe_bool(settings.get("roughcut_boundary_fusion_enabled", True), True):
        return boundary_rows_from_scene_changes(scene_changes, fps=fps)

    rows = boundary_rows_from_scene_changes(scene_changes, fps=fps)
    silence_gap = _safe_float(
        settings.get("roughcut_silence_gap_prefer_sec", settings.get("silence_gap_threshold", 1.0)),
        1.0,
    )
    rows.extend(
        build_silence_boundary_rows(
            subtitle_segments,
            fps=fps,
            min_silence_sec=silence_gap,
            media_duration=media_duration,
        )
    )
    rows.extend(
        build_stt_context_shift_boundary_rows(
            subtitle_segments,
            fps=fps,
            threshold=_clamp(settings.get("roughcut_context_shift_boundary_threshold"), 0.0, 1.0, 0.65),
            min_gap_sec=_safe_float(settings.get("roughcut_context_shift_min_gap_sec"), 0.0),
        )
    )
    return fuse_cut_boundary_rows(
        rows,
        fps=fps,
        settings=settings,
        media_duration=media_duration,
    )


__all__ = [
    "CUT_BOUNDARY_FUSION_SCHEMA",
    "FUSED_BOUNDARY_SOURCE",
    "SILENCE_BOUNDARY_SOURCE",
    "SILENCE_LINE_COLOR",
    "STT_CONTEXT_BOUNDARY_SOURCE",
    "STT_CONTEXT_LINE_COLOR",
    "boundary_rows_from_scene_changes",
    "boundary_source_kind",
    "boundary_time_sec",
    "build_roughcut_fusion_boundary_rows",
    "build_silence_boundary_rows",
    "build_stt_context_shift_boundary_rows",
    "fuse_cut_boundary_rows",
    "score_fused_boundary_row",
]
