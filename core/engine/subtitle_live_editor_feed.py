from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.timeline_time import segment_display_time_bounds

SUBTITLE_LIVE_EDITOR_FEED_SCHEMA = "ai_subtitle_studio.subtitle_live_editor_feed.v1"
SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA = "ai_subtitle_studio.subtitle_live_editor_runtime_tracks.v1"
SUBTITLE_LIVE_EDITOR_RUNTIME_STATUS_SCHEMA = "ai_subtitle_studio.subtitle_live_editor_runtime_status.v1"

_RUNTIME_TRACK_ORDER = ("VAD", "STT1", "STT2", "subtitle_preview", "final")
_RUNTIME_TRACK_ROLES = {
    "VAD": "runtime_reference_only",
    "STT1": "runtime_reference_only",
    "STT2": "runtime_reference_only",
    "subtitle_preview": "runtime_reference_only",
    "final": "save_export_render_authority",
}
_STT_SOURCE_KEYS = (
    "stt_preview_source",
    "stt_selected_source",
    "stt_source",
    "stt_ensemble_source",
    "source",
)


def _copy_rows(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> list[dict[str, Any]]:
    return [dict(row) for row in list(rows or []) if isinstance(row, dict)]


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        _copy_rows(rows),
        key=lambda row: segment_display_time_bounds(row),
    )


def _stt_runtime_track(row: dict[str, Any]) -> str:
    return _explicit_stt_runtime_track(row) or "STT1"


def _explicit_stt_runtime_track(row: dict[str, Any]) -> str | None:
    source = str(next((row.get(key) for key in _STT_SOURCE_KEYS if row.get(key)), "")).strip().upper()
    if "STT2" in source:
        return "STT2"
    if "STT1" in source or source == "STT":
        return "STT1"
    return None


def _runtime_track_row(row: dict[str, Any], *, track: str) -> dict[str, Any]:
    out = dict(row)
    out["_nle_runtime_track"] = track
    out["_nle_runtime_role"] = _RUNTIME_TRACK_ROLES.get(track, "runtime_reference_only")
    out["_nle_save_export_authority"] = track == "final"
    return out


