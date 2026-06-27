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

from core.project.nle_persistence_guard import (
    NLE_PERSISTENCE_QUARANTINE_KEY,
    UNAPPROVED_NLE_PERSISTENCE_KEYS,
    assert_no_unapproved_nle_persistence_fields,
    strip_unapproved_nle_persistence_fields,
)
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
)
from core.project.nle_project_state import NLEProjectState, NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


SCHEMA = "ai_subtitle_studio.nle_persistence_cutover_readiness.v1"
CUTOVER_BLOCKERS = (
    "persisted_nle_project_fields_not_approved",
    "legacy_disk_shape_required_for_compatibility",
    "owner_approval_required_before_disk_format_change",
)


def _legacy_project() -> dict[str, Any]:
    return {
        "project_name": "nle_persistence_cutover_audit",
        "mode": "single",
        "video": {"duration_sec": 4.0, "primary_fps": 30.0},
        "timeline": {
            "total_duration": 4.0,
            "timebase": {"primary_fps": 30.0},
            "tracks": [{"clips": []}],
        },
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {"id": "caption_2", "start": 2.0, "end": 3.0, "text": "second", "speaker": "01"},
            ],
            primary_fps=30.0,
        ),
    }


def _three_caption_project() -> dict[str, Any]:
    return {
        "project_name": "nle_persistence_operation_roundtrip",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {"id": "caption_1", "start": 0.0, "end": 1.0, "text": "first", "speaker": "00"},
                {"id": "caption_2", "start": 1.0, "end": 2.0, "text": "second", "speaker": "01"},
                {"id": "caption_3", "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
            ],
            primary_fps=30.0,
        ),
    }


def _storage_has_unapproved_nle_fields(storage: dict[str, Any]) -> bool:
    if not isinstance(storage, dict):
        return True
    return any(key in storage for key in UNAPPROVED_NLE_PERSISTENCE_KEYS) or NLE_PERSISTENCE_QUARANTINE_KEY in storage


def _runtime_roundtrip_check(work_dir: Path) -> dict[str, Any]:
    project_path = work_dir / "nle-persistence-cutover-audit.aissproj"
    project = _legacy_project()
    write_project_file(str(project_path), project)
    clear_project_file_cache(str(project_path))

    loaded = read_project_file(str(project_path))
    state = loaded.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface="audit_storage")
    storage_clean = not _storage_has_unapproved_nle_fields(storage)

    return {
        "project_path": str(project_path),
        "loaded_runtime_state": isinstance(state, NLEProjectState),
        "runtime_state_schema": str(getattr(state, "schema", "") or ""),
        "runtime_caption_count": len(getattr(state, "captions", []) or []),
        "storage_clean": storage_clean,
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "storage_has_quarantine": NLE_PERSISTENCE_QUARANTINE_KEY in storage,
        "storage_schema": str(storage.get("storage_schema", "") or ""),
    }


def _future_payload_quarantine_check() -> dict[str, Any]:
    project = _legacy_project()
    project["nle"] = {"future_doc": {"tracks": []}}
    project["nle_snapshot"] = {"schema": "future_snapshot"}
    project[NLE_PROJECT_STATE_RUNTIME_KEY] = {"schema": "persisted_future_state"}
    report = strip_unapproved_nle_persistence_fields(project, source="audit_future_payload")
    assert_no_unapproved_nle_persistence_fields(project, surface="audit_future_payload")
    return {
        "quarantine_recorded": isinstance(report, dict),
        "stripped_keys": list(report.get("stripped_keys") or []) if isinstance(report, dict) else [],
        "remaining_unapproved_fields": [
            key for key in UNAPPROVED_NLE_PERSISTENCE_KEYS if key in project
        ],
        "quarantine_key_present": NLE_PERSISTENCE_QUARANTINE_KEY in project,
    }


def _row_signature(
    rows: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    include_id: bool,
) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {
            "text": str(row.get("text") or ""),
            "is_gap": bool(row.get("is_gap")),
            "start_frame": int(row.get("start_frame", row.get("timeline_start_frame", 0)) or 0),
            "end_frame": int(row.get("end_frame", row.get("timeline_end_frame", 0)) or 0),
        }
        if include_id:
            item["id"] = str(row.get("id") or "")
        signature.append(item)
    return signature


