"""Layout helpers for STT preview candidate lanes."""

from __future__ import annotations

# Allow each STT source to split into at most two visual rows when restored
# project candidates overlap. This avoids text overdraw while keeping the
# fixed STT1/STT2 lane pair compact.
MAX_STT_PREVIEW_SUBLANES = 2


def _safe_time(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except Exception:
        return float(default)


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


__all__ = ["MAX_STT_PREVIEW_SUBLANES", "assign_stt_preview_lanes", "stt_preview_lane_geometry"]
