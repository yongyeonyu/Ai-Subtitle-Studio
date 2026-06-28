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
    apply_caption_merge_dual_write_pilot,
    apply_caption_move_dual_write_pilot,
    apply_caption_split_dual_write_pilot,
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


SCHEMA = "ai_subtitle_studio.nle_projection_metadata_preservation.v1"
AUDIT_ID = "nle_projection_metadata_preservation_20260628"
BLOCKED_SCOPE = (
    "persisted_nle_project_fields_not_approved",
    "per_pixel_drag_nle_writes_not_allowed",
    "ui_layout_or_label_changes_not_allowed",
    "stt_or_cache_default_policy_not_changed",
    "app_store_packaging_not_in_scope",
    "custom_legacy_schema_expansion_not_in_scope",
)


def _project_with_nested_caption_metadata() -> dict[str, Any]:
    return {
        "project_name": "nle_projection_metadata_preservation",
        "mode": "single",
        "video": {"duration_sec": 8.0, "primary_fps": 30.0},
        "editor_state": build_editor_state(
            mode="single",
            media_files=[],
            segments=[
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "first",
                    "speaker": "00",
                    "speaker_list": ["00", "host"],
                    "words": [{"word": "first", "start": 0.1, "end": 0.7, "score": 0.91}],
                    "quality": {"confidence_label": "high", "components": {"text": 0.93, "timing": 0.88}},
                    "quality_history": [{"stage": "initial", "score": 0.91}],
                    "quality_candidates": [{"source": "llm", "score": 0.92}],
                    "stt_candidates": [
                        {"source": "STT1", "start": 0.0, "end": 1.0, "text": "first raw", "score": 0.8}
                    ],
                },
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "second",
                    "speaker": "01",
                    "speaker_list": ["01", "guest"],
                    "words": [{"word": "second", "start": 1.1, "end": 1.7, "score": 0.89}],
                    "quality": {"confidence_label": "medium", "components": {"text": 0.83, "timing": 0.79}},
                    "quality_history": [{"stage": "initial", "score": 0.81}],
                    "quality_candidates": [{"source": "stt2", "score": 0.84}],
                },
                {
                    "start": 2.0,
                    "end": 3.0,
                    "text": "third",
                    "speaker": "02",
                    "speaker_list": ["02"],
                    "words": [{"word": "third", "start": 2.1, "end": 2.7, "score": 0.9}],
                    "quality": {"confidence_label": "high", "components": {"text": 0.95, "timing": 0.9}},
                },
            ],
            primary_fps=30.0,
        ),
    }


def _row_by_id(rows: list[dict[str, Any]] | tuple[dict[str, Any], ...], row_id: str) -> dict[str, Any]:
    for row in rows:
        if isinstance(row, dict) and row.get("id") == row_id:
            return row
    return {}


def _raw_vector_segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (
        ((project.get("editor_state", {}) or {}).get("rendering", {}) or {})
        .get("subtitle_canvas", {})
        .get("segments", [])
    )
    return [dict(row) for row in rows or [] if isinstance(row, dict)]


def _raw_vector_by_id(project: dict[str, Any], row_id: str) -> dict[str, Any]:
    return _row_by_id(_raw_vector_segments(project), row_id)


def _function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.find(marker)
    if start < 0:
        return ""
    next_def = source.find("\ndef ", start + len(marker))
    return source[start:] if next_def < 0 else source[start:next_def]


def _static_deepcopy_check() -> dict[str, Any]:
    dual_write_source = (ROOT / "core/project/nle_dual_write.py").read_text(encoding="utf-8")
    operations_source = (ROOT / "core/project/nle_operations.py").read_text(encoding="utf-8")
    retime_body = _function_body(dual_write_source, "_retime_row")
    manual_body = _function_body(dual_write_source, "_manual_caption_edit_row")
    sort_body = _function_body(dual_write_source, "_sorted_editor_rows")
    shadow_body = _function_body(dual_write_source, "_shadow_project_with_rows")
    operation_to_dict_body = _function_body(operations_source, "to_dict")
    passed = (
        "deepcopy(row)" in retime_body
        and "deepcopy(row)" in manual_body
        and "deepcopy(row)" in sort_body
        and "segments=[deepcopy(row) for row in rows]" in shadow_body
        and "deepcopy(row)" in operation_to_dict_body
    )
    return {
        "case": "static_projection_deepcopy_contract",
        "passed": passed,
        "retime_uses_deepcopy": "deepcopy(row)" in retime_body,
        "manual_edit_uses_deepcopy": "deepcopy(row)" in manual_body,
        "sort_uses_deepcopy": "deepcopy(row)" in sort_body,
        "shadow_uses_deepcopy": "segments=[deepcopy(row) for row in rows]" in shadow_body,
        "operation_to_dict_uses_deepcopy": "deepcopy(row)" in operation_to_dict_body,
    }


def _projection_gate(result: Any) -> bool:
    return (
        result.after_projection.diff_summary == "ok"
        and result.after_projection.invalid_duration_count == 0
        and result.after_projection.non_monotonic_count == 0
        and result.after_projection.overlap_count == 0
        and result.after_projection.max_active_segments <= 1
        and result.after_projection.save_reload_stable
        and result.after_projection.global_canvas_stable
    )


