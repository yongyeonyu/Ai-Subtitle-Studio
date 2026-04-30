# Version: 03.01.22
# Phase: PHASE2
"""VAD alignment checks for subtitle quality review."""

from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_vad_segments(vad_segments: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in vad_segments or ():
        if not isinstance(item, dict):
            continue
        start = max(0.0, _as_float(item.get("start"), 0.0))
        end = max(start, _as_float(item.get("end"), start))
        if end <= start:
            continue
        out = dict(item)
        out["start"] = start
        out["end"] = end
        normalized.append(out)
    return normalized


def vad_overlap_seconds(
    start: float,
    end: float,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> float:
    overlap = 0.0
    for vad in normalize_vad_segments(vad_segments):
        overlap += max(0.0, min(end, vad["end"]) - max(start, vad["start"]))
    return overlap


def vad_alignment_info(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    start = _as_float(segment.get("start"), 0.0)
    end = _as_float(segment.get("end"), start)
    duration = max(0.0, end - start)
    if duration <= 0.0 or not vad_segments:
        return {
            "vad_overlap_ratio": None,
            "vad_overlap_sec": 0.0,
            "vad_duration_sec": round(duration, 6),
            "vad_aligned": None,
        }

    overlap = vad_overlap_seconds(start, end, vad_segments)
    ratio = round(max(0.0, min(1.0, overlap / duration)), 6)
    return {
        "vad_overlap_ratio": ratio,
        "vad_overlap_sec": round(overlap, 6),
        "vad_duration_sec": round(duration, 6),
        "vad_aligned": ratio >= 0.35,
    }


def vad_overlap_ratio(segment: dict[str, Any], vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> float | None:
    return vad_alignment_info(segment, vad_segments).get("vad_overlap_ratio")


def annotate_segment_vad_alignment(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    out = dict(segment or {})
    info = vad_alignment_info(out, vad_segments)
    asr_metadata = dict(out.get("asr_metadata") or {})
    asr_metadata["vad_alignment"] = info
    out["asr_metadata"] = asr_metadata

    quality = dict(out.get("quality") or {})
    flags = list(quality.get("flags") or ())
    ratio = info.get("vad_overlap_ratio")
    if ratio is not None:
        quality["vad_alignment_score"] = round(float(ratio) * 100.0, 3)
        if ratio < 0.2 and "outside_vad_speech" not in flags:
            flags.append("outside_vad_speech")
    if flags:
        quality["flags"] = tuple(flags)
    out["quality"] = quality
    return out


def review_vad_enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(settings.get("review_vad_before_stt_enabled", False))


def review_vad_config(settings: dict[str, Any] | None) -> dict[str, Any]:
    settings = settings or {}
    enabled = review_vad_enabled(settings)
    strict = bool(settings.get("review_vad_strict_mode", True))
    return {
        "review_vad_before_stt_enabled": enabled,
        "review_vad_strict_mode": strict,
        "review_vad_speech_pad_sec": _as_float(settings.get("review_vad_speech_pad_sec"), 0.35),
        "review_vad_min_silence_sec": _as_float(settings.get("review_vad_min_silence_sec"), 0.8),
    }


def apply_review_vad_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(settings or {})
    cfg = review_vad_config(out)
    if not cfg["review_vad_before_stt_enabled"] or not cfg["review_vad_strict_mode"]:
        return out
    out["vad_speech_pad"] = max(0.0, cfg["review_vad_speech_pad_sec"])
    out["vad_min_silence"] = max(0.1, cfg["review_vad_min_silence_sec"])
    return out
