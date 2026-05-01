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


def adjust_segments_to_vad_boundaries(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    max_shift_sec: float = 0.7,
    edge_pad_sec: float = 0.04,
) -> tuple[list[dict[str, Any]], int]:
    """Snap subtitle edges to nearby VAD speech boundaries without stretching rows."""
    vad = normalize_vad_segments(vad_segments)
    if not segments or not vad:
        return [dict(seg) for seg in (segments or [])], 0

    max_shift = max(0.0, _as_float(max_shift_sec, 0.7))
    pad = max(0.0, _as_float(edge_pad_sec, 0.04))
    adjusted: list[dict[str, Any]] = []
    changed = 0

    for segment in segments:
        out = dict(segment or {})
        start = max(0.0, _as_float(out.get("start"), 0.0))
        end = max(start, _as_float(out.get("end"), start))
        if end <= start:
            adjusted.append(out)
            continue

        overlaps = [v for v in vad if v["end"] >= start and v["start"] <= end]
        nearby = [v for v in vad if v["end"] >= start - max_shift and v["start"] <= end + max_shift]
        refs = overlaps or nearby
        if not refs:
            adjusted.append(out)
            continue

        new_start = start
        new_end = end

        # 시작점은 가까운 VAD 시작 경계 또는 자막이 음성보다 먼저 열린 경우에만 조정합니다.
        first = refs[0]
        if abs(first["start"] - start) <= max_shift or (start < first["start"] and first["start"] < end):
            new_start = max(0.0, first["start"] - pad)

        # 끝점은 가까운 VAD 끝 경계 또는 자막이 음성보다 늦게 닫힌 경우에만 조정합니다.
        last = refs[-1]
        if abs(last["end"] - end) <= max_shift or (start < last["end"] and end > last["end"]):
            new_end = max(new_start + 0.05, last["end"] + pad)

        if new_end <= new_start:
            new_end = new_start + max(0.05, end - start)

        if abs(new_start - start) > 0.001 or abs(new_end - end) > 0.001:
            changed += 1
            meta = dict(out.get("asr_metadata") or {})
            meta["vad_timing_adjustment"] = {
                "from": [round(start, 3), round(end, 3)],
                "to": [round(new_start, 3), round(new_end, 3)],
            }
            out["asr_metadata"] = meta
        out["start"] = round(new_start, 3)
        out["end"] = round(new_end, 3)
        adjusted.append(annotate_segment_vad_alignment(out, vad))

    adjusted.sort(key=lambda item: (_as_float(item.get("start")), _as_float(item.get("end"))))
    for idx in range(1, len(adjusted)):
        prev = adjusted[idx - 1]
        cur = adjusted[idx]
        if _as_float(prev.get("end")) > _as_float(cur.get("start")):
            prev["end"] = round(max(_as_float(prev.get("start")) + 0.05, _as_float(cur.get("start")) - 0.02), 3)
    return adjusted, changed


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
