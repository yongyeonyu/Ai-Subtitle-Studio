from __future__ import annotations

from bisect import bisect_right
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, segment_frame_bounds
from core.project.nle_project_state import NLECaptionState

NLE_RUNTIME_CUTOVER_SCHEMA = "ai_subtitle_studio.nle_runtime_cutover.v1"

_PREVIEW_KEYS = ("stt_pending", "_live_stt_preview", "_live_subtitle_preview")
_CANDIDATE_KEYS = (
    "stt_candidates",
    "stt_lattice_candidates",
    "manual_stt_candidates",
    "stt_retry_candidates",
    "stt_recheck_candidates",
    "stt_rescue_candidates",
)
_OVERLAY_DROP_KEYS = set(_PREVIEW_KEYS + _CANDIDATE_KEYS + ("is_gap", "quality_candidates"))
_MICRO_OVERLAP_MAX_FRAMES = 1


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _is_preview_row(row: dict[str, Any]) -> bool:
    return any(bool(row.get(key)) for key in _PREVIEW_KEYS)


def _is_runtime_reference_row(row: dict[str, Any]) -> bool:
    if row.get("_nle_save_export_authority") is False:
        return True
    track = str(row.get("_nle_runtime_track") or "").strip()
    if track and track != "final":
        return True
    role = str(row.get("_nle_runtime_role") or "").strip()
    return role == "runtime_reference_only"


def _is_final_overlay_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if bool(row.get("is_gap")) or _is_preview_row(row) or _is_runtime_reference_row(row):
        return False
    return bool(str(row.get("text", "") or "").strip())


