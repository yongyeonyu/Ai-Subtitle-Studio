from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.generate_nle_canonical_load_owner_review_packet import (
    build_review_packet_from_audit,
    render_markdown,
    write_review_packet,
)


ROOT = Path(__file__).resolve().parents[1]


def _audit_payload() -> dict:
    return {
        "schema": "ai_subtitle_studio.nle_persistence_cutover_readiness.v1",
        "status": "blocked",
        "prep_ready": True,
        "persistence_cutover_ready": False,
        "blockers": [
            "top_level_nle_shadow_not_canonical_load_owner",
            "runtime_nle_project_state_must_remain_runtime_only",
            "legacy_disk_shape_required_for_full_cutover",
        ],
        "operation_roundtrip_all_passed": True,
        "operation_roundtrip_family_count": 11,
        "render_export_parity_passed": True,
        "top_level_nle_shadow_ready": True,
        "remaining_full_cutover_gates": [
            "making top-level nle payloads canonical load owners",
            "persisting _nle_project_state payloads",
            "making nle_snapshot the canonical load source",
            "changing legacy editor_state compatibility guarantees",
        ],
        "checks": {
            "runtime_roundtrip": {
                "loaded_runtime_state": True,
                "storage_clean": True,
                "storage_has_runtime_nle_key": False,
                "storage_has_nle": False,
                "storage_has_nle_snapshot": False,
            },
            "approved_snapshot_persistence": {
                "ready": True,
                "snapshot_persisted": True,
                "legacy_rows_stable": True,
                "readback_parity_stable": True,
            },
            "approved_top_level_nle_shadow": {
                "ready": True,
                "storage_has_nle": True,
                "storage_has_nle_snapshot": True,
                "shadow_schema": "ai_subtitle_studio.nle_shadow_project.v1",
                "shadow_role": "shadow_metadata",
                "canonical_load_owner": "legacy_editor_state",
                "runtime_project_state_persisted": False,
                "legacy_rows_stable": True,
                "readback_parity_stable": True,
            },
            "corrupted_snapshot_readback": {
                "drift_detected": True,
                "legacy_rows_stable": True,
                "runtime_report_persisted": False,
            },
            "roughcut_sidecar_readback": {
                "approved_readback_stable": True,
                "corrupted_marker_drift_detected": True,
                "render_export_stable": True,
                "roughcut_sidecar_stable": True,
            },
            "render_export_parity": {
                "stable": True,
                "storage_clean": True,
                "invalid_duration_count": 0,
                "non_monotonic_count": 0,
                "overlap_count": 0,
                "max_active_segments": 1,
            },
        },
    }


def test_review_packet_keeps_canonical_load_owner_blocked() -> None:
    packet = build_review_packet_from_audit(_audit_payload())

    assert packet["schema"] == "ai_subtitle_studio.nle_canonical_load_owner_review_packet.v1"
    assert packet["status"] == "owner_review_required_blocked"
    assert packet["not_runtime_change"] is True
    assert packet["canonical_load_owner_unchanged"] is True
    assert packet["current_canonical_load_owner"] == "legacy_editor_state"
    assert packet["canonical_load_owner_change_allowed"] is False
    assert packet["disk_format_cutover_allowed"] is False
    assert packet["evidence_summary"]["persistence_cutover_ready"] is False
    assert packet["evidence_summary"]["top_level_nle_shadow_ready"] is True


