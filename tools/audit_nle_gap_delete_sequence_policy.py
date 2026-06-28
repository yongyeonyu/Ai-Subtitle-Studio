#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.project.nle_dual_write import (
    GAP_DELETE_SEQUENCE_POLICY,
    apply_gap_delete_dual_write_pilot,
)
from core.project.nle_project_state import (
    NLE_PROJECT_STATE_RUNTIME_KEY,
    project_segments_from_nle_state,
)
from core.project.project_context import build_editor_state, project_segments_to_editor
from core.project.project_io import (
    clear_project_file_cache,
    read_project_file,
    read_project_storage_payload,
    write_project_file,
)


SCHEMA = "ai_subtitle_studio.nle_gap_delete_sequence_policy.v1"
BLOCKED_SCOPE = (
    "gap_delete_ripple_timeline_shift_not_allowed_without_owner_approval",
    "ui_layout_or_label_changes_not_allowed",
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "stt_or_cache_default_policy_not_changed",
    "app_store_packaging_not_in_scope",
)


def _project_with_gap() -> dict[str, Any]:
    return {
        "project_name": "nle_gap_delete_sequence_policy",
        "mode": "single",
        "video": {"duration_sec": 6.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {
                    "id": "caption_1",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                    "stt_candidates": [
                        {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.8}
                    ],
                },
                {"id": "gap_1", "start": 1.0, "end": 2.0, "text": "", "is_gap": True},
                {
                    "id": "caption_2",
                    "start": 2.0,
                    "end": 3.0,
                    "text": "second",
                    "speaker": "01",
                    "stt_candidates": [
                        {"source": "STT2", "start": 2.0, "end": 3.0, "text": "second raw", "score": 0.7}
                    ],
                },
            ],
            stt_preview_segments=[
                {"start": 4.0, "end": 5.0, "text": "diagnostic", "stt_preview_source": "STT1"}
            ],
            primary_fps=30.0,
        ),
    }


def _raw_vector_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (
        ((project.get("editor_state", {}) or {}).get("rendering", {}) or {})
        .get("subtitle_canvas", {})
        .get("segments", [])
    )
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _caption_bounds(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, tuple[float, float, int, int]]:
    bounds: dict[str, tuple[float, float, int, int]] = {}
    for row in rows or []:
        if not isinstance(row, dict) or bool(row.get("is_gap")):
            continue
        text = str(row.get("text") or "")
        if not text:
            continue
        bounds[text] = (
            float(row.get("start", 0.0) or 0.0),
            float(row.get("end", 0.0) or 0.0),
            int(row.get("start_frame", 0) or 0),
            int(row.get("end_frame", 0) or 0),
        )
    return bounds


