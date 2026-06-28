#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_dual_write import (
    apply_candidate_confirm_dual_write_pilot,
    apply_caption_delete_dual_write_pilot,
    apply_caption_merge_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
    apply_caption_range_replace_dual_write_pilot,
    apply_caption_resize_dual_write_pilot,
    apply_caption_split_dual_write_pilot,
    apply_caption_text_edit_dual_write_pilot,
    apply_gap_delete_dual_write_pilot,
    apply_gap_generate_dual_write_pilot,
    apply_marker_edit_dual_write_pilot,
)
from core.project.nle_operations import (
    NLEEditorOperation,
    NLE_OPERATION_SCHEMA,
    NLE_UNDO_SNAPSHOT_SCHEMA,
)
from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_QUARANTINE_KEY,
    UNAPPROVED_NLE_PERSISTENCE_KEYS,
    assert_no_unapproved_nle_persistence_fields,
)
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.nle_project_state import NLE_OPERATION_JOURNAL_ENTRY_SCHEMA, NLEProjectState
from core.project.project_io import (
    clear_project_file_cache,
    read_project_storage_payload,
    write_project_file,
)
from tools.audit_nle_persistence_cutover import _legacy_project, _three_caption_project


SCHEMA = "ai_subtitle_studio.nle_operation_journal_contract.v1"
AUDIT_ID = "nle_operation_journal_contract_20260628"
BLOCKED_SCOPE = (
    "persisted_operation_journal_not_approved",
    "runtime_undo_redo_ui_behavior_not_changed",
    "per_pixel_nle_drag_writes_not_allowed",
    "qml_or_gpu_timeline_default_surface_not_allowed",
)


def _storage_has_unapproved_nle_fields(storage: dict[str, Any]) -> bool:
    if not isinstance(storage, dict):
        return True
    return any(key in storage for key in UNAPPROVED_NLE_PERSISTENCE_KEYS) or NLE_PERSISTENCE_QUARANTINE_KEY in storage


def _contains_value(payload: Any, wanted: str) -> bool:
    if isinstance(payload, dict):
        return any(_contains_value(key, wanted) or _contains_value(value, wanted) for key, value in payload.items())
    if isinstance(payload, (list, tuple)):
        return any(_contains_value(item, wanted) for item in payload)
    return str(payload) == wanted


