# Version: 03.01.23
# Phase: PHASE2
"""Extended word timestamp regrouping helpers.

This module wraps the existing core.engine.word_resegmenter implementation and
adds stable-ts-inspired post-processing without replacing the original engine.
"""

from __future__ import annotations

from typing import Any

from core.engine.word_resegmenter import resegment_by_word_timestamps
from core.subtitle_quality.models import attach_asr_metadata


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _char_count(text: str) -> int:
    return len(str(text or "").replace(" ", "").replace("\n", ""))


def _boundary_key(segment: dict[str, Any]) -> tuple[Any, Any]:
    meta = dict(segment.get("asr_metadata") or {})
    return (
        segment.get("speaker"),
        meta.get("_clip_idx", segment.get("_clip_idx")),
    )


def _same_merge_boundary(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _boundary_key(left) == _boundary_key(right)


def _merge_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = {
        **left,
        "start": left.get("start", 0.0),
        "end": right.get("end", left.get("end", 0.0)),
        "text": f"{str(left.get('text', '')).strip()} {str(right.get('text', '')).strip()}".strip(),
        "words": list(left.get("words") or []) + list(right.get("words") or []),
    }
    if right.get("speaker") is not None:
        merged.setdefault("speaker", right.get("speaker"))
    meta = dict(left.get("asr_metadata") or {})
    right_meta = dict(right.get("asr_metadata") or {})
    for key in ("backend", "chunk_path", "language_probability", "_clip_idx"):
        if meta.get(key) is None and right_meta.get(key) is not None:
            meta[key] = right_meta.get(key)
    if meta:
        merged["asr_metadata"] = meta
    return attach_asr_metadata(merged, backend=(merged.get("asr_metadata") or {}).get("backend"))


def merge_short_segments_by_gap(
    segments: list[dict[str, Any]],
    *,
    min_duration: float,
    max_chars: int,
    gap_break_sec: float,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    min_duration = max(0.0, float(min_duration or 0.0))
    max_chars = max(2, int(max_chars or 10))
    gap_break_sec = max(0.05, float(gap_break_sec or 1.5))
    result: list[dict[str, Any]] = []

    for seg in sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start"))):
        if not result:
            result.append(seg)
            continue

        prev = result[-1]
        gap = _as_float(seg.get("start")) - _as_float(prev.get("end"))
        prev_dur = _as_float(prev.get("end")) - _as_float(prev.get("start"))
        cur_dur = _as_float(seg.get("end")) - _as_float(seg.get("start"))
        merged_chars = _char_count(prev.get("text", "")) + _char_count(seg.get("text", ""))
        should_merge = (
            gap <= gap_break_sec
            and _same_merge_boundary(prev, seg)
            and (prev_dur < min_duration or cur_dur < min_duration or merged_chars <= max_chars)
            and merged_chars <= int(max_chars * 1.5)
        )
        if should_merge:
            result[-1] = _merge_pair(prev, seg)
        else:
            result.append(seg)

    return result


def clamp_segment_durations(
    segments: list[dict[str, Any]],
    *,
    max_duration: float,
    gap_break_sec: float,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    max_duration = max(0.5, float(max_duration or 6.0))
    gap_break_sec = max(0.05, float(gap_break_sec or 1.5))
    clamped: list[dict[str, Any]] = []
    ordered = sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start")))
    for index, seg in enumerate(ordered):
        start = _as_float(seg.get("start"))
        end = max(start + 0.05, _as_float(seg.get("end"), start + 0.05))
        if end - start > max_duration:
            end = start + max_duration
        if index + 1 < len(ordered):
            next_start = _as_float(ordered[index + 1].get("start"), end)
            if next_start - end >= gap_break_sec:
                end = min(end, next_start - 0.02)
        seg["start"] = round(start, 3)
        seg["end"] = round(max(start + 0.05, end), 3)
        clamped.append(attach_asr_metadata(seg, backend=(seg.get("asr_metadata") or {}).get("backend")))
    return clamped


def regroup_by_word_timestamps(segments: list[dict[str, Any]], **kwargs) -> list[dict[str, Any]]:
    regrouped = resegment_by_word_timestamps(segments, **kwargs)
    max_chars = int(kwargs.get("max_chars", 10) or 10)
    min_duration = float(kwargs.get("min_duration", 0.0) or 0.0)
    max_duration = float(kwargs.get("max_duration", 6.0) or 6.0)
    gap_break_sec = float(kwargs.get("gap_break_sec", 1.5) or 1.5)
    regrouped = merge_short_segments_by_gap(
        regrouped,
        min_duration=min_duration,
        max_chars=max_chars,
        gap_break_sec=min(gap_break_sec, 0.8),
    )
    return clamp_segment_durations(
        regrouped,
        max_duration=max_duration,
        gap_break_sec=gap_break_sec,
    )
