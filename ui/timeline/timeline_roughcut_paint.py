# Version: 03.14.31
# Phase: PHASE2
"""Paint-prep helpers for the roughcut timeline lane."""
from __future__ import annotations

from typing import Any


_PAINT_IDENTITY_KEYS = (
    "kind",
    "label",
    "display_label",
    "title",
    "status",
    "color",
)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _paint_identity(marker: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(marker.get(key, "") or "") for key in _PAINT_IDENTITY_KEYS)


def coalesce_roughcut_paint_markers(
    markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    pps: float = 1.0,
    max_gap_px: float = 2.0,
) -> list[dict[str, Any]]:
    """Merge visually identical adjacent roughcut markers for painting only."""
    rows: list[dict[str, Any]] = []
    for marker in markers or ():
        if not isinstance(marker, dict):
            continue
        start = _safe_float(marker.get("start"), None)
        if start is None:
            continue
        end = _safe_float(marker.get("end"), start)
        if end is None:
            end = start
        start = max(0.0, start)
        end = max(start, end)
        row = dict(marker)
        row["start"] = start
        row["end"] = end
        rows.append(row)
    if len(rows) <= 1:
        return rows

    pixels_per_second = max(0.001, float(pps or 1.0))
    max_gap_sec = max(0.034, float(max_gap_px or 0.0) / pixels_per_second)
    rows.sort(key=lambda item: (float(item["start"]), float(item["end"])))

    merged: list[dict[str, Any]] = []
    for row in rows:
        if not merged:
            merged.append(row)
            continue
        prev = merged[-1]
        if (
            _paint_identity(prev) == _paint_identity(row)
            and float(row["start"]) <= float(prev["end"]) + max_gap_sec
        ):
            prev["end"] = max(float(prev["end"]), float(row["end"]))
            continue
        merged.append(row)
    return merged


__all__ = ["coalesce_roughcut_paint_markers"]
