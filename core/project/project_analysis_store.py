from __future__ import annotations

from typing import Any

from core.project.project_assets import (
    copy_project_rows,
    copy_project_track_rows_with_counts,
    stt_candidate_track_counts,
)

VOICE_ACTIVITY_SCHEMA = "subtitle_detection.v1"
STT_CANDIDATE_TRACK_SCHEMA = "stt_candidate_tracks.v1"
VOICE_ACTIVITY_OPTIONAL_KEYS = ("score", "priority", "alpha", "selection_state", "selected_source")


def _iter_rows(rows: Any):
    if rows is None:
        return ()
    return rows


def _dict_rows_list(rows: Any) -> list[dict[str, Any]]:
    return [row for row in _iter_rows(rows) if isinstance(row, dict)]


def ensure_project_analysis_store(project: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    analysis = project.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
        project["analysis"] = analysis
    editor_state = project.get("editor_state")
    if not isinstance(editor_state, dict):
        return analysis, None
    editor_analysis = editor_state.get("analysis")
    if not isinstance(editor_analysis, dict):
        editor_analysis = {}
        editor_state["analysis"] = editor_analysis
    return analysis, editor_analysis


def store_project_voice_activity_segments(
    project: dict[str, Any],
    rows: list[dict[str, Any]] | None,
    *,
    copy_rows: bool = False,
    schema: str = VOICE_ACTIVITY_SCHEMA,
    timebase: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    analysis, _editor_analysis = ensure_project_analysis_store(project)
    stored_rows = copy_project_rows(rows) if copy_rows else _dict_rows_list(rows)
    analysis["voice_activity_schema"] = schema
    analysis["voice_activity_segments"] = stored_rows
    if isinstance(timebase, dict):
        analysis["voice_activity_timebase"] = dict(timebase)
    return stored_rows


def normalize_project_voice_activity_segment(
    item: dict[str, Any] | None,
    idx: int,
    *,
    start: float | None = None,
    end: float | None = None,
    include_id: bool = True,
) -> dict[str, Any]:
    source = item if isinstance(item, dict) else {}
    normalized_start = float((source.get("start", 0.0) if start is None else start) or 0.0)
    normalized_end = float((source.get("end", normalized_start) if end is None else end) or normalized_start)
    normalized = {
        "index": idx + 1,
        "start": normalized_start,
        "end": max(normalized_start, normalized_end),
        "kind": str(source.get("kind", "uncertain") or "uncertain"),
        "label": str(source.get("label", "") or ""),
        "source": str(source.get("source", "") or ""),
        "color": str(source.get("color", "") or ""),
    }
    if include_id:
        normalized["id"] = str(source.get("id") or f"subtitle_detection_{idx + 1:04d}")
    for key in VOICE_ACTIVITY_OPTIONAL_KEYS:
        if key in source:
            normalized[key] = source.get(key)
    if "priority" not in normalized:
        normalized["priority"] = 0
    return normalized


def normalize_project_voice_activity_segments(
    rows: list[dict[str, Any]] | None,
    *,
    priority_as_int: bool = False,
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for idx, item in enumerate(_iter_rows(rows)):
        if not isinstance(item, dict):
            continue
        normalized = normalize_project_voice_activity_segment(item, idx)
        if priority_as_int:
            normalized["priority"] = int(normalized.get("priority", 0) or 0)
        normalized_rows.append(normalized)
    return normalized_rows


def mirror_project_voice_activity_analysis(
    project: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
    *,
    copy_rows: bool = False,
    schema: str | None = None,
    timebase: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    analysis, editor_analysis = ensure_project_analysis_store(project)
    if editor_analysis is None:
        return []
    source_rows = rows if isinstance(rows, list) else analysis.get("voice_activity_segments")
    if not isinstance(source_rows, list):
        return []
    mirrored_rows = copy_project_rows(source_rows) if copy_rows else list(source_rows)
    editor_analysis["voice_activity_segments"] = mirrored_rows
    editor_analysis["voice_activity_schema"] = str(
        schema or analysis.get("voice_activity_schema") or VOICE_ACTIVITY_SCHEMA
    )
    if isinstance(timebase, dict):
        editor_analysis["voice_activity_timebase"] = dict(timebase)
    elif isinstance(analysis.get("voice_activity_timebase"), dict):
        editor_analysis["voice_activity_timebase"] = dict(analysis.get("voice_activity_timebase") or {})
    return mirrored_rows


def store_project_stt_candidate_tracks(
    project: dict[str, Any],
    candidate_tracks: dict[str, list[dict[str, Any]]] | None,
    *,
    copy_tracks: bool = False,
    schema: str = STT_CANDIDATE_TRACK_SCHEMA,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(candidate_tracks, dict) or not candidate_tracks:
        return {}
    analysis, _editor_analysis = ensure_project_analysis_store(project)
    counts: dict[str, int]
    if copy_tracks:
        stored_tracks, counts = copy_project_track_rows_with_counts(candidate_tracks)
    else:
        stored_tracks = candidate_tracks
        counts = stt_candidate_track_counts(stored_tracks)
    analysis["stt_candidate_schema"] = schema
    analysis["stt_candidate_tracks"] = stored_tracks
    analysis["stt_candidate_counts"] = counts
    return stored_tracks
