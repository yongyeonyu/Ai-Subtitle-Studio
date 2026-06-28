import json
import tempfile
from pathlib import Path

from tools.audit_nle_operation_journal import (
    build_nle_operation_journal_report,
    write_nle_operation_journal_report,
)


def test_nle_operation_journal_audit_covers_release_undo_contracts():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_operation_journal_report(output_dir=Path(tmp))

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["operation_family_count"] == 11
    assert report["release_metadata_count"] == 11
    assert report["undo_snapshot_count"] == 11
    assert report["storage_clean_count"] == 11
    families = {row["operation_family"] for row in report["checks"]}
    assert families == {
        "candidate_confirm",
        "caption_delete",
        "caption_merge",
        "caption_move",
        "caption_range_replace",
        "caption_resize",
        "caption_split",
        "caption_text_edit",
        "gap_delete",
        "gap_generate",
        "marker_edit",
    }
    for row in report["checks"]:
        assert row["operation_schema_ok"] is True
        assert row["target_count"] > 0
        assert row["time_domain"] == "sequence"
        assert row["frame_policy_unit"] == "frame"
        assert row["frame_policy_allow_final_overlap"] is False
        assert row["release_metadata"] is True
        assert row["undo_snapshot_schema_ok"] is True
        assert row["undo_editor_row_count"] > 0
        assert row["undo_release_metadata"] is True
        assert row["invalid_duration_count"] == 0
        assert row["non_monotonic_count"] == 0
        assert row["overlap_count"] == 0
        assert row["max_active_segments"] <= 1
        assert row["storage_clean"] is True
        assert row["operation_schema_persisted"] is False
        assert row["undo_schema_persisted"] is False
        assert row["runtime_state_persisted"] is False


def test_nle_operation_journal_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_operation_journal_report(output_dir=output_dir)
        write_nle_operation_journal_report(output_dir, report)

        json_path = output_dir / "nle_operation_journal_audit.json"
        markdown_path = output_dir / "nle_operation_journal_audit.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        assert saved["schema"] == report["schema"]
        assert markdown.startswith("# NLE Operation Journal Contract Audit")
        assert "## Operation Matrix" in markdown
        assert "| caption_move | caption_move | True | True |" in markdown
        assert "| marker_edit | marker_edit | True | True |" in markdown
