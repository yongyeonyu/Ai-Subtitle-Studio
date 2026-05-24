from __future__ import annotations

"""Pure-Python subtitle segment facade for save/reopen invariants."""

from dataclasses import dataclass
from typing import Any, Callable

from core.frame_time import normalize_fps, normalize_segments_to_frame_grid


SUBTITLE_SEGMENTS_FACADE_SCHEMA = "ai_subtitle_studio.subtitle_segments.facade.v1"


@dataclass(frozen=True)
class PreparedSubtitleSegments:
    schema: str
    source_segments: list[dict[str, Any]]
    prepared_segments: list[dict[str, Any]]
    fps: float | None


def copy_segment_rows(segments: Any) -> list[dict[str, Any]]:
    return [dict(seg) for seg in list(segments or []) if isinstance(seg, dict)]


def infer_save_fps(segments: list[dict[str, Any]], fps: float | int | str | None = None) -> float | None:
    try:
        if fps is not None and float(fps) > 0.0:
            return normalize_fps(fps)
    except (TypeError, ValueError):
        pass
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        frame_range = seg.get("frame_range")
        if isinstance(frame_range, dict):
            value = frame_range.get("timeline_frame_rate")
            try:
                if value is not None and float(value) > 0.0:
                    return normalize_fps(value)
            except (TypeError, ValueError):
                pass
        for key in ("timeline_frame_rate", "frame_rate"):
            value = seg.get(key)
            try:
                if value is not None and float(value) > 0.0:
                    return normalize_fps(value)
            except (TypeError, ValueError):
                continue
    return None


def prepare_save_reopen_segments(
    segments: list[dict[str, Any]],
    *,
    apply_offset: bool = True,
    adjust_timing_func: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    fps: float | int | str | None = None,
) -> PreparedSubtitleSegments:
    source = segments
    if apply_offset and callable(adjust_timing_func):
        source = adjust_timing_func(segments)
    source_segments = copy_segment_rows(source)
    effective_fps = infer_save_fps(source_segments, fps)
    prepared_segments = (
        normalize_segments_to_frame_grid(source_segments, effective_fps, min_frames=1, preserve_order=True)
        if effective_fps is not None
        else copy_segment_rows(source_segments)
    )
    return PreparedSubtitleSegments(
        schema=SUBTITLE_SEGMENTS_FACADE_SCHEMA,
        source_segments=source_segments,
        prepared_segments=prepared_segments,
        fps=effective_fps,
    )


__all__ = [
    "PreparedSubtitleSegments",
    "SUBTITLE_SEGMENTS_FACADE_SCHEMA",
    "copy_segment_rows",
    "infer_save_fps",
    "prepare_save_reopen_segments",
]