def _operation_roundtrip_check(work_dir: Path, operation_name: str, project: dict[str, Any], result: Any) -> dict[str, Any]:
    operation_dir = work_dir / operation_name
    operation_dir.mkdir(parents=True, exist_ok=True)
    project_path = operation_dir / f"{operation_name}.aissproj"
    expected_rows = _row_signature(list(result.projected_rows or []), include_id=False)
    expected_identity_rows = _row_signature(list(result.projected_rows or []), include_id=True)

    write_project_file(str(project_path), deepcopy(project))
    storage = read_project_storage_payload(str(project_path))
    assert_no_unapproved_nle_persistence_fields(storage, surface=f"{operation_name}_storage")
    clear_project_file_cache(str(project_path))
    reopened = read_project_file(str(project_path))
    reopened_state = reopened.get(NLE_PROJECT_STATE_RUNTIME_KEY)
    reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)
    reopened_signature = _row_signature(reopened_rows, include_id=False)
    reopened_identity_signature = _row_signature(reopened_rows, include_id=True)

    return {
        "operation_family": operation_name,
        "project_path": str(project_path),
        "operation_kind": str(getattr(result.operation, "kind", "") or ""),
        "runtime_state_hydrated": isinstance(reopened_state, NLEProjectState),
        "storage_clean": not _storage_has_unapproved_nle_fields(storage),
        "storage_has_runtime_nle_key": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "reopened_matches_projected": reopened_signature == expected_rows,
        "reopened_identity_preserved": reopened_identity_signature == expected_identity_rows,
        "projected_count": len(expected_rows),
        "reopened_count": len(reopened_signature),
        "invalid_duration_count": int(getattr(result.after_projection, "invalid_duration_count", 0) or 0),
        "non_monotonic_count": int(getattr(result.after_projection, "non_monotonic_count", 0) or 0),
        "overlap_count": int(getattr(result.after_projection, "overlap_count", 0) or 0),
        "max_active_segments": int(getattr(result.after_projection, "max_active_segments", 0) or 0),
    }


def _operation_roundtrip_matrix(work_dir: Path) -> list[dict[str, Any]]:
    cases: list[tuple[str, dict[str, Any], Any]] = []

    project = _legacy_project()
    cases.append(("gap_delete", project, apply_gap_delete_dual_write_pilot(project, gap_id="gap_1")))

    project = _legacy_project()
    cases.append((
        "gap_generate",
        project,
        apply_gap_generate_dual_write_pilot(project, gap_id="gap_1", sub_start=1.5, sub_end=2.0, mode="from", text="새자막"),
    ))

    project = _legacy_project()
    cases.append((
        "caption_move",
        project,
        apply_caption_move_dual_write_pilot(project, caption_id="subtitle_vector_0002", new_start=3.0, new_end=4.0),
    ))

    project = _three_caption_project()
    cases.append((
        "caption_resize",
        project,
        apply_caption_resize_dual_write_pilot(project, caption_id="subtitle_vector_0002", new_start=0.5, new_end=2.0, edge="square_left"),
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
        ),
    ))

    project = _legacy_project()
    cases.append((
        "caption_delete",
        project,
        apply_caption_delete_dual_write_pilot(project, caption_id="subtitle_vector_0002", replacement_gap_id="gap_deleted_caption_2"),
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
        ),
    ))

    return [
        _operation_roundtrip_check(work_dir, operation_name, project, result)
        for operation_name, project, result in cases
    ]


