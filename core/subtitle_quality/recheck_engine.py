# Version: 03.01.25
# Phase: PHASE2
"""Low-confidence recheck target selection for subtitle quality review."""

from __future__ import annotations

from typing import Any


RECHECK_FLAGS = {
    "non_speech_hallucination_risk",
    "known_hallucination_phrase",
    "high_no_speech_prob",
    "outside_vad_speech",
    "high_cps",
    "too_short_duration",
    "metadata_missing",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip_bounds(segment: dict[str, Any], clip_boundaries: list[dict[str, Any]] | None) -> tuple[float | None, float | None]:
    if not clip_boundaries:
        return None, None
    start = _as_float(segment.get("start"), 0.0)
    clip_idx = segment.get("_clip_idx")
    if clip_idx is not None:
        try:
            boundary = clip_boundaries[int(clip_idx)]
            return _as_float(boundary.get("start"), 0.0), _as_float(boundary.get("end"), 0.0)
        except Exception:
            pass
    for boundary in clip_boundaries:
        b_start = _as_float(boundary.get("start"), 0.0)
        b_end = _as_float(boundary.get("end"), b_start)
        if b_start <= start < b_end + 0.001:
            return b_start, b_end
    return None, None


def is_low_confidence_segment(segment: dict[str, Any]) -> bool:
    quality = dict(segment.get("quality") or {})
    label = str(quality.get("confidence_label") or "gray")
    flags = set(str(flag) for flag in (quality.get("flags") or ()))
    if label in {"red", "gray"}:
        return True
    if label == "yellow" and flags.intersection(RECHECK_FLAGS):
        return True
    return False


def recheck_low_confidence_segments(
    segments: list[dict[str, Any]],
    *,
    buffer_sec: float = 1.2,
    clip_boundaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    pad = max(0.0, float(buffer_sec or 0.0))
    for index, segment in enumerate(segments or []):
        if segment.get("is_gap") or not is_low_confidence_segment(segment):
            continue
        start = _as_float(segment.get("start"), 0.0)
        end = max(start, _as_float(segment.get("end"), start))
        clip_start, clip_end = _clip_bounds(segment, clip_boundaries)
        recheck_start = max(0.0 if clip_start is None else clip_start, start - pad)
        recheck_end = end + pad
        if clip_end is not None:
            recheck_end = min(clip_end, recheck_end)
        item = dict(segment)
        item["segment_index"] = int(segment.get("line", index) if segment.get("line") is not None else index)
        item["recheck_start"] = round(recheck_start, 3)
        item["recheck_end"] = round(max(recheck_start, recheck_end), 3)
        item["recheck_reason"] = ",".join(dict(segment.get("quality") or {}).get("flags") or ()) or dict(segment.get("quality") or {}).get("confidence_label", "gray")
        targets.append(item)
    return targets


__all__ = ["RECHECK_FLAGS", "is_low_confidence_segment", "recheck_low_confidence_segments"]
