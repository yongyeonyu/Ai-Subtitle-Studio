import tempfile
from pathlib import Path

from tools.audit_trace_log_bundle import (
    REQUIRED_EVENT_FIELDS,
    REQUIRED_MANIFEST_FIELDS,
    build_trace_log_bundle_audit,
    write_trace_log_bundle_audit,
)


def test_trace_log_bundle_audit_proves_nle_action_trace_contract():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_trace_log_bundle_audit(output_dir=Path(tmp))

    assert report["passed"] is True
    assert report["required_dirs_created"] is True
    assert report["manifest_schema"] == "ai_subtitle_studio.trace_manifest.v1"
    assert report["manifest_missing_fields"] == []
    assert report["event_count"] >= 3
    assert report["latest_event_count"] >= 1
    assert report["event_missing_fields"] == []
    assert report["frame_precision_ok"] is True
    assert report["bounded_media_fingerprint"] is True
    assert "sha256" not in report["media_fingerprint_keys"]
    assert "file_hash" not in report["media_fingerprint_keys"]
    assert report["package_complete"] is True
    assert all(report["package_files"].values())
    assert report["package_event_count"] >= 3
    assert report["retention_ok"] is True
    assert report["retained_run_count"] <= report["retention_limit"]
    assert report["retention_removed_count"] > 0
    assert report["trace_disabled"] is False
    assert report["trace_drop_counts"] == {}
    assert REQUIRED_MANIFEST_FIELDS
    assert REQUIRED_EVENT_FIELDS


def test_trace_log_bundle_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_trace_log_bundle_audit(output_dir=output_dir)
        write_trace_log_bundle_audit(output_dir, report)

        markdown = (output_dir / "trace_log_bundle_audit.md").read_text(encoding="utf-8")
        saved_json = (output_dir / "trace_log_bundle_audit.json").read_text(encoding="utf-8")

    assert "Trace Log Bundle Audit" in markdown
    assert "Frame precision ok: `True`" in markdown
    assert "Retention ok: `True`" in markdown
    assert "| package_manifest | True |" in markdown
    assert '"passed": true' in saved_json
