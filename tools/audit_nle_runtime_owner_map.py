#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "ai_subtitle_studio.nle_runtime_owner_map.v1"

OWNER_EVIDENCE: tuple[dict[str, Any], ...] = (
    {
        "owner_id": "gap_delete",
        "operation_family": "gap_delete",
        "commit_boundary": "release",
        "source_surface": "live_editor_gap",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_gap_delete_dual_write_pilot"],
            "tests/test_project_nle_dual_write.py": [
                "test_gap_delete_dual_write_routes_through_nle_state_and_projects_legacy_rows"
            ],
        },
    },
    {
        "owner_id": "gap_generate",
        "operation_family": "gap_generate",
        "commit_boundary": "release",
        "source_surface": "live_editor_gap",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_gap_generate_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_gap_generate_routes_live_editor_mutation_through_nle_dual_write"
            ],
        },
    },
    {
        "owner_id": "caption_move_center",
        "operation_family": "caption_move",
        "commit_boundary": "release",
        "source_surface": "timeline_body_drag",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_move_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_center_drag_free_space_routes_through_nle_caption_move"
            ],
        },
    },
    {
        "owner_id": "caption_move_gap_absorb",
        "operation_family": "caption_move",
        "commit_boundary": "release",
        "source_surface": "timeline_body_drag",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_move_commit_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_center_drag_over_single_gap_absorbs_gap_without_final_overlap"
            ],
        },
    },
    {
        "owner_id": "caption_move_overwrite_trim",
        "operation_family": "caption_move",
        "commit_boundary": "release",
        "source_surface": "timeline_body_drag",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_center_drag_right_preserves_duration_and_trims_overwritten_next_subtitle",
                "test_center_drag_left_preserves_duration_and_trims_overwritten_previous_subtitle",
            ],
        },
    },
    {
        "owner_id": "caption_move_neighbor_reorder",
        "operation_family": "caption_move",
        "commit_boundary": "release",
        "source_surface": "timeline_body_drag",
        "evidence": {
            "tests/test_project_nle_dual_write.py": [
                "test_caption_move_dual_write_supports_taption_neighbor_reorder_contract",
                "test_caption_move_dual_write_supports_taption_left_neighbor_reorder_contract",
            ],
            "tests/test_timeline_playhead_fit.py": [
                "test_center_reorder_left_commit_routes_through_nle_caption_move"
            ],
        },
    },
    {
        "owner_id": "caption_move_diamond_delete",
        "operation_family": "caption_move",
        "commit_boundary": "release",
        "source_surface": "timeline_diamond_delete",
        "evidence": {
            "tests/test_project_nle_dual_write.py": [
                "test_caption_move_commit_dual_write_adopts_diamond_delete_keep_left_plan"
            ],
            "tests/test_timeline_playhead_fit.py": [
                "test_diamond_delete_routes_keep_left_through_nle_move_commit",
                "test_diamond_delete_routes_keep_right_through_nle_move_commit",
            ],
        },
    },
    {
        "owner_id": "caption_resize_square_handles",
        "operation_family": "caption_resize",
        "commit_boundary": "release",
        "source_surface": "live_editor_boundary_handle",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_resize_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_square_left_resize_routes_live_editor_mutation_through_nle_dual_write",
                "test_square_right_resize_routes_live_editor_mutation_through_nle_dual_write",
            ],
        },
    },
    {
        "owner_id": "caption_resize_diamond",
        "operation_family": "caption_resize",
        "commit_boundary": "release",
        "source_surface": "live_editor_diamond",
        "evidence": {
            "tests/test_project_nle_dual_write.py": [
                "test_caption_resize_dual_write_diamond_updates_shared_boundary_atomically"
            ],
            "tests/test_timeline_playhead_fit.py": [
                "test_diamond_resize_routes_live_editor_mutation_through_nle_dual_write"
            ],
        },
    },
    {
        "owner_id": "caption_resize_shortcut_playhead",
        "operation_family": "caption_resize",
        "commit_boundary": "release",
        "source_surface": "shortcut_playhead",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_segment_start_shortcut_routes_gap_absorb_through_nle_resize",
                "test_segment_end_shortcut_routes_gap_absorb_through_nle_resize",
            ],
        },
    },
    {
        "owner_id": "caption_text_inline",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "timeline_inline_text",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_text_edit_dual_write_pilot"],
            "tests/test_project_nle_dual_write.py": [
                "test_caption_text_edit_dual_write_updates_text_without_timing_drift"
            ],
        },
    },
    {
        "owner_id": "caption_text_popup_replace_all",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "popup_replace_all",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_replace_text_in_all_subtitles_routes_through_nle_caption_text_edit"
            ],
        },
    },
    {
        "owner_id": "caption_text_quality_candidate",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "quality_review",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_quality_candidate_text_commit_routes_through_nle_caption_text_edit"
            ],
        },
    },
    {
        "owner_id": "caption_text_speaker_split",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "speaker_edit",
        "evidence": {
            "tests/test_project_nle_dual_write.py": [
                "test_caption_text_edit_dual_write_preserves_speaker_split_metadata"
            ],
            "tests/test_timeline_playhead_fit.py": [
                "test_canvas_speaker_split_routes_stable_caption_through_nle_text_edit"
            ],
        },
    },
    {
        "owner_id": "caption_text_speaker_drop",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "speaker_edit",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_speaker_circle_drop_routes_same_caption_reorder_through_nle_text_edit"
            ],
        },
    },
    {
        "owner_id": "caption_text_speaker_change",
        "operation_family": "caption_text_edit",
        "commit_boundary": "release",
        "source_surface": "speaker_edit",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_change_speaker_for_line_routes_single_caption_through_nle_text_edit"
            ],
        },
    },
    {
        "owner_id": "caption_split_smart",
        "operation_family": "caption_split",
        "commit_boundary": "release",
        "source_surface": "timeline_split",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_split_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_smart_split_routes_release_commit_through_nle_caption_split"
            ],
        },
    },
    {
        "owner_id": "caption_split_shortcut",
        "operation_family": "caption_split",
        "commit_boundary": "release",
        "source_surface": "shortcut_split",
        "evidence": {
            "tests/test_timeline_playhead_fit.py": [
                "test_split_shortcut_routes_playhead_insert_through_nle_caption_split"
            ],
        },
    },
    {
        "owner_id": "caption_range_replace_partial_insert",
        "operation_family": "caption_range_replace",
        "commit_boundary": "release",
        "source_surface": "partial_insert",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_range_replace_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_partial_insert_routes_range_replace_through_nle_transaction"
            ],
        },
    },
    {
        "owner_id": "caption_merge_diamond",
        "operation_family": "caption_merge",
        "commit_boundary": "release",
        "source_surface": "timeline_diamond_merge",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_merge_dual_write_pilot"],
            "tests/test_project_nle_dual_write.py": [
                "test_caption_merge_dual_write_merges_adjacent_final_captions"
            ],
            "tests/test_timeline_playhead_fit.py": [
                "self.assertEqual(operation.get(\"kind\"), \"caption_merge\")",
                "self.assertEqual(operation.get(\"metadata\", {}).get(\"operation_family\"), \"caption_merge\")",
            ],
        },
    },
    {
        "owner_id": "caption_delete_live_editor",
        "operation_family": "caption_delete",
        "commit_boundary": "release",
        "source_surface": "live_editor_segment_delete",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_caption_delete_dual_write_pilot"],
            "tests/test_timeline_playhead_fit.py": [
                "test_segment_delete_routes_live_editor_mutation_through_nle_dual_write"
            ],
        },
    },
    {
        "owner_id": "candidate_confirm_stt_lane",
        "operation_family": "candidate_confirm",
        "commit_boundary": "release",
        "source_surface": "stt_candidate_confirm",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_candidate_confirm_dual_write_pilot"],
            "tests/test_project_nle_dual_write.py": [
                "test_candidate_confirm_dual_write_replaces_final_caption_and_preserves_candidate_lane"
            ],
        },
    },
    {
        "owner_id": "marker_edit_provisional_cut_boundary",
        "operation_family": "marker_edit",
        "commit_boundary": "release",
        "source_surface": "provisional_cut_boundary",
        "evidence": {
            "core/project/nle_dual_write.py": ["def apply_marker_edit_dual_write_pilot"],
            "tests/test_timeline_hit_targets.py": [
                "test_scan_boundary_create_records_nle_marker_edit_operation",
                "test_scan_boundary_delete_removes_requested_boundary_from_editor_state",
            ],
        },
    },
)

