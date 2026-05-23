from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Any

import numpy as np

from core.coerce import safe_float as _safe_float
from core.timeline_time import segment_display_time_bounds


class TimelineSegmentStore:
    """Compact time index for subtitle timeline rows.

    The canvas still owns the original row dictionaries for editing, but pan,
    zoom, hover, and hit-test queries use numeric arrays so we avoid rebuilding
    large Python tuple indexes on every viewport change.
    """

    __slots__ = (
        "rows",
        "starts",
        "ends",
        "order",
        "ordered_starts",
        "max_span",
        "_visible_cache_key",
        "_visible_cache_result",
    )

    def __init__(self, rows: list[dict[str, Any]] | None):
        self.rows = rows if isinstance(rows, list) else list(rows or [])
        self._visible_cache_key = None
        self._visible_cache_result: list[dict[str, Any]] = []
        count = len(self.rows)
        starts = np.zeros(count, dtype=np.float64)
        ends = np.zeros(count, dtype=np.float64)
        max_span = 0.0
        for idx, row in enumerate(self.rows):
            if isinstance(row, dict):
                start, end = segment_display_time_bounds(row)
            else:
                start = _safe_float(row)
                end = start
            if end < start:
                start, end = end, start
            starts[idx] = start
            ends[idx] = end
            max_span = max(max_span, max(0.0, end - start))
        self.starts = starts
        self.ends = ends
        self.order = np.argsort(starts, kind="mergesort") if count else np.zeros(0, dtype=np.int64)
        self.ordered_starts = starts[self.order] if count else np.zeros(0, dtype=np.float64)
        self.max_span = float(max_span)

    def set_rows(self, rows: list[dict[str, Any]] | None) -> None:
        self.rows = rows if isinstance(rows, list) else list(rows or [])
        self._visible_cache_key = None
        self._visible_cache_result = []

    def visible(self, start_sec: float, end_sec: float) -> list[dict[str, Any]]:
        if not self.rows:
            return []
        start = max(0.0, float(start_sec or 0.0))
        end = max(start, float(end_sec or start))
        cache_key = (
            id(self.rows),
            len(self.rows),
            round(start, 3),
            round(end, 3),
        )
        if self._visible_cache_key == cache_key:
            return self._visible_cache_result
        left = bisect_left(self.ordered_starts, max(0.0, start - self.max_span))
        right = bisect_right(self.ordered_starts, end)
        if right <= left:
            self._visible_cache_key = cache_key
            self._visible_cache_result = []
            return []
        indices = self.order[left:right]
        ends = self.ends[indices]
        starts = self.starts[indices]
        mask = (ends >= start) & (starts <= end)
        visible = [self.rows[int(idx)] for idx in indices[mask]]
        self._visible_cache_key = cache_key
        self._visible_cache_result = visible
        return visible


__all__ = ["TimelineSegmentStore"]
