import json
import tempfile
from pathlib import Path

from tools.audit_nle_preview_skimming_cache import (
    build_nle_preview_skimming_cache_report,
    write_nle_preview_skimming_cache_report,
)


def test_nle_preview_skimming_cache_audit_proves_user_preview_only_contract():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_preview_skimming_cache_report(output_dir=Path(tmp))

    assert report["ready"] is True
    assert report["ui_runtime_change_applied"] is False
    assert report["preview_cache_contract_applied"] is True
    assert report["preview_workspace_isolated"] is True
    assert "Preview" in report["preview_cache_dir"]
    assert "Diagnostics/Trace" not in report["preview_cache_dir"]
    assert report["nearest_cached_preview_frame_hit"] is True
    assert report["manifest_schema"] == "ai_subtitle_studio.preview_frame_cache.v1"
    assert report["manifest_purpose"] == "editor_preview_skimming"
    assert report["manifest_evidence_role"] == "user_preview_only"
    assert report["manifest_cut_boundary_evidence"] is False
    assert report["manifest_ui_thread_decode_allowed"] is False
    assert report["source_fps_grid_ok"] is True
    contract = report["video_surface_contract"]
    assert contract["nearest_lookup_before_worker_schedule"] is True
    assert contract["cache_miss_worker_schedule_present"] is True
    assert contract["preview_worker_uses_ensure_preview_frame"] is True
    assert contract["legacy_sync_thumbnail_helper_not_called_by_unprimed_preview"] is True
    trace = report["trace_event_contract"]
    assert trace["uses_trace_logger_queue"] is True
    assert trace["best_effort_trace_failure"] is True
    assert trace["events_present"] is True
    assert trace["preview_only_fields_present"] is True
    assert trace["exact_fps_fields_present"] is True
    assert trace["preview_seek_throttle_present"] is True


def test_nle_preview_skimming_cache_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_preview_skimming_cache_report(output_dir=output_dir)
        write_nle_preview_skimming_cache_report(output_dir, report)

        json_path = output_dir / "nle_preview_skimming_cache_audit.json"
        markdown_path = output_dir / "nle_preview_skimming_cache_audit.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        assert saved["schema"] == report["schema"]
        assert markdown.startswith("# NLE Preview Skimming Cache Contract Audit")
        assert "Preview cache contract applied: `True`" in markdown
        assert "Manifest cut-boundary evidence: `False`" in markdown
        assert "| ui.editor.video_player_surface.VideoPlayerSurfaceMixin | True | True | True | True |" in markdown
        assert "## Trace Event Contract" in markdown
        assert "| ui.editor.video_player_surface.VideoPlayerSurfaceMixin | True | True | True | True | True | True |" in markdown
