import json
import tempfile
from pathlib import Path

from tools.audit_nle_dual_write_duration_bound import (
    OWNER_FUNCTIONS,
    build_nle_dual_write_duration_bound_report,
    write_nle_dual_write_duration_bound_report,
)


def test_nle_dual_write_duration_bound_audit_covers_release_commit_rows():
    report = build_nle_dual_write_duration_bound_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is True
    assert report["persisted_nle_fields_changed"] is False
    assert report["ui_change_applied"] is False
    assert report["stt_or_cache_default_changed"] is False
    assert report["duration_bound_helper_imported"] is True
    assert report["duration_bound_public_helper"] is True
    assert report["owner_count"] == len(OWNER_FUNCTIONS)
    assert report["owner_covered_count"] == report["owner_count"]
    assert {row["function"] for row in report["owner_checks"]} == set(OWNER_FUNCTIONS)
    assert all(row["found"] for row in report["owner_checks"])
    assert all(row["duration_bound_helper_called"] for row in report["owner_checks"])

    dynamic = {row["case"]: row for row in report["dynamic_checks"]}
    assert dynamic["caption_move_tail_clamp"]["passed"] is True
    assert dynamic["caption_move_tail_clamp"]["operation_trimmed_row_count"] == 1
    assert dynamic["caption_move_tail_clamp"]["operation_dropped_row_count"] == 0
    assert dynamic["caption_move_tail_clamp"]["legacy_end_frame"] == 180
    assert dynamic["caption_move_tail_clamp"]["raw_end_frame"] == 180
    assert dynamic["candidate_confirm_late_drop"]["passed"] is True
    assert dynamic["candidate_confirm_late_drop"]["operation_trimmed_row_count"] == 0
    assert dynamic["candidate_confirm_late_drop"]["operation_dropped_row_count"] == 1
    assert dynamic["candidate_confirm_late_drop"]["legacy_has_late_row"] is False
    assert dynamic["candidate_confirm_late_drop"]["nle_has_late_row"] is False
    assert dynamic["candidate_confirm_late_drop"]["raw_has_late_row"] is False
    assert all(row["invalid_duration_count"] == 0 for row in dynamic.values())
    assert all(row["non_monotonic_count"] == 0 for row in dynamic.values())
    assert all(row["overlap_count"] == 0 for row in dynamic.values())
    assert all(row["max_active_segments"] <= 1 for row in dynamic.values())


def test_nle_dual_write_duration_bound_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_dual_write_duration_bound_report()
        write_nle_dual_write_duration_bound_report(output_dir, report)

        json_path = output_dir / "nle_dual_write_duration_bound.json"
        markdown_path = output_dir / "nle_dual_write_duration_bound.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Dual-Write Duration Bound Audit")
    assert "Owner coverage: `11/11`" in markdown
    assert "| apply_caption_move_dual_write_pilot | True | True |" in markdown
    assert "| caption_move_tail_clamp | True | 1 | 0 | 0 | 1 |" in markdown
    assert "| candidate_confirm_late_drop | True | 0 | 1 | 0 | 1 |" in markdown
    assert "- Raw editor-state duration bound required: `True`" in markdown
