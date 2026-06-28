import json
import tempfile
from pathlib import Path

from core.project.nle_dual_write import GAP_DELETE_SEQUENCE_POLICY
from tools.audit_nle_gap_delete_sequence_policy import (
    build_nle_gap_delete_sequence_policy_report,
    write_nle_gap_delete_sequence_policy_report,
)


def test_nle_gap_delete_sequence_policy_audit_proves_no_ripple_contract():
    report = build_nle_gap_delete_sequence_policy_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is True
    assert report["ui_change_applied"] is False
    assert report["persisted_nle_fields_changed"] is False
    assert report["stt_or_cache_default_changed"] is False
    assert report["sequence_policy"] == GAP_DELETE_SEQUENCE_POLICY
    assert report["ripple_delete_allowed"] is False

    checks = {row["case"]: row for row in report["checks"]}
    assert checks["static_gap_delete_policy_contract"]["passed"] is True
    assert checks["static_gap_delete_policy_contract"]["policy_referenced"] is True
    assert checks["static_gap_delete_policy_contract"]["ripple_flag_recorded"] is True

    dynamic = checks["dynamic_gap_delete_no_ripple"]
    assert dynamic["passed"] is True
    assert dynamic["operation_policy"] == GAP_DELETE_SEQUENCE_POLICY
    assert dynamic["state_policy"] == GAP_DELETE_SEQUENCE_POLICY
    assert dynamic["undo_policy"] == GAP_DELETE_SEQUENCE_POLICY
    assert dynamic["operation_ripple_applied"] is False
    assert dynamic["state_ripple_applied"] is False
    assert dynamic["legacy_gap_count"] == 0
    assert dynamic["before_caption_bounds"] == dynamic["legacy_caption_bounds"]
    assert dynamic["before_caption_bounds"] == dynamic["nle_caption_bounds"]
    assert dynamic["raw_caption_bounds"] == {
        "first": (0, 30),
        "second": (60, 90),
    }
    assert dynamic["invalid_duration_count"] == 0
    assert dynamic["non_monotonic_count"] == 0
    assert dynamic["overlap_count"] == 0
    assert dynamic["max_active_segments"] <= 1

    storage = checks["storage_gap_delete_runtime_fields_clean"]
    assert storage["passed"] is True
    assert storage["storage_has_runtime_nle_state"] is False
    assert storage["storage_has_nle"] is False
    assert storage["storage_has_nle_snapshot"] is False
    assert storage["reopened_gap_count"] == 0


def test_nle_gap_delete_sequence_policy_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_gap_delete_sequence_policy_report()
        write_nle_gap_delete_sequence_policy_report(output_dir, report)

        json_path = output_dir / "nle_gap_delete_sequence_policy.json"
        markdown_path = output_dir / "nle_gap_delete_sequence_policy.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Gap Delete Sequence Policy Audit")
    assert f"Sequence policy: `{GAP_DELETE_SEQUENCE_POLICY}`" in markdown
    assert "Ripple delete allowed: `False`" in markdown
    assert "| dynamic_gap_delete_no_ripple | True | remove_gap_row_no_ripple | 0 | 1 |" in markdown
    assert "- Caption bounds preserved across gap delete: `True`" in markdown
