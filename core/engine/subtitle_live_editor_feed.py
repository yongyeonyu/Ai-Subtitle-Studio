from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.timeline_time import segment_display_time_bounds

SUBTITLE_LIVE_EDITOR_FEED_SCHEMA = "ai_subtitle_studio.subtitle_live_editor_feed.v1"


def _copy_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> list[dict[str, Any]]:
    return [dict(row) for row in list(rows or []) if isinstance(row, dict)]


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        _copy_rows(rows),
        key=lambda row: segment_display_time_bounds(row),
    )


@dataclass(frozen=True)
class SubtitleLiveEditorFeed:
    schema: str
    confirmed_segments: tuple[dict[str, Any], ...]
    stt_preview_segments: tuple[dict[str, Any], ...]
    subtitle_preview_segments: tuple[dict[str, Any], ...]
    final_surface_segments: tuple[dict[str, Any], ...]
    preview_lane_segments: tuple[dict[str, Any], ...]
    combined_segments: tuple[dict[str, Any], ...]
    total_duration: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "confirmed_segments": [dict(row) for row in self.confirmed_segments],
            "stt_preview_segments": [dict(row) for row in self.stt_preview_segments],
            "subtitle_preview_segments": [dict(row) for row in self.subtitle_preview_segments],
            "final_surface_segments": [dict(row) for row in self.final_surface_segments],
            "preview_lane_segments": [dict(row) for row in self.preview_lane_segments],
            "combined_segments": [dict(row) for row in self.combined_segments],
            "total_duration": self.total_duration,
            "surface_contract": {
                "final_surface": "confirmed_segments_only",
                "preview_lane": "subtitle_preview_plus_stt_preview",
                "combined_segments": "diagnostic_candidate_lane_only_not_final_overlay_or_save",
            },
            "counts": {
                "confirmed": len(self.confirmed_segments),
                "stt_preview": len(self.stt_preview_segments),
                "subtitle_preview": len(self.subtitle_preview_segments),
                "final_surface": len(self.final_surface_segments),
                "preview_lane": len(self.preview_lane_segments),
                "combined": len(self.combined_segments),
            },
        }


def build_subtitle_live_editor_feed(
    *,
    confirmed_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    stt_preview_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    subtitle_preview_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    total_duration_floor: float = 0.0,
) -> SubtitleLiveEditorFeed:
    confirmed = _sort_rows(_copy_rows(confirmed_segments))
    stt_preview = _sort_rows(_copy_rows(stt_preview_segments))
    subtitle_preview = _sort_rows(_copy_rows(subtitle_preview_segments))
    final_surface = _sort_rows(confirmed)
    preview_lane = _sort_rows(subtitle_preview + stt_preview)
    combined = _sort_rows(final_surface + preview_lane)
    total_duration = 0.0
    if combined:
        try:
            total_duration = float(segment_display_time_bounds(combined[-1])[1])
        except Exception:
            total_duration = 0.0
    try:
        total_duration = max(total_duration, float(total_duration_floor or 0.0))
    except Exception:
        pass
    return SubtitleLiveEditorFeed(
        schema=SUBTITLE_LIVE_EDITOR_FEED_SCHEMA,
        confirmed_segments=tuple(confirmed),
        stt_preview_segments=tuple(stt_preview),
        subtitle_preview_segments=tuple(subtitle_preview),
        final_surface_segments=tuple(final_surface),
        preview_lane_segments=tuple(preview_lane),
        combined_segments=tuple(combined),
        total_duration=total_duration,
    )


__all__ = [
    "SUBTITLE_LIVE_EDITOR_FEED_SCHEMA",
    "SubtitleLiveEditorFeed",
    "build_subtitle_live_editor_feed",
]
