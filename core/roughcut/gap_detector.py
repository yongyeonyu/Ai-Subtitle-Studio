# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import SubtitleSegment, subtitle_from_dict


@dataclass(frozen=True, slots=True)
class TimelineGap:
    start: float
    end: float
    kind: str = "subtitle_gap"

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _normalize_segments(segments: Iterable[SubtitleSegment | dict]) -> list[SubtitleSegment]:
    normalized: list[SubtitleSegment] = []
    for index, segment in enumerate(segments):
        item = subtitle_from_dict(segment, fallback_id=index) if isinstance(segment, dict) else segment
        if item.end > item.start:
            normalized.append(item)
    return sorted(normalized, key=lambda seg: (seg.start, seg.end))


def detect_subtitle_gaps(
    segments: Iterable[SubtitleSegment | dict],
    media_duration: float | None = None,
    min_gap: float = 0.5,
    include_leading: bool = True,
    include_trailing: bool = True,
) -> list[TimelineGap]:
    """Return silent/no-subtitle regions without mutating subtitle data."""
    items = _normalize_segments(segments)
    gaps: list[TimelineGap] = []
    threshold = max(0.0, float(min_gap))

    cursor = 0.0
    for item in items:
        if item.start - cursor >= threshold and (include_leading or cursor > 0.0):
            gaps.append(TimelineGap(cursor, item.start))
        cursor = max(cursor, item.end)

    if media_duration is not None:
        duration = max(0.0, float(media_duration))
        if include_trailing and duration - cursor >= threshold:
            gaps.append(TimelineGap(cursor, duration))

    return gaps


def merge_close_gaps(gaps: Iterable[TimelineGap], merge_distance: float = 0.2) -> list[TimelineGap]:
    ordered = sorted(gaps, key=lambda gap: (gap.start, gap.end))
    if not ordered:
        return []

    merged: list[TimelineGap] = [ordered[0]]
    distance = max(0.0, float(merge_distance))
    for gap in ordered[1:]:
        previous = merged[-1]
        if gap.start - previous.end <= distance:
            merged[-1] = TimelineGap(previous.start, max(previous.end, gap.end), previous.kind)
        else:
            merged.append(gap)
    return merged
