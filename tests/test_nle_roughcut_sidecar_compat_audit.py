import json
import tempfile
from pathlib import Path

from tools.audit_nle_roughcut_sidecar_compat import (
    build_nle_roughcut_sidecar_compat_report,
    write_nle_roughcut_sidecar_compat_report,
)


def test_nle_roughcut_sidecar_compat_audit_proves_file_restore_and_parity():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_roughcut_sidecar_compat_report(output_dir=Path(tmp))

    assert report["ready"] is True
    assert report["runtime_behavior_changed"] is False
    assert report["ui_layout_change_applied"] is False
    assert report["persisted_nle_fields_changed"] is False
    assert report["sidecar_files_written"] is True
    assert report["sidecar_restore_matches"] is True
    assert report["parity_diff_summary"] == "ok"
    assert report["final_invalid_duration_count"] == 0
    assert report["final_non_monotonic_count"] == 0
    assert report["final_overlap_count"] == 0
    assert report["global_max_active_segments"] == 1
    assert report["roughcut_sidecar_stable"] is True
    assert report["exported_assets_stable"] is True
    assert report["render_segment_count"] == 2
    assert report["manifest_count"] == 2
    assert report["stitched_boundary_count"] == 1
    assert report["sidecar_forbidden_key_count"] == 0
    assert report["storage_forbidden_key_count"] == 0
    assert "persisted_nle_project_fields_not_approved" in report["blocked_scope"]


def test_nle_roughcut_sidecar_compat_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_roughcut_sidecar_compat_report(output_dir=output_dir)
        write_nle_roughcut_sidecar_compat_report(output_dir, report)

        json_path = output_dir / "nle_roughcut_sidecar_compat.json"
        markdown_path = output_dir / "nle_roughcut_sidecar_compat.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Roughcut Sidecar Compatibility Audit")
    assert "Sidecar restore matches: `True`" in markdown
    assert "Parity diff summary: `ok`" in markdown
    assert "Sidecar forbidden key count: `0`" in markdown
