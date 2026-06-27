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
    sync_project_nle_state_from_editor_rows,
)
from core.project.nle_projection_parity import (
    ProjectionParityReport,
    build_project_nle_projection_parity_report,
)
from core.project.project_context import (
    build_editor_state,
    project_clip_boundaries,
    project_media_files,
    project_segments_to_editor,
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
        },
        metadata={"pilot": "dual_write_gap_generate"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="gap_generate",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={
            "pilot": "dual_write",
            "operation_family": "gap_generate",
            "gap_id": target_id,
            "generated_caption_id": caption_id,
            "mode": str(mode or ""),
            "left_gap_preserved": caption_start > target_start + 0.001,
            "right_gap_preserved": caption_end < target_end - 0.001,
        },
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "gap_generate",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_generated_caption_id": caption_id,
    }
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
        },
        metadata={"pilot": "dual_write_caption_merge"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_merge",
        target_ids=[left_id, right_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={
            "pilot": "dual_write",
            "operation_family": "caption_merge",
            "kept_caption_id": keep_id,
            "removed_caption_id": remove_id,
            "merged_text": text,
            "merged_start": merged_start,
            "merged_end": merged_end,
        },
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_merge",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_kept_caption_id": keep_id,
        "dual_write_removed_caption_id": remove_id,
    }
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

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
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
        },
        metadata={"pilot": "dual_write_caption_split"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_split",
        target_ids=[target_id, right_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={
            "pilot": "dual_write",
            "operation_family": "caption_split",
            "caption_id": target_id,
            "new_caption_id": right_id,
            "split_sec": split_at,
            "left_text": left,
            "right_text": right,
        },
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_split",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_split_caption_id": target_id,
        "dual_write_new_caption_id": right_id,
    }
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
        },
        metadata={"pilot": "dual_write_candidate_confirm"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="candidate_confirm",
        target_ids=target_ids,
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={
            "pilot": "dual_write",
            "operation_family": "candidate_confirm",
            "candidate_id": candidate_id,
            "candidate_source": source,
            "candidate_text": str(candidate.get("text", "") or ""),
            "candidate_start": _row_start(candidate),
            "candidate_end": _row_end(candidate, _row_start(candidate)),
            "confirmed_row_count": len(after_rows),
            "replaced_target_ids": list(target_ids),
        },
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "candidate_confirm",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_candidate_id": candidate_id,
        "dual_write_candidate_source": source,
    }
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
    after_rows = [dict(row) for row in before_rows]
    after_rows[target_index] = _caption_row_to_gap(after_rows[target_index], caption_id=target_id, gap_id=gap_id)
    after_rows = _sorted_editor_rows(after_rows)

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
        },
        metadata={"pilot": "dual_write_caption_delete"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="caption_delete",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={
            "pilot": "dual_write",
            "operation_family": "caption_delete",
            "caption_id": target_id,
            "replacement_gap_id": gap_id,
            "delete_mode": "replace_with_silence_gap",
        },
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "caption_delete",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
        "dual_write_replacement_gap_id": gap_id,
    }
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
    }
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
    }
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
    }
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
    if old_text == text:
        raise ValueError("nle_caption_text_edit_unchanged")

    after_rows = [dict(row) for row in before_rows]
    after_rows[target_index]["text"] = text
    after_rows = _sorted_editor_rows(after_rows)

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
    if commit_boundary:
        metadata["commit_boundary"] = commit_boundary
    if commit_source:
        metadata["commit_source"] = commit_source
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
    }
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
    after_rows = [
        dict(row)
        for index, row in enumerate(before_rows)
        if index != target_index
    ]

    before_projection = build_project_nle_projection_parity_report(project, project_path=project_path)
    shadow_after = _shadow_project_with_rows(project, after_rows)
    after_projection = build_project_nle_projection_parity_report(shadow_after, project_path=project_path)
    undo = build_nle_undo_snapshot(
        operation_id=f"dual_write_gap_delete:{target_id}",
        editor_rows=before_rows,
        candidate_lanes=_candidate_lanes(project, before_rows),
        silence_gaps=[row for _index, row in gap_rows],
        ui_state_ref={"operation_family": "gap_delete", "target_id": target_id},
        metadata={"pilot": "dual_write_gap_delete"},
    )
    operation = build_nle_editor_operation(
        operation_id=undo.operation_id,
        kind="gap_delete",
        target_ids=[target_id],
        before_projection=before_projection,
        after_projection=after_projection,
        time_domain="sequence",
        undo_snapshot=undo,
        metadata={"pilot": "dual_write", "operation_family": "gap_delete"},
    )

    state = sync_project_nle_state_from_editor_rows(project, after_rows, project_path=project_path)
    state.metadata = {
        **dict(state.metadata or {}),
        "dual_write_pilot_family": "gap_delete",
        "dual_write_last_operation_id": operation.operation_id,
        "dual_write_projected_count": len(after_rows),
    }
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


__all__ = [
    "NLEDualWritePilotResult",
    "apply_candidate_confirm_dual_write_pilot",
    "apply_caption_delete_dual_write_pilot",
    "apply_caption_merge_dual_write_pilot",
    "apply_caption_move_commit_dual_write_pilot",
    "apply_caption_move_dual_write_pilot",
    "apply_caption_resize_dual_write_pilot",
    "apply_caption_split_dual_write_pilot",
    "apply_caption_text_edit_dual_write_pilot",
    "apply_gap_delete_dual_write_pilot",
    "apply_gap_generate_dual_write_pilot",
]
