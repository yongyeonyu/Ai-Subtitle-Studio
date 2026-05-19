# Version: 04.00.10
# Phase: PHASE2
"""Small, testable paint-pass planners for the timeline canvas.

The painter still owns drawing, but row selection and marker planning live here
so hot paint paths can be tested without constructing a full QPainter scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from core.frame_time import normalize_fps
from ui.timeline.timeline_constants import RULER_H, SEG_TOP, WAVE_H
from ui.timeline.timeline_segment_style import (
    cut_boundary_scan_marker_verified,
    official_boundary_marker_visual,
    scan_boundary_marker_label,
    scan_boundary_marker_visual,
)


def _list_rows(rows: Sequence | Iterable | None) -> list:
    return [] if rows is None else list(rows)


@dataclass(frozen=True)
class CutBoundaryLinePaintItem:
    kind: str
    sec: float
    x: int
    color: str
    width: int
    style: str = "solid"
    label: str = ""


@dataclass(frozen=True)
class CutBoundaryWorkLanePaintPlan:
    lane_top: int
    lane_h: int
    lines: tuple[CutBoundaryLinePaintItem, ...]
    labels: tuple[CutBoundaryLinePaintItem, ...]

    @property
    def has_items(self) -> bool:
        return bool(self.lines or self.labels)


def _iter_visible(
    rows: Sequence | Iterable | None,
    *,
    key: str,
    visible_start_sec: float,
    visible_end_sec: float,
    visible_filter: Callable | None,
):
    if visible_filter is None:
        return _list_rows(rows)
    source_rows = _list_rows(rows)
    try:
        return list(
            visible_filter(
                source_rows,
                key,
                float(visible_start_sec),
                float(visible_end_sec),
                pad_sec=0.05,
            )
            or []
        )
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return source_rows


def _row_sec(item) -> float | None:
    try:
        if isinstance(item, dict):
            return float(item.get("timeline_sec", item.get("time", item.get("start", 0.0))) or 0.0)
        return float(item or 0.0)
    except (TypeError, ValueError):
        return None


def _visual_hidden(visual: dict | None) -> bool:
    return not isinstance(visual, dict) or bool(visual.get("hidden")) or visual.get("visible") is False


def build_cut_boundary_work_lane_paint_plan(
    *,
    official_rows,
    scan_rows,
    visible_start_sec: float,
    visible_end_sec: float,
    clip_left: int,
    clip_right: int,
    total_duration: float,
    fps: float,
    dense_segment_mode: bool,
    sec_to_x: Callable[[float], int],
    visible_filter: Callable | None = None,
) -> CutBoundaryWorkLanePaintPlan:
    """Build visible cut-boundary marker geometry for the painter."""

    lane_top = RULER_H + WAVE_H + 5
    lane_h = max(18, SEG_TOP - lane_top - 7)
    official_items = _iter_visible(
        official_rows,
        key="boundary_times",
        visible_start_sec=visible_start_sec,
        visible_end_sec=visible_end_sec,
        visible_filter=visible_filter,
    )
    scan_items = [
        item
        for item in _iter_visible(
            scan_rows,
            key="scan_boundaries",
            visible_start_sec=visible_start_sec,
            visible_end_sec=visible_end_sec,
            visible_filter=visible_filter,
        )
        if isinstance(item, dict)
    ]
    if not official_items and not scan_items:
        return CutBoundaryWorkLanePaintPlan(lane_top=lane_top, lane_h=lane_h, lines=(), labels=())

    try:
        timeline_end_sec = max(0.0, float(total_duration or 0.0))
    except (TypeError, ValueError):
        timeline_end_sec = 0.0
    try:
        fps = normalize_fps(fps or 30.0)
    except (TypeError, ValueError):
        fps = 30.0
    end_boundary_slop = max(0.05, 2.0 / max(1.0, float(fps or 30.0)))

    def _is_timeline_end_boundary(sec: float) -> bool:
        return timeline_end_sec > 0.0 and float(sec) >= max(0.0, timeline_end_sec - end_boundary_slop)

    lines: list[CutBoundaryLinePaintItem] = []
    labels: list[CutBoundaryLinePaintItem] = []
    official_secs: set[float] = set()

    for item in official_items:
        sec = _row_sec(item)
        if sec is None or _is_timeline_end_boundary(sec):
            continue
        x = int(sec_to_x(float(sec)))
        if x < int(clip_left) - 8 or x > int(clip_right) + 8:
            continue
        visual = official_boundary_marker_visual(item)
        if _visual_hidden(visual):
            continue
        official_secs.add(round(float(sec), 3))
        lines.append(
            CutBoundaryLinePaintItem(
                kind="official",
                sec=float(sec),
                x=x,
                color=str(visual.get("color") or "#F5F7FA"),
                width=max(1, int(visual.get("width", 1) or 1)),
                style="solid",
            )
        )

    for item in scan_items:
        sec = _row_sec(item)
        if sec is None or _is_timeline_end_boundary(sec):
            continue
        x = int(sec_to_x(float(sec)))
        if x < int(clip_left) - 8 or x > int(clip_right) + 8:
            continue
        visual = scan_boundary_marker_visual(item)
        if _visual_hidden(visual):
            continue
        if cut_boundary_scan_marker_verified(item) and round(float(sec), 3) in official_secs:
            x -= 1
        marker = CutBoundaryLinePaintItem(
            kind="scan",
            sec=float(sec),
            x=x,
            color=str(visual.get("color") or "#8E8E93"),
            width=max(1, int(visual.get("width", 1) or 1)),
            style=str(visual.get("style") or "solid"),
            label=str(scan_boundary_marker_label(item) or ""),
        )
        lines.append(marker)
        if marker.label and not bool(dense_segment_mode):
            labels.append(marker)

    return CutBoundaryWorkLanePaintPlan(
        lane_top=lane_top,
        lane_h=lane_h,
        lines=tuple(lines),
        labels=tuple(labels),
    )


__all__ = [
    "CutBoundaryLinePaintItem",
    "CutBoundaryWorkLanePaintPlan",
    "build_cut_boundary_work_lane_paint_plan",
]