def test_review_packet_preserves_nle_audit_evidence_and_blockers() -> None:
    packet = build_review_packet_from_audit(_audit_payload())
    evidence = packet["evidence_summary"]

    assert evidence["blockers"] == [
        "top_level_nle_shadow_not_canonical_load_owner",
        "runtime_nle_project_state_must_remain_runtime_only",
        "legacy_disk_shape_required_for_full_cutover",
    ]
    assert evidence["remaining_full_cutover_gates"] == [
        "making top-level nle payloads canonical load owners",
        "persisting _nle_project_state payloads",
        "making nle_snapshot the canonical load source",
        "changing legacy editor_state compatibility guarantees",
    ]
    assert evidence["operation_roundtrip_all_passed"] is True
    assert evidence["operation_roundtrip_family_count"] == 11
    assert evidence["render_export_parity_passed"] is True
    assert evidence["top_level_nle_shadow"]["shadow_schema"] == "ai_subtitle_studio.nle_shadow_project.v1"
    assert evidence["top_level_nle_shadow"]["shadow_role"] == "shadow_metadata"
    assert evidence["top_level_nle_shadow"]["runtime_project_state_persisted"] is False
    assert evidence["runtime_roundtrip"]["storage_has_runtime_nle_key"] is False
    assert evidence["corrupted_snapshot_readback"]["drift_detected"] is True
    assert evidence["corrupted_snapshot_readback"]["legacy_rows_stable"] is True
    assert evidence["roughcut_sidecar_readback"]["render_export_stable"] is True
    assert evidence["render_export_parity"]["invalid_duration_count"] == 0
    assert evidence["render_export_parity"]["non_monotonic_count"] == 0
    assert evidence["render_export_parity"]["overlap_count"] == 0
    assert evidence["render_export_parity"]["max_active_segments"] == 1


def test_decision_matrix_requires_owner_approval_and_blocks_cutover() -> None:
    packet = build_review_packet_from_audit(_audit_payload())

    assert {row["id"] for row in packet["decision_matrix"]} == {
        "top_level_nle_as_canonical_load_owner",
        "nle_snapshot_as_canonical_load_source",
        "runtime_nle_project_state_persisted",
        "legacy_editor_state_compatibility_removed",
    }
    for row in packet["decision_matrix"]:
        assert row["evidence_ready"] is True
        assert row["owner_approval_required"] is True
        assert row["canonical_change_allowed"] is False
        assert row["disk_format_cutover_allowed"] is False
        assert row["rollback_boundary_required"] is True
        assert row["blocker_present"] is True


def test_markdown_and_written_artifacts_avoid_misleading_claims(tmp_path: Path) -> None:
    output_dir = tmp_path / "packet"
    packet = build_review_packet_from_audit(_audit_payload(), output_dir=output_dir)
    written = write_review_packet(packet, output_dir)
    names = {path.name for path in written}
    markdown = render_markdown(packet)

    assert "nle_canonical_load_owner_review_packet.json" in names
    assert "nle_canonical_load_owner_review_packet.md" in names
    assert "decision_matrix.json" in names
    assert "owner-review blocker map" in markdown
    assert "Current canonical load owner: `legacy_editor_state`" in markdown
    assert "Canonical load owner change allowed by this packet: `False`" in markdown
    assert "Disk format cutover allowed by this packet: `False`" in markdown
    assert "Shadow schema/role: `ai_subtitle_studio.nle_shadow_project.v1` / `shadow_metadata`" in markdown
    assert "Runtime project state on disk: `False`" in markdown
    for forbidden in (
        "canonical load owner ready",
        "disk-format cutover complete",
        "load owner switched",
        "runtime state persisted",
        "legacy editor_state replaced",
        "project load now uses NLE",
        "full NLE persistence enabled",
    ):
        assert forbidden not in markdown


def test_review_packet_cli_writes_summary(tmp_path: Path) -> None:
    output_dir = tmp_path / "packet"
    audit_dir = tmp_path / "audit"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/generate_nle_canonical_load_owner_review_packet.py"),
            "--output-dir",
            str(output_dir),
            "--audit-output-dir",
            str(audit_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "owner_review_required_blocked"
    assert payload["canonical_load_owner_unchanged"] is True
    assert payload["canonical_load_owner_change_allowed"] is False
    assert payload["disk_format_cutover_allowed"] is False
    assert (output_dir / "nle_canonical_load_owner_review_packet.md").is_file()
    assert (output_dir / "decision_matrix.json").is_file()
    assert (audit_dir / "nle_persistence_cutover_audit.md").is_file()
