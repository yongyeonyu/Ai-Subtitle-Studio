"""Layout helpers for STT preview candidate lanes."""

from __future__ import annotations

from collections.abc import Iterable

from core.timeline_time import segment_display_time_bounds

# Allow each STT source to split into a few visual rows when restored project
# candidates overlap. Three rows is the current compact limit that prevents the
# common STT1/2 overdraw case without changing the timeline scenario.
MAX_STT_PREVIEW_SUBLANES = 3
STT_PREVIEW_SUBLANE_KEY = "stt_preview_sublane"
STT_PREVIEW_SUBLANE_COUNT_KEY = "stt_preview_sublane_count"
# STT preview boxes are frame-snapped later by the renderers. If two candidates
# merely touch, borders/text can still overpaint by a pixel and look overlapped.
# Keep a tiny visual gap when deciding whether a source row can reuse a sublane.
STT_PREVIEW_MIN_LANE_GAP_SEC = 0.08


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


def _coerce_lane(value, *, default: int | None = None) -> int | None:
    try:
        lane = int(round(float(value)))
    except Exception:
        return default
    return max(0, min(MAX_STT_PREVIEW_SUBLANES - 1, lane))


def _explicit_lane(seg: dict) -> int | None:
    if not isinstance(seg, dict):
        return None
    for key in (
        STT_PREVIEW_SUBLANE_KEY,
        "stt_preview_lane",
        "stt_preview_row",
        "stt_sublane",
    ):
        if key in seg:
            lane = _coerce_lane(seg.get(key))
            if lane is not None:
                return lane
    return None


def _explicit_lane_count(seg: dict) -> int | None:
    if not isinstance(seg, dict):
        return None
    for key in (
        STT_PREVIEW_SUBLANE_COUNT_KEY,
        "stt_preview_lane_count",
        "stt_preview_row_count",
        "stt_sublane_count",
    ):
        if key in seg:
            try:
                value = int(round(float(seg.get(key))))
            except Exception:
                continue
            return max(1, min(MAX_STT_PREVIEW_SUBLANES, value))
    return None


def _overlap_ratio(left: dict, right: dict) -> float:
    left_start, left_end = segment_display_time_bounds(left)
    right_start, right_end = segment_display_time_bounds(right)
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    base = max(0.001, min(max(0.001, left_end - left_start), max(0.001, right_end - right_start)))
    return overlap / base


def _assignments_have_visible_overlap(
    segments: list[dict] | tuple[dict, ...],
    assignments: dict[int, int],
) -> bool:
    lanes: dict[int, list[tuple[float, float]]] = {}
    for seg in segments or ():
        if not isinstance(seg, dict):
            continue
        lane = int(assignments.get(id(seg), 0) or 0)
        start, end = segment_display_time_bounds(seg)
        if end <= start:
            end = start + 0.001
        lanes.setdefault(lane, []).append((start, end))
    for items in lanes.values():
        cursor = None
        for start, end in sorted(items):
            if cursor is not None and start < cursor + STT_PREVIEW_MIN_LANE_GAP_SEC - 0.001:
                return True
            cursor = max(float(cursor or end), end)
    return False


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


def _computed_stt_preview_lanes(segments: list[dict] | tuple[dict, ...]) -> tuple[dict[int, int], int]:
    items: list[tuple[float, float, int, dict]] = []
    for order, seg in enumerate(segments or ()):
        if not isinstance(seg, dict):
            continue
        start, end = segment_display_time_bounds(seg)
        items.append((start, end, order, seg))
    if not items:
        return {}, 1

    lane_ends: list[float] = []
    assignments: dict[int, int] = {}
    for start, end, _order, seg in sorted(items, key=lambda item: (item[0], item[1], item[2])):
        lane_idx = None
        for idx, lane_end in enumerate(lane_ends):
            if start >= lane_end + STT_PREVIEW_MIN_LANE_GAP_SEC - 0.001:
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


def assign_stt_preview_lanes(segments: list[dict] | tuple[dict, ...]) -> tuple[dict[int, int], int]:
    """Assign STT candidates to stable vertical sublanes.

    Persisted/live rows may carry explicit sublane numbers.  Prefer those so a
    candidate that was split onto row 2 does not jump back to row 1 when the
    viewport/playhead stops including its overlapping neighbor.
    """
    computed, computed_count = _computed_stt_preview_lanes(segments)
    if not segments:
        return {}, 1

    assignments: dict[int, int] = {}
    lane_count = max(1, int(computed_count or 1))
    has_explicit = False
    for seg in segments or ():
        if not isinstance(seg, dict):
            continue
        explicit = _explicit_lane(seg)
        has_explicit = has_explicit or explicit is not None
        if explicit is None:
            explicit = int(computed.get(id(seg), 0))
        assignments[id(seg)] = explicit
        lane_count = max(lane_count, explicit + 1)
        explicit_count = _explicit_lane_count(seg)
        if explicit_count is not None:
            lane_count = max(lane_count, explicit_count)
    lane_count = max(1, min(MAX_STT_PREVIEW_SUBLANES, lane_count))
    if has_explicit and _assignments_have_visible_overlap(segments, assignments):
        assignments = {id(seg): int(computed.get(id(seg), 0)) for seg in segments or () if isinstance(seg, dict)}
        lane_count = max(1, min(MAX_STT_PREVIEW_SUBLANES, int(computed_count or 1)))
    return assignments, lane_count


def ensure_stt_preview_lane_numbers(segments: Iterable[dict] | None, *, mutate: bool = True) -> list[dict]:
    """Attach deterministic STT preview sublane metadata by source.

    The returned rows keep existing explicit lane metadata.  Missing rows are
    assigned from the full source track, not the current viewport, so playback
    cannot reshuffle two-line STT1/STT2 candidates.
    """
    rows = [seg for seg in list(segments or []) if isinstance(seg, dict)]
    if not rows:
        return []

    grouped: dict[str, list[dict]] = {"STT1": [], "STT2": []}
    for seg in rows:
        source = _source(seg)
        if source == "STT2":
            grouped["STT2"].append(seg)
        elif source == "STT1" or bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
            grouped["STT1"].append(seg)

    output = [dict(seg) for seg in rows] if not mutate else rows
    id_to_output = {id(src): output[idx] for idx, src in enumerate(rows)}
    for source_rows in grouped.values():
        if not source_rows:
            continue
        assignments, lane_count = assign_stt_preview_lanes(source_rows)
        for seg in source_rows:
            target = id_to_output.get(id(seg))
            if target is None:
                continue
            lane = int(assignments.get(id(seg), 0))
            target[STT_PREVIEW_SUBLANE_KEY] = max(0, min(lane_count - 1, int(lane or 0)))
            target[STT_PREVIEW_SUBLANE_COUNT_KEY] = lane_count
    return output


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
    gap = 2 if lane_count > 1 and preview_height >= 24 else 0
    usable = max(1, preview_height - (gap * (lane_count - 1)))
    slot_h = max(1, usable // lane_count)
    used_h = (slot_h * lane_count) + (gap * (lane_count - 1))
    top_pad = max(0, (preview_height - used_h) // 2)
    return preview_top + top_pad + (lane_idx * (slot_h + gap)), slot_h


__all__ = [
    "MAX_STT_PREVIEW_SUBLANES",
    "STT_PREVIEW_SUBLANE_COUNT_KEY",
    "STT_PREVIEW_SUBLANE_KEY",
    "assign_stt_preview_lanes",
    "dedupe_stt_preview_segments_for_display",
    "ensure_stt_preview_lane_numbers",
    "stt_preview_lane_geometry",
]