def _window_rows(
    rows: list[dict[str, Any]],
    *,
    center_sec: float,
    before_sec: float,
    after_sec: float,
    max_segments: int,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    starts = [_as_float(row.get("start", row.get("timeline_start", 0.0)), 0.0) for row in rows]
    left_sec = max(0.0, center_sec - before_sec)
    right_sec = center_sec + after_sec
    left = max(0, bisect_right(starts, left_sec) - 1)
    right = min(len(rows), bisect_right(starts, right_sec) + 1)
    if right - left <= max_segments:
        return rows[left:right]
    center_idx = min(len(rows) - 1, max(0, bisect_right(starts, center_sec) - 1))
    half = max(1, max_segments // 2)
    trim_left = max(0, center_idx - half)
    trim_right = min(len(rows), trim_left + max_segments)
    trim_left = max(0, trim_right - max_segments)
    return rows[trim_left:trim_right]


def _row_frame_bounds(row: dict[str, Any], *, fps: float) -> tuple[int, int]:
    return segment_frame_bounds(row, fps, min_frames=0)


def _set_row_start_frame(row: dict[str, Any], *, start_frame: int, fps: float) -> dict[str, Any]:
    updated = dict(row)
    start = frame_to_sec(start_frame, fps)
    updated["start_frame"] = int(start_frame)
    updated["timeline_start_frame"] = int(start_frame)
    frame_range = dict(updated.get("frame_range") or {}) if isinstance(updated.get("frame_range"), dict) else {}
    frame_range["start"] = int(start_frame)
    updated["frame_range"] = frame_range
    updated["start"] = start
    updated["timeline_start"] = start
    updated["_nle_runtime_overlap_repaired"] = "shared_boundary"
    return updated


def _final_surface_rows_without_overlap(
    rows: list[dict[str, Any]],
    *,
    surface: str,
    primary_fps: float,
    block_unfixable: bool,
) -> list[dict[str, Any]]:
    stable: list[dict[str, Any]] = []
    previous_end_frame: int | None = None
    for row in rows:
        start_frame, end_frame = _row_frame_bounds(row, fps=primary_fps)
        if end_frame <= start_frame:
            if block_unfixable:
                raise ValueError(f"nle_{surface}_invalid_duration")
            continue
        if previous_end_frame is not None and start_frame < previous_end_frame:
            overlap_frames = previous_end_frame - start_frame
            can_share_boundary = (
                overlap_frames <= _MICRO_OVERLAP_MAX_FRAMES
                and end_frame > previous_end_frame
            )
            if not can_share_boundary:
                if block_unfixable:
                    raise ValueError(f"nle_{surface}_final_overlap")
                continue
            row = _set_row_start_frame(row, start_frame=previous_end_frame, fps=primary_fps)
            start_frame = previous_end_frame
        stable.append(row)
        previous_end_frame = end_frame
    return stable


def _nle_final_surface_segments_from_editor_rows(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    surface: str,
    primary_fps: float = 30.0,
    window: bool = False,
    center_sec: float = 0.0,
    before_sec: float = 75.0,
    after_sec: float = 105.0,
    max_segments: int = 480,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    caption_states = [
        NLECaptionState.from_editor_row(row, index=index, fps=fps)
        for index, row in enumerate(list(rows or []))
        if _is_final_overlay_row(row)
    ]
    overlay_rows: list[dict[str, Any]] = []
    for index, caption in enumerate(caption_states):
        row = caption.to_editor_row(index=index, fps=fps)
        for key in _OVERLAY_DROP_KEYS:
            row.pop(key, None)
        row["_nle_runtime_surface"] = str(surface or "final")
        row["_nle_runtime_schema"] = NLE_RUNTIME_CUTOVER_SCHEMA
        overlay_rows.append(row)
    overlay_rows.sort(key=lambda item: (_as_float(item.get("start", item.get("timeline_start", 0.0))), int(item.get("line", 0) or 0)))
    overlay_rows = _final_surface_rows_without_overlap(
        overlay_rows,
        surface=str(surface or "final"),
        primary_fps=fps,
        block_unfixable=str(surface or "") == "save_export",
    )
    if not window:
        return overlay_rows
    try:
        max_count = int(max_segments)
    except Exception:
        max_count = 480
    return _window_rows(
        overlay_rows,
        center_sec=max(0.0, _as_float(center_sec, 0.0)),
        before_sec=max(10.0, _as_float(before_sec, 75.0)),
        after_sec=max(20.0, _as_float(after_sec, 105.0)),
        max_segments=max(1, max_count),
    )


def nle_final_overlay_segments_from_editor_rows(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    primary_fps: float = 30.0,
    center_sec: float = 0.0,
    before_sec: float = 75.0,
    after_sec: float = 105.0,
    max_segments: int = 480,
) -> list[dict[str, Any]]:
    return _nle_final_surface_segments_from_editor_rows(
        rows,
        surface="final_overlay",
        primary_fps=primary_fps,
        window=True,
        center_sec=center_sec,
        before_sec=before_sec,
        after_sec=after_sec,
        max_segments=max_segments,
    )


def nle_global_canvas_segments_from_editor_rows(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    return _nle_final_surface_segments_from_editor_rows(
        rows,
        surface="global_canvas",
        primary_fps=primary_fps,
        window=False,
    )


def nle_timeline_canvas_segments_from_editor_rows(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps or 30.0)
    source_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    final_rows: list[dict[str, Any]] = []
    passthrough_by_ordinal: dict[int, dict[str, Any]] = {}
    for ordinal, row in enumerate(source_rows):
        if _is_final_overlay_row(row):
            line_index = _as_float(row.get("line"), float(ordinal))
            try:
                line_index_int = int(line_index)
            except (TypeError, ValueError):
                line_index_int = ordinal
            caption = NLECaptionState.from_editor_row(row, index=ordinal, fps=fps)
            projected = caption.to_editor_row(index=line_index_int, fps=fps)
            projected["_nle_timeline_source_ordinal"] = ordinal
            projected["_nle_runtime_surface"] = "timeline_canvas"
            projected["_nle_runtime_schema"] = NLE_RUNTIME_CUTOVER_SCHEMA
            final_rows.append(projected)
        else:
            passthrough = dict(row)
            passthrough["_nle_timeline_source_ordinal"] = ordinal
            passthrough["_nle_runtime_surface"] = (
                "timeline_canvas_gap" if bool(passthrough.get("is_gap")) else "timeline_canvas_preview"
            )
            passthrough["_nle_runtime_schema"] = NLE_RUNTIME_CUTOVER_SCHEMA
            passthrough_by_ordinal[ordinal] = passthrough

    final_rows.sort(
        key=lambda item: (
            _as_float(item.get("start", item.get("timeline_start", 0.0))),
            int(item.get("_nle_timeline_source_ordinal", 0) or 0),
        )
    )
    stable_final_rows = _final_surface_rows_without_overlap(
        final_rows,
        surface="timeline_canvas",
        primary_fps=fps,
        block_unfixable=False,
    )
    final_by_ordinal: dict[int, dict[str, Any]] = {}
    for row in stable_final_rows:
        try:
            ordinal = int(row.get("_nle_timeline_source_ordinal", -1))
        except (TypeError, ValueError):
            ordinal = -1
        final_by_ordinal[ordinal] = row
    projected_rows: list[dict[str, Any]] = []
    for ordinal, row in enumerate(source_rows):
        if _is_final_overlay_row(row):
            projected = final_by_ordinal.get(ordinal)
            if projected is not None:
                projected_rows.append(projected)
        else:
            projected_rows.append(passthrough_by_ordinal[ordinal])
    return projected_rows


def nle_save_export_segments_from_editor_rows(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    return _nle_final_surface_segments_from_editor_rows(
        rows,
        surface="save_export",
        primary_fps=primary_fps,
        window=False,
    )


__all__ = [
    "NLE_RUNTIME_CUTOVER_SCHEMA",
    "nle_final_overlay_segments_from_editor_rows",
    "nle_global_canvas_segments_from_editor_rows",
    "nle_timeline_canvas_segments_from_editor_rows",
    "nle_save_export_segments_from_editor_rows",
]
