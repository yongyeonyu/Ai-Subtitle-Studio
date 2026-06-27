import json
import tempfile
from pathlib import Path

from tools.audit_nle_persistence_cutover import (
    build_nle_persistence_cutover_report,
    write_nle_persistence_cutover_report,
)


def test_nle_persistence_cutover_audit_keeps_cutover_blocked_while_runtime_contract_passes():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_persistence_cutover_report(output_dir=Path(tmp))

    assert report["prep_ready"] is True
    assert report["persistence_cutover_ready"] is False
    assert report["operation_roundtrip_all_passed"] is True
    assert report["operation_roundtrip_family_count"] == 8
    assert "persisted_nle_project_fields_not_approved" in report["blockers"]
    runtime = report["checks"]["runtime_roundtrip"]
    assert runtime["loaded_runtime_state"] is True
    assert runtime["runtime_caption_count"] == 3
    assert runtime["storage_clean"] is True
    assert runtime["storage_has_runtime_nle_key"] is False
    assert runtime["storage_has_nle"] is False
    assert runtime["storage_has_nle_snapshot"] is False
    assert runtime["storage_has_quarantine"] is False


def test_nle_persistence_cutover_audit_records_future_payload_quarantine():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_persistence_cutover_report(output_dir=Path(tmp))

    future = report["checks"]["future_payload_quarantine"]
    assert future["quarantine_recorded"] is True
    assert future["stripped_keys"] == ["nle", "nle_snapshot", "_nle_project_state"]
    assert future["remaining_unapproved_fields"] == []
    assert future["quarantine_key_present"] is True


def test_nle_persistence_cutover_audit_roundtrips_dual_write_operation_families():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_persistence_cutover_report(output_dir=Path(tmp))

    matrix = report["checks"]["operation_roundtrip_matrix"]
    families = {row["operation_family"] for row in matrix}
    assert families == {
        "candidate_confirm",
        "caption_delete",
        "caption_merge",
        "caption_move",
        "caption_resize",
        "caption_split",
        "gap_delete",
        "gap_generate",
    }
    for row in matrix:
        assert row["runtime_state_hydrated"] is True
        assert row["storage_clean"] is True
        assert row["storage_has_runtime_nle_key"] is False
        assert row["storage_has_nle"] is False
        assert row["storage_has_nle_snapshot"] is False
        assert row["reopened_matches_projected"] is True
        assert row["reopened_identity_preserved"] is True
        assert row["invalid_duration_count"] == 0
        assert row["non_monotonic_count"] == 0
        assert row["overlap_count"] == 0
        assert row["max_active_segments"] <= 1


def test_nle_persistence_cutover_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_persistence_cutover_report(output_dir=output_dir)
        write_nle_persistence_cutover_report(output_dir, report)

        json_path = output_dir / "nle_persistence_cutover_audit.json"
        markdown_path = output_dir / "nle_persistence_cutover_audit.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        assert saved["schema"] == report["schema"]
        assert markdown.startswith("# NLE Persistence Cutover Audit")
        assert "## Operation Roundtrip Matrix" in markdown
        assert "| candidate_confirm | True | True | True | True | 0 | 1 |" in markdown
