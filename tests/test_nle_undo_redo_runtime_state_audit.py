import json
import tempfile
from pathlib import Path

from tools.audit_nle_undo_redo_runtime_state import (
    build_nle_undo_redo_runtime_state_report,
    write_nle_undo_redo_runtime_state_report,
)


def test_nle_undo_redo_runtime_state_audit_proves_restore_sync_contract():
    report = build_nle_undo_redo_runtime_state_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is True
    assert report["ui_layout_changed"] is False
    assert report["persisted_nle_fields_changed"] is False
    assert report["operation_journal_write_allowed"] is False
    assert report["nas_required_for_contract"] is False
    assert report["static_contract"]["undo_restore_calls_runtime_sync"] is True
    assert report["static_contract"]["undo_restore_sync_source"] is True
    assert report["static_contract"]["undo_restore_appends_operation_journal"] is False
    assert report["runtime_check"]["before_signature"] == [("before", 30, 90)]
    assert report["runtime_check"]["after_signature"] == [("after left", 30, 60), ("after right", 60, 90)]
    assert report["runtime_check"]["sync_source"] == "undo_redo_restore"
    assert report["runtime_check"]["operation_journal_count"] == 0
    assert report["runtime_check"]["storage_has_runtime_nle_key"] is False


def test_nle_undo_redo_runtime_state_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_undo_redo_runtime_state_report()
        write_nle_undo_redo_runtime_state_report(output_dir, report)

        json_path = output_dir / "nle_undo_redo_runtime_state.json"
        markdown_path = output_dir / "nle_undo_redo_runtime_state.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Undo/Redo Runtime State Audit")
    assert "- Ready: `True`" in markdown
    assert "- Sync source: `undo_redo_restore`" in markdown