def build_nle_persistence_cutover_report(*, output_dir: Path | None = None) -> dict[str, Any]:
    out_dir = Path(output_dir or ROOT / "output" / "manual_verification" / "latest" / "nle_persistence_cutover_audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    runtime_roundtrip = _runtime_roundtrip_check(out_dir / "roundtrip_fixture")
    future_payload = _future_payload_quarantine_check()
    operation_roundtrip_matrix = _operation_roundtrip_matrix(out_dir / "operation_roundtrip_matrix")
    operation_roundtrip_all_passed = all(
        bool(row.get("runtime_state_hydrated"))
        and bool(row.get("storage_clean"))
        and bool(row.get("reopened_matches_projected"))
        and int(row.get("invalid_duration_count") or 0) == 0
        and int(row.get("non_monotonic_count") or 0) == 0
        and int(row.get("overlap_count") or 0) == 0
        and int(row.get("max_active_segments") or 0) <= 1
        for row in operation_roundtrip_matrix
    )

    checks = {
        "runtime_roundtrip": runtime_roundtrip,
        "future_payload_quarantine": future_payload,
        "operation_roundtrip_matrix": operation_roundtrip_matrix,
    }
    prep_ready = (
        runtime_roundtrip["loaded_runtime_state"]
        and runtime_roundtrip["storage_clean"]
        and future_payload["quarantine_recorded"]
        and not future_payload["remaining_unapproved_fields"]
        and operation_roundtrip_all_passed
    )
    return {
        "schema": SCHEMA,
        "status": "blocked",
        "prep_ready": prep_ready,
        "persistence_cutover_ready": False,
        "blockers": list(CUTOVER_BLOCKERS),
        "checks": checks,
        "operation_roundtrip_all_passed": operation_roundtrip_all_passed,
        "operation_roundtrip_family_count": len(operation_roundtrip_matrix),
        "owner_approval_required_before": [
            "persisting top-level nle payloads",
            "persisting nle_snapshot payloads",
            "persisting _nle_project_state payloads",
            "changing .aissproj legacy disk shape",
        ],
        "next_safe_steps": [
            "keep runtime-only NLE hydration and legacy disk payload",
            "expand tests around save/reopen/export parity before any persisted NLE format proposal",
            "treat this audit as readiness evidence only, not cutover approval",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _markdown_report(payload: dict[str, Any]) -> str:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    runtime = checks.get("runtime_roundtrip") if isinstance(checks.get("runtime_roundtrip"), dict) else {}
    future = checks.get("future_payload_quarantine") if isinstance(checks.get("future_payload_quarantine"), dict) else {}
    operations = checks.get("operation_roundtrip_matrix") if isinstance(checks.get("operation_roundtrip_matrix"), list) else []
    lines = [
        "# NLE Persistence Cutover Audit",
        "",
        f"- Status: `{payload.get('status')}`",
        f"- Prep ready: `{bool(payload.get('prep_ready'))}`",
        f"- Persistence cutover ready: `{bool(payload.get('persistence_cutover_ready'))}`",
        f"- Operation roundtrip families: `{payload.get('operation_roundtrip_family_count')}`",
        f"- Operation roundtrip all passed: `{bool(payload.get('operation_roundtrip_all_passed'))}`",
        "",
        "## Runtime Roundtrip",
        "",
        f"- Runtime NLE state hydrated: `{bool(runtime.get('loaded_runtime_state'))}`",
        f"- Runtime caption count: `{runtime.get('runtime_caption_count')}`",
        f"- Disk storage clean of NLE runtime fields: `{bool(runtime.get('storage_clean'))}`",
        f"- Storage schema: `{runtime.get('storage_schema')}`",
        "",
        "## Future Payload Quarantine",
        "",
        f"- Quarantine recorded: `{bool(future.get('quarantine_recorded'))}`",
        f"- Stripped keys: `{', '.join(future.get('stripped_keys') or [])}`",
        f"- Remaining unapproved fields: `{', '.join(future.get('remaining_unapproved_fields') or []) or 'none'}`",
        "",
        "## Operation Roundtrip Matrix",
        "",
        "| Operation | Runtime NLE | Storage Clean | Reopened Matches | ID Preserved | Final Overlap | Max Active |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in operations:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join([
                str(row.get("operation_family") or ""),
                str(bool(row.get("runtime_state_hydrated"))),
                str(bool(row.get("storage_clean"))),
                str(bool(row.get("reopened_matches_projected"))),
                str(bool(row.get("reopened_identity_preserved"))),
                str(row.get("overlap_count")),
                str(row.get("max_active_segments")),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## Blockers",
        "",
    ])
    lines.extend(f"- `{item}`" for item in payload.get("blockers") or [])
    lines.extend(["", "## Next Safe Steps", ""])
    lines.extend(f"- {item}" for item in payload.get("next_safe_steps") or [])
    lines.append("")
    return "\n".join(lines)


def write_nle_persistence_cutover_report(output_dir: Path, payload: dict[str, Any]) -> None:
    _write_json(output_dir / "nle_persistence_cutover_audit.json", payload)
    (output_dir / "nle_persistence_cutover_audit.md").write_text(_markdown_report(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NLE persistence cutover readiness without changing disk format.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_persistence_cutover_audit_20260628")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    payload = build_nle_persistence_cutover_report(output_dir=output_dir)
    write_nle_persistence_cutover_report(output_dir, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
