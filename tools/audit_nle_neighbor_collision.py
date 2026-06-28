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
    apply_caption_move_commit_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
    apply_caption_resize_dual_write_pilot,
)
from core.project.nle_operations import NLEOperationValidationError
from core.project.nle_project_state import NLE_PROJECT_STATE_RUNTIME_KEY
from core.project.project_context import build_editor_state, project_segments_to_editor


SCHEMA = "ai_subtitle_studio.nle_neighbor_collision_guard.v1"
AUDIT_ID = "nle_neighbor_collision_guard_20260628"
BLOCKED_SCOPE = (
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "ui_layout_or_label_changes_not_changed",
    "stt_or_cache_default_policy_not_changed",
    "app_store_packaging_not_in_scope",
)


def _three_caption_project() -> dict[str, Any]:
    return {
        "project_name": "nle_neighbor_collision_audit",
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


def _row_signature(rows: list[dict[str, Any]]) -> list[tuple[str, str, bool, float, float]]:
    out: list[tuple[str, str, bool, float, float]] = []
    for row in rows:
        out.append((
            str(row.get("id") or ""),
            str(row.get("text") or ""),
            bool(row.get("is_gap")),
            round(float(row.get("start", 0.0) or 0.0), 6),
            round(float(row.get("end", 0.0) or 0.0), 6),
        ))
    return out


def _unchanged(project: dict[str, Any], before_rows: list[dict[str, Any]]) -> bool:
    after_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    return _row_signature(after_rows) == _row_signature(before_rows) and NLE_PROJECT_STATE_RUNTIME_KEY not in project


def _check(name: str, passed: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": dict(detail or {})}


def _move_overlap_reject_check() -> dict[str, Any]:
    project = _three_caption_project()
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    error = ""
    try:
        apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=0.5,
            new_end=1.5,
            commit_boundary="release",
            commit_source="neighbor_collision_audit",
        )
    except NLEOperationValidationError as exc:
        error = str(exc)
    return _check(
        "caption_move_overlap_rejected_without_mutation",
        bool(error) and _unchanged(project, before_rows),
        {"error": error, "runtime_state_created": NLE_PROJECT_STATE_RUNTIME_KEY in project},
    )


def _move_commit_overlap_reject_check() -> dict[str, Any]:
    project = _three_caption_project()
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    committed_rows = [
        {"line": 0, "start": 0.0, "end": 1.25, "text": "first", "speaker": "00"},
        {"line": 1, "start": 1.0, "end": 2.0, "text": "second", "speaker": "01"},
        {"line": 2, "start": 2.0, "end": 3.0, "text": "third", "speaker": "02"},
    ]
    error = ""
    try:
        apply_caption_move_commit_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            committed_rows=committed_rows,
            committed_caption_line=1,
            commit_boundary="release",
            commit_source="neighbor_collision_audit",
            commit_mode="center_invalid_overlap",
        )
    except NLEOperationValidationError as exc:
        error = str(exc)
    return _check(
        "caption_move_commit_overlap_rejected_without_mutation",
        bool(error) and _unchanged(project, before_rows),
        {"error": error, "runtime_state_created": NLE_PROJECT_STATE_RUNTIME_KEY in project},
    )


def _resize_split_required_reject_check() -> dict[str, Any]:
    project = _three_caption_project()
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    error = ""
    try:
        apply_caption_resize_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0002",
            new_start=0.25,
            new_end=0.75,
            edge="square_left",
            commit_boundary="release",
            commit_source="neighbor_collision_audit",
        )
    except ValueError as exc:
        error = str(exc)
    return _check(
        "caption_resize_split_required_neighbor_collision_rejected_without_mutation",
        error == "nle_caption_resize_split_required" and _unchanged(project, before_rows),
        {"error": error, "runtime_state_created": NLE_PROJECT_STATE_RUNTIME_KEY in project},
    )


