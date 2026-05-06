from __future__ import annotations

from statistics import median
from typing import Any


SUBTITLE_BUNDLE_POLICY_SCHEMA = "ai_subtitle_studio.subtitle_bundle_policy.v1"
SUBTITLE_BUNDLE_POLICY_MODEL_ID = "cut_lora_deep_bundle_policy_v1"


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "아니오"}
    return bool(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    return max(float(low), min(float(high), _safe_float(value, default)))


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    return max(int(low), min(int(high), _safe_int(value, default)))


def _boundary_sec(row: Any) -> float | None:
    try:
        if isinstance(row, dict):
            value = row.get("timeline_sec", row.get("time", row.get("start", row.get("sec", 0.0))))
            return float(value or 0.0)
        return float(row)
    except Exception:
        return None


def _boundary_times(rows: list[Any] | None) -> list[float]:
    values: list[float] = []
    for row in list(rows or []):
        sec = _boundary_sec(row)
        if sec is not None and sec > 0.0:
            values.append(round(float(sec), 3))
    return sorted(set(values))


def _segment_span(segments: list[dict[str, Any]] | None) -> tuple[float, float, float]:
    starts: list[float] = []
    ends: list[float] = []
    for row in list(segments or []):
        if not isinstance(row, dict):
            continue
        start = _safe_float(row.get("start"), 0.0)
        end = _safe_float(row.get("end"), start)
        starts.append(start)
        ends.append(max(start, end))
    if not starts or not ends:
        return 0.0, 0.0, 0.0
    start = min(starts)
    end = max(ends)
    return round(start, 3), round(end, 3), max(0.0, end - start)


def _profile_setting_values(profile: dict[str, Any] | None, key: str) -> list[float]:
    profile = dict(profile or {})
    sources: list[dict[str, Any]] = []
    for source_key in ("applied_settings", "retrieved_settings"):
        source = profile.get(source_key)
        if isinstance(source, dict):
            sources.append(source)
    for item in list(profile.get("setting_sources") or []):
        if isinstance(item, dict) and isinstance(item.get("settings"), dict):
            sources.append(dict(item.get("settings") or {}))
    values: list[float] = []
    for source in sources:
        if key not in source:
            continue
        value = _safe_float(source.get(key), 0.0)
        if value > 0.0 and value < 99999:
            values.append(value)
    return values


def _lora_bundle_seconds(segments: list[dict[str, Any]] | None) -> list[float]:
    values: list[float] = []
    keys = (
        "subtitle_bundle_target_sec",
        "chunk_time_limit",
        "subtitle_bundle_max_sec",
    )
    for row in list(segments or []):
        if not isinstance(row, dict):
            continue
        segment_settings = dict(row.get("_lora_segment_settings") or {})
        for key in keys:
            value = _safe_float(segment_settings.get(key), 0.0)
            if value > 0.0 and value < 99999:
                values.append(value)
        profile = dict(row.get("_lora_generation_profile") or {})
        for key in keys:
            values.extend(_profile_setting_values(profile, key))
    return values


def _latest_crossed_boundary(
    boundaries: list[float],
    *,
    start: float,
    end: float,
    min_span_sec: float,
    snap_window_sec: float,
) -> float | None:
    lower = start + max(0.0, min_span_sec)
    upper = end + max(0.0, snap_window_sec)
    crossed = [sec for sec in boundaries if lower <= sec <= upper]
    return crossed[-1] if crossed else None


def resolve_subtitle_bundle_policy(
    settings: dict[str, Any] | None,
    *,
    segments: list[dict[str, Any]] | None = None,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
    current_duration: float | None = None,
    media_duration_sec: float | None = None,
) -> dict[str, Any]:
    settings = dict(settings or {})
    start, end, segment_duration = _segment_span(segments)
    duration = _safe_float(current_duration, segment_duration)
    if duration <= 0.0:
        duration = segment_duration

    manual_limit = _safe_float(settings.get("chunk_time_limit"), 180.0)
    if manual_limit >= 99999:
        manual_limit = _safe_float(settings.get("subtitle_bundle_target_sec"), 180.0)
    target = _safe_float(settings.get("subtitle_bundle_target_sec"), manual_limit or 180.0)

    lora_values = _lora_bundle_seconds(segments)
    if lora_values and _safe_bool(settings.get("subtitle_bundle_lora_enabled"), True):
        lora_target = float(median(lora_values))
        blend = _clamp(settings.get("subtitle_bundle_lora_blend"), 0.0, 1.0, 0.35)
        target = (target * (1.0 - blend)) + (lora_target * blend)

    min_sec = _clamp(settings.get("subtitle_bundle_min_sec"), 30.0, 240.0, 90.0)
    max_sec = _clamp(settings.get("subtitle_bundle_max_sec"), max(min_sec, 90.0), 900.0, 300.0)
    target = _clamp(target, min_sec, max_sec, 180.0)
    confirmed_min = _clamp(settings.get("subtitle_bundle_confirmed_cut_min_sec"), 10.0, max_sec, 45.0)
    provisional_min = _clamp(settings.get("subtitle_bundle_provisional_cut_min_sec"), 30.0, max_sec, 120.0)
    snap_window = _clamp(settings.get("subtitle_bundle_boundary_snap_window_sec"), 0.0, 5.0, 1.0)

    confirmed = _boundary_times(cut_boundaries)
    provisional = _boundary_times(provisional_cut_boundaries)
    crossed_confirmed = (
        _latest_crossed_boundary(
            confirmed,
            start=start,
            end=end,
            min_span_sec=confirmed_min,
            snap_window_sec=snap_window,
        )
        if _safe_bool(settings.get("subtitle_bundle_use_confirmed_cuts"), True)
        else None
    )
    crossed_provisional = (
        _latest_crossed_boundary(
            provisional,
            start=start,
            end=end,
            min_span_sec=provisional_min,
            snap_window_sec=snap_window,
        )
        if _safe_bool(settings.get("subtitle_bundle_use_provisional_cuts"), True)
        else None
    )

    reason = "hold"
    flush = False
    boundary_sec: float | None = None
    if duration >= max_sec:
        flush = True
        reason = "max_sec"
    elif crossed_confirmed is not None:
        flush = True
        reason = "confirmed_cut"
        boundary_sec = crossed_confirmed
    elif crossed_provisional is not None:
        flush = True
        reason = "provisional_cut"
        boundary_sec = crossed_provisional
    elif duration >= target:
        flush = True
        reason = "target_sec"

    if media_duration_sec and end >= _safe_float(media_duration_sec, 0.0) - 0.15:
        flush = True
        reason = "media_end"

    return {
        "schema": SUBTITLE_BUNDLE_POLICY_SCHEMA,
        "model": SUBTITLE_BUNDLE_POLICY_MODEL_ID,
        "task": "subtitle_bundle_policy",
        "autopilot": _safe_bool(settings.get("subtitle_bundle_autopilot_enabled"), True),
        "flush": bool(flush),
        "reason": reason,
        "target_sec": round(target, 3),
        "min_sec": round(min_sec, 3),
        "max_sec": round(max_sec, 3),
        "confirmed_cut_min_sec": round(confirmed_min, 3),
        "provisional_cut_min_sec": round(provisional_min, 3),
        "start": round(start, 3),
        "end": round(end, 3),
        "duration_sec": round(duration, 3),
        "segment_count": len([row for row in list(segments or []) if isinstance(row, dict)]),
        "boundary_sec": round(boundary_sec, 3) if boundary_sec is not None else None,
        "confirmed_cut_count": len(confirmed),
        "provisional_cut_count": len(provisional),
        "lora_values": [round(value, 3) for value in lora_values[:8]],
    }


def should_flush_subtitle_bundle(
    current_duration: float,
    chunk_time_limit: int | float,
    *,
    settings: dict[str, Any] | None = None,
    segments: list[dict[str, Any]] | None = None,
    cut_boundaries: list[Any] | None = None,
    provisional_cut_boundaries: list[Any] | None = None,
    media_duration_sec: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    merged = dict(settings or {})
    if "chunk_time_limit" not in merged:
        merged["chunk_time_limit"] = chunk_time_limit
    if not _safe_bool(merged.get("subtitle_bundle_autopilot_enabled"), True):
        limit = _safe_float(merged.get("chunk_time_limit"), _safe_float(chunk_time_limit, 180.0))
        if limit >= 99999:
            return False, {
                "schema": SUBTITLE_BUNDLE_POLICY_SCHEMA,
                "model": SUBTITLE_BUNDLE_POLICY_MODEL_ID,
                "task": "subtitle_bundle_policy",
                "autopilot": False,
                "flush": False,
                "reason": "manual_all",
                "target_sec": limit,
                "duration_sec": round(_safe_float(current_duration, 0.0), 3),
            }
        flush = _safe_float(current_duration, 0.0) >= max(1.0, limit)
        return flush, {
            "schema": SUBTITLE_BUNDLE_POLICY_SCHEMA,
            "model": SUBTITLE_BUNDLE_POLICY_MODEL_ID,
            "task": "subtitle_bundle_policy",
            "autopilot": False,
            "flush": flush,
            "reason": "manual_limit" if flush else "hold",
            "target_sec": round(limit, 3),
            "duration_sec": round(_safe_float(current_duration, 0.0), 3),
        }
    policy = resolve_subtitle_bundle_policy(
        merged,
        segments=segments,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        current_duration=current_duration,
        media_duration_sec=media_duration_sec,
    )
    return bool(policy.get("flush")), policy


__all__ = [
    "SUBTITLE_BUNDLE_POLICY_MODEL_ID",
    "SUBTITLE_BUNDLE_POLICY_SCHEMA",
    "resolve_subtitle_bundle_policy",
    "should_flush_subtitle_bundle",
]
