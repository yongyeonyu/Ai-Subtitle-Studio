#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_dual_write import (
    apply_candidate_confirm_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
)
from core.project.nle_project_state import (
    NLE_PROJECT_STATE_RUNTIME_KEY,
    project_segments_from_nle_state,
)
from core.project.project_context import build_editor_state, project_segments_to_editor


SCHEMA = "ai_subtitle_studio.nle_dual_write_duration_bound.v1"
OWNER_FUNCTIONS = (
    "apply_gap_generate_dual_write_pilot",
    "apply_caption_merge_dual_write_pilot",
    "apply_caption_split_dual_write_pilot",
    "apply_candidate_confirm_dual_write_pilot",
    "apply_caption_delete_dual_write_pilot",
    "apply_caption_resize_dual_write_pilot",
    "apply_caption_move_dual_write_pilot",
    "apply_caption_range_replace_dual_write_pilot",
    "apply_caption_move_commit_dual_write_pilot",
    "apply_caption_text_edit_dual_write_pilot",
    "apply_gap_delete_dual_write_pilot",
)
BLOCKED_SCOPE = (
    "ui_layout_or_label_changes_not_allowed",
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "stt_or_cache_default_policy_not_changed",
    "app_store_packaging_not_in_scope",
)


def _three_caption_project() -> dict[str, Any]:
    return {
        "project_name": "nle_duration_bound_audit",
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


def _raw_vector_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    return list(
        (
            ((project.get("editor_state", {}) or {}).get("rendering", {}) or {})
            .get("subtitle_canvas", {})
            .get("segments", [])
        )
        or []
    )


def _function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.find(marker)
    if start < 0:
        return ""
    next_def = source.find("\ndef ", start + len(marker))
    return source[start:] if next_def < 0 else source[start:next_def]


def _static_owner_checks() -> list[dict[str, Any]]:
    source_path = ROOT / "core/project/nle_dual_write.py"
    source = source_path.read_text(encoding="utf-8")
    checks: list[dict[str, Any]] = []
    for function_name in OWNER_FUNCTIONS:
        body = _function_body(source, function_name)
        checks.append({
            "function": function_name,
            "found": bool(body),
            "duration_bound_helper_called": "_enforce_dual_write_project_duration_bound(" in body,
        })
    return checks


def _caption_move_tail_clamp_check() -> dict[str, Any]:
    project = _three_caption_project()
    result = apply_caption_move_dual_write_pilot(
        project,
        caption_id="subtitle_vector_0003",
        new_start=5.5,
        new_end=6.2,
        commit_boundary="release",
        commit_source="duration_bound_audit",
    )
    legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    nle_rows = project_segments_from_nle_state(project)
    raw_rows = _raw_vector_segments(project)
    target_legacy = next(row for row in legacy_rows if row.get("id") == "subtitle_vector_0003")
    target_nle = next(row for row in nle_rows if row.get("id") == "subtitle_vector_0003")
    target_raw = next(row for row in raw_rows if row.get("id") == "subtitle_vector_0003")
    metadata = dict(result.operation.metadata or {})
    state_metadata = dict(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata or {})
    passed = (
        metadata.get("duration_bound_trim_applied") is True
        and metadata.get("duration_bound_trimmed_row_count") == 1
        and metadata.get("duration_bound_dropped_row_count") == 0
        and round(float(target_legacy.get("end", 0.0) or 0.0), 6) == 6.0
        and int(target_legacy.get("end_frame", -1) or -1) == 180
        and round(float(target_nle.get("end", 0.0) or 0.0), 6) == 6.0
        and int(target_nle.get("end_frame", -1) or -1) == 180
        and int((target_raw.get("time", {}) or {}).get("end_frame", -1) or -1) == 180
        and state_metadata.get("dual_write_duration_bound_trimmed_row_count") == 1
        and result.after_projection.invalid_duration_count == 0
        and result.after_projection.non_monotonic_count == 0
        and result.after_projection.overlap_count == 0
        and result.after_projection.max_active_segments <= 1
    )
    return {
        "case": "caption_move_tail_clamp",
        "passed": passed,
        "legacy_end": target_legacy.get("end"),
        "legacy_end_frame": target_legacy.get("end_frame"),
        "nle_end": target_nle.get("end"),
        "nle_end_frame": target_nle.get("end_frame"),
        "raw_end_frame": (target_raw.get("time", {}) or {}).get("end_frame"),
        "operation_trimmed_row_count": metadata.get("duration_bound_trimmed_row_count", 0),
        "operation_dropped_row_count": metadata.get("duration_bound_dropped_row_count", 0),
        "invalid_duration_count": result.after_projection.invalid_duration_count,
        "non_monotonic_count": result.after_projection.non_monotonic_count,
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def _candidate_confirm_late_drop_check() -> dict[str, Any]:
    project = _three_caption_project()
    confirmed_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    confirmed_rows.append({
        "id": "subtitle_vector_late",
        "start": 6.25,
        "end": 7.0,
        "text": "late candidate",
        "speaker": "00",
    })
    result = apply_candidate_confirm_dual_write_pilot(
        project,
        confirmed_rows=confirmed_rows,
        candidate={"start": 6.25, "end": 7.0, "text": "late candidate"},
        candidate_source="STT2",
        commit_boundary="release",
        commit_source="duration_bound_audit",
    )
    legacy_ids = {row.get("id") for row in project_segments_to_editor(project, include_analysis_candidates=False)}
    nle_ids = {row.get("id") for row in project_segments_from_nle_state(project)}
    raw_ids = {row.get("id") for row in _raw_vector_segments(project)}
    metadata = dict(result.operation.metadata or {})
    state_metadata = dict(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata or {})
    passed = (
        metadata.get("duration_bound_trim_applied") is True
        and metadata.get("duration_bound_trimmed_row_count") == 0
        and metadata.get("duration_bound_dropped_row_count") == 1
        and metadata.get("duration_bound_input_count") == 4
        and metadata.get("duration_bound_output_count") == 3
        and state_metadata.get("dual_write_duration_bound_dropped_row_count") == 1
        and "subtitle_vector_late" not in legacy_ids
        and "subtitle_vector_late" not in nle_ids
        and "subtitle_vector_late" not in raw_ids
        and result.after_projection.invalid_duration_count == 0
        and result.after_projection.non_monotonic_count == 0
        and result.after_projection.overlap_count == 0
        and result.after_projection.max_active_segments <= 1
    )
    return {
        "case": "candidate_confirm_late_drop",
        "passed": passed,
        "legacy_has_late_row": "subtitle_vector_late" in legacy_ids,
        "nle_has_late_row": "subtitle_vector_late" in nle_ids,
        "raw_has_late_row": "subtitle_vector_late" in raw_ids,
        "operation_trimmed_row_count": metadata.get("duration_bound_trimmed_row_count", 0),
        "operation_dropped_row_count": metadata.get("duration_bound_dropped_row_count", 0),
        "operation_input_count": metadata.get("duration_bound_input_count", 0),
        "operation_output_count": metadata.get("duration_bound_output_count", 0),
        "invalid_duration_count": result.after_projection.invalid_duration_count,
        "non_monotonic_count": result.after_projection.non_monotonic_count,
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def build_nle_dual_write_duration_bound_report() -> dict[str, Any]:
    source = (ROOT / "core/project/nle_dual_write.py").read_text(encoding="utf-8")
    project_context_source = (ROOT / "core/project/project_context.py").read_text(encoding="utf-8")
    owner_checks = _static_owner_checks()
    dynamic_checks = [_caption_move_tail_clamp_check(), _candidate_confirm_late_drop_check()]
    helper_imported = "trim_editor_rows_to_project_duration" in source
    helper_public = "def trim_editor_rows_to_project_duration(" in project_context_source
    static_ready = all(row["found"] and row["duration_bound_helper_called"] for row in owner_checks)
    dynamic_ready = all(row["passed"] for row in dynamic_checks)
    return {
        "schema": SCHEMA,
        "audit_id": "nle_dual_write_duration_bound_20260628",
        "ready": bool(helper_imported and helper_public and static_ready and dynamic_ready),
        "runtime_change_applied": True,
        "persisted_nle_fields_changed": False,
        "ui_change_applied": False,
        "stt_or_cache_default_changed": False,
        "duration_bound_helper_imported": helper_imported,
        "duration_bound_public_helper": helper_public,
        "owner_count": len(owner_checks),
        "owner_covered_count": sum(1 for row in owner_checks if row["duration_bound_helper_called"]),
        "owner_checks": owner_checks,
        "dynamic_checks": dynamic_checks,
        "blocked_scope": list(BLOCKED_SCOPE),
        "acceptance_gate": {
            "final_invalid_duration_count": 0,
            "final_non_monotonic_count": 0,
            "final_overlap_count": 0,
            "global_canvas_max_active_segments": 1,
            "raw_editor_state_duration_bound_required": True,
            "runtime_nle_state_duration_bound_required": True,
            "nas_heydealer_required_for_release_regression": True,
        },
    }


def write_nle_dual_write_duration_bound_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_dual_write_duration_bound.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Dual-Write Duration Bound Audit",
        "",
        f"Schema: `{report['schema']}`",
        f"Ready: `{report['ready']}`",
        f"Runtime change applied: `{report['runtime_change_applied']}`",
        f"Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"UI change applied: `{report['ui_change_applied']}`",
        f"STT/cache default changed: `{report['stt_or_cache_default_changed']}`",
        f"Owner coverage: `{report['owner_covered_count']}/{report['owner_count']}`",
        "",
        "## Owner Function Coverage",
        "",
        "| function | found | duration-bound helper |",
        "| --- | --- | --- |",
    ]
    for row in report["owner_checks"]:
        lines.append(
            f"| {row['function']} | {row['found']} | {row['duration_bound_helper_called']} |"
        )
    lines.extend([
        "",
        "## Dynamic Checks",
        "",
        "| case | passed | trimmed | dropped | overlap | max active |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for row in report["dynamic_checks"]:
        lines.append(
            "| {case} | {passed} | {trimmed} | {dropped} | {overlap} | {max_active} |".format(
                case=row["case"],
                passed=row["passed"],
                trimmed=row.get("operation_trimmed_row_count", 0),
                dropped=row.get("operation_dropped_row_count", 0),
                overlap=row.get("overlap_count", 0),
                max_active=row.get("max_active_segments", 0),
            )
        )
    lines.extend([
        "",
        "## Blocked Scope",
        "",
        *[f"- `{item}`" for item in report["blocked_scope"]],
        "",
        "## Acceptance Gate",
        "",
        f"- Raw editor-state duration bound required: `{report['acceptance_gate']['raw_editor_state_duration_bound_required']}`",
        f"- Runtime NLE-state duration bound required: `{report['acceptance_gate']['runtime_nle_state_duration_bound_required']}`",
        f"- NAS HeyDealer release regression required: `{report['acceptance_gate']['nas_heydealer_required_for_release_regression']}`",
    ])
    (output_dir / "nle_dual_write_duration_bound.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_dual_write_duration_bound_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_dual_write_duration_bound_report()
    write_nle_dual_write_duration_bound_report(output_dir, report)
    print(json.dumps({
        "ready": report["ready"],
        "owner_coverage": f"{report['owner_covered_count']}/{report['owner_count']}",
        "output_dir": str(output_dir),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