BLOCKED_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "persisted_nle_project_fields",
        "status": "blocked_owner_approval_required",
        "reason": "Disk-format cutover still requires explicit owner approval and compatibility proof.",
    },
    {
        "candidate_id": "per_pixel_drag_nle_writes",
        "status": "blocked_by_taption_contract",
        "reason": "Taption-style drag remains preview-only until release commit; NLE writes must stay at commit boundaries.",
    },
    {
        "candidate_id": "qml_or_gpu_timeline_surface_default",
        "status": "blocked_by_source_app_contract",
        "reason": "Qt Widgets 2D timeline surface remains the default; UI surface replacement is not approved.",
    },
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _evaluate_owner(owner: dict[str, Any], *, root: Path) -> dict[str, Any]:
    evidence = dict(owner.get("evidence") or {})
    missing: list[dict[str, str]] = []
    found_count = 0
    expected_count = 0
    for rel_path, patterns in evidence.items():
        text = _read_text(root / rel_path)
        for pattern in list(patterns or []):
            expected_count += 1
            if pattern in text:
                found_count += 1
            else:
                missing.append({"file": rel_path, "pattern": str(pattern)})
    status = "covered" if not missing and expected_count > 0 else "missing_evidence"
    return {
        "owner_id": str(owner.get("owner_id") or ""),
        "operation_family": str(owner.get("operation_family") or ""),
        "commit_boundary": str(owner.get("commit_boundary") or ""),
        "source_surface": str(owner.get("source_surface") or ""),
        "status": status,
        "evidence_pattern_count": expected_count,
        "evidence_pattern_found_count": found_count,
        "missing_evidence": missing,
    }


