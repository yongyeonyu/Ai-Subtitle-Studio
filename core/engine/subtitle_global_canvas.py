from __future__ import annotations

"""Pure-Python facade for global-canvas/minimap subtitle lane data."""

from typing import Any

from core.native_subtitle_global_canvas import global_canvas_merged_segments


SUBTITLE_GLOBAL_CANVAS_FACADE_SCHEMA = "ai_subtitle_studio.subtitle_global_canvas.facade.v1"


def subtitle_global_canvas_lane_for_segment(seg: dict[str, Any]) -> str:
    if bool(seg.get("stt_pending") or seg.get("_live_stt_preview")):
        source = str(
            seg.get("stt_preview_source")
            or seg.get("stt_source")
            or seg.get("stt_ensemble_source")
            or ""
        ).strip().upper()
        return "STT2" if source == "STT2" else "STT1"
    return "SUBTITLE"


def global_canvas_merge_gap_sec(width: int, total: float, *, merge_gap_px: int = 4) -> float:
    if width <= 0 or total <= 0:
        return 0.0
    return float(merge_gap_px) * float(total) / float(max(1, width))


def global_canvas_minimap_rows(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    lanes: tuple[str, ...],
) -> list[dict[str, Any]]:
    lane_set = set(str(name) for name in lanes)
    rows: list[dict[str, Any]] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        try:
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
        except Exception:
            continue
        lane = subtitle_global_canvas_lane_for_segment(seg)
        if lane not in lane_set:
            continue
        rows.append(
            {
                "start": start,
                "end": end,
                "lane": lane,
                "text": str(seg.get("text", "") or "").strip(),
            }
        )
    return rows


def merged_global_canvas_minimap_segments(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    width: int,
    total: float,
    lanes: tuple[str, ...],
    output_lane: str,
    merge_gap_px: int = 4,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    if width <= 0 or total <= 0:
        return []
    rows = global_canvas_minimap_rows(segments, lanes=lanes)
    return global_canvas_merged_segments(
        rows,
        lanes=lanes,
        output_lane=output_lane,
        max_gap_sec=global_canvas_merge_gap_sec(width, total, merge_gap_px=merge_gap_px),
        include_text=include_text,
    )


def global_canvas_silence_rows(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        try:
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = max(start, float(seg.get("end", start) or start))
        except Exception:
            continue
        if end <= start:
            continue
        rows.append({"start": start, "end": end, "lane": "SILENCE"})
    return rows


def merged_global_canvas_silence_segments(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    width: int,
    total: float,
    merge_gap_px: int = 4,
) -> list[dict[str, Any]]:
    if width <= 0 or total <= 0:
        return []
    return global_canvas_merged_segments(
        global_canvas_silence_rows(segments),
        lanes=("SILENCE",),
        output_lane="SILENCE",
        max_gap_sec=global_canvas_merge_gap_sec(width, total, merge_gap_px=merge_gap_px),
        include_text=False,
    )


__all__ = [
    "SUBTITLE_GLOBAL_CANVAS_FACADE_SCHEMA",
    "global_canvas_merge_gap_sec",
    "global_canvas_minimap_rows",
    "global_canvas_silence_rows",
    "merged_global_canvas_minimap_segments",
    "merged_global_canvas_silence_segments",
    "subtitle_global_canvas_lane_for_segment",
]