def _raw_caption_bounds(rows: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    bounds: dict[str, tuple[int, int]] = {}
    for row in rows:
        text = str(row.get("text") or "")
        time = row.get("time") if isinstance(row.get("time"), dict) else {}
        if text:
            bounds[text] = (
                int(time.get("start_frame", 0) or 0),
                int(time.get("end_frame", 0) or 0),
            )
    return bounds


def _function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.find(marker)
    if start < 0:
        return ""
    next_def = source.find("\ndef ", start + len(marker))
    return source[start:] if next_def < 0 else source[start:next_def]


def _static_policy_check() -> dict[str, Any]:
    source = (ROOT / "core/project/nle_dual_write.py").read_text(encoding="utf-8")
    body = _function_body(source, "apply_gap_delete_dual_write_pilot")
    return {
        "case": "static_gap_delete_policy_contract",
        "passed": bool(
            f'GAP_DELETE_SEQUENCE_POLICY = "{GAP_DELETE_SEQUENCE_POLICY}"' in source
            and "GAP_DELETE_SEQUENCE_POLICY" in body
            and "gap_delete_sequence_policy" in body
            and "gap_delete_ripple_applied" in body
            and "dual_write_gap_delete_sequence_policy" in body
        ),
        "function_found": bool(body),
        "policy": GAP_DELETE_SEQUENCE_POLICY,
        "policy_referenced": "GAP_DELETE_SEQUENCE_POLICY" in body,
        "operation_metadata_recorded": "gap_delete_sequence_policy" in body,
        "ripple_flag_recorded": "gap_delete_ripple_applied" in body,
        "state_metadata_recorded": "dual_write_gap_delete_sequence_policy" in body,
    }


def _dynamic_no_ripple_check() -> dict[str, Any]:
    project = _project_with_gap()
    before_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    before_bounds = _caption_bounds(before_rows)
    result = apply_gap_delete_dual_write_pilot(
        project,
        gap_id="gap_1",
        commit_boundary="release",
        commit_source="gap_delete_sequence_policy",
    )
    legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    nle_rows = project_segments_from_nle_state(project)
    raw_rows = _raw_vector_segments(project)
    state_metadata = dict(project[NLE_PROJECT_STATE_RUNTIME_KEY].metadata or {})
    operation_metadata = dict(result.operation.metadata or {})
    undo_metadata = dict(result.operation.undo_snapshot.metadata or {})
    legacy_bounds = _caption_bounds(legacy_rows)
    nle_bounds = _caption_bounds(nle_rows)
    raw_bounds = _raw_caption_bounds(raw_rows)
    raw_expected = {
        key: (value[2], value[3])
        for key, value in before_bounds.items()
    }
    passed = (
        result.operation.kind == "gap_delete"
        and result.before_projection.gap_count == 1
        and result.after_projection.gap_count == 0
        and result.after_projection.invalid_duration_count == 0
        and result.after_projection.non_monotonic_count == 0
        and result.after_projection.overlap_count == 0
        and result.after_projection.max_active_segments <= 1
        and before_bounds == legacy_bounds == nle_bounds
        and raw_bounds == raw_expected
        and not any(row.get("is_gap") for row in legacy_rows)
        and operation_metadata.get("gap_delete_sequence_policy") == GAP_DELETE_SEQUENCE_POLICY
        and operation_metadata.get("gap_delete_ripple_applied") is False
        and state_metadata.get("dual_write_gap_delete_sequence_policy") == GAP_DELETE_SEQUENCE_POLICY
        and state_metadata.get("dual_write_gap_delete_ripple_applied") is False
        and result.operation.undo_snapshot.ui_state_ref.get("sequence_policy") == GAP_DELETE_SEQUENCE_POLICY
        and undo_metadata.get("gap_delete_sequence_policy") == GAP_DELETE_SEQUENCE_POLICY
        and len(result.operation.undo_snapshot.silence_gaps) == 1
    )
    return {
        "case": "dynamic_gap_delete_no_ripple",
        "passed": passed,
        "policy": GAP_DELETE_SEQUENCE_POLICY,
        "before_caption_bounds": before_bounds,
        "legacy_caption_bounds": legacy_bounds,
        "nle_caption_bounds": nle_bounds,
        "raw_caption_bounds": raw_bounds,
        "legacy_gap_count": sum(1 for row in legacy_rows if row.get("is_gap")),
        "operation_policy": operation_metadata.get("gap_delete_sequence_policy"),
        "operation_ripple_applied": operation_metadata.get("gap_delete_ripple_applied"),
        "state_policy": state_metadata.get("dual_write_gap_delete_sequence_policy"),
        "state_ripple_applied": state_metadata.get("dual_write_gap_delete_ripple_applied"),
        "undo_policy": undo_metadata.get("gap_delete_sequence_policy"),
        "undo_silence_gap_count": len(result.operation.undo_snapshot.silence_gaps),
        "invalid_duration_count": result.after_projection.invalid_duration_count,
        "non_monotonic_count": result.after_projection.non_monotonic_count,
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def _storage_clean_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "gap-delete-sequence-policy.aissproj"
        project = _project_with_gap()
        result = apply_gap_delete_dual_write_pilot(project, gap_id="gap_1", project_path=str(project_path))
        write_project_file(str(project_path), copy.deepcopy(project))
        storage = read_project_storage_payload(str(project_path))
        clear_project_file_cache(str(project_path))
        reopened = read_project_file(str(project_path))
        reopened_rows = project_segments_to_editor(reopened, include_analysis_candidates=False)
    passed = (
        result.after_projection.diff_summary == "ok"
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        and "nle" not in storage
        and "nle_snapshot" not in storage
        and not any(row.get("is_gap") for row in reopened_rows)
        and _caption_bounds(reopened_rows) == {
            "first": (0.0, 1.0, 0, 30),
            "second": (2.0, 3.0, 60, 90),
        }
    )
    return {
        "case": "storage_gap_delete_runtime_fields_clean",
        "passed": passed,
        "storage_has_runtime_nle_state": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "reopened_caption_bounds": _caption_bounds(reopened_rows),
        "reopened_gap_count": sum(1 for row in reopened_rows if row.get("is_gap")),
        "diff_summary": result.after_projection.diff_summary,
    }


def build_nle_gap_delete_sequence_policy_report() -> dict[str, Any]:
    static_check = _static_policy_check()
    dynamic_checks = [_dynamic_no_ripple_check(), _storage_clean_check()]
    checks = [static_check, *dynamic_checks]
    ready = all(row["passed"] for row in checks)
    return {
        "schema": SCHEMA,
        "audit_id": "nle_gap_delete_sequence_policy_20260628",
        "ready": ready,
        "runtime_change_applied": True,
        "ui_change_applied": False,
        "persisted_nle_fields_changed": False,
        "stt_or_cache_default_changed": False,
        "sequence_policy": GAP_DELETE_SEQUENCE_POLICY,
        "ripple_delete_allowed": False,
        "checks": checks,
        "blocked_scope": list(BLOCKED_SCOPE),
        "acceptance_gate": {
            "caption_bounds_preserved_across_gap_delete": True,
            "runtime_nle_state_policy_metadata_required": True,
            "legacy_editor_storage_clean": True,
            "final_invalid_duration_count": 0,
            "final_non_monotonic_count": 0,
            "final_overlap_count": 0,
            "global_canvas_max_active_segments": 1,
            "nas_heydealer_required_for_release_regression": True,
        },
    }


def write_nle_gap_delete_sequence_policy_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_gap_delete_sequence_policy.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Gap Delete Sequence Policy Audit",
        "",
        f"Schema: `{report['schema']}`",
        f"Ready: `{report['ready']}`",
        f"Runtime change applied: `{report['runtime_change_applied']}`",
        f"UI change applied: `{report['ui_change_applied']}`",
        f"Persisted NLE fields changed: `{report['persisted_nle_fields_changed']}`",
        f"STT/cache default changed: `{report['stt_or_cache_default_changed']}`",
        f"Sequence policy: `{report['sequence_policy']}`",
        f"Ripple delete allowed: `{report['ripple_delete_allowed']}`",
        "",
        "## Checks",
        "",
        "| case | passed | policy | overlap | max active |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for row in report["checks"]:
        lines.append(
            "| {case} | {passed} | {policy} | {overlap} | {max_active} |".format(
                case=row["case"],
                passed=row["passed"],
                policy=row.get("policy", report["sequence_policy"]),
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
        f"- Caption bounds preserved across gap delete: `{report['acceptance_gate']['caption_bounds_preserved_across_gap_delete']}`",
        f"- Runtime NLE state policy metadata required: `{report['acceptance_gate']['runtime_nle_state_policy_metadata_required']}`",
        f"- Legacy editor storage clean: `{report['acceptance_gate']['legacy_editor_storage_clean']}`",
        f"- Final invalid/non-monotonic/overlap: `{report['acceptance_gate']['final_invalid_duration_count']}/{report['acceptance_gate']['final_non_monotonic_count']}/{report['acceptance_gate']['final_overlap_count']}`",
        f"- Global canvas max-active gate: `{report['acceptance_gate']['global_canvas_max_active_segments']}`",
        f"- NAS HeyDealer release regression required: `{report['acceptance_gate']['nas_heydealer_required_for_release_regression']}`",
    ])
    (output_dir / "nle_gap_delete_sequence_policy.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_gap_delete_sequence_policy_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_gap_delete_sequence_policy_report()
    write_nle_gap_delete_sequence_policy_report(output_dir, report)
    print(json.dumps({
        "ready": report["ready"],
        "sequence_policy": report["sequence_policy"],
        "output_dir": str(output_dir),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
