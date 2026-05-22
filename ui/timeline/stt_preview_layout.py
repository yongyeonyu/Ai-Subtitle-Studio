"""Layout helpers for STT preview candidate lanes."""

from __future__ import annotations

from collections.abc import Iterable

# Allow each STT source to split into at most two visual rows when restored
# project candidates overlap. This avoids text overdraw while keeping the
# fixed STT1/STT2 lane pair compact.
MAX_STT_PREVIEW_SUBLANES = 2


def _safe_time(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return float(default)


def _source(row: dict) -> str:
    return str(
        row.get("stt_preview_source")
        or row.get("stt_source")
        or row.get("stt_ensemble_source")
        or row.get("source")
        or ""
    ).strip().upper()


def _text_key(row: dict) -> str:
    text = str(row.get("text", "") or "")
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _score(row: dict) -> float:
    for key in ("stt_score", "score", "confidence"):
        try:
            value = float(row.get(key, 0.0) or 0.0)
        except Exception:
            continue
        if value <= 1.0:
            value *= 100.0
        return max(0.0, min(100.0, value))
    return 0.0


def _overlap_ratio(left: dict, right: dict) -> float:
    left_start = _safe_time(left, "start", _safe_time(left, "timeline_start", 0.0))
    left_end = max(left_start, _safe_time(left, "end", _safe_time(left, "timeline_end", left_start)))
    right_start = _safe_time(right, "start", _safe_time(right, "timeline_start", 0.0))
    right_end = max(right_start, _safe_time(right, "end", _safe_time(right, "timeline_end", right_start)))
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    base = max(0.001, min(max(0.001, left_end - left_start), max(0.001, right_end - right_start)))
    return overlap / base


def dedupe_stt_preview_segments_for_display(segments: Iterable[dict] | None) -> list[dict]:
    """Drop visually duplicate same-source STT rows without mutating subtitle data."""
    kept: list[dict] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        source = _source(seg)
        text_key = _text_key(seg)
        replace_idx = None
        skip = False
        for idx, existing in enumerate(kept):
            if source and source != _source(existing):
                continue
            if not text_key or text_key != _text_key(existing):
                continue
            if _overlap_ratio(seg, existing) < 0.82:
                continue
            if _score(seg) > _score(existing):
                replace_idx = idx
            else:
                skip = True
            break
        if replace_idx is not None:
            kept[replace_idx] = seg
        elif not skip:
            kept.append(seg)
    return kept


def assign_stt_preview_lanes(segments: list[dict] | tuple[dict, ...]) -> tuple[dict[int, int], int]:
    """Assign overlapping STT candidates to vertical sublanes to avoid alpha overdraw."""
    items: list[tuple[float, float, int, dict]] = []
    for order, seg in enumerate(segments or ()):
        if not isinstance(seg, dict):
            continue
        start = _safe_time(seg, "start", _safe_time(seg, "timeline_start", 0.0))
        end = max(start, _safe_time(seg, "end", _safe_time(seg, "timeline_end", start)))
        items.append((start, end, order, seg))
    if not items:
        return {}, 1

    lane_ends: list[float] = []
    assignments: dict[int, int] = {}
    for start, end, _order, seg in sorted(items, key=lambda item: (item[0], item[1], item[2])):
        lane_idx = None
        for idx, lane_end in enumerate(lane_ends):
            if start >= lane_end - 0.001:
                lane_idx = idx
                break
        if lane_idx is None:
            if len(lane_ends) < MAX_STT_PREVIEW_SUBLANES:
                lane_idx = len(lane_ends)
                lane_ends.append(end)
            else:
                # Cap the visible split count so STT lanes stay readable. When
                # overlaps exceed the cap, reuse the earliest-finishing lane to
                # keep the repaint surface bounded instead of endlessly stacking.
                lane_idx = min(range(len(lane_ends)), key=lambda idx: lane_ends[idx])
                lane_ends[lane_idx] = max(lane_ends[lane_idx], end)
        else:
            lane_ends[lane_idx] = end
        assignments[id(seg)] = int(lane_idx)
    return assignments, max(1, len(lane_ends))


def stt_preview_lane_geometry(
    lane_top: int,
    lane_bot: int,
    lane_idx: int,
    lane_count: int,
    *,
    inset: int = 0,
) -> tuple[int, int]:
    preview_top = int(lane_top) + int(inset)
    preview_height = max(12, (int(lane_bot) - int(lane_top)) - (int(inset) * 2))
    lane_count = max(1, int(lane_count or 1))
    lane_idx = max(0, min(lane_count - 1, int(lane_idx or 0)))
    gap = 0
    usable = max(1, preview_height - (gap * (lane_count - 1)))
    slot_h = max(1, usable // lane_count)
    used_h = (slot_h * lane_count) + (gap * (lane_count - 1))
    top_pad = max(0, (preview_height - used_h) // 2)
    return preview_top + top_pad + (lane_idx * (slot_h + gap)), slot_h


__all__ = [
    "MAX_STT_PREVIEW_SUBLANES",
    "assign_stt_preview_lanes",
    "dedupe_stt_preview_segments_for_display",
    "stt_preview_lane_geometry",
]