def build_nle_runtime_owner_map_report(*, root: Path | None = None) -> dict[str, Any]:
    repo_root = Path(root or ROOT)
    owners = [_evaluate_owner(owner, root=repo_root) for owner in OWNER_EVIDENCE]
    missing = [owner for owner in owners if owner["status"] != "covered"]
    family_counts = Counter(owner["operation_family"] for owner in owners)
    source_surface_counts = Counter(owner["source_surface"] for owner in owners)
    return {
        "schema": SCHEMA,
        "repo_root": str(repo_root),
        "runtime_owner_map_ready": not missing,
        "runtime_change_applied": False,
        "owner_count": len(owners),
        "covered_owner_count": len(owners) - len(missing),
        "missing_owner_count": len(missing),
        "operation_family_counts": dict(sorted(family_counts.items())),
        "source_surface_counts": dict(sorted(source_surface_counts.items())),
        "owners": owners,
        "blocked_candidates": list(BLOCKED_CANDIDATES),
        "next_gate": {
            "status": "fresh_owner_map_ready" if not missing else "missing_evidence",
            "required_before_new_runtime_adoption": [
                "identify_new_mutation_source",
                "prove_taption_release_commit_contract",
                "prove_no_per_pixel_nle_write",
                "prove_final_invalid_non_monotonic_overlap_0",
                "prove_global_canvas_max_active_lte_1",
                "prove_save_reopen_identity_preserved",
            ],
        },
    }


def _markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# NLE Runtime Owner Map Audit",
        "",
        f"- Schema: `{payload.get('schema')}`",
        f"- Runtime owner map ready: `{bool(payload.get('runtime_owner_map_ready'))}`",
        f"- Runtime change applied: `{bool(payload.get('runtime_change_applied'))}`",
        f"- Covered owners: `{payload.get('covered_owner_count')}/{payload.get('owner_count')}`",
        f"- Missing owners: `{payload.get('missing_owner_count')}`",
        "",
        "## Operation Families",
        "",
        "| operation_family | owner_count |",
        "| --- | --- |",
    ]
    for family, count in dict(payload.get("operation_family_counts") or {}).items():
        lines.append(f"| {family} | {count} |")
    lines.extend(
        [
            "",
            "## Owner Evidence Matrix",
            "",
            "| owner_id | family | source_surface | status | found/expected | missing |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for owner in list(payload.get("owners") or []):
        missing = len(list(owner.get("missing_evidence") or []))
        lines.append(
            "| {owner_id} | {family} | {surface} | {status} | {found}/{expected} | {missing} |".format(
                owner_id=owner.get("owner_id"),
                family=owner.get("operation_family"),
                surface=owner.get("source_surface"),
                status=owner.get("status"),
                found=owner.get("evidence_pattern_found_count"),
                expected=owner.get("evidence_pattern_count"),
                missing=missing,
            )
        )
    lines.extend(["", "## Blocked Candidates", "", "| candidate | status | reason |", "| --- | --- | --- |"])
    for candidate in list(payload.get("blocked_candidates") or []):
        lines.append(
            f"| {candidate.get('candidate_id')} | {candidate.get('status')} | {candidate.get('reason')} |"
        )
    gate = dict(payload.get("next_gate") or {})
    lines.extend(["", "## Next Gate", "", f"- Status: `{gate.get('status')}`"])
    for requirement in list(gate.get("required_before_new_runtime_adoption") or []):
        lines.append(f"- `{requirement}`")
    lines.append("")
    return "\n".join(lines)


def write_nle_runtime_owner_map_report(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "nle_runtime_owner_map_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "nle_runtime_owner_map_audit.md").write_text(_markdown_report(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source-app NLE runtime owner map without runtime changes.")
    parser.add_argument("--output-dir", default="output/manual_verification/latest/nle_runtime_owner_map_audit_20260628")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    payload = build_nle_runtime_owner_map_report()
    write_nle_runtime_owner_map_report(output_dir, payload)
    print(output_dir / "nle_runtime_owner_map_audit.md")
    return 0 if payload.get("runtime_owner_map_ready") else 2


if __name__ == "__main__":
    raise SystemExit(main())
