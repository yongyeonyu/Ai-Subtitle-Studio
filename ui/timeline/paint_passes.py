# Version: 04.00.10
# Phase: PHASE2
"""Small, testable paint-pass planners for the timeline canvas.

The painter still owns drawing, but row selection and marker planning live here
so hot paint paths can be tested without constructing a full QPainter scene.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from PyQt6.QtCore import QRect

from core.frame_time import normalize_fps
from core.timeline_time import segment_display_time_bounds
from ui.timeline.timeline_constants import (
    ICON_SZ,
    RULER_H,
    SEG_TOP,
    STT_PREVIEW_VERTICAL_INSET,
    WAVE_H,
)
from ui.timeline.stt_preview_layout import assign_stt_preview_lanes, stt_preview_lane_geometry
from ui.timeline.timeline_segment_style import (
    cut_boundary_scan_marker_verified,
    official_boundary_marker_visual,
    scan_boundary_marker_label,
    scan_boundary_marker_visual,
    stt_candidate_selection_state,
)

CUT_BOUNDARY_WORK_LANE_DIM_ALPHA = 128


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
    alpha: int = CUT_BOUNDARY_WORK_LANE_DIM_ALPHA


@dataclass(frozen=True)
class CutBoundaryWorkLanePaintPlan:
    lane_top: int
    lane_h: int
    lines: tuple[CutBoundaryLinePaintItem, ...]
    labels: tuple[CutBoundaryLinePaintItem, ...]

    @property
    def has_items(self) -> bool:
        return bool(self.lines or self.labels)


@dataclass(frozen=True)
class GapLanePaintItem:
    rect: QRect
    icon_rect: QRect


@dataclass(frozen=True)
class GapLanePaintPlan:
    compact_gap_mode: bool
    inactive_rects: tuple[QRect, ...]
    inactive_plus_rects: tuple[QRect, ...]
    active_items: tuple[GapLanePaintItem, ...]

    @property
    def has_items(self) -> bool:
        return bool(self.inactive_rects or self.inactive_plus_rects or self.active_items)


@dataclass(frozen=True)
class STTPreviewPaintItem:
    segment: dict
    rect: QRect
    selection_state: str
    is_selected: bool


@dataclass(frozen=True)
class STTPreviewLanePaintPlan:
    aggregate_rects: tuple[QRect, ...]
    items: tuple[STTPreviewPaintItem, ...]

    @property
    def has_items(self) -> bool:
        return bool(self.aggregate_rects or self.items)


@dataclass(frozen=True)
class AggregateVectorSubtitlePaintPlan:
    enabled: bool
    subtitle_rects: tuple[QRect, ...]
    speaker_rects: tuple[QRect, ...]
    detail_segments: tuple[dict, ...]

    @property
    def has_items(self) -> bool:
        return bool(self.subtitle_rects or self.speaker_rects or self.detail_segments)


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


def _segment_x_bounds(seg: dict, sec_to_x: Callable[[float], int]) -> tuple[int, int] | None:
    try:
        start, end = segment_display_time_bounds(seg)
    except (AttributeError, TypeError, ValueError):
        return None
    return int(sec_to_x(start)), int(sec_to_x(end))


def visible_pixel_span(
    x1: int,
    x2: int,
    *,
    clip_left: int,
    clip_right: int,
    min_edge_fragment_px: int = 0,
) -> tuple[int, int] | None:
    """Return the visible half-open pixel span or drop clipped edge slivers."""

    left = min(int(x1), int(x2))
    right = max(int(x1), int(x2))
    if right <= left:
        right = left + 1
    visible_left = max(left, int(clip_left))
    visible_right = min(right, int(clip_right) + 1)
    if visible_right <= visible_left:
        return None
    visible_width = visible_right - visible_left
    clipped = visible_left != left or visible_right != right
    if clipped and visible_width <= max(0, int(min_edge_fragment_px)):
        return None
    return visible_left, visible_right


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
                alpha=CUT_BOUNDARY_WORK_LANE_DIM_ALPHA,
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
            alpha=CUT_BOUNDARY_WORK_LANE_DIM_ALPHA,
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


def coalesce_rects_by_row(rects, *, max_gap_px: int = 0) -> list[QRect]:
    """Merge adjacent same-lane rects in dense modes to reduce painter calls."""

    rows: dict[tuple[int, int], list[QRect]] = {}
    for rect in rects or []:
        if rect is None or not rect.isValid() or rect.isEmpty():
            continue
        rows.setdefault((int(rect.y()), int(rect.height())), []).append(rect)
    merged: list[QRect] = []
    for (y, h), row_rects in rows.items():
        row_rects.sort(key=lambda r: (int(r.left()), int(r.right())))
        cur_left: int | None = None
        cur_right: int | None = None
        for rect in row_rects:
            left = int(rect.left())
            right = int(rect.right())
            if cur_left is not None and left <= cur_right + max(0, int(max_gap_px)) + 1:
                cur_right = max(cur_right, right)
                continue
            if cur_left is not None:
                merged.append(QRect(cur_left, y, max(1, cur_right - cur_left + 1), h))
            cur_left, cur_right = left, right
        if cur_left is not None:
            merged.append(QRect(cur_left, y, max(1, cur_right - cur_left + 1), h))
    return merged


def build_gap_lane_paint_plan(
    *,
    gaps,
    clip_left: int,
    clip_right: int,
    seg_top: int,
    seg_bot: int,
    overview_mode: bool,
    ultra_dense_segment_mode: bool,
    dense_segment_mode: bool,
    show_gap_insert_controls: bool,
    sec_to_x: Callable[[float], int],
    icon_rect_builder: Callable[[int, int], QRect],
    plus_rect_builder: Callable[[int, int], QRect],
) -> GapLanePaintPlan:
    """Build visible gap-lane geometry without touching QPainter."""

    if not bool(show_gap_insert_controls) or not gaps:
        return GapLanePaintPlan(False, (), (), ())
    compact_gap_mode = bool(overview_mode or ultra_dense_segment_mode or len(gaps) >= 512)
    inactive_rects: list[QRect] = []
    inactive_plus_rects: list[QRect] = []
    active_items: list[GapLanePaintItem] = []
    for gap in gaps:
        bounds = _segment_x_bounds(gap, sec_to_x)
        if bounds is None:
            continue
        x1, x2 = bounds
        visible_span = visible_pixel_span(
            x1,
            x2,
            clip_left=clip_left,
            clip_right=clip_right,
            min_edge_fragment_px=2,
        )
        if visible_span is None:
            continue
        draw_x1, draw_x2 = visible_span
        sw = max(4, draw_x2 - draw_x1)
        rect = QRect(int(draw_x1), int(seg_top), int(sw), int(seg_bot - seg_top))
        if bool(gap.get("active", False)):
            active_items.append(GapLanePaintItem(rect=rect, icon_rect=icon_rect_builder(draw_x1, draw_x2)))
            continue
        if compact_gap_mode:
            continue
        inactive_rects.append(rect)
        if sw >= int(ICON_SZ) + 8 and not bool(dense_segment_mode):
            inactive_plus_rects.append(plus_rect_builder(draw_x1, draw_x2))
    return GapLanePaintPlan(
        compact_gap_mode=compact_gap_mode,
        inactive_rects=tuple(inactive_rects),
        inactive_plus_rects=tuple(inactive_plus_rects),
        active_items=tuple(active_items),
    )


def build_stt_preview_lane_paint_plan(
    *,
    preview_segments,
    clip_left: int,
    clip_right: int,
    lane_top: int,
    lane_bot: int,
    pps: float,
    ultra_dense_segment_mode: bool,
    selected_final_stt_segments,
    selected_final_stt_index,
    sec_to_x: Callable[[float], int],
    sublane_map=None,
    sublane_count: int = 1,
    selection_state_map=None,
) -> STTPreviewLanePaintPlan:
    """Build preview-lane geometry and selection state outside the painter."""

    if not preview_segments:
        return STTPreviewLanePaintPlan((), ())
    preview_top = int(lane_top + STT_PREVIEW_VERTICAL_INSET)
    preview_height = max(12, int((lane_bot - lane_top) - (STT_PREVIEW_VERTICAL_INSET * 2)))
    if bool(ultra_dense_segment_mode) and len(preview_segments) >= 96 and not bool(selected_final_stt_segments):
        spans: list[tuple[int, int]] = []
        cur_l: int | None = None
        cur_r: int | None = None
        merge_gap_px = 4 if float(pps or 0.0) < 10.0 else 3
        for seg in preview_segments:
            bounds = _segment_x_bounds(seg, sec_to_x)
            if bounds is None:
                continue
            x1, x2 = bounds
            visible_span = visible_pixel_span(
                x1,
                x2,
                clip_left=clip_left,
                clip_right=clip_right,
            )
            if visible_span is None:
                continue
            draw_x1, draw_x2 = visible_span
            if cur_l is not None and draw_x1 <= cur_r + merge_gap_px:
                cur_r = max(cur_r, draw_x2)
            else:
                if cur_l is not None:
                    spans.append((cur_l, cur_r))
                cur_l, cur_r = draw_x1, draw_x2
        if cur_l is not None:
            spans.append((cur_l, cur_r))
        aggregate_rects = tuple(
            QRect(left, preview_top, max(1, right - left), max(1, preview_height - 1))
            for left, right in spans
        )
        return STTPreviewLanePaintPlan(aggregate_rects, ())

    sublane_map = dict(sublane_map or {})
    sublane_count = max(1, int(sublane_count or 1))
    if not sublane_map:
        sublane_map, sublane_count = assign_stt_preview_lanes(preview_segments)
    selection_state_map = dict(selection_state_map or {})
    items: list[STTPreviewPaintItem] = []
    for seg in preview_segments:
        bounds = _segment_x_bounds(seg, sec_to_x)
        if bounds is None:
            continue
        x1, x2 = bounds
        visible_span = visible_pixel_span(
            x1,
            x2,
            clip_left=clip_left,
            clip_right=clip_right,
            min_edge_fragment_px=2,
        )
        if visible_span is None:
            continue
        draw_x1, draw_x2 = visible_span
        sw = max(2, draw_x2 - draw_x1)
        sublane_y, sublane_h = stt_preview_lane_geometry(
            lane_top,
            lane_bot,
            sublane_map.get(id(seg), 0),
            sublane_count,
            inset=STT_PREVIEW_VERTICAL_INSET,
        )
        rect = QRect(int(draw_x1) + 1, int(sublane_y), max(2, int(sw) - 2), max(1, int(sublane_h) - 1))
        selection_state = str(selection_state_map.get(id(seg), "") or "")
        if not selection_state and selected_final_stt_segments:
            selection_state = stt_candidate_selection_state(
                seg,
                selected_final_stt_segments,
                selected_final_stt_index,
            )
        items.append(
            STTPreviewPaintItem(
                segment=seg,
                rect=rect,
                selection_state=selection_state,
                is_selected=selection_state in {"manual", "llm"},
            )
        )
    return STTPreviewLanePaintPlan((), tuple(items))


def build_aggregate_vector_subtitle_paint_plan(
    *,
    segments,
    clip_left: int,
    clip_right: int,
    pps: float,
    subtitle_top: int,
    subtitle_bot: int,
    speaker_top: int,
    speaker_bot: int,
    ultra_dense_segment_mode: bool,
    active_seg_start,
    hover_line,
) -> AggregateVectorSubtitlePaintPlan:
    """Build the aggregate dense-overview subtitle strip pass."""

    aggregate_overview = bool(
        ultra_dense_segment_mode
        and (len(segments) >= 96 or (len(segments) >= 32 and float(pps or 0.0) < 10.0))
    )
    if not aggregate_overview:
        return AggregateVectorSubtitlePaintPlan(False, (), (), ())
    spans: list[tuple[int, int]] = []
    detail_segments: list[dict] = []
    try:
        active_start_f = float(active_seg_start) if active_seg_start is not None else None
    except (TypeError, ValueError):
        active_start_f = None
    merge_gap_px = 4 if float(pps or 0.0) < 10.0 else 3
    cur_l: int | None = None
    cur_r: int | None = None
    for seg in segments:
        try:
            start = float(seg.get("start", 0.0) or 0.0)
            end = float(seg.get("end", start) or start)
        except (AttributeError, TypeError, ValueError):
            continue
        if end < start:
            start, end = end, start
        x1 = int(start * float(pps or 1.0))
        x2 = int(end * float(pps or 1.0))
        visible_span = visible_pixel_span(
            x1,
            x2,
            clip_left=clip_left,
            clip_right=clip_right,
        )
        if visible_span is None:
            continue
        is_active = active_start_f is not None and abs(start - active_start_f) < 0.001
        is_hover = hover_line == seg.get("line")
        if is_active or is_hover:
            detail_segments.append(seg)
            continue
        draw_x1, draw_x2 = visible_span
        if cur_l is not None and draw_x1 <= cur_r + merge_gap_px:
            if draw_x2 > cur_r:
                cur_r = draw_x2
        else:
            if cur_l is not None:
                spans.append((cur_l, cur_r))
            cur_l, cur_r = draw_x1, draw_x2
    if cur_l is not None:
        spans.append((cur_l, cur_r))
    subtitle_rects = tuple(
        QRect(left, int(subtitle_top), max(1, right - left), int(subtitle_bot - subtitle_top))
        for left, right in spans
    )
    speaker_rects = tuple(
        QRect(left, int(speaker_top), max(1, right - left), int(speaker_bot - speaker_top))
        for left, right in spans
    )
    return AggregateVectorSubtitlePaintPlan(
        enabled=True,
        subtitle_rects=subtitle_rects,
        speaker_rects=speaker_rects,
        detail_segments=tuple(detail_segments),
    )


__all__ = [
    "AggregateVectorSubtitlePaintPlan",
    "CUT_BOUNDARY_WORK_LANE_DIM_ALPHA",
    "CutBoundaryLinePaintItem",
    "CutBoundaryWorkLanePaintPlan",
    "GapLanePaintItem",
    "GapLanePaintPlan",
    "STTPreviewLanePaintPlan",
    "STTPreviewPaintItem",
    "build_aggregate_vector_subtitle_paint_plan",
    "build_cut_boundary_work_lane_paint_plan",
    "build_gap_lane_paint_plan",
    "build_stt_preview_lane_paint_plan",
    "coalesce_rects_by_row",
    "visible_pixel_span",
]