def _build_runtime_tracks(
    *,
    final_surface: list[dict[str, Any]],
    stt_preview: list[dict[str, Any]],
    subtitle_preview: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    tracks: dict[str, list[dict[str, Any]]] = {track: [] for track in _RUNTIME_TRACK_ORDER}
    for row in _sort_rows(vad_segments):
        tracks["VAD"].append(_runtime_track_row(row, track="VAD"))
    for row in _sort_rows(stt_preview):
        track = _stt_runtime_track(row)
        tracks[track].append(_runtime_track_row(row, track=track))
    for row in _sort_rows(subtitle_preview):
        tracks["subtitle_preview"].append(_runtime_track_row(row, track="subtitle_preview"))
        track = _explicit_stt_runtime_track(row)
        if track in {"STT1", "STT2"}:
            tracks[track].append(_runtime_track_row(row, track=track))
    for row in _sort_rows(final_surface):
        tracks["final"].append(_runtime_track_row(row, track="final"))
    return {track: tuple(_sort_rows(rows)) for track, rows in tracks.items()}


def _compact_runtime_tracks_status(
    runtime_tracks: dict[str, tuple[dict[str, Any], ...]],
) -> dict[str, Any]:
    tracks: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    active_tracks: list[str] = []
    for track in _RUNTIME_TRACK_ORDER:
        rows = tuple(runtime_tracks.get(track) or ())
        count = len(rows)
        counts[track] = count
        if count > 0:
            active_tracks.append(track)
        tracks[track] = {
            "role": _RUNTIME_TRACK_ROLES.get(track, "runtime_reference_only"),
            "count": count,
            "active": count > 0,
            "authoritative_for_save_export": track == "final",
        }
    return {
        "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_STATUS_SCHEMA,
        "tracks": tracks,
        "counts": counts,
        "active_tracks": active_tracks,
        "total_count": sum(counts.values()),
        "final_authority_track": "final",
        "compact_payload": True,
    }


@dataclass(frozen=True)
class SubtitleLiveEditorFeed:
    schema: str
    confirmed_segments: tuple[dict[str, Any], ...]
    stt_preview_segments: tuple[dict[str, Any], ...]
    subtitle_preview_segments: tuple[dict[str, Any], ...]
    final_surface_segments: tuple[dict[str, Any], ...]
    preview_lane_segments: tuple[dict[str, Any], ...]
    combined_segments: tuple[dict[str, Any], ...]
    vad_segments: tuple[dict[str, Any], ...]
    runtime_tracks: dict[str, tuple[dict[str, Any], ...]]
    runtime_track_segments: tuple[dict[str, Any], ...]
    total_duration: float

    def runtime_status(self) -> dict[str, Any]:
        return _compact_runtime_tracks_status(self.runtime_tracks)

    def to_dict(self) -> dict[str, Any]:
        runtime_tracks = {
            track: {
                "schema": SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA,
                "role": _RUNTIME_TRACK_ROLES.get(track, "runtime_reference_only"),
                "authoritative_for_save_export": track == "final",
                "segments": [dict(row) for row in rows],
                "count": len(rows),
            }
            for track, rows in self.runtime_tracks.items()
        }
        return {
            "schema": self.schema,
            "confirmed_segments": [dict(row) for row in self.confirmed_segments],
            "stt_preview_segments": [dict(row) for row in self.stt_preview_segments],
            "subtitle_preview_segments": [dict(row) for row in self.subtitle_preview_segments],
            "final_surface_segments": [dict(row) for row in self.final_surface_segments],
            "preview_lane_segments": [dict(row) for row in self.preview_lane_segments],
            "combined_segments": [dict(row) for row in self.combined_segments],
            "vad_segments": [dict(row) for row in self.vad_segments],
            "runtime_tracks": runtime_tracks,
            "runtime_track_status": self.runtime_status(),
            "runtime_track_segments": [dict(row) for row in self.runtime_track_segments],
            "total_duration": self.total_duration,
            "surface_contract": {
                "final_surface": "confirmed_segments_only",
                "preview_lane": "subtitle_preview_plus_stt_preview",
                "combined_segments": "diagnostic_candidate_lane_only_not_final_overlay_or_save",
            },
            "runtime_track_contract": {
                "final": "only_track_with_save_export_render_authority",
                "STT1": "runtime_reference_only_not_save_export",
                "STT2": "runtime_reference_only_not_save_export",
                "VAD": "runtime_reference_only_not_save_export",
                "subtitle_preview": "runtime_reference_only_not_save_export",
            },
            "counts": {
                "confirmed": len(self.confirmed_segments),
                "stt_preview": len(self.stt_preview_segments),
                "subtitle_preview": len(self.subtitle_preview_segments),
                "final_surface": len(self.final_surface_segments),
                "preview_lane": len(self.preview_lane_segments),
                "combined": len(self.combined_segments),
                "vad": len(self.vad_segments),
                "runtime_tracks": {track: len(rows) for track, rows in self.runtime_tracks.items()},
                "runtime_track_segments": len(self.runtime_track_segments),
            },
        }


def build_subtitle_live_editor_feed(
    *,
    confirmed_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    stt_preview_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    subtitle_preview_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    total_duration_floor: float = 0.0,
) -> SubtitleLiveEditorFeed:
    confirmed = _sort_rows(_copy_rows(confirmed_segments))
    stt_preview = _sort_rows(_copy_rows(stt_preview_segments))
    subtitle_preview = _sort_rows(_copy_rows(subtitle_preview_segments))
    vad = _sort_rows(_copy_rows(vad_segments))
    final_surface = _sort_rows(confirmed)
    preview_lane = _sort_rows(subtitle_preview + stt_preview)
    combined = _sort_rows(final_surface + preview_lane)
    runtime_tracks = _build_runtime_tracks(
        final_surface=final_surface,
        stt_preview=stt_preview,
        subtitle_preview=subtitle_preview,
        vad_segments=vad,
    )
    runtime_track_segments = tuple(
        _sort_rows([row for rows in runtime_tracks.values() for row in rows])
    )
    total_duration = 0.0
    timeline_rows = _sort_rows(combined + vad)
    if timeline_rows:
        try:
            total_duration = float(segment_display_time_bounds(timeline_rows[-1])[1])
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
        vad_segments=tuple(vad),
        runtime_tracks=runtime_tracks,
        runtime_track_segments=runtime_track_segments,
        total_duration=total_duration,
    )


__all__ = [
    "SUBTITLE_LIVE_EDITOR_FEED_SCHEMA",
    "SUBTITLE_LIVE_EDITOR_RUNTIME_TRACKS_SCHEMA",
    "SUBTITLE_LIVE_EDITOR_RUNTIME_STATUS_SCHEMA",
    "SubtitleLiveEditorFeed",
    "build_subtitle_live_editor_feed",
]
