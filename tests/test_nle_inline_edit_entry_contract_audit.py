import json
import tempfile
from pathlib import Path

from tools.audit_nle_inline_edit_entry_contract import (
    build_nle_inline_edit_entry_contract_report,
    write_nle_inline_edit_entry_contract_report,
)


def test_nle_inline_edit_entry_contract_audit_proves_preview_only_entry():
    report = build_nle_inline_edit_entry_contract_report()

    assert report["ready"] is True
    assert report["taption_contract"] == "inline_edit_entry_preview_only_until_text_commit"
    assert report["entry_trace_enabled"] is True
    assert report["nle_write_allowed_on_entry"] is False
    assert report["normal_caption_row_rewrite_allowed_on_entry"] is False
    assert report["project_save_allowed_on_entry"] is False
    assert report["row_validation_allowed_on_entry"] is False
    assert report["caption_text_payload_allowed"] is False
    assert report["nas_validation_required"] is False
    assert all(row["method_present"] for row in report["method_contracts"])
    assert all(row["forbidden_call_count"] == 0 for row in report["method_contracts"])
    assert report["trace_payload_contract"]["forbidden_payload_key_count"] == 0
    assert report["trace_payload_contract"]["caption_payload_included"] is True
    assert all(row["all_tokens_present"] for row in report["token_contracts"])


def test_nle_inline_edit_entry_contract_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_inline_edit_entry_contract_report()
        write_nle_inline_edit_entry_contract_report(output_dir, report)

        json_path = output_dir / "nle_inline_edit_entry_contract.json"
        markdown_path = output_dir / "nle_inline_edit_entry_contract.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Inline Edit Entry Contract Audit")
    assert "## Trace Payload Contract" in markdown
    assert "| TimelineInlineEditMixin.start_inline_edit | ui/editor/ux/timeline_canvas_editing.py | True | 0 |" in markdown
    assert "inline_edit_entry_trace_must_not_include_caption_text_or_target_ids" in markdown