def _move_metadata_check() -> dict[str, Any]:
    project = _project_with_nested_caption_metadata()
    result = apply_caption_move_dual_write_pilot(
        project,
        caption_id="subtitle_vector_0001",
        new_start=3.0,
        new_end=4.0,
        commit_boundary="release",
        commit_source="metadata_preservation_move",
    )
    legacy_row = _row_by_id(project_segments_to_editor(project, include_analysis_candidates=False), "subtitle_vector_0001")
    nle_row = _row_by_id(project_segments_from_nle_state(project), "subtitle_vector_0001")
    raw_row = _raw_vector_by_id(project, "subtitle_vector_0001")
    payload = result.to_dict()
    payload["projected_rows"][2]["quality"]["components"]["text"] = -1.0
    fresh_row = _row_by_id(project_segments_from_nle_state(project), "subtitle_vector_0001")
    passed = (
        _projection_gate(result)
        and legacy_row.get("quality", {}).get("components", {}).get("text") == 0.93
        and nle_row.get("quality", {}).get("components", {}).get("timing") == 0.88
        and raw_row.get("meta", {}).get("quality", {}).get("confidence_label") == "high"
        and legacy_row.get("quality_history") == [{"stage": "initial", "score": 0.91}]
        and nle_row.get("quality_candidates") == [{"source": "llm", "score": 0.92}]
        and (legacy_row.get("stt_candidates") or [{}])[0].get("source") == "STT1"
        and fresh_row.get("quality", {}).get("components", {}).get("text") == 0.93
    )
    return {
        "case": "dynamic_caption_move_metadata_preserved",
        "passed": passed,
        "operation_kind": result.operation.kind,
        "legacy_quality_label": legacy_row.get("quality", {}).get("confidence_label"),
        "nle_quality_timing": nle_row.get("quality", {}).get("components", {}).get("timing"),
        "raw_quality_label": raw_row.get("meta", {}).get("quality", {}).get("confidence_label"),
        "fresh_quality_after_payload_mutation": fresh_row.get("quality", {}).get("components", {}).get("text"),
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def _merge_metadata_check() -> dict[str, Any]:
    project = _project_with_nested_caption_metadata()
    result = apply_caption_merge_dual_write_pilot(
        project,
        left_caption_id="subtitle_vector_0001",
        right_caption_id="subtitle_vector_0002",
        merged_text="first second",
        commit_boundary="release",
        commit_source="metadata_preservation_merge",
    )
    legacy_row = _row_by_id(project_segments_to_editor(project, include_analysis_candidates=False), "subtitle_vector_0001")
    nle_row = _row_by_id(project_segments_from_nle_state(project), "subtitle_vector_0001")
    raw_row = _raw_vector_by_id(project, "subtitle_vector_0001")
    passed = (
        _projection_gate(result)
        and legacy_row.get("speaker_list") == ["00", "host"]
        and nle_row.get("words") == [{"word": "first", "start": 0.1, "end": 0.7, "score": 0.91}]
        and raw_row.get("meta", {}).get("quality", {}).get("components", {}).get("text") == 0.93
        and legacy_row.get("quality_history") == [{"stage": "initial", "score": 0.91}]
        and nle_row.get("merged_caption_ids") == ["subtitle_vector_0001", "subtitle_vector_0002"]
    )
    return {
        "case": "dynamic_caption_merge_metadata_preserved",
        "passed": passed,
        "operation_kind": result.operation.kind,
        "speaker_list": legacy_row.get("speaker_list"),
        "merged_caption_ids": nle_row.get("merged_caption_ids"),
        "legacy_quality_history_count": len(legacy_row.get("quality_history") or []),
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def _split_metadata_check() -> dict[str, Any]:
    project = _project_with_nested_caption_metadata()
    result = apply_caption_split_dual_write_pilot(
        project,
        caption_id="subtitle_vector_0002",
        split_sec=1.4,
        left_text="sec",
        right_text="ond",
        commit_boundary="release",
        commit_source="metadata_preservation_split",
    )
    legacy_rows = project_segments_to_editor(project, include_analysis_candidates=False)
    nle_rows = project_segments_from_nle_state(project)
    left_legacy = _row_by_id(legacy_rows, "subtitle_vector_0002")
    right_legacy = _row_by_id(legacy_rows, "subtitle_vector_0002_split_right")
    left_nle = _row_by_id(nle_rows, "subtitle_vector_0002")
    right_nle = _row_by_id(nle_rows, "subtitle_vector_0002_split_right")
    expected_words = [{"word": "second", "start": 1.1, "end": 1.7, "score": 0.89}]
    passed = (
        _projection_gate(result)
        and left_legacy.get("speaker_list") == ["01", "guest"]
        and right_legacy.get("speaker_list") == ["01", "guest"]
        and left_nle.get("words") == expected_words
        and right_nle.get("words") == expected_words
        and "quality" not in left_legacy
        and "quality" not in right_legacy
    )
    return {
        "case": "dynamic_caption_split_metadata_preserved",
        "passed": passed,
        "operation_kind": result.operation.kind,
        "left_speaker_list": left_legacy.get("speaker_list"),
        "right_speaker_list": right_legacy.get("speaker_list"),
        "left_quality_removed_by_manual_policy": "quality" not in left_legacy,
        "right_quality_removed_by_manual_policy": "quality" not in right_legacy,
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def _storage_clean_check() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        project_path = Path(tmp) / "nle-projection-metadata.aissproj"
        project = _project_with_nested_caption_metadata()
        result = apply_caption_move_dual_write_pilot(
            project,
            caption_id="subtitle_vector_0001",
            new_start=3.0,
            new_end=4.0,
            commit_boundary="release",
            commit_source="metadata_preservation_storage",
            project_path=str(project_path),
        )
        write_project_file(str(project_path), copy.deepcopy(project))
        storage = read_project_storage_payload(str(project_path))
        clear_project_file_cache(str(project_path))
        reopened = read_project_file(str(project_path))
        reopened_row = _row_by_id(project_segments_to_editor(reopened, include_analysis_candidates=False), "subtitle_vector_0001")
    passed = (
        _projection_gate(result)
        and NLE_PROJECT_STATE_RUNTIME_KEY not in storage
        and "nle" not in storage
        and "nle_snapshot" not in storage
        and reopened_row.get("quality", {}).get("components", {}).get("text") == 0.93
        and reopened_row.get("quality_history") == [{"stage": "initial", "score": 0.91}]
    )
    return {
        "case": "storage_projection_metadata_runtime_fields_clean",
        "passed": passed,
        "storage_has_runtime_nle_state": NLE_PROJECT_STATE_RUNTIME_KEY in storage,
        "storage_has_nle": "nle" in storage,
        "storage_has_nle_snapshot": "nle_snapshot" in storage,
        "reopened_quality_label": reopened_row.get("quality", {}).get("confidence_label"),
        "reopened_quality_history_count": len(reopened_row.get("quality_history") or []),
        "overlap_count": result.after_projection.overlap_count,
        "max_active_segments": result.after_projection.max_active_segments,
    }


def build_nle_projection_metadata_preservation_report() -> dict[str, Any]:
    checks = [
        _static_deepcopy_check(),
        _move_metadata_check(),
        _merge_metadata_check(),
        _split_metadata_check(),
        _storage_clean_check(),
    ]
    ready = all(row["passed"] for row in checks)
    return {
        "schema": SCHEMA,
        "audit_id": AUDIT_ID,
        "ready": ready,
        "runtime_change_applied": True,
        "ui_change_applied": False,
        "persisted_nle_fields_changed": False,
        "stt_or_cache_default_changed": False,
        "checks": checks,
        "blocked_scope": list(BLOCKED_SCOPE),
        "acceptance_gate": {
            "caption_move_metadata_preserved": True,
            "caption_merge_kept_row_metadata_preserved": True,
            "caption_split_child_metadata_preserved": True,
            "runtime_nle_projection_deepcopy_required": True,
            "legacy_editor_storage_clean": True,
            "final_invalid_duration_count": 0,
            "final_non_monotonic_count": 0,
            "final_overlap_count": 0,
            "global_canvas_max_active_segments": 1,
            "nas_heydealer_required_for_release_regression": True,
        },
    }


def write_nle_projection_metadata_preservation_report(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_projection_metadata_preservation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# NLE Projection Metadata Preservation Audit",
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
        "| case | passed | overlap | max active |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in report["checks"]:
        lines.append(
            "| {case} | {passed} | {overlap} | {max_active} |".format(
                case=row["case"],
                passed=row["passed"],
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
        f"- Caption move metadata preserved: `{report['acceptance_gate']['caption_move_metadata_preserved']}`",
        f"- Caption merge kept-row metadata preserved: `{report['acceptance_gate']['caption_merge_kept_row_metadata_preserved']}`",
        f"- Caption split child metadata preserved: `{report['acceptance_gate']['caption_split_child_metadata_preserved']}`",
        f"- Runtime NLE projection deepcopy required: `{report['acceptance_gate']['runtime_nle_projection_deepcopy_required']}`",
        f"- Legacy editor storage clean: `{report['acceptance_gate']['legacy_editor_storage_clean']}`",
        f"- Final invalid/non-monotonic/overlap: `{report['acceptance_gate']['final_invalid_duration_count']}/{report['acceptance_gate']['final_non_monotonic_count']}/{report['acceptance_gate']['final_overlap_count']}`",
        f"- Global canvas max-active gate: `{report['acceptance_gate']['global_canvas_max_active_segments']}`",
        f"- NAS HeyDealer release regression required: `{report['acceptance_gate']['nas_heydealer_required_for_release_regression']}`",
    ])
    (output_dir / "nle_projection_metadata_preservation.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="output/manual_verification/latest/nle_projection_metadata_preservation_20260628",
    )
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    report = build_nle_projection_metadata_preservation_report()
    write_nle_projection_metadata_preservation_report(output_dir, report)
    print(json.dumps({
        "ready": report["ready"],
        "audit_id": report["audit_id"],
        "output_dir": str(output_dir),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