def _operation_cases() -> list[tuple[str, dict[str, Any], Any]]:
    cases: list[tuple[str, dict[str, Any], Any]] = []

    project = _legacy_project()
    cases.append((
        "gap_delete",
        project,
        apply_gap_delete_dual_write_pilot(
            project,
            gap_id="gap_1",
            commit_boundary="release",
            commit_source="gap_delete",
        ),
    ))

    project = _legacy_project()
    cases.append((
        "gap_generate",
        project,
        apply_gap_generate_dual_write_pilot(
            project,
            gap_id="gap_1",
            sub_start=1.5,
            sub_end=2.0,
            mode="from",
            text="새자막",
            commit_boundary="release",
            commit_source="gap_generate",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_move",
        project,
        apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=3.0,
            new_end=4.0,
            commit_boundary="release",
            commit_source="center",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_resize",
        project,
        apply_caption_resize_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=0.5,
            new_end=2.0,
            edge="square_left",
            commit_boundary="release",
            commit_source="square_left",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_text_edit",
        project,
        apply_caption_text_edit_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_text="second\nedited",
            commit_boundary="release",
            commit_source="timeline_inline_text",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_split",
        project,
        apply_caption_split_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            split_sec=1.4,
            left_text="left",
            right_text="right",
            new_caption_id="subtitle_vector_0002_split_right",
            commit_boundary="release",
            commit_source="timeline_smart_split",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_range_replace",
        project,
        apply_caption_range_replace_dual_write_pilot(
            project,
            target_start=1.0,
            target_end=2.0,
            committed_rows=[
                {"line": 0, "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"line": 1, "start": 1.0, "end": 1.5, "text": "second-a", "speaker": "01"},
                {"line": 2, "start": 1.5, "end": 2.0, "text": "second-b", "speaker": "01"},
                {"line": 3, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ],
            commit_boundary="release",
            commit_source="partial_insert_range_replace",
        ),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_merge",
        project,
        apply_caption_merge_dual_write_pilot(
            project,
            left_caption_id="subtitle_vector_0001",
            right_caption_id="subtitle_vector_0002",
            merged_text="first second",
            commit_boundary="release",
            commit_source="live_editor_caption_merge",
        ),
    ))

    project = _legacy_project()
    cases.append((
        "caption_delete",
        project,
        apply_caption_delete_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            replacement_gap_id="gap_deleted_caption_2",
            commit_boundary="release",
            commit_source="segment_delete_to_gap",
        ),
    ))

    project = _three_caption_project()
    candidate = {"source": "STT2", "start": 1.0, "end": 2.0, "text": "STT2 후보"}
    confirmed_rows = [
        {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
        {
            "id": "caption_2",
            "start": 1.0,
            "end": 2.0,
            "text": "STT2 후보",
            "speaker": "01",
            "stt_selected_source": "STT2",
            "stt_candidates": [dict(candidate)],
        },
        {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
    ]
    cases.append((
        "candidate_confirm",
        project,
        apply_candidate_confirm_dual_write_pilot(
            project,
            confirmed_rows=confirmed_rows,
            candidate=candidate,
            candidate_source="STT2",
            candidate_lanes=[candidate],
            commit_boundary="release",
            commit_source="stt_candidate_confirm",
        ),
    ))

    project = _legacy_project()
    marker = {"timeline_sec": 1.5, "timeline_frame": 45, "fps": 30.0, "status": "provisional"}
    cases.append((
        "marker_edit",
        project,
        apply_marker_edit_dual_write_pilot(
            project,
            action="create",
            marker=marker,
            before_markers=[],
            after_markers=[marker],
            commit_source="provisional_cut_boundary_create",
        ),
    ))
    return cases


def _audit_case(work_dir: Path, family: str, project: dict[str, Any], result: Any) -> dict[str, Any]:
    op = getattr(result, "operation", None)
    undo = getattr(op, "undo_snapshot", None)
    metadata = dict(getattr(op, "metadata", {}) or {}) if op is not None else {}
    undo_ui = dict(getattr(undo, "ui_state_ref", {}) or {}) if undo is not None else {}
    state = project.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    journal_rows = list(getattr(state, "operation_journal", ()) or ()) if isinstance(state, NLEProjectState) else []
    latest_journal = journal_rows[-1] if journal_rows else None
    project_path = work_dir / f"{family}.aissproj"
    write_project_file(str(project_path), deepcopy(project))
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface=f"{family}_operation_journal_storage")
    clear_project_file_cache(str(project_path))
    release_metadata = metadata.get("commit_boundary") == "release" and bool(metadata.get("commit_source"))
    undo_release_metadata = undo_ui.get("commit_boundary") == "release" and bool(undo_ui.get("commit_source"))
    frame_policy = dict(getattr(op, "frame_policy", {}) or {}) if op is not None else {}
    after_projection = getattr(result, "after_projection", None)
    invalid = int(getattr(after_projection, "invalid_duration_count", 0) or 0)
    non_monotonic = int(getattr(after_projection, "non_monotonic_count", 0) or 0)
    overlap = int(getattr(after_projection, "overlap_count", 0) or 0)
    max_active = int(getattr(after_projection, "max_active_segments", 0) or 0)
    return {
        "operation_family": family,
        "operation_kind": str(getattr(op, "kind", "") or ""),
        "operation_schema_ok": isinstance(op, NLEEditorOperation) and getattr(op, "schema", "") == NLE_OPERATION_SCHEMA,
        "operation_id": str(getattr(op, "operation_id", "") or ""),
        "target_count": len(tuple(getattr(op, "target_ids", ()) or ())) if op is not None else 0,
        "time_domain": str(getattr(op, "time_domain", "") or ""),
        "frame_policy_unit": str(frame_policy.get("unit") or ""),
        "frame_policy_allow_final_overlap": bool(frame_policy.get("allow_final_overlap")),
        "release_metadata": release_metadata,
        "undo_snapshot_schema_ok": getattr(undo, "schema", "") == NLE_UNDO_SNAPSHOT_SCHEMA,
        "undo_snapshot_id": str(getattr(undo, "snapshot_id", "") or ""),
        "undo_editor_row_count": len(tuple(getattr(undo, "editor_rows", ()) or ())) if undo is not None else 0,
        "undo_candidate_lane_count": len(tuple(getattr(undo, "candidate_lanes", ()) or ())) if undo is not None else 0,
        "undo_silence_gap_count": len(tuple(getattr(undo, "silence_gaps", ()) or ())) if undo is not None else 0,
        "undo_marker_count": len(tuple(getattr(undo, "markers", ()) or ())) if undo is not None else 0,
        "undo_release_metadata": undo_release_metadata,
        "runtime_journal_count": len(journal_rows),
        "runtime_journal_latest_schema_ok": getattr(latest_journal, "schema", "") == NLE_OPERATION_JOURNAL_ENTRY_SCHEMA,
        "runtime_journal_latest_operation_id": str(getattr(latest_journal, "operation_id", "") or ""),
        "runtime_journal_latest_kind": str(getattr(latest_journal, "operation_kind", "") or ""),
        "runtime_journal_latest_release_metadata": (
            getattr(latest_journal, "commit_boundary", "") == "release"
            and bool(getattr(latest_journal, "commit_source", ""))
        ),
        "runtime_journal_latest_overlap_count": int(getattr(latest_journal, "after_overlap_count", 0) or 0),
        "invalid_duration_count": invalid,
        "non_monotonic_count": non_monotonic,
        "overlap_count": overlap,
        "max_active_segments": max_active,
        "storage_clean": not _storage_has_unapproved_nle_fields(storage),
        "operation_schema_persisted": _contains_value(storage, NLE_OPERATION_SCHEMA),
        "undo_schema_persisted": _contains_value(storage, NLE_UNDO_SNAPSHOT_SCHEMA),
        "journal_schema_persisted": _contains_value(storage, NLE_OPERATION_JOURNAL_ENTRY_SCHEMA),
        "runtime_state_persisted": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
    }


def build_nle_operation_journal_report(*, output_dir: Path) -> dict[str, Any]:
    work_dir = output_dir / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    rows = [_audit_case(work_dir, family, project, result) for family, project, result in _operation_cases()]
    all_passed = all(
        row["operation_schema_ok"]
        and row["target_count"] > 0
        and row["time_domain"] == "sequence"
        and row["frame_policy_unit"] == "frame"
        and row["frame_policy_allow_final_overlap"] is False
        and row["release_metadata"]
        and row["undo_snapshot_schema_ok"]
        and row["undo_editor_row_count"] > 0
        and row["undo_release_metadata"]
        and row["runtime_journal_count"] == 1
        and row["runtime_journal_latest_schema_ok"]
        and row["runtime_journal_latest_operation_id"] == row["operation_id"]
        and row["runtime_journal_latest_kind"] == row["operation_kind"]
        and row["runtime_journal_latest_release_metadata"]
        and row["runtime_journal_latest_overlap_count"] == 0
        and row["invalid_duration_count"] == 0
        and row["non_monotonic_count"] == 0
        and row["overlap_count"] == 0
        and row["max_active_segments"] <= 1
        and row["storage_clean"]
        and not row["operation_schema_persisted"]
        and not row["undo_schema_persisted"]
        and not row["journal_schema_persisted"]
        and not row["runtime_state_persisted"]
        for row in rows
    )
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "runtime_change_applied": False,
        "runtime_nle_journal_applied": all(row["runtime_journal_count"] == 1 for row in rows),
        "ready": all_passed,
        "operation_family_count": len(rows),
        "release_metadata_count": sum(1 for row in rows if row["release_metadata"] and row["undo_release_metadata"]),
        "undo_snapshot_count": sum(1 for row in rows if row["undo_snapshot_schema_ok"]),
        "runtime_journal_count": sum(1 for row in rows if row["runtime_journal_count"] == 1),
        "storage_clean_count": sum(1 for row in rows if row["storage_clean"]),
        "checks": rows,
        "blocked_scope": list(BLOCKED_SCOPE),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# NLE Operation Journal Contract Audit",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Ready: `{report['ready']}`",
        f"- Runtime change applied: `{report['runtime_change_applied']}`",
        f"- Runtime NLE journal applied: `{report['runtime_nle_journal_applied']}`",
        f"- Operation families: `{report['operation_family_count']}`",
        f"- Release metadata count: `{report['release_metadata_count']}`",
        f"- Undo snapshot count: `{report['undo_snapshot_count']}`",
        f"- Runtime journal count: `{report['runtime_journal_count']}`",
        f"- Storage clean count: `{report['storage_clean_count']}`",
        "",
        "## Operation Matrix",
        "",
        "| family | kind | release | undo_release | runtime_journal | undo_rows | invalid | non_monotonic | overlap | max_active | storage_clean |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["checks"]:
        lines.append(
            "| {family} | {kind} | {release} | {undo_release} | {runtime_journal} | {undo_rows} | {invalid} | {non_monotonic} | {overlap} | {max_active} | {storage_clean} |".format(
                family=row["operation_family"],
                kind=row["operation_kind"],
                release=row["release_metadata"],
                undo_release=row["undo_release_metadata"],
                runtime_journal=row["runtime_journal_latest_schema_ok"],
                undo_rows=row["undo_editor_row_count"],
                invalid=row["invalid_duration_count"],
                non_monotonic=row["non_monotonic_count"],
                overlap=row["overlap_count"],
                max_active=row["max_active_segments"],
                storage_clean=row["storage_clean"],
            )
        )
    lines.extend(["", "## Blocked Scope", ""])
    for item in report["blocked_scope"]:
        lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def write_nle_operation_journal_report(output_dir: Path, report: dict[str, Any]) -> None:
    _write_json(output_dir / "nle_operation_journal_audit.json", report)
    (output_dir / "nle_operation_journal_audit.md").write_text(_markdown_report(report), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NLE dual-write operation journal and undo contracts.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_operation_journal_audit_20260628")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    report = build_nle_operation_journal_report(output_dir=output_dir)
    write_nle_operation_journal_report(output_dir, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if bool(report.get("ready")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
