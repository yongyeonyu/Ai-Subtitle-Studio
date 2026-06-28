from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from core.project.nle_operations import (
    NLEEditorOperation,
    build_nle_editor_operation,
    build_nle_undo_snapshot,
)
from core.project.nle_project_state import (
    assert_nle_editor_rows_consistent,
    project_segments_from_nle_state,
    record_nle_operation_journal_entry,
    sync_project_nle_state_from_editor_rows,
)
from core.project.nle_projection_parity import (
    ProjectionParityReport,
    build_project_nle_projection_parity_report,
)
from core.project.nle_snapshot import build_project_nle_snapshot
from core.project.project_context import (
    build_editor_state,
    project_clip_boundaries,
    project_cut_boundary_provisional_segments,
    project_media_files,
    project_segments_to_editor,
    trim_editor_rows_to_project_duration,
)
from core.project.project_format import project_primary_fps


@dataclass(frozen=True, slots=True)
class NLEDualWritePilotResult:
    operation_family: str
    operation: NLEEditorOperation
    before_projection: ProjectionParityReport
    after_projection: ProjectionParityReport
    projected_rows: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operation"] = self.operation.to_dict()
        payload["before_projection"] = self.before_projection.to_dict()
        payload["after_projection"] = self.after_projection.to_dict()
        payload["projected_rows"] = [dict(row) for row in self.projected_rows]
        return payload


def _editor_state_dict(project: dict[str, Any]) -> dict[str, Any]:
    editor_state = project.get("editor_state")
    return editor_state if isinstance(editor_state, dict) else {}


def _analysis_cut_boundaries(project: dict[str, Any]) -> list[dict[str, Any]]:
    editor_state = _editor_state_dict(project)
    analysis = editor_state.get("analysis") if isinstance(editor_state.get("analysis"), dict) else {}
    rows = analysis.get("cut_boundaries") if isinstance(analysis.get("cut_boundaries"), list) else None
    if rows is None:
        project_analysis = project.get("analysis") if isinstance(project.get("analysis"), dict) else {}
        rows = project_analysis.get("cut_boundaries") if isinstance(project_analysis.get("cut_boundaries"), list) else []
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _shadow_project_with_rows_and_provisional_markers(
    project: dict[str, Any],
    rows: list[dict[str, Any]],
    markers: list[dict[str, Any]],
) -> dict[str, Any]:
    shadow = _shadow_project_with_rows(project, rows)
    editor_state = _editor_state_dict(shadow)
    media_files = project_media_files(shadow)
    if not media_files:
        media_files = list(editor_state.get("media_files") or [])
    mode = str(editor_state.get("mode") or shadow.get("mode") or "single")
    shadow["editor_state"] = build_editor_state(
        mode=mode,
        media_files=media_files,
        segments=[dict(row) for row in rows],
        workspace=editor_state.get("workspace") if isinstance(editor_state.get("workspace"), dict) else shadow.get("workspace"),
        clip_boundaries=project_clip_boundaries(shadow),
        stt_preview_segments=_stt_preview_segments(shadow),
        cut_boundaries=_analysis_cut_boundaries(shadow),
        provisional_cut_boundaries=[dict(row) for row in markers if isinstance(row, dict)],
        primary_fps=project_primary_fps(shadow),
        preserve_segment_identity=True,
    )
    shadow["analysis"] = dict((shadow["editor_state"].get("analysis") or {}))
    return shadow


