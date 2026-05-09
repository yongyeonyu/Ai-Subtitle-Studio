# Version: 01.00.00
"""Fast cut-boundary jump helpers.

The editor scan buttons should prefer already-known cut boundaries over a
frame-by-frame visual scan. These helpers keep that path pure and cheap so the
UI can jump with a sorted lookup.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from typing import Any


_TIME_KEYS = (
    "timeline_sec",
    "time",
    "start",
    "timeline_start",
    "sec",
    "seconds",
)
_FRAME_KEYS = ("timeline_frame", "frame")
_REJECTED_STATUSES = {"deleted", "rejected", "disabled", "off", "removed"}


def boundary_second(value: Any, *, primary_fps: float | None = None) -> float | None:
    """Return a cut-boundary time in seconds, or None when the row is unusable."""

    if isinstance(value, dict):
        status = str(value.get("status", "") or "").strip().lower()
        if status in _REJECTED_STATUSES:
            return None

        for key in _TIME_KEYS:
            if key not in value:
                continue
            try:
                sec = float(value.get(key) or 0.0)
            except Exception:
                continue
            if sec > 0.0:
                return sec

        fps = primary_fps
        try:
            fps = float(value.get("fps") or fps or 0.0)
        except Exception:
            fps = float(primary_fps or 0.0)
        if fps and fps > 0.0:
            for key in _FRAME_KEYS:
                if key not in value:
                    continue
                try:
                    frame = int(value.get(key) or 0)
                except Exception:
                    continue
                if frame > 0:
                    return frame / fps
        return None

    try:
        sec = float(value or 0.0)
    except Exception:
        return None
    return sec if sec > 0.0 else None


def normalize_boundary_seconds(
    values: Iterable[Any] | None,
    *,
    primary_fps: float | None = None,
    max_sec: float | None = None,
    dedupe_epsilon_sec: float = 0.055,
) -> list[float]:
    """Sort and dedupe boundary seconds for O(log n) previous/next lookup."""

    seconds: list[float] = []
    for value in list(values or []):
        sec = boundary_second(value, primary_fps=primary_fps)
        if sec is None or sec <= 0.0:
            continue
        if max_sec is not None and max_sec > 0.0 and sec > float(max_sec):
            continue
        seconds.append(float(sec))

    if not seconds:
        return []

    seconds.sort()
    epsilon = max(0.0, float(dedupe_epsilon_sec or 0.0))
    deduped: list[float] = []
    for sec in seconds:
        if deduped and abs(sec - deduped[-1]) <= epsilon:
            continue
        deduped.append(sec)
    return deduped


def nearest_boundary_second(
    values: Iterable[Any] | None,
    *,
    current_sec: float,
    direction: int,
    primary_fps: float | None = None,
    max_sec: float | None = None,
    min_gap_sec: float = 0.08,
) -> float | None:
    """Return the previous/next boundary around current_sec."""

    seconds = normalize_boundary_seconds(values, primary_fps=primary_fps, max_sec=max_sec)
    if not seconds:
        return None

    try:
        current = float(current_sec or 0.0)
    except Exception:
        current = 0.0
    gap = max(0.0, float(min_gap_sec or 0.0))

    if int(direction or 0) >= 0:
        idx = bisect_right(seconds, current + gap)
        return seconds[idx] if idx < len(seconds) else None

    idx = bisect_left(seconds, current - gap) - 1
    return seconds[idx] if idx >= 0 else None


__all__ = [
    "boundary_second",
    "nearest_boundary_second",
    "normalize_boundary_seconds",
]
