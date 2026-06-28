from pathlib import Path

from tools.audit_nle_selection_view_state_isolation import (
    build_nle_selection_view_state_isolation_report,
    write_nle_selection_view_state_isolation_report,
)


def test_nle_selection_view_state_isolation_audit_ready(tmp_path: Path):
    report = build_nle_selection_view_state_isolation_report()
    assert report["ready"] is True
    assert report["selection_view_state_only_contract"] is True
    assert report["runtime_change_applied"] is False
    assert report["nle_write_allowed"] is False
    assert report["project_save_allowed"] is False
    assert report["primary_row_rewrite_allowed"] is False
    assert all(row["forbidden_call_count"] == 0 for row in report["method_contracts"])
    assert all(row["forbidden_assignment_count"] == 0 for row in report["method_contracts"])

    json_path, markdown_path = write_nle_selection_view_state_isolation_report(tmp_path, report)
    assert json_path.exists()
    assert markdown_path.exists()
    assert "NLE Selection View-State Isolation Audit" in markdown_path.read_text(encoding="utf-8")
