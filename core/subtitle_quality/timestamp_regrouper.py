# Version: 03.01.23
# Phase: PHASE2
"""Extended word timestamp regrouping helpers.

This module wraps the existing core.engine.word_resegmenter implementation and
adds stable-ts-inspired post-processing without replacing the original engine.
"""

from __future__ import annotations

from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.engine.word_resegmenter import resegment_by_word_timestamps
from core.subtitle_quality.models import attach_asr_metadata
from core.subtitle_quality.vad_alignment_checker import annotate_segment_vad_alignment, normalize_vad_segments


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _char_count(text: str) -> int:
    return len(str(text or "").replace(" ", "").replace("\n", ""))


def _snap_edge_to_frame(sec: float, fps: float, *, edge: str) -> float:
    frame = sec_to_frame(sec, fps)
    snapped = frame_to_sec(frame, fps)
    if edge in {"start", "end"} and snapped < sec:
        snapped = frame_to_sec(frame + 1, fps)
    return round(max(0.0, snapped), 6)


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
    vad_segments: list[dict[str, Any]] | None = None,
    word_gap_break_sec: float = 0.65,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    min_duration = max(0.0, float(min_duration or 0.0))
    max_chars = max(2, int(max_chars or 10))
    gap_break_sec = max(0.05, float(gap_break_sec or 1.5))
    vad = normalize_vad_segments(vad_segments or [])
    word_gap_break_sec = max(0.08, float(word_gap_break_sec or 0.65))
    result: list[dict[str, Any]] = []

    for seg in sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start"))):
        if not result:
            result.append(seg)
            continue

        prev = result[-1]
        gap = _as_float(seg.get("start")) - _as_float(prev.get("end"))
        hard_boundary = gap >= word_gap_break_sec or _segments_have_vad_boundary(prev, seg, vad)
        prev_dur = _as_float(prev.get("end")) - _as_float(prev.get("start"))
        cur_dur = _as_float(seg.get("end")) - _as_float(seg.get("start"))
        merged_chars = _char_count(prev.get("text", "")) + _char_count(seg.get("text", ""))
        should_merge = (
            not hard_boundary
            and
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


def _word_vad_index(word: dict[str, Any], vad_segments: list[dict[str, Any]]) -> int | None:
    if not vad_segments:
        return None
    start = _as_float(word.get("start"))
    end = max(start, _as_float(word.get("end"), start))
    center = (start + end) / 2.0
    for idx, vad in enumerate(vad_segments):
        if vad["start"] <= center <= vad["end"]:
            return idx
    return None


def _edge_word(segment: dict[str, Any], *, last: bool) -> dict[str, Any] | None:
    words = [
        dict(word)
        for word in (segment.get("words") or [])
        if str(word.get("word", "") or "").strip()
        and word.get("start") is not None
        and word.get("end") is not None
    ]
    if not words:
        return None
    words.sort(key=lambda item: _as_float(item.get("start")))
    return words[-1] if last else words[0]


def _segments_have_vad_boundary(
    left: dict[str, Any],
    right: dict[str, Any],
    vad_segments: list[dict[str, Any]],
) -> bool:
    if not vad_segments:
        return False
    left_word = _edge_word(left, last=True)
    right_word = _edge_word(right, last=False)
    if left_word is None or right_word is None:
        return False
    left_idx = _word_vad_index(left_word, vad_segments)
    right_idx = _word_vad_index(right_word, vad_segments)
    return left_idx is not None and right_idx is not None and left_idx != right_idx


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


def _word_edges(segment: dict[str, Any]) -> tuple[float, float] | None:
    words = [
        dict(word)
        for word in (segment.get("words") or [])
        if str(word.get("word", "") or "").strip()
        and word.get("start") is not None
        and word.get("end") is not None
    ]
    if not words:
        return None
    words.sort(key=lambda item: _as_float(item.get("start")))
    start = _as_float(words[0].get("start"))
    end = max(start + 0.05, _as_float(words[-1].get("end"), start + 0.05))
    return start, end


def _nearby_vad_for_edges(
    start: float,
    end: float,
    vad_segments: list[dict[str, Any]],
    *,
    max_edge_shift: float,
) -> list[dict[str, Any]]:
    return [
        vad for vad in vad_segments
        if vad["end"] >= start - max_edge_shift and vad["start"] <= end + max_edge_shift
    ]


def snap_segments_to_word_vad_boundaries(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
    *,
    edge_pad_sec: float = 0.04,
    max_edge_shift_sec: float = 0.25,
) -> list[dict[str, Any]]:
    if not segments:
        return []

    vad = normalize_vad_segments(vad_segments or [])
    pad = max(0.0, float(edge_pad_sec or 0.0))
    max_shift = max(0.0, float(max_edge_shift_sec or 0.0))
    snapped: list[dict[str, Any]] = []

    for segment in sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start"))):
        edges = _word_edges(segment)
        if edges is None:
            snapped.append(segment)
            continue

        old_start = _as_float(segment.get("start"))
        old_end = max(old_start + 0.05, _as_float(segment.get("end"), old_start + 0.05))
        word_start, word_end = edges
        new_start = word_start
        new_end = word_end

        refs = _nearby_vad_for_edges(word_start, word_end, vad, max_edge_shift=max_shift)
        if refs:
            first = refs[0]
            last = refs[-1]
            if abs(first["start"] - word_start) <= max_shift:
                new_start = min(new_start, max(0.0, first["start"] - pad))
            if abs(last["end"] - word_end) <= max_shift:
                new_end = max(new_end, last["end"] + pad)

        if new_end <= new_start:
            new_end = new_start + max(0.05, word_end - word_start)

        segment["start"] = round(max(0.0, new_start), 3)
        segment["end"] = round(max(new_start + 0.05, new_end), 3)
        if abs(segment["start"] - old_start) > 0.001 or abs(segment["end"] - old_end) > 0.001:
            meta = dict(segment.get("asr_metadata") or {})
            meta["word_vad_timing"] = {
                "from": [round(old_start, 3), round(old_end, 3)],
                "to": [segment["start"], segment["end"]],
                "source": "whisper_words+vad",
            }
            segment["asr_metadata"] = meta
        if vad:
            segment = annotate_segment_vad_alignment(segment, vad)
        else:
            segment = attach_asr_metadata(segment, backend=(segment.get("asr_metadata") or {}).get("backend"))
        snapped.append(segment)

    for idx in range(1, len(snapped)):
        prev = snapped[idx - 1]
        cur = snapped[idx]
        if _as_float(prev.get("end")) > _as_float(cur.get("start")):
            prev["end"] = round(max(_as_float(prev.get("start")) + 0.05, _as_float(cur.get("start")) - 0.02), 3)
    return snapped


def refine_segment_edges_with_context(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
    *,
    frame_rate: float | None = None,
    leading_pad_sec: float = 0.02,
    trailing_pad_sec: float = 0.05,
    max_word_shift_sec: float = 0.12,
    max_vad_shift_sec: float = 0.10,
) -> list[dict[str, Any]]:
    """Final timing polish using word edges, nearby VAD, and frame snapping.

    This pass is intentionally conservative. It only nudges boundaries when the
    target edge is close enough to the current segment edge, then re-clamps
    neighboring overlaps and optionally snaps to the active frame grid.
    """
    if not segments:
        return []

    vad = normalize_vad_segments(vad_segments or [])
    fps = normalize_fps(frame_rate) if frame_rate not in (None, "", 0, 0.0) else 0.0
    leading_pad = max(0.0, float(leading_pad_sec or 0.0))
    trailing_pad = max(0.0, float(trailing_pad_sec or 0.0))
    max_word_shift = max(0.0, float(max_word_shift_sec or 0.0))
    max_vad_shift = max(0.0, float(max_vad_shift_sec or 0.0))

    refined: list[dict[str, Any]] = []
    ordered = sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start")))

    for segment in ordered:
        start = max(0.0, _as_float(segment.get("start")))
        end = max(start + 0.05, _as_float(segment.get("end"), start + 0.05))
        old_start, old_end = start, end
        edges = _word_edges(segment)
        if edges is None:
            refined.append(segment)
            continue

        word_start, word_end = edges
        target_start = word_start
        target_end = word_end

        refs = _nearby_vad_for_edges(word_start, word_end, vad, max_edge_shift=max_vad_shift)
        if refs:
            first = refs[0]
            last = refs[-1]
            if abs(_as_float(first.get("start")) - word_start) <= max_vad_shift:
                target_start = min(target_start, max(0.0, _as_float(first.get("start")) - leading_pad))
            if abs(_as_float(last.get("end")) - word_end) <= max_vad_shift:
                target_end = max(target_end, _as_float(last.get("end")) + trailing_pad)

        if abs(target_start - start) <= max_word_shift:
            start = max(0.0, target_start)
        if abs(target_end - end) <= max(max_word_shift, max_vad_shift):
            end = max(start + 0.05, target_end)

        if fps > 0.0:
            start = _snap_edge_to_frame(start, fps, edge="start")
            end = _snap_edge_to_frame(end, fps, edge="end")
            end = max(start + (1.0 / fps), end)

        segment["start"] = round(max(0.0, start), 3)
        segment["end"] = round(max(segment["start"] + 0.05, end), 3)
        if abs(segment["start"] - old_start) > 0.001 or abs(segment["end"] - old_end) > 0.001:
            meta = dict(segment.get("asr_metadata") or {})
            meta["precision_timing"] = {
                "from": [round(old_start, 3), round(old_end, 3)],
                "to": [segment["start"], segment["end"]],
                "source": "words+vad+frame",
            }
            segment["asr_metadata"] = meta
        refined.append(segment)

    for idx in range(1, len(refined)):
        prev = refined[idx - 1]
        cur = refined[idx]
        prev_start = _as_float(prev.get("start"))
        cur_start = _as_float(cur.get("start"))
        if _as_float(prev.get("end")) > cur_start:
            boundary = max(prev_start + 0.05, cur_start - 0.02)
            if fps > 0.0:
                boundary = _snap_edge_to_frame(boundary, fps, edge="end")
            prev["end"] = round(max(prev_start + 0.05, boundary), 3)
            if _as_float(cur.get("end")) <= _as_float(cur.get("start")):
                cur["end"] = round(_as_float(cur.get("start")) + 0.05, 3)

    return refined


def regroup_by_word_timestamps(segments: list[dict[str, Any]], **kwargs) -> list[dict[str, Any]]:
    vad_segments = kwargs.pop("vad_segments", None)
    frame_rate = kwargs.pop("frame_rate", None)
    word_gap_break_sec = kwargs.pop("word_gap_break_sec", 0.65)
    regrouped = resegment_by_word_timestamps(
        segments,
        **kwargs,
        vad_segments=vad_segments,
        word_gap_break_sec=word_gap_break_sec,
    )
    max_chars = int(kwargs.get("max_chars", 10) or 10)
    min_duration = float(kwargs.get("min_duration", 0.0) or 0.0)
    max_duration = float(kwargs.get("max_duration", 6.0) or 6.0)
    gap_break_sec = float(kwargs.get("gap_break_sec", 1.5) or 1.5)
    regrouped = merge_short_segments_by_gap(
        regrouped,
        min_duration=min_duration,
        max_chars=max_chars,
        gap_break_sec=min(gap_break_sec, 0.8),
        vad_segments=vad_segments,
        word_gap_break_sec=word_gap_break_sec,
    )
    clamped = clamp_segment_durations(
        regrouped,
        max_duration=max_duration,
        gap_break_sec=gap_break_sec,
    )
    snapped = snap_segments_to_word_vad_boundaries(
        clamped,
        vad_segments=vad_segments,
        edge_pad_sec=0.04,
        max_edge_shift_sec=min(0.35, max(0.12, float(word_gap_break_sec or 0.65) * 0.5)),
    )
    return refine_segment_edges_with_context(
        snapped,
        vad_segments=vad_segments,
        frame_rate=frame_rate,
    )