def _stt_preview_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    stt_state = _editor_state_dict(project).get("stt")
    if not isinstance(stt_state, dict):
        return []
    rows = stt_state.get("preview_segments")
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _candidate_lanes(project: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    lanes: list[dict[str, Any]] = []
    stt_state = _editor_state_dict(project).get("stt")
    tracks = stt_state.get("candidate_tracks") if isinstance(stt_state, dict) and isinstance(stt_state.get("candidate_tracks"), dict) else {}
    for source, track_rows in tracks.items():
        if not isinstance(track_rows, list):
            continue
        for row in track_rows:
            if isinstance(row, dict):
                lanes.append({"source": str(source), **deepcopy(row)})
    for row in rows:
        if not isinstance(row, dict):
            continue
        for candidate in list(row.get("stt_candidates") or []):
            if isinstance(candidate, dict):
                lanes.append({"linked_caption_id": str(row.get("id") or ""), **deepcopy(candidate)})
    return tuple(lanes)


def _shadow_project_with_rows(project: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    shadow = deepcopy(project)
    editor_state = _editor_state_dict(project)
    media_files = project_media_files(project)
    if not media_files:
        media_files = list(editor_state.get("media_files") or [])
    mode = str(editor_state.get("mode") or project.get("mode") or "single")
    shadow["editor_state"] = build_editor_state(
        mode=mode,
        media_files=media_files,
        segments=[dict(row) for row in rows],
        workspace=editor_state.get("workspace") if isinstance(editor_state.get("workspace"), dict) else project.get("workspace"),
        clip_boundaries=project_clip_boundaries(project),
        stt_preview_segments=_stt_preview_segments(project),
        cut_boundaries=_analysis_cut_boundaries(project),
        primary_fps=project_primary_fps(project),
        preserve_segment_identity=True,
    )
    return shadow


def _gap_identity(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or row.get("gap_id") or f"gap_{index + 1:04d}")


def _caption_identity(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or f"caption_{index + 1:04d}")


def _marker_identity(row: dict[str, Any], index: int) -> str:
    raw = row if isinstance(row, dict) else {}
    marker_id = str(raw.get("id") or raw.get("marker_id") or "").strip()
    if marker_id:
        return marker_id
    frame = raw.get("timeline_frame", raw.get("frame"))
    try:
        frame_num = int(frame)
    except (TypeError, ValueError):
        frame_num = -1
    if frame_num >= 0:
        return f"cut_marker_{frame_num:08d}"
    try:
        millis = int(round(float(raw.get("timeline_sec", raw.get("time", raw.get("start", 0.0))) or 0.0) * 1000.0))
    except (TypeError, ValueError):
        millis = index + 1
    return f"cut_marker_ms_{max(0, millis):010d}"


def _is_final_caption_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    return not bool(
        row.get("is_gap")
        or row.get("stt_pending")
        or row.get("_live_stt_preview")
        or row.get("_live_subtitle_preview")
    )


def _row_start(row: dict[str, Any]) -> float:
    try:
        return float(row.get("start", row.get("timeline_start", 0.0)) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _row_end(row: dict[str, Any], default: float = 0.0) -> float:
    try:
        return float(row.get("end", row.get("timeline_end", default)) or default)
    except (TypeError, ValueError):
        return float(default)


def _retime_row(row: dict[str, Any], start: float, end: float) -> dict[str, Any]:
    updated = dict(row)
    updated["start"] = float(start)
    updated["end"] = max(float(start), float(end))
    updated["timeline_start"] = updated["start"]
    updated["timeline_end"] = updated["end"]
    for key in ("start_frame", "end_frame", "timeline_start_frame", "timeline_end_frame", "frame_range"):
        updated.pop(key, None)
    return updated


def _caption_row_to_gap(row: dict[str, Any], *, caption_id: str, gap_id: str) -> dict[str, Any]:
    updated = dict(row)
    updated["id"] = gap_id
    updated["gap_id"] = gap_id
    updated["deleted_caption_id"] = caption_id
    updated["gap_source"] = "caption_delete"
    updated["text"] = ""
    updated["is_gap"] = True
    for key in (
        "stt_candidates",
        "stt_pending",
        "_live_stt_preview",
        "_live_subtitle_preview",
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
    ):
        updated.pop(key, None)
    return updated


def _gap_row_copy(row: dict[str, Any], *, gap_id: str, start: float, end: float) -> dict[str, Any]:
    updated = _retime_row(row, start, end)
    updated["id"] = gap_id
    updated["gap_id"] = gap_id
    updated["text"] = ""
    updated["is_gap"] = True
    updated["gap_source"] = str(updated.get("gap_source") or "gap_generate")
    return updated


def _caption_row_from_gap(
    row: dict[str, Any],
    *,
    caption_id: str,
    start: float,
    end: float,
    text: str,
) -> dict[str, Any]:
    updated = _retime_row(row, start, end)
    updated["id"] = caption_id
    updated["text"] = str(text or "새자막")
    updated["is_gap"] = False
    updated["speaker"] = str(updated.get("speaker") or updated.get("spk") or "00")
    for key in ("gap_id", "gap_source", "deleted_caption_id"):
        updated.pop(key, None)
    return updated


def _manual_caption_edit_row(row: dict[str, Any]) -> dict[str, Any]:
    updated = dict(row)
    for key in (
        "stt_candidates",
        "stt_pending",
        "_live_stt_preview",
        "_live_subtitle_preview",
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
        "quality",
        "quality_history",
        "quality_candidates",
        "quality_stale",
    ):
        updated.pop(key, None)
    updated["is_gap"] = False
    return updated


def _merged_caption_text(left: dict[str, Any], right: dict[str, Any], explicit_text: str = "") -> str:
    if str(explicit_text or "").strip():
        return " ".join(str(explicit_text or "").replace("\u2028", "\n").split())
    parts = [
        " ".join(str(row.get("text", "") or "").replace("\u2028", "\n").split())
        for row in (left, right)
    ]
    return " ".join(part for part in parts if part).strip()


def _split_caption_text(left_text: str, right_text: str) -> tuple[str, str]:
    left = " ".join(str(left_text or "").replace("\u2028", "\n").split()).strip()
    right = " ".join(str(right_text or "").replace("\u2028", "\n").split()).strip()
    if not left:
        raise ValueError("nle_caption_split_left_text_required")
    if not right:
        right = "새자막"
    return left, right


def _normalized_speaker_list(value: Any) -> list[str]:
    if value is None:
        return []
    source = value if isinstance(value, (list, tuple)) else [value]
    speakers: list[str] = []
    for item in source:
        speaker = str(item or "").strip()
        if speaker and speaker not in speakers:
            speakers.append(speaker)
    return speakers


def _find_row_by_identity(
    rows: list[dict[str, Any]],
    row_id: str,
    *,
    final_only: bool,
    missing_prefix: str = "nle_caption_move_target_missing",
) -> tuple[int, dict[str, Any]]:
    wanted = str(row_id or "").strip()
    if not wanted:
        raise ValueError(f"{missing_prefix.replace('_missing', '_required')}")
    for index, row in enumerate(rows):
        if final_only and not _is_final_caption_row(row):
            continue
        if _caption_identity(row, index) == wanted:
            return index, row
    raise ValueError(f"{missing_prefix}:{wanted}")


def _sorted_editor_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in sorted(
            rows,
            key=lambda item: (_row_start(item), bool(item.get("is_gap")), int(item.get("line", 0) or 0)),
        )
    ]


def _duration_bound_row_identity(row: dict[str, Any], index: int) -> str:
    kind = "gap" if bool(row.get("is_gap")) else "caption"
    explicit = str(row.get("id") or row.get("gap_id") or "").strip()
    return f"{kind}:{explicit or index}"


def _duration_bound_end_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start = round(_row_start(row), 6)
    end = round(_row_end(row, _row_start(row)), 6)
    return (
        start,
        end,
        row.get("end_frame"),
        row.get("timeline_end_frame"),
        frame_range.get("end"),
    )


def _duration_bound_trim_stats(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    before_by_id = {
        _duration_bound_row_identity(row, index): dict(row)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict)
    }
    after_by_id = {
        _duration_bound_row_identity(row, index): dict(row)
        for index, row in enumerate(after_rows)
        if isinstance(row, dict)
    }
    dropped_count = sum(1 for row_id in before_by_id if row_id not in after_by_id)
    trimmed_count = sum(
        1
        for row_id, before in before_by_id.items()
        if row_id in after_by_id
        and _duration_bound_end_signature(before) != _duration_bound_end_signature(after_by_id[row_id])
    )
    return {
        "changed": bool(dropped_count or trimmed_count),
        "input_count": len(before_by_id),
        "output_count": len(after_by_id),
        "trimmed_row_count": trimmed_count,
        "dropped_row_count": dropped_count,
    }


def _enforce_dual_write_project_duration_bound(
    project: dict[str, Any],
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    before_rows = _sorted_editor_rows([dict(row) for row in list(rows or []) if isinstance(row, dict)])
    after_rows = trim_editor_rows_to_project_duration(
        before_rows,
        project,
        primary_fps=project_primary_fps(project),
    )
    after_rows = _sorted_editor_rows(after_rows)
    return after_rows, _duration_bound_trim_stats(before_rows, after_rows)


def _duration_bound_operation_metadata(stats: dict[str, Any]) -> dict[str, Any]:
    if not bool(stats.get("changed")):
        return {}
    return {
        "duration_bound_trim_applied": True,
        "duration_bound_input_count": int(stats.get("input_count", 0) or 0),
        "duration_bound_output_count": int(stats.get("output_count", 0) or 0),
        "duration_bound_trimmed_row_count": int(stats.get("trimmed_row_count", 0) or 0),
        "duration_bound_dropped_row_count": int(stats.get("dropped_row_count", 0) or 0),
    }


def _duration_bound_state_metadata(stats: dict[str, Any]) -> dict[str, Any]:
    if not bool(stats.get("changed")):
        return {}
    return {
        "dual_write_duration_bound_trim_applied": True,
        "dual_write_duration_bound_input_count": int(stats.get("input_count", 0) or 0),
        "dual_write_duration_bound_output_count": int(stats.get("output_count", 0) or 0),
        "dual_write_duration_bound_trimmed_row_count": int(stats.get("trimmed_row_count", 0) or 0),
        "dual_write_duration_bound_dropped_row_count": int(stats.get("dropped_row_count", 0) or 0),
    }


def _interval_overlap(left_start: float, left_end: float, right_start: float, right_end: float) -> bool:
    return min(left_end, right_end) > max(left_start, right_start)


def _resolve_rows_around_updated_final_ranges(
    rows: list[dict[str, Any]],
    updated_indices: set[int],
) -> tuple[list[dict[str, Any]], int, int]:
    updated_ranges = [
        (_row_start(rows[index]), _row_end(rows[index], _row_start(rows[index])))
        for index in sorted(updated_indices)
        if 0 <= index < len(rows)
    ]
    resolved: list[dict[str, Any]] = []
    trimmed_count = 0
    deleted_count = 0
    for index, row in enumerate(rows):
        current = dict(row)
        if index in updated_indices:
            resolved.append(current)
            continue
        row_start = _row_start(current)
        row_end = _row_end(current, row_start)
        keep = True
        for updated_start, updated_end in updated_ranges:
            if not _interval_overlap(row_start, row_end, updated_start, updated_end):
                continue
            if updated_start <= row_start and updated_end >= row_end:
                keep = False
                deleted_count += 1
                break
            if row_start < updated_start and row_end <= updated_end:
                row_end = updated_start
                current = _retime_row(current, row_start, row_end)
                trimmed_count += 1
                continue
            if updated_start <= row_start and updated_end < row_end:
                row_start = updated_end
                current = _retime_row(current, row_start, row_end)
                trimmed_count += 1
                continue
            raise ValueError("nle_caption_resize_split_required")
        if keep and _row_end(current, _row_start(current)) > _row_start(current):
            resolved.append(current)
        elif keep:
            deleted_count += 1
    return resolved, trimmed_count, deleted_count


def apply_gap_generate_dual_write_pilot(
    project: dict[str, Any],
    *,
    gap_id: str = "",
    gap_start: float | None = None,
    gap_end: float | None = None,
    sub_start: float,
    sub_end: float,
    mode: str = "",
    text: str = "새자막",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    gap_rows = [
        (index, row)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and bool(row.get("is_gap"))
    ]
    if not gap_rows:
        raise ValueError("nle_gap_generate_target_missing")
    target_index = -1
    target_gap: dict[str, Any] | None = None
    wanted_id = str(gap_id or "").strip()
    if wanted_id:
        for index, row in gap_rows:
            if _gap_identity(row, index) == wanted_id:
                target_index, target_gap = index, row
                break
        if target_gap is None:
            raise ValueError(f"nle_gap_generate_target_missing:{wanted_id}")
    else:
        try:
            wanted_start = float(gap_start if gap_start is not None else 0.0)
            wanted_end = float(gap_end if gap_end is not None else wanted_start)
        except (TypeError, ValueError) as exc:
            raise ValueError("nle_gap_generate_gap_time_invalid") from exc
        tolerance = max(0.05, 1.5 / max(1.0, project_primary_fps(project)))
        for index, row in gap_rows:
            row_start = _row_start(row)
            row_end = _row_end(row, row_start)
            if abs(row_start - wanted_start) <= tolerance and abs(row_end - wanted_end) <= tolerance:
                target_index, target_gap = index, row
                break
        if target_gap is None:
            raise ValueError("nle_gap_generate_target_missing")

    assert target_gap is not None
    target_id = _gap_identity(target_gap, target_index)
    target_start = _row_start(target_gap)
    target_end = _row_end(target_gap, target_start)
    try:
        caption_start = float(sub_start)
        caption_end = float(sub_end)
    except (TypeError, ValueError) as exc:
        raise ValueError("nle_gap_generate_caption_time_invalid") from exc
    if caption_end <= caption_start:
        raise ValueError("nle_gap_generate_caption_duration_invalid")
    if caption_start < target_start - 0.001 or caption_end > target_end + 0.001:
        raise ValueError("nle_gap_generate_caption_outside_gap")
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()

    generated_rows: list[dict[str, Any]] = []
    if caption_start > target_start + 0.001:
        generated_rows.append(_gap_row_copy(
            target_gap,
            gap_id=f"{target_id}_left",
            start=target_start,
            end=caption_start,
        ))
    caption_id = f"caption_from_{target_id}"
    generated_rows.append(_caption_row_from_gap(
        target_gap,
        caption_id=caption_id,
        start=caption_start,
        end=caption_end,
        text=text,
    ))
    if caption_end < target_end - 0.001:
        generated_rows.append(_gap_row_copy(
            target_gap,
            gap_id=f"{target_id}_right",
            start=caption_end,
            end=target_end,
        ))

    after_rows = [dict(row) for row in before_rows[:target_index]]
    after_rows.extend(generated_rows)
    after_rows.extend(dict(row) for row in before_rows[target_index + 1:])
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    if int(after_projection.invalid_duration_count or 0) != 0:
        raise ValueError("nle_gap_generate_final_invalid_duration")
    if int(after_projection.non_monotonic_count or 0) != 0:
        raise ValueError("nle_gap_generate_final_non_monotonic")
    if int(after_projection.overlap_count or 0) != 0:
        raise ValueError("nle_gap_generate_final_overlap")
    if int(after_projection.max_active_segments or 0) > 1:
        raise ValueError("nle_gap_generate_final_max_active_segments")

    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_gap_generate:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for _index, row in gap_rows],
        ui_state_ref={
            "operation_family": "gap_generate",
            "target_id": target_id,
            "caption_id": caption_id,
            "sub_start": caption_start,
            "sub_end": caption_end,
            "mode": str(mode or ""),
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_gap_generate"},
    )
    metadata = {
        "pilot": "dual_write",
        "operation_family": "gap_generate",
        "gap_id": target_id,
        "generated_caption_id": caption_id,
        "mode": str(mode or ""),
        "left_gap_preserved": caption_start > target_start + 0.001,
        "right_gap_preserved": caption_end < target_end - 0.001,
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="gap_generate",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "gap_generate",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_generated_caption_id": caption_id,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="gap_generate",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_merge_dual_write_pilot(
    project: dict[str, Any],
    *,
    left_caption_id: str,
    right_caption_id: str,
    merged_text: str = "",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    left_index, left_row = _find_row_by_identity(
        before_rows,
        left_caption_id,
        final_only=True,
        missing_prefix="nle_caption_merge_left_target_missing",
    )
    right_index, right_row = _find_row_by_identity(
        before_rows,
        right_caption_id,
        final_only=True,
        missing_prefix="nle_caption_merge_right_target_missing",
    )
    if left_index == right_index:
        raise ValueError("nle_caption_merge_distinct_targets_required")
    left_id = _caption_identity(left_row, left_index)
    right_id = _caption_identity(right_row, right_index)
    ordered = sorted(
        ((left_index, dict(left_row)), (right_index, dict(right_row))),
        key=lambda item: (_row_start(item[1]), item[0]),
    )
    keep_index, keep_row = ordered[0]
    remove_index, remove_row = ordered[1]
    keep_id = _caption_identity(keep_row, keep_index)
    remove_id = _caption_identity(remove_row, remove_index)
    merged_start = min(_row_start(keep_row), _row_start(remove_row))
    merged_end = max(
        _row_end(keep_row, _row_start(keep_row)),
        _row_end(remove_row, _row_start(remove_row)),
    )
    if merged_end <= merged_start:
        raise ValueError("nle_caption_merge_duration_invalid")
    text = _merged_caption_text(keep_row, remove_row, merged_text)
    if not text:
        raise ValueError("nle_caption_merge_text_required")
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()

    merged_row = _retime_row(keep_row, merged_start, merged_end)
    merged_row["id"] = keep_id
    merged_row["text"] = text
    merged_row["is_gap"] = False
    merged_row["merged_caption_ids"] = [keep_id, remove_id]
    after_rows = []
    for index, row in enumerate(before_rows):
        if index == keep_index:
            after_rows.append(dict(merged_row))
        elif index == remove_index:
            continue
        else:
            after_rows.append(dict(row))
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_merge:{keep_id}:{remove_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_merge",
            "left_caption_id": left_id,
            "right_caption_id": right_id,
            "kept_caption_id": keep_id,
            "removed_caption_id": remove_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_merge"},
    )
    metadata = {
        "pilot": "dual_write",
        "operation_family": "caption_merge",
        "kept_caption_id": keep_id,
        "removed_caption_id": remove_id,
        "merged_text": text,
        "merged_start": merged_start,
        "merged_end": merged_end,
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_merge",
        target_ids=[left_id, right_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_merge",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_kept_caption_id": keep_id,
        "dual_write_removed_caption_id": remove_id,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_merge",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_split_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    split_sec: float,
    left_text: str,
    right_text: str,
    new_caption_id: str = "",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    target_index, target_row = _find_row_by_identity(
        before_rows,
        caption_id,
        final_only=True,
        missing_prefix="nle_caption_split_target_missing",
    )
    target_id = _caption_identity(target_row, target_index)
    try:
        split_at = float(split_sec)
    except (TypeError, ValueError) as exc:
        raise ValueError("nle_caption_split_time_invalid") from exc
    target_start = _row_start(target_row)
    target_end = _row_end(target_row, target_start)
    if split_at <= target_start or split_at >= target_end:
        raise ValueError("nle_caption_split_time_outside_target")
    left, right = _split_caption_text(left_text, right_text)

    left_row = _manual_caption_edit_row(_retime_row(target_row, target_start, split_at))
    left_row["id"] = target_id
    left_row["text"] = left
    left_row["split_child_caption_id"] = str(new_caption_id or f"{target_id}_split_right")

    right_id = str(new_caption_id or f"{target_id}_split_right")
    right_row = _manual_caption_edit_row(_retime_row(target_row, split_at, target_end))
    right_row["id"] = right_id
    right_row["text"] = right
    right_row["split_parent_caption_id"] = target_id

    if _row_end(left_row, target_start) <= _row_start(left_row):
        raise ValueError("nle_caption_split_left_duration_invalid")
    if _row_end(right_row, split_at) <= _row_start(right_row):
        raise ValueError("nle_caption_split_right_duration_invalid")

    after_rows = []
    for index, row in enumerate(before_rows):
        if index == target_index:
            after_rows.append(dict(left_row))
            after_rows.append(dict(right_row))
        else:
            after_rows.append(dict(row))
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)
    if not after_rows:
        raise ValueError("nle_caption_split_duration_bound_rows_empty")

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_split:{target_id}:{right_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_split",
            "target_id": target_id,
            "new_caption_id": right_id,
            "split_sec": split_at,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_split"},
    )
    metadata = {
        "pilot": "dual_write",
        "operation_family": "caption_split",
        "caption_id": target_id,
        "new_caption_id": right_id,
        "split_sec": split_at,
        "left_text": left,
        "right_text": right,
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_split",
        target_ids=[target_id, right_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_split",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_split_caption_id": target_id,
        "dual_write_new_caption_id": right_id,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_split",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def _candidate_confirm_id(candidate: dict[str, Any], source: str) -> str:
    try:
        start = _row_start(candidate)
        end = _row_end(candidate, start)
    except Exception:
        start, end = 0.0, 0.0
    return f"candidate_confirm:{str(source or '').strip().upper()}:{start:.3f}:{end:.3f}"


def _canonicalize_confirmed_caption_identities(
    before_rows: list[dict[str, Any]],
    confirmed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    before_candidates = [
        (index, dict(row))
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and _is_final_caption_row(row)
    ]
    used_before: set[int] = set()
    out: list[dict[str, Any]] = []
    for row in confirmed_rows:
        item = dict(row)
        if not _is_final_caption_row(item):
            out.append(item)
            continue
        current_id = str(item.get("id", "") or "").strip()
        if current_id.startswith("subtitle_vector_"):
            out.append(item)
            continue
        row_start = _row_start(item)
        row_end = _row_end(item, row_start)
        best_index = -1
        best_overlap = 0.0
        for before_index, before in before_candidates:
            if before_index in used_before:
                continue
            before_start = _row_start(before)
            before_end = _row_end(before, before_start)
            overlap = max(0.0, min(row_end, before_end) - max(row_start, before_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_index = before_index
        if best_index >= 0 and best_overlap > 0.0:
            before = next(before for index, before in before_candidates if index == best_index)
            item["id"] = _caption_identity(before, best_index)
            used_before.add(best_index)
        elif current_id.startswith("caption_") and current_id[8:].isdigit():
            item.pop("id", None)
        out.append(item)
    return out


def _overlapping_caption_ids_for_candidate(
    rows: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> list[str]:
    cand_start = _row_start(candidate)
    cand_end = _row_end(candidate, cand_start)
    ids: list[str] = []
    if cand_end <= cand_start:
        return ids
    for index, row in enumerate(rows):
        if not _is_final_caption_row(row):
            continue
        row_start = _row_start(row)
        row_end = _row_end(row, row_start)
        if _interval_overlap(row_start, row_end, cand_start, cand_end):
            ids.append(_caption_identity(row, index))
    return ids


def apply_candidate_confirm_dual_write_pilot(
    project: dict[str, Any],
    *,
    confirmed_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    candidate: dict[str, Any],
    candidate_source: str,
    candidate_lanes: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    source = str(candidate_source or "").strip().upper()
    if not source:
        raise ValueError("nle_candidate_confirm_source_required")
    if not isinstance(candidate, dict):
        raise TypeError("candidate_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    after_rows = _sorted_editor_rows([dict(row) for row in list(confirmed_rows or []) if isinstance(row, dict)])
    after_rows = _canonicalize_confirmed_caption_identities(before_rows, after_rows)
    if not after_rows:
        raise ValueError("nle_candidate_confirm_rows_required")
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)
    if not after_rows:
        raise ValueError("nle_candidate_confirm_duration_bound_rows_empty")
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()

    candidate_id = _candidate_confirm_id(candidate, source)
    target_ids = _overlapping_caption_ids_for_candidate(before_rows, candidate)
    if not target_ids:
        target_ids = [candidate_id]

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_candidate_confirm:{candidate_id}",
        editor_rows=before_rows,
        candidate_lanes=[
            *_candidate_lanes(project, before_rows),
            *[dict(row) for row in list(candidate_lanes or []) if isinstance(row, dict)],
            {**deepcopy(candidate), "candidate_id": candidate_id, "source": source},
        ],
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "candidate_confirm",
            "candidate_id": candidate_id,
            "candidate_source": source,
            "target_ids": list(target_ids),
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_candidate_confirm"},
    )
    metadata = {
        "pilot": "dual_write",
        "operation_family": "candidate_confirm",
        "candidate_id": candidate_id,
        "candidate_source": source,
        "candidate_text": str(candidate.get("text", "") or ""),
        "candidate_start": _row_start(candidate),
        "candidate_end": _row_end(candidate, _row_start(candidate)),
        "confirmed_row_count": len(after_rows),
        "replaced_target_ids": list(target_ids),
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="candidate_confirm",
        target_ids=target_ids,
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "candidate_confirm",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_candidate_id": candidate_id,
        "dual_write_candidate_source": source,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="candidate_confirm",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_delete_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    replacement_gap_id: str = "",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    target_index, target_row = _find_row_by_identity(
        before_rows,
        caption_id,
        final_only=True,
        missing_prefix="nle_caption_delete_target_missing",
    )
    target_id = _caption_identity(target_row, target_index)
    gap_id = str(replacement_gap_id or f"gap_from_{target_id}")
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    after_rows = [dict(row) for row in before_rows]
    after_rows[target_index] = _caption_row_to_gap(after_rows[target_index], caption_id=target_id, gap_id=gap_id)
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_delete:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_delete",
            "target_id": target_id,
            "replacement_gap_id": gap_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_delete"},
    )
    metadata = {
        "pilot": "dual_write",
        "operation_family": "caption_delete",
        "caption_id": target_id,
        "replacement_gap_id": gap_id,
        "delete_mode": "replace_with_silence_gap",
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_delete",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_delete",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_replacement_gap_id": gap_id,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_delete",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_resize_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    new_start: float,
    new_end: float,
    edge: str = "",
    linked_caption_id: str = "",
    linked_new_start: float | None = None,
    linked_new_end: float | None = None,
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    moving_index, moving_row = _find_row_by_identity(
        before_rows,
        caption_id,
        final_only=True,
        missing_prefix="nle_caption_resize_target_missing",
    )
    target_id = _caption_identity(moving_row, moving_index)
    try:
        target_start = float(new_start)
        target_end = float(new_end)
    except (TypeError, ValueError) as exc:
        raise ValueError("nle_caption_resize_time_invalid") from exc
    if target_end <= target_start:
        raise ValueError("nle_caption_resize_duration_invalid")
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()

    after_rows = [dict(row) for row in before_rows]
    after_rows[moving_index] = _retime_row(after_rows[moving_index], target_start, target_end)
    updated_indices = {moving_index}
    target_ids = [target_id]
    linked_id = ""
    if linked_caption_id:
        linked_index, linked_row = _find_row_by_identity(
            after_rows,
            linked_caption_id,
            final_only=True,
            missing_prefix="nle_caption_resize_linked_target_missing",
        )
        if linked_new_start is None or linked_new_end is None:
            raise ValueError("nle_caption_resize_linked_time_required")
        try:
            linked_start = float(linked_new_start)
            linked_end = float(linked_new_end)
        except (TypeError, ValueError) as exc:
            raise ValueError("nle_caption_resize_linked_time_invalid") from exc
        if linked_end <= linked_start:
            raise ValueError("nle_caption_resize_linked_duration_invalid")
        after_rows[linked_index] = _retime_row(after_rows[linked_index], linked_start, linked_end)
        updated_indices.add(linked_index)
        linked_id = _caption_identity(linked_row, linked_index)
        target_ids.append(linked_id)

    after_rows, trimmed_count, deleted_count = _resolve_rows_around_updated_final_ranges(after_rows, updated_indices)
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "caption_resize",
        "caption_id": target_id,
        "edge": str(edge or "boundary"),
        "trimmed_neighbor_count": trimmed_count,
        "deleted_neighbor_count": deleted_count,
        "linked_caption_id": linked_id,
    }
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_resize:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_resize",
            "target_id": target_id,
            "new_start": target_start,
            "new_end": target_end,
            "edge": str(edge or "boundary"),
            "linked_caption_id": linked_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_resize"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_resize",
        target_ids=target_ids,
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_resize",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_trimmed_neighbor_count": trimmed_count,
        "dual_write_deleted_neighbor_count": deleted_count,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_resize",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_move_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    new_start: float,
    new_end: float,
    reorder_neighbor_id: str = "",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    moving_index, moving_row = _find_row_by_identity(before_rows, caption_id, final_only=True)
    target_id = _caption_identity(moving_row, moving_index)
    try:
        target_start = float(new_start)
        target_end = float(new_end)
    except (TypeError, ValueError) as exc:
        raise ValueError("nle_caption_move_time_invalid") from exc
    if target_end <= target_start:
        raise ValueError("nle_caption_move_duration_invalid")

    after_rows = [dict(row) for row in before_rows]
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "caption_move",
        "caption_id": target_id,
    }
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    old_start = _row_start(moving_row)
    old_end = _row_end(moving_row, old_start)
    if reorder_neighbor_id:
        neighbor_index, neighbor_row = _find_row_by_identity(after_rows, reorder_neighbor_id, final_only=True)
        direction = "right" if neighbor_index > moving_index else "left"
        neighbor_start = _row_start(neighbor_row)
        neighbor_end = _row_end(neighbor_row, neighbor_start)
        neighbor_duration = max(0.0, neighbor_end - neighbor_start)
        after_rows[moving_index] = _retime_row(after_rows[moving_index], target_start, target_end)
        if direction == "right":
            after_rows[neighbor_index] = _retime_row(after_rows[neighbor_index], old_start, old_start + neighbor_duration)
        else:
            after_rows[neighbor_index] = _retime_row(after_rows[neighbor_index], target_end, target_end + neighbor_duration)
        metadata.update({
            "taption_reorder": True,
            "reorder_direction": direction,
            "reorder_neighbor_id": _caption_identity(neighbor_row, neighbor_index),
        })
    else:
        after_rows[moving_index] = _retime_row(after_rows[moving_index], target_start, target_end)
        metadata["taption_reorder"] = False
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_move:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_move",
            "target_id": target_id,
            "new_start": target_start,
            "new_end": target_end,
            "reorder_neighbor_id": str(reorder_neighbor_id or ""),
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_move"},
    )
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_move",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_move",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_taption_reorder": bool(reorder_neighbor_id),
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_move",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def _committed_target_row_index(
    rows: list[dict[str, Any]],
    *,
    target_id: str,
    committed_caption_line: int | None,
    moving_row: dict[str, Any],
) -> int:
    for index, row in enumerate(rows):
        if _is_final_caption_row(row) and _caption_identity(row, index) == target_id:
            return index
    if committed_caption_line is not None:
        for index, row in enumerate(rows):
            if not _is_final_caption_row(row):
                continue
            try:
                if int(row.get("line", -1)) == int(committed_caption_line):
                    return index
            except Exception:
                continue
    best_index = -1
    best_overlap = 0.0
    moving_start = _row_start(moving_row)
    moving_end = _row_end(moving_row, moving_start)
    for index, row in enumerate(rows):
        if not _is_final_caption_row(row):
            continue
        row_start = _row_start(row)
        row_end = _row_end(row, row_start)
        overlap = max(0.0, min(row_end, moving_end) - max(row_start, moving_start))
        if overlap > best_overlap:
            best_index = index
            best_overlap = overlap
    return best_index


def _editor_row_identity(row: dict[str, Any], index: int) -> str:
    return _gap_identity(row, index) if bool(row.get("is_gap")) else _caption_identity(row, index)


def _changed_row_count(before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> int:
    after_by_id = {
        _editor_row_identity(row, index): row
        for index, row in enumerate(after_rows)
        if isinstance(row, dict)
    }
    changed = 0
    for index, row in enumerate(before_rows):
        if not isinstance(row, dict):
            continue
        row_id = _editor_row_identity(row, index)
        after = after_by_id.get(row_id)
        if after is None:
            continue
        if (
            _row_start(row) != _row_start(after)
            or _row_end(row, _row_start(row)) != _row_end(after, _row_start(after))
            or bool(row.get("is_gap")) != bool(after.get("is_gap"))
        ):
            changed += 1
    return changed


def _row_in_start_range(row: dict[str, Any], range_start: float, range_end: float, *, tolerance: float) -> bool:
    start = _row_start(row)
    return start >= range_start - tolerance and start < range_end - 1e-9


def _row_preservation_signature(row: dict[str, Any]) -> tuple[float, float, bool, str]:
    start = round(_row_start(row), 6)
    end = round(_row_end(row, _row_start(row)), 6)
    is_gap = bool(row.get("is_gap"))
    text = "" if is_gap else str(row.get("text", "") or "")
    return start, end, is_gap, text


def _assert_rows_preserve_before_outside_range(
    before_rows: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
    *,
    range_start: float,
    range_end: float,
    tolerance: float,
) -> None:
    remaining: dict[tuple[float, float, bool, str], int] = {}
    for row in after_rows:
        signature = _row_preservation_signature(row)
        remaining[signature] = remaining.get(signature, 0) + 1
    for row in before_rows:
        if _row_in_start_range(row, range_start, range_end, tolerance=tolerance):
            continue
        signature = _row_preservation_signature(row)
        count = remaining.get(signature, 0)
        if count <= 0:
            raise ValueError("nle_caption_range_replace_outside_drift")
        remaining[signature] = count - 1


def _ensure_unique_range_replace_row_identities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, row in enumerate(rows):
        item = dict(row)
        row_id = _editor_row_identity(item, index)
        explicit_id = str(item.get("id") or item.get("gap_id") or "").strip()
        if not explicit_id or row_id in used:
            prefix = "gap_range_replace" if bool(item.get("is_gap")) else "caption_range_replace"
            next_id = f"{prefix}_{index + 1:04d}"
            counter = index + 1
            while next_id in used:
                counter += 1
                next_id = f"{prefix}_{counter:04d}"
            item["id"] = next_id
            if bool(item.get("is_gap")):
                item["gap_id"] = next_id
            row_id = next_id
        used.add(row_id)
        out.append(item)
    return out


def apply_caption_range_replace_dual_write_pilot(
    project: dict[str, Any],
    *,
    target_start: float,
    target_end: float,
    committed_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    try:
        range_start = float(target_start)
        range_end = float(target_end)
    except (TypeError, ValueError) as exc:
        raise ValueError("nle_caption_range_replace_target_time_invalid") from exc
    if range_end <= range_start:
        raise ValueError("nle_caption_range_replace_target_duration_invalid")
    tolerance = max(0.05, 1.5 / max(1.0, project_primary_fps(project)))
    target_ids = [
        _editor_row_identity(row, index)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and _row_in_start_range(row, range_start, range_end, tolerance=tolerance)
    ]
    if not target_ids:
        raise ValueError("nle_caption_range_replace_target_missing")

    after_rows = _sorted_editor_rows([dict(row) for row in list(committed_rows or []) if isinstance(row, dict)])
    if not after_rows:
        raise ValueError("nle_caption_range_replace_rows_required")
    for row in after_rows:
        if bool(row.get("stt_pending") or row.get("_live_stt_preview") or row.get("_live_subtitle_preview")):
            raise ValueError("nle_caption_range_replace_preview_rows_unsupported")
    _assert_rows_preserve_before_outside_range(
        before_rows,
        after_rows,
        range_start=range_start,
        range_end=range_end,
        tolerance=tolerance,
    )
    after_rows = _canonicalize_confirmed_caption_identities(before_rows, after_rows)
    after_rows = _sorted_editor_rows(after_rows)
    after_rows = _ensure_unique_range_replace_row_identities(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)
    if not after_rows:
        raise ValueError("nle_caption_range_replace_duration_bound_rows_empty")

    after_ids = {
        _editor_row_identity(row, index)
        for index, row in enumerate(after_rows)
        if isinstance(row, dict)
    }
    deleted_ids = [
        _editor_row_identity(row, index)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and _editor_row_identity(row, index) not in after_ids
    ]
    changed_count = _changed_row_count(before_rows, after_rows)
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_range_replace:{range_start:.3f}:{range_end:.3f}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_range_replace",
            "target_start": range_start,
            "target_end": range_end,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
            "target_ids": list(target_ids),
        },
        metadata={"pilot": "dual_write_caption_range_replace"},
    )
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "caption_range_replace",
        "target_start": range_start,
        "target_end": range_end,
        "commit_boundary": commit_boundary,
        "commit_source": commit_source,
        "replaced_target_ids": list(target_ids),
        "replaced_row_count": len(target_ids),
        "committed_row_count": len(after_rows),
        "deleted_row_count": len(deleted_ids),
        "changed_row_count": changed_count,
    }
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_range_replace",
        target_ids=target_ids,
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_range_replace",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_range_replace_target_start": range_start,
        "dual_write_range_replace_target_end": range_end,
        "dual_write_range_replace_target_count": len(target_ids),
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_range_replace",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_move_commit_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    committed_rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    committed_caption_line: int | None = None,
    commit_boundary: str = "",
    commit_source: str = "",
    commit_mode: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    moving_index, moving_row = _find_row_by_identity(
        before_rows,
        caption_id,
        final_only=True,
        missing_prefix="nle_caption_move_commit_target_missing",
    )
    target_id = _caption_identity(moving_row, moving_index)
    after_rows = _sorted_editor_rows([dict(row) for row in list(committed_rows or []) if isinstance(row, dict)])
    if not after_rows:
        raise ValueError("nle_caption_move_commit_rows_required")

    target_after_index = _committed_target_row_index(
        after_rows,
        target_id=target_id,
        committed_caption_line=committed_caption_line,
        moving_row=moving_row,
    )
    if target_after_index < 0:
        raise ValueError(f"nle_caption_move_commit_target_missing:{target_id}")
    for index, row in enumerate(after_rows):
        if index != target_after_index and _is_final_caption_row(row) and _caption_identity(row, index) == target_id:
            row.pop("id", None)
    after_rows[target_after_index]["id"] = target_id
    after_rows = _canonicalize_confirmed_caption_identities(before_rows, after_rows)
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    after_ids = {
        _editor_row_identity(row, index)
        for index, row in enumerate(after_rows)
        if isinstance(row, dict)
    }
    deleted_ids = [
        _editor_row_identity(row, index)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and _editor_row_identity(row, index) not in after_ids
    ]
    silence_gap_deleted_count = sum(
        1
        for index, row in enumerate(before_rows)
        if isinstance(row, dict)
        and bool(row.get("is_gap"))
        and _editor_row_identity(row, index) not in after_ids
    )
    changed_count = _changed_row_count(before_rows, after_rows)
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    commit_mode = str(commit_mode or "center_commit_plan").strip()

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_move_commit:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_move",
            "target_id": target_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
            "commit_mode": commit_mode,
        },
        metadata={"pilot": "dual_write_caption_move_commit"},
    )
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "caption_move",
        "caption_id": target_id,
        "commit_boundary": commit_boundary,
        "commit_source": commit_source,
        "commit_mode": commit_mode,
        "taption_reorder": False,
        "committed_row_count": len(after_rows),
        "deleted_row_count": len(deleted_ids),
        "changed_row_count": changed_count,
        "silence_gap_deleted_count": silence_gap_deleted_count,
    }
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_move",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_move",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_taption_reorder": False,
        "dual_write_caption_move_commit_mode": commit_mode,
        "dual_write_deleted_row_count": len(deleted_ids),
        "dual_write_silence_gap_deleted_count": silence_gap_deleted_count,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_move",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_caption_text_edit_dual_write_pilot(
    project: dict[str, Any],
    *,
    caption_id: str,
    new_text: str,
    new_speaker: str | None = None,
    new_speaker_list: list[str] | tuple[str, ...] | None = None,
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    target_index, target_row = _find_row_by_identity(
        before_rows,
        caption_id,
        final_only=True,
        missing_prefix="nle_caption_text_edit_target_missing",
    )
    target_id = _caption_identity(target_row, target_index)
    text = str(new_text or "").replace("\u2028", "\n")
    old_text = str(target_row.get("text", "") or "")
    old_speaker = str(target_row.get("speaker", target_row.get("spk", "00")) or "00").strip()
    old_speaker_list = _normalized_speaker_list(target_row.get("speaker_list")) or ([old_speaker] if old_speaker else [])
    speaker_requested = new_speaker is not None
    speaker_list_requested = new_speaker_list is not None
    speaker = str(new_speaker or "").strip() if speaker_requested else old_speaker
    speaker_list = _normalized_speaker_list(new_speaker_list) if speaker_list_requested else []
    if speaker_list_requested and not speaker and speaker_list:
        speaker = speaker_list[0]
    if speaker_list_requested and not speaker_list and speaker:
        speaker_list = [speaker]
    if not speaker:
        speaker = old_speaker or "00"
    if (
        old_text == text
        and (not speaker_requested or old_speaker == speaker)
        and (not speaker_list_requested or old_speaker_list == speaker_list)
    ):
        raise ValueError("nle_caption_text_edit_unchanged")

    after_rows = [dict(row) for row in before_rows]
    after_rows[target_index]["text"] = text
    if speaker_requested or speaker_list_requested:
        after_rows[target_index]["speaker"] = speaker
    if speaker_list_requested:
        after_rows[target_index]["speaker_list"] = speaker_list
    after_rows = _sorted_editor_rows(after_rows)
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_caption_text_edit:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "caption_text_edit",
            "target_id": target_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_caption_text_edit"},
    )
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "caption_text_edit",
        "caption_id": target_id,
        "old_text": old_text,
        "new_text": text,
    }
    if speaker_requested or speaker_list_requested:
        metadata["old_speaker"] = old_speaker
        metadata["new_speaker"] = speaker
    if speaker_list_requested:
        metadata["old_speaker_list"] = list(old_speaker_list)
        metadata["new_speaker_list"] = list(speaker_list)
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_text_edit",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_text_edit",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_caption_text_edit_target": target_id,
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="caption_text_edit",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_gap_delete_dual_write_pilot(
    project: dict[str, Any],
    *,
    gap_id: str = "",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    gap_rows = [
        (index, row)
        for index, row in enumerate(before_rows)
        if isinstance(row, dict) and bool(row.get("is_gap"))
    ]
    if not gap_rows:
        raise ValueError("nle_gap_delete_target_missing")
    target_index, target_gap = gap_rows[0]
    if gap_id:
        for index, row in gap_rows:
            if _gap_identity(row, index) == str(gap_id):
                target_index, target_gap = index, row
                break
        else:
            raise ValueError(f"nle_gap_delete_target_missing:{gap_id}")
    target_id = _gap_identity(target_gap, target_index)
    commit_boundary = str(commit_boundary or "").strip()
    commit_source = str(commit_source or "").strip()
    after_rows = [
        dict(row)
        for index, row in enumerate(before_rows)
        if index != target_index
    ]
    after_rows, duration_bound_stats = _enforce_dual_write_project_duration_bound(project, after_rows)

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_gap_delete:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for _index, row in gap_rows],
        ui_state_ref={
            "operation_family": "gap_delete",
            "target_id": target_id,
            "commit_boundary": commit_boundary,
            "commit_source": commit_source,
        },
        metadata={"pilot": "dual_write_gap_delete"},
    )
    metadata = {"pilot": "dual_write", "operation_family": "gap_delete"}
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
    metadata.update(_duration_bound_operation_metadata(duration_bound_stats))
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="gap_delete",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "gap_delete",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        **_duration_bound_state_metadata(duration_bound_stats),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(after_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(after_rows, projected_rows, primary_fps=project_primary_fps(project))
    project["editor_state"] = shadow_after["editor_state"]
    return NLEDualWritePilotResult(
        operation_family="gap_delete",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def apply_marker_edit_dual_write_pilot(
    project: dict[str, Any],
    *,
    action: str,
    marker: dict[str, Any],
    before_markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    after_markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    action_key = str(action or "").strip().lower()
    if action_key not in {"create", "delete"}:
        raise ValueError("nle_marker_edit_action_invalid")
    marker_row = dict(marker or {})
    if not marker_row:
        raise ValueError("nle_marker_edit_marker_required")
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    before_marker_rows = [
        dict(row)
        for row in (before_markers if before_markers is not None else project_cut_boundary_provisional_segments(project))
        if isinstance(row, dict)
    ]
    after_marker_rows = [
        dict(row)
        for row in (after_markers if after_markers is not None else before_marker_rows)
        if isinstance(row, dict)
    ]
    marker_id = _marker_identity(marker_row, len(before_marker_rows))

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows_and_provisional_markers(project, before_rows, after_marker_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    commit_source_key = str(commit_source or f"provisional_cut_boundary_{action_key}")
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_marker_edit:{marker_id}:{action_key}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        markers=before_marker_rows,
        ui_state_ref={
            "operation_family": "marker_edit",
            "target_id": marker_id,
            "action": action_key,
            "commit_boundary": "release",
            "commit_source": commit_source_key,
        },
        metadata={"pilot": "dual_write_marker_edit"},
    )
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "marker_edit",
        "marker_id": marker_id,
        "marker_kind": "cut_boundary",
        "action": action_key,
        "commit_boundary": "release",
        "commit_source": commit_source_key,
        "before_marker_count": len(before_marker_rows),
        "after_marker_count": len(after_marker_rows),
        "marker_status": str(marker_row.get("status") or ""),
    }
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="marker_edit",
        target_ids=[marker_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata=metadata,
    )

    state = sync_project_nle_state_from_editor_rows(project, before_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "marker_edit",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_marker_action": action_key,
        "dual_write_marker_count": len(after_marker_rows),
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(before_rows))
    project["editor_state"] = shadow_after["editor_state"]
    project["analysis"] = dict(shadow_after.get("analysis") or {})
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(before_rows, projected_rows, primary_fps=project_primary_fps(project))
    return NLEDualWritePilotResult(
        operation_family="marker_edit",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


def _roughcut_candidates(project: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    state = project.get("roughcut_state") if isinstance(project.get("roughcut_state"), dict) else {}
    candidates = [dict(item) for item in list(state.get("candidates") or []) if isinstance(item, dict)]
    return dict(state), candidates


def _roughcut_candidate_index(project: dict[str, Any], candidate_id: str = "") -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    state, candidates = _roughcut_candidates(project)
    selected_id = str(candidate_id or state.get("selected_candidate_id") or "").strip()
    for index, candidate in enumerate(candidates):
        if str(candidate.get("candidate_id") or "") == selected_id:
            return state, candidates, index
    if not selected_id and candidates:
        return state, candidates, 0
    raise ValueError(f"nle_roughcut_range_edit_candidate_missing:{selected_id}")


def _roughcut_output_counts(candidate: dict[str, Any]) -> dict[str, int]:
    outputs = candidate.get("outputs") if isinstance(candidate.get("outputs"), dict) else {}
    edl = outputs.get("edl") if isinstance(outputs.get("edl"), dict) else {}
    render_plan = outputs.get("render_plan") if isinstance(outputs.get("render_plan"), dict) else {}
    return {
        "edl_segment_count": len([row for row in list(edl.get("segments") or []) if isinstance(row, dict)]),
        "render_manifest_count": len([row for row in list(render_plan.get("segment_manifest") or []) if isinstance(row, dict)]),
        "stitched_boundary_count": len(
            [
                row
                for row in list(render_plan.get("stitched_cut_boundaries") or edl.get("stitched_cut_boundaries") or [])
                if isinstance(row, dict)
            ]
        ),
    }


def apply_roughcut_range_edit_dual_write_pilot(
    project: dict[str, Any],
    *,
    candidate_id: str = "",
    target_ids: list[str] | tuple[str, ...] | None = None,
    after_candidate: dict[str, Any],
    edit_type: str = "range_edit",
    commit_boundary: str = "",
    commit_source: str = "",
    project_path: str = "",
) -> NLEDualWritePilotResult:
    if not isinstance(project, dict):
        raise TypeError("project_required")
    if not isinstance(after_candidate, dict):
        raise TypeError("after_candidate_required")
    state_payload, candidates, index = _roughcut_candidate_index(project, candidate_id=candidate_id)
    before_candidate = deepcopy(candidates[index])
    target_candidate_id = str(candidate_id or before_candidate.get("candidate_id") or after_candidate.get("candidate_id") or "").strip()
    if not target_candidate_id:
        raise ValueError("nle_roughcut_range_edit_candidate_id_required")
    updated_candidate = deepcopy(after_candidate)
    updated_candidate["candidate_id"] = target_candidate_id
    targets = tuple(str(item).strip() for item in list(target_ids or ()) if str(item).strip())
    if not targets:
        raise ValueError("nle_roughcut_range_edit_targets_required")

    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)

    candidates[index] = updated_candidate
    after_state = dict(state_payload)
    after_state["selected_candidate_id"] = target_candidate_id
    after_state["candidates"] = candidates
    shadow_after = deepcopy(project)
    shadow_after["roughcut_state"] = after_state
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    if int(after_projection.invalid_duration_count or 0) != 0:
        raise ValueError("nle_roughcut_range_edit_final_invalid_duration")
    if int(after_projection.non_monotonic_count or 0) != 0:
        raise ValueError("nle_roughcut_range_edit_final_non_monotonic")
    if int(after_projection.overlap_count or 0) != 0:
        raise ValueError("nle_roughcut_range_edit_final_overlap")
    if int(after_projection.max_active_segments or 0) > 1:
        raise ValueError("nle_roughcut_range_edit_final_max_active_segments")
    if not bool(after_projection.render_export_stable):
        raise ValueError("nle_roughcut_range_edit_render_export_drift")

    edit_key = str(edit_type or "range_edit").strip() or "range_edit"
    commit_boundary_key = str(commit_boundary or "").strip()
    commit_source_key = str(commit_source or "").strip()
    before_counts = _roughcut_output_counts(before_candidate)
    after_counts = _roughcut_output_counts(updated_candidate)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_roughcut_range_edit:{target_candidate_id}:{edit_key}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for row in before_rows if isinstance(row, dict) and bool(row.get("is_gap"))],
        ui_state_ref={
            "operation_family": "roughcut_range_edit",
            "candidate_id": target_candidate_id,
            "target_ids": list(targets),
            "edit_type": edit_key,
            "commit_boundary": commit_boundary_key,
            "commit_source": commit_source_key,
            "before_counts": before_counts,
            "after_counts": after_counts,
        },
        metadata={"pilot": "dual_write_roughcut_range_edit"},
    )
    metadata: dict[str, Any] = {
        "pilot": "dual_write",
        "operation_family": "roughcut_range_edit",
        "candidate_id": target_candidate_id,
        "edit_type": edit_key,
        "before_counts": before_counts,
        "after_counts": after_counts,
    }
    if commit_boundary_key:
        metadata["commit_boundary"] = commit_boundary_key
    if commit_source_key:
        metadata["commit_source"] = commit_source_key
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="roughcut_range_edit",
        target_ids=targets,
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="output",
        undo_snapshot=undo,
        metadata=metadata,
    )

    project["roughcut_state"] = after_state
    state = sync_project_nle_state_from_editor_rows(project, before_rows, project_path=project_path)
    state.snapshot = build_project_nle_snapshot(project, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "roughcut_range_edit",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(before_rows),
        "dual_write_roughcut_candidate_id": target_candidate_id,
        "dual_write_roughcut_edit_type": edit_key,
    }
    record_nle_operation_journal_entry(state, operation, projected_count=len(before_rows))
    projected_rows = project_segments_from_nle_state(project, project_path=project_path)
    assert_nle_editor_rows_consistent(before_rows, projected_rows, primary_fps=project_primary_fps(project))
    return NLEDualWritePilotResult(
        operation_family="roughcut_range_edit",
        operation=operation,
        before_projection=before_projection,
        after_projection=after_projection,
        projected_rows=tuple(dict(row) for row in projected_rows),
    )


__all__ = [
    "NLEDualWritePilotResult",
    "apply_candidate_confirm_dual_write_pilot",
    "apply_caption_delete_dual_write_pilot",
    "apply_caption_merge_dual_write_pilot",
    "apply_caption_move_commit_dual_write_pilot",
    "apply_caption_move_dual_write_pilot",
    "apply_caption_range_replace_dual_write_pilot",
    "apply_caption_resize_dual_write_pilot",
    "apply_caption_split_dual_write_pilot",
    "apply_caption_text_edit_dual_write_pilot",
    "apply_gap_delete_dual_write_pilot",
    "apply_gap_generate_dual_write_pilot",
    "apply_marker_edit_dual_write_pilot",
    "apply_roughcut_range_edit_dual_write_pilot",
]
