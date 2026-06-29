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
    assert report["top_level_nle_shadow_ready"] is True
    assert report["app_version"]
    assert "top_level_nle_shadow_not_canonical_load_owner" in report["blockers"]
    assert "top_level_nle_projection_gap_coverage_missing" not in report["blockers"]
    gate_matrix = report["canonical_load_owner_gate_matrix"]
    assert gate_matrix["status"] == "blocked"
    assert gate_matrix["overall_stoplight"] == "red"
    assert gate_matrix["current_canonical_load_owner"] == "legacy_editor_state"
    assert gate_matrix["target_load_owner_candidate"] == "top_level_nle_shadow_metadata"
    assert gate_matrix["not_runtime_change"] is True
    assert gate_matrix["not_disk_format_cutover"] is True
    assert gate_matrix["not_ui_change"] is True
    assert gate_matrix["ready_gate_count"] == 7
    assert gate_matrix["blocked_gate_count"] == 5
    assert gate_matrix["blocked_gate_ids"] == [
        "canonical_load_owner_change_allowed",
        "nle_snapshot_canonical_load_source_allowed",
        "runtime_project_state_persistence_allowed",
        "legacy_disk_shape_replacement_allowed",
        "final_cutover_ready",
    ]
    gates = {row["id"]: row for row in gate_matrix["gates"]}
    assert gates["top_level_shadow_ready"]["status"] == "ready"
    assert gates["compatibility_projection_ready"]["status"] == "ready"
    assert gates["legacy_default_load_still_canonical"]["status"] == "ready"
    assert gates["operation_roundtrip_ready"]["status"] == "ready"
    assert gates["render_export_parity_ready"]["status"] == "ready"
    assert gates["roughcut_sidecar_ready"]["status"] == "ready"
    assert gates["rollback_boundary_defined"]["status"] == "ready"
    assert gates["canonical_load_owner_change_allowed"]["status"] == "blocked"
    assert gates["nle_snapshot_canonical_load_source_allowed"]["status"] == "blocked"
    assert gates["runtime_project_state_persistence_allowed"]["status"] == "blocked"
    assert gates["legacy_disk_shape_replacement_allowed"]["status"] == "blocked"
    assert gates["final_cutover_ready"]["status"] == "blocked"
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
    top_level = report["checks"]["approved_top_level_nle_shadow"]
    assert top_level["ready"] is True
    assert top_level["storage_has_nle"] is True
    assert top_level["storage_has_nle_snapshot"] is True
    assert top_level["canonical_load_owner"] == "legacy_editor_state"
    assert top_level["runtime_project_state_persisted"] is False
    assert top_level["legacy_rows_stable"] is True
    assert top_level["readback_parity_stable"] is True
    assert top_level["caption_count"] == 2
    assert top_level["gap_count"] == 1
    assert top_level["runtime_report_persisted"] is False
    assert top_level["runtime_state_persisted"] is False
    assert top_level["quarantine_persisted"] is False
    compatibility = report["checks"]["top_level_nle_compatibility_projection"]
    assert compatibility["status"] == "gap_projection_coverage_ready_blocked"
    assert compatibility["not_runtime_change"] is True
    assert compatibility["canonical_load_owner_unchanged"] is True
    assert compatibility["current_canonical_load_owner"] == "legacy_editor_state"
    assert compatibility["canonical_load_owner_change_allowed"] is False
    assert compatibility["disk_format_cutover_allowed"] is False
    assert compatibility["explicit_projection_uses_top_level_nle"] is True
    assert compatibility["default_load_uses_legacy_rows"] is True
    assert compatibility["explicit_projection_differs_from_default"] is True
    assert compatibility["explicit_projection_row_count"] == 3
    assert compatibility["explicit_projection_caption_count"] == 2
    assert compatibility["explicit_projection_gap_count"] == 1
    assert compatibility["default_row_count"] == 3
    assert compatibility["default_caption_count"] == 2
    assert compatibility["default_gap_count"] == 1
    assert compatibility["shadow_override_caption_text"] == "nle shadow first"
    assert compatibility["explicit_first_caption_text"] == "nle shadow first"
    assert compatibility["default_first_caption_text"] == "first"
    assert compatibility["resave_first_caption_text"] == "first"
    assert compatibility["shadow_override_visible_in_explicit_projection"] is True
    assert compatibility["shadow_override_absent_from_default_load"] is True
    assert compatibility["default_load_preserved_legacy_text"] is True
    assert compatibility["resave_discarded_shadow_override"] is True
    assert compatibility["resave_preserved_legacy_text"] is True
    assert compatibility["gap_coverage_ready"] is True
    assert compatibility["runtime_state_hydrated_from_legacy"] is True
    assert compatibility["runtime_report_persisted_after_resave"] is False
    assert compatibility["runtime_state_persisted_after_resave"] is False
    assert compatibility["quarantine_persisted_after_resave"] is False
    assert compatibility["resave_rebuilt_shadow_from_legacy"] is True
    rollback = report["checks"]["canonical_load_owner_rollback_boundary"]
    assert rollback["ready"] is True
    assert rollback["status"] == "defined"
    assert rollback["rollback_target"] == "legacy_editor_state"
    assert rollback["candidate_load_owner"] == "top_level_nle_shadow_metadata"
    assert rollback["candidate_runtime_state_persistence_attempted"] is True
    assert rollback["candidate_snapshot_canonical_source_attempted"] is True
    assert rollback["candidate_shadow_text"] == "rollback candidate shadow text"
    assert rollback["loaded_first_caption_text"] == "first"
    assert rollback["resave_first_caption_text"] == "first"
    assert rollback["candidate_shadow_text_leaked_to_default_load"] is False
    assert rollback["candidate_shadow_text_leaked_after_resave"] is False
    assert rollback["quarantine_recorded"] is True
    assert set(rollback["stripped_keys"]) == {"nle", "nle_snapshot", "_nle_project_state"}
    assert rollback["default_load_preserved_legacy_rows"] is True
    assert rollback["runtime_state_hydrated_from_legacy"] is True
    assert rollback["storage_after_clean"] is True
    assert rollback["storage_after_nle_canonical_load_owner"] == "legacy_editor_state"
    assert rollback["storage_after_has_nle"] is True
    assert rollback["storage_after_has_nle_snapshot"] is True
    assert rollback["storage_after_has_runtime_nle_key"] is False
    assert rollback["storage_after_has_quarantine"] is False
    assert report["top_level_nle_compatibility_projection_passed"] is True
    assert report["top_level_nle_canonical_projection_complete"] is False
    corrupted = report["checks"]["corrupted_snapshot_readback"]
    assert corrupted["drift_detected"] is True
    assert corrupted["mismatch_count"] > 0
    assert corrupted["legacy_rows_stable"] is True
    assert corrupted["runtime_report_persisted"] is False
    assert corrupted["runtime_state_persisted"] is False
    assert corrupted["quarantine_persisted"] is False
    roughcut = report["checks"]["roughcut_sidecar_readback"]
    assert roughcut["approved_snapshot_persisted"] is True
    assert roughcut["approved_readback_checked"] is True
    assert roughcut["approved_readback_stable"] is True
    assert roughcut["approved_roughcut_sidecar_stable"] is True
    assert roughcut["persisted_marker_count_before_corruption"] == 2
    assert roughcut["corrupted_marker_drift_detected"] is True
    assert roughcut["mismatch_count"] > 0
    assert roughcut["render_export_stable"] is True
    assert roughcut["roughcut_sidecar_stable"] is True
    assert roughcut["sidecar_stitched_boundary_count"] == 1
    assert roughcut["roughcut_marker_count"] == 1
    assert roughcut["runtime_report_persisted"] is False
    assert roughcut["runtime_state_persisted"] is False
    assert roughcut["top_level_nle_persisted"] is False
    assert roughcut["quarantine_persisted"] is False


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