def _resize_trim_neighbor_check() -> dict[str, Any]:
    project = _three_caption_project()
    result = apply_caption_resize_dual_write_pilot(
        project,
        caption_id="subtitle_vector_0002",
        new_start=0.5,
        new_end=2.0,
        edge="square_left",
        commit_boundary="release",
        commit_source="neighbor_collision_audit",
    )
    rows = project_segments_to_editor(project, include_analysis_candidates=False)
    return _check(
        "caption_resize_partial_neighbor_collision_trims_to_shared_boundary",
        result.after_projection.overlap_count == 0
        and result.after_projection.max_active_segments <= 1
        and result.operation.metadata.get("trimmed_neighbor_count") == 1
        and _row_signature(rows) == [
            ("subtitle_vector_0001", "first", False, 0.0, 0.5),
            ("subtitle_vector_0002", "second", False, 0.5, 2.0),
            ("subtitle_vector_0003", "third", False, 2.0, 3.0),
        ],
        {
            "trimmed_neighbor_count": result.operation.metadata.get("trimmed_neighbor_count"),
            "overlap_count": result.after_projection.overlap_count,
            "max_active_segments": result.after_projection.max_active_segments,
        },
    )


def _static_checks() -> list[dict[str, Any]]:
    source = (ROOT / "core/project/nle_dual_write.py").read_text(encoding="utf-8")
    return [
        _check(
            "resize_split_required_guard_present",
            "nle_caption_resize_split_required" in source
            and "def _resolve_rows_around_updated_final_ranges(" in source,
        ),
        _check(
            "move_commit_routes_through_operation_validation",
            "def apply_caption_move_commit_dual_write_pilot(" in source
            and "build_nle_editor_operation(" in source,
        ),
    ]


def build_nle_neighbor_collision_report() -> dict[str, Any]:
    checks = [
        *_static_checks(),
        _move_overlap_reject_check(),
        _move_commit_overlap_reject_check(),
        _resize_split_required_reject_check(),
        _resize_trim_neighbor_check(),
    ]
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": all(item["passed"] for item in checks),
        "runtime_change_applied": False,
        "ui_change_applied": False,
        "persisted_nle_fields_changed": False,
        "stt_or_cache_default_changed": False,
        "checks": checks,
        "blocked_scope": list(BLOCKED_SCOPE),
        "acceptance_gate": {
            "final_invalid_duration_count": 0,
            "final_non_monotonic_count": 0,
            "final_overlap_count": 0,
            "global_canvas_max_active_segments": 1,
            "rejected_collision_must_not_mutate_project": True,
            "nas_heydealer_required_for_release_regression": False,
        },
    }


def write_nle_neighbor_collision_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_neighbor_collision_guard.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Neighbor Collision Guard Audit",
        "",
        f"Schema: `{report['schema']}`",
        f"Ready: `{report['ready']}`",
        f"Runtime change applied: `{report['runtime_change_applied']}`",
        f"UI change applied: `{report['ui_change_applied']}`",
        f"Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"STT/cache default changed: `{report['stt_or_cache_default_changed']}`",
        "",
        "## Checks",
        "",
        "| check | passed |",
        "| --- | --- |",
    ]
    for item in report["checks"]:
        lines.append(f"| {item['name']} | {item['passed']} |")
    lines.extend([
        "",
        "## Acceptance Gate",
        "",
        f"- Final invalid duration count: `{report['acceptance_gate']['final_invalid_duration_count']}`",
        f"- Final non-monotonic count: `{report['acceptance_gate']['final_non_monotonic_count']}`",
        f"- Final overlap count: `{report['acceptance_gate']['final_overlap_count']}`",
        f"- Global canvas max active segments: `{report['acceptance_gate']['global_canvas_max_active_segments']}`",
        f"- Rejected collision must not mutate project: `{report['acceptance_gate']['rejected_collision_must_not_mutate_project']}`",
        f"- NAS HeyDealer release regression required: `{report['acceptance_gate']['nas_heydealer_required_for_release_regression']}`",
        "",
        "## Blocked Scope",
        "",
        *[f"- `{item}`" for item in report["blocked_scope"]],
    ])
    (output_dir / "nle_neighbor_collision_guard.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_neighbor_collision_guard_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_neighbor_collision_report()
    write_nle_neighbor_collision_report(output_dir, report)
    print(json.dumps({
        "ready": report["ready"],
        "check_count": len(report["checks"]),
        "output_dir": str(output_dir),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
