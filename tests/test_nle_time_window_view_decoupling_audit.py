import json
import tempfile
from pathlib import Path

from tools.audit_nle_time_window_view_decoupling import (
    build_nle_time_window_view_decoupling_report,
    write_nle_time_window_view_decoupling_report,
)


def test_nle_time_window_view_decoupling_audit_proves_view_only_contract():
    report = build_nle_time_window_view_decoupling_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["view_window_only_contract"] is True
    assert report["model_validation_allowed"] is False
    assert report["project_save_allowed"] is False
    assert report["nle_write_allowed"] is False
    assert report["nas_validation_required"] is False
    assert all(row["method_present"] for row in report["method_contracts"])
    assert all(row["forbidden_call_count"] == 0 for row in report["method_contracts"])
    assert all(row["forbidden_assignment_count"] == 0 for row in report["method_contracts"])
    assert all(row["all_tokens_present"] for row in report["token_contracts"])


def test_nle_time_window_view_decoupling_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_time_window_view_decoupling_report()
        write_nle_time_window_view_decoupling_report(output_dir, report)

        json_path = output_dir / "nle_time_window_view_decoupling.json"
        markdown_path = output_dir / "nle_time_window_view_decoupling.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Time Window View Decoupling Audit")
    assert "## Method Contracts" in markdown
    assert "| TimelineWidget.fit_to_view | ui/timeline/timeline_widget.py | True | 0 | 0 |" in markdown
    assert "| TimelineTimeWindowMixin.show_time_window_seconds | ui/timeline/timeline_time_window.py | True | 0 | 0 |" in markdown
    assert "time_window_fit_to_view_must_not_validate_or_rewrite_primary_subtitle_model" in markdown