def test_nle_persistence_cutover_markdown_includes_top_level_shadow_section():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_persistence_cutover_report(output_dir=output_dir)
        write_nle_persistence_cutover_report(output_dir, report)

        markdown = (output_dir / "nle_persistence_cutover_audit.md").read_text(encoding="utf-8")

        assert "## Top-Level NLE Shadow" in markdown
        assert "- Storage has top-level NLE: `True`" in markdown
        assert "- Canonical load owner: `legacy_editor_state`" in markdown
        assert "- Caption/gap count: `2` / `1`" in markdown
        assert "## Top-Level NLE Compatibility Projection" in markdown
        assert "Compatibility audit evidence only." in markdown
        assert "## Canonical Load-Owner Gate Matrix" in markdown
        assert "This matrix is a cutover preflight only." in markdown
        assert "- Overall stoplight: `red`" in markdown
        assert "| rollback_boundary_defined | ready |" in markdown
        assert "| canonical_load_owner_change_allowed | blocked |" in markdown
        assert "| final_cutover_ready | blocked |" in markdown
        assert "## Canonical Load-Owner Rollback Boundary" in markdown
        assert "Rollback-boundary audit evidence only." in markdown
        assert "- Ready: `True`" in markdown
        assert "- Rollback target: `legacy_editor_state`" in markdown
        assert "- Candidate load owner: `top_level_nle_shadow_metadata`" in markdown
        assert "- Candidate shadow text: `rollback candidate shadow text`" in markdown
        assert "- Loaded first caption text: `first`" in markdown
        assert "- Resave first caption text: `first`" in markdown
        assert "- Candidate shadow text leaked to default load: `False`" in markdown
        assert "- Candidate shadow text leaked after resave: `False`" in markdown
        assert "- Stripped keys: `nle, nle_snapshot, _nle_project_state`" in markdown
        assert "- Storage after NLE canonical load owner: `legacy_editor_state`" in markdown
        assert "- Storage after has NLE/snapshot/runtime/quarantine: `True/True/False/False`" in markdown
        assert "- Status: `gap_projection_coverage_ready_blocked`" in markdown
        assert "- Default load source: `legacy_editor_state`" in markdown
        assert "- Explicit projection uses top-level NLE: `True`" in markdown
        assert "- Default load uses legacy rows: `True`" in markdown
        assert "- Explicit projection row count: `3`" in markdown
        assert "- Explicit projection caption/gap count: `2` / `1`" in markdown
        assert "- Default row/caption/gap count: `3` / `2` / `1`" in markdown
        assert "- Shadow override caption text: `nle shadow first`" in markdown
        assert "- Explicit/default/resave first caption text: `nle shadow first` / `first` / `first`" in markdown
        assert "- Shadow override visible in explicit projection: `True`" in markdown
        assert "- Shadow override absent from default load: `True`" in markdown
        assert "- Resave discarded shadow override: `True`" in markdown
        assert "- Gap coverage ready: `True`" in markdown
        for forbidden in (
            "canonical load owner ready",
            "cutover ready",
            "disk-format cutover complete",
            "load owner switched",
            "project load now uses NLE",
            "nle_snapshot is canonical",
            "legacy editor_state replaced",
            "full NLE persistence enabled",
        ):
            assert forbidden not in markdown


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
        assert "## Roughcut Sidecar Readback" in markdown
        assert "- Corrupted marker drift detected: `True`" in markdown
        assert "- Render/export stable after corrupted snapshot read: `True`" in markdown
        assert "| exported_assets | True | 2 | 0 | 0 | 2 | 2 | 1 |" in markdown
        assert "## Operation Roundtrip Matrix" in markdown
        assert "| caption_text_edit | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| caption_range_replace | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| candidate_confirm | True | True | True | True | True | 0 | 1 |" in markdown
        assert "| marker_edit | True | True | True | True | True | 0 | 1 |" in markdown
