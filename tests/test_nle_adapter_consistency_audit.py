import json
import tempfile
from pathlib import Path

from tools.audit_nle_adapter_consistency import (
    build_nle_adapter_consistency_report,
    write_nle_adapter_consistency_report,
)


def test_nle_adapter_consistency_audit_proves_runtime_state_stays_cache_only():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_adapter_consistency_report(output_dir=Path(tmp), cycles=5)

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["cycles_requested"] == 5
    assert report["cycles_passed"] == 5
    assert report["initial"]["runtime_state_hydrated"] is True
    assert report["initial"]["runtime_caption_count"] == 4
    assert report["initial"]["storage_clean"] is True
    for cycle in report["checks"]["repeated_save_reopen"]:
        assert cycle["runtime_state_hydrated"] is True
        assert cycle["same_cache_state_id_stable"] is True
        assert cycle["post_clear_runtime_state_rehydrated"] is True
        assert cycle["post_clear_same_cache_state_id_stable"] is True
        assert cycle["runtime_marker_visible_before_clear"] is True
        assert cycle["runtime_marker_persisted_after_clear"] is False
        assert cycle["row_signature_stable"] is True
        assert cycle["storage_clean"] is True
        assert cycle["storage_has_runtime_nle_key"] is False
        assert cycle["storage_has_nle"] is False
        assert cycle["storage_has_nle_snapshot"] is False
        assert cycle["storage_has_quarantine"] is False
        assert cycle["invalid_duration_count"] == 0
        assert cycle["non_monotonic_count"] == 0
        assert cycle["overlap_count"] == 0
        assert cycle["max_active_segments"] == 1
        assert cycle["global_canvas_stable"] is True
        assert cycle["save_reload_stable"] is True


def test_nle_adapter_consistency_audit_records_project_io_lru_limit():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_adapter_consistency_report(output_dir=Path(tmp), cycles=2)

    lru = report["checks"]["lru_cache_limit"]
    assert lru["cache_owner"] == "core.project.project_io._PROJECT_FILE_CACHE"
    assert lru["cache_max_entries"] == 4
    assert lru["paths_written"] == 6
    assert lru["cache_entry_count"] <= lru["cache_max_entries"]
    assert lru["cache_limit_respected"] is True
    assert "persisted_nle_project_fields_not_approved" in report["blocked_scope"]
    assert "per_pixel_nle_drag_writes_not_allowed" in report["blocked_scope"]


def test_nle_adapter_consistency_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_adapter_consistency_report(output_dir=output_dir, cycles=3)
        write_nle_adapter_consistency_report(output_dir, report)

        json_path = output_dir / "nle_adapter_consistency_audit.json"
        markdown_path = output_dir / "nle_adapter_consistency_audit.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        assert saved["schema"] == report["schema"]
        assert markdown.startswith("# NLE Adapter Cache Consistency Audit")
        assert "## Repeated Save / Reopen" in markdown
        assert "## LRU Cache Limit" in markdown
        assert "| 1 | True | True | True | False | True | 0 | 0 | 0 | 1 |" in markdown
