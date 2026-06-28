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
    assert report["operation_roundtrip_family_count"] == 11
    assert report["render_export_parity_passed"] is True
    assert "top_level_nle_payload_not_cut_over" in report["blockers"]
    runtime = report["checks"]["runtime_roundtrip"]
    assert runtime["loaded_runtime_state"] is True
    assert runtime["runtime_caption_count"] == 3
    assert runtime["storage_clean"] is True
    assert runtime["storage_has_runtime_nle_key"] is False
    assert runtime["storage_has_nle"] is False
    assert runtime["storage_has_nle_snapshot"] is False
    assert runtime["storage_has_quarantine"] is False
    approved = report["checks"]["approved_snapshot_persistence"]
    assert approved["ready"] is True
    assert approved["snapshot_persisted"] is True
    assert approved["storage_has_nle_snapshot"] is True
    assert approved["storage_has_nle"] is False
    assert approved["storage_has_runtime_nle_key"] is False
    assert approved["legacy_rows_stable"] is True
    assert approved["readback_parity_checked"] is True
    assert approved["readback_parity_stable"] is True
    assert approved["readback_mismatch_count"] == 0
    corrupted = report["checks"]["corrupted_snapshot_readback"]
    assert corrupted["drift_detected"] is True
    assert corrupted["mismatch_count"] > 0
    assert corrupted["legacy_rows_stable"] is True
    assert corrupted["runtime_report_persisted"] is False
    assert corrupted["runtime_state_persisted"] is False
    assert corrupted["quarantine_persisted"] is False


def test_nle_persistence_cutover_audit_includes_render_export_parity_gate():
    with tempfile.TemporaryDirectory() as tmp:
        report = build_nle_persistence_cutover_report(output_dir=Path(tmp))

    parity = report["checks"]["render_export_parity"]
    assert parity["stable"] is True
    assert parity["storage_clean"] is True
    assert parity["caption_count"] == 2
    assert parity["gap_count"] == 1
    assert parity["candidate_count"] == 2
    assert parity["render_segment_count"] == 2
    assert parity["manifest_count"] == 2
    assert parity["stitched_boundary_count"] == 1
    assert parity["invalid_duration_count"] == 0
    assert parity["non_monotonic_count"] == 0
    assert parity["overlap_count"] == 0
    assert parity["max_active_segments"] == 1
    surfaces = {surface["target_surface"]: surface for surface in parity["surface_reports"]}
    assert set(surfaces) == {
        "source_subtitles",
        "final_overlay",
        "global_canvas",
        "roughcut_sidecar",
        "exported_assets",
    }
    assert all(surface["stable"] for surface in surfaces.values())
    assert surfaces["final_overlay"]["gap_count"] == 0
    assert surfaces["global_canvas"]["gap_count"] == 1
    assert surfaces["global_canvas"]["candidate_count"] == 2
    assert surfaces["exported_assets"]["render_segment_count"] == 2


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
        "caption_range_replace",
        "caption_resize",
        "caption_split",
        "caption_text_edit",
        "gap_delete",
        "gap_generate",
        "marker_edit",
    }
    for row in matrix:
        assert row["runtime_state_hydrated"] is True
        assert row["storage_clean"] is True
        assert row["storage_has_runtime_nle_key"] is False
        assert row["storage_has_nle"] is False
        assert row["storage_has_nle_snapshot"] is False
        assert row["reopened_matches_projected"] is True
        assert row["reopened_identity_preserved"] is True
        assert row["reopened_markers_preserved"] is True
        assert row["invalid_duration_count"] == 0
        assert row["non_monotonic_count"] == 0
        assert row["overlap_count"] == 0
        assert row["max_active_segments"] <= 1
    marker_row = next(row for row in matrix if row["operation_family"] == "marker_edit")
    assert marker_row["operation_kind"] == "marker_edit"
    assert marker_row["projected_marker_count"] == 1
    assert marker_row["reopened_marker_count"] == 1


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
        assert "## Render / Export Parity" in markdown
        assert "## Approved Snapshot Persistence" in markdown
        assert "- Snapshot persisted: `True`" in markdown
        assert "- Read-back parity stable: `True`" in markdown
        assert "## Corrupted Snapshot Readback" in markdown
        assert "- Drift detected: `True`" in markdown
        assert "| exported_assets | True | 2 | 0 | 0 | 2 | 2 | 1 |" in markdown
        assert "## Operation Roundtrip Matrix" in markdown
        assert "| caption_text_edit | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| caption_range_replace | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| candidate_confirm | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| marker_edit | True | True | True | True | True | 0 | 1 |" in markdown
