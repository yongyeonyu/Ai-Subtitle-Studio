#!/usr/bin/env python3
"""Build an owner-review packet for NLE canonical load-owner cutover."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.audit_nle_persistence_cutover import (
    build_nle_persistence_cutover_report,
    write_nle_persistence_cutover_report,
)


DEFAULT_AUDIT_DIR = "output/manual_verification/latest/nle_canonical_load_owner_audit"

DECISION_ROWS = (
    {
        "id": "top_level_nle_as_canonical_load_owner",
        "label": "Top-level nle as canonical load owner",
        "current_owner": "legacy_editor_state",
        "target_owner": "top_level_nle",
        "blocker": "top_level_nle_shadow_not_canonical_load_owner",
    },
    {
        "id": "nle_snapshot_as_canonical_load_source",
        "label": "nle_snapshot as canonical load source",
        "current_owner": "legacy_editor_state",
        "target_owner": "nle_snapshot",
        "blocker": "making nle_snapshot the canonical load source",
    },
    {
        "id": "runtime_nle_project_state_persisted",
        "label": "_nle_project_state persisted on disk",
        "current_owner": "runtime_only",
        "target_owner": "persisted_nle_project_state",
        "blocker": "runtime_nle_project_state_must_remain_runtime_only",
    },
    {
        "id": "legacy_editor_state_compatibility_removed",
        "label": "Legacy editor_state compatibility removal",
        "current_owner": "legacy_editor_state_required",
        "target_owner": "nle_disk_format_only",
        "blocker": "legacy_disk_shape_required_for_full_cutover",
    },
)


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value
    return root / value


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _decision_matrix(audit: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = set(str(item) for item in (audit.get("blockers") or []))
    remaining_gates = set(str(item) for item in (audit.get("remaining_full_cutover_gates") or []))
    rows: list[dict[str, Any]] = []
    for row in DECISION_ROWS:
        blocker = row["blocker"]
        rows.append(
            {
                "id": row["id"],
                "label": row["label"],
                "current_owner": row["current_owner"],
                "target_owner": row["target_owner"],
                "evidence_ready": bool(audit.get("prep_ready")),
                "owner_approval_required": True,
                "canonical_change_allowed": False,
                "disk_format_cutover_allowed": False,
                "rollback_boundary_required": True,
                "blocking_reason": blocker,
                "blocker_present": blocker in blockers or blocker in remaining_gates,
                "focused_proof_required_after_any_change": [
                    "same_project_save_reopen_parity",
                    "nle_and_legacy_row_identity_parity",
                    "final_invalid_non_monotonic_overlap_0_0_0",
                    "render_export_parity",
                    "direct_srt_precedence_preserved",
                    "legacy_project_compatibility_preserved",
                ],
            }
        )
    return rows


def build_review_packet_from_audit(
    audit: dict[str, Any],
    *,
    root: Path = ROOT,
    output_dir: str | Path | None = None,
    audit_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    output_path = _resolve(
        root,
        output_dir or "output/manual_verification/latest/nle_canonical_load_owner_review_packet",
    )
    checks = audit.get("checks") if isinstance(audit.get("checks"), dict) else {}
    top_level = checks.get("approved_top_level_nle_shadow") if isinstance(checks.get("approved_top_level_nle_shadow"), dict) else {}
    runtime = checks.get("runtime_roundtrip") if isinstance(checks.get("runtime_roundtrip"), dict) else {}
    approved = checks.get("approved_snapshot_persistence") if isinstance(checks.get("approved_snapshot_persistence"), dict) else {}
    corrupted = checks.get("corrupted_snapshot_readback") if isinstance(checks.get("corrupted_snapshot_readback"), dict) else {}
    roughcut = checks.get("roughcut_sidecar_readback") if isinstance(checks.get("roughcut_sidecar_readback"), dict) else {}
    render_export = checks.get("render_export_parity") if isinstance(checks.get("render_export_parity"), dict) else {}

    current_owner = str(top_level.get("canonical_load_owner") or "legacy_editor_state")
    canonical_unchanged = current_owner == "legacy_editor_state"
    packet = {
        "schema": "ai_subtitle_studio.nle_canonical_load_owner_review_packet.v1",
        "root": str(root),
        "output_dir": str(output_path),
        "source_audit_dir": str(_resolve(root, audit_dir or DEFAULT_AUDIT_DIR)),
        "status": "owner_review_required_blocked",
        "not_runtime_change": True,
        "canonical_load_owner_unchanged": canonical_unchanged,
        "current_canonical_load_owner": current_owner,
        "canonical_load_owner_change_allowed": False,
        "disk_format_cutover_allowed": False,
        "owner_review_required": True,
        "evidence_summary": {
            "audit_schema": audit.get("schema"),
            "audit_status": audit.get("status"),
            "prep_ready": bool(audit.get("prep_ready")),
            "persistence_cutover_ready": bool(audit.get("persistence_cutover_ready")),
            "blockers": list(audit.get("blockers") or []),
            "remaining_full_cutover_gates": list(audit.get("remaining_full_cutover_gates") or []),
            "operation_roundtrip_all_passed": bool(audit.get("operation_roundtrip_all_passed")),
            "operation_roundtrip_family_count": audit.get("operation_roundtrip_family_count"),
            "render_export_parity_passed": bool(audit.get("render_export_parity_passed")),
            "top_level_nle_shadow_ready": bool(audit.get("top_level_nle_shadow_ready")),
            "runtime_roundtrip": {
                "loaded_runtime_state": bool(runtime.get("loaded_runtime_state")),
                "storage_clean": bool(runtime.get("storage_clean")),
                "storage_has_runtime_nle_key": bool(runtime.get("storage_has_runtime_nle_key")),
                "storage_has_nle": bool(runtime.get("storage_has_nle")),
                "storage_has_nle_snapshot": bool(runtime.get("storage_has_nle_snapshot")),
            },
            "approved_snapshot_persistence": {
                "ready": bool(approved.get("ready")),
                "snapshot_persisted": bool(approved.get("snapshot_persisted")),
                "legacy_rows_stable": bool(approved.get("legacy_rows_stable")),
                "readback_parity_stable": bool(approved.get("readback_parity_stable")),
            },
            "top_level_nle_shadow": {
                "ready": bool(top_level.get("ready")),
                "storage_has_nle": bool(top_level.get("storage_has_nle")),
                "storage_has_nle_snapshot": bool(top_level.get("storage_has_nle_snapshot")),
                "shadow_schema": str(top_level.get("shadow_schema") or ""),
                "shadow_role": str(top_level.get("shadow_role") or ""),
                "canonical_load_owner": current_owner,
                "runtime_project_state_persisted": bool(top_level.get("runtime_project_state_persisted")),
                "legacy_rows_stable": bool(top_level.get("legacy_rows_stable")),
                "readback_parity_stable": bool(top_level.get("readback_parity_stable")),
            },
            "corrupted_snapshot_readback": {
                "drift_detected": bool(corrupted.get("drift_detected")),
                "legacy_rows_stable": bool(corrupted.get("legacy_rows_stable")),
                "runtime_report_persisted": bool(corrupted.get("runtime_report_persisted")),
            },
            "roughcut_sidecar_readback": {
                "approved_readback_stable": bool(roughcut.get("approved_readback_stable")),
                "corrupted_marker_drift_detected": bool(roughcut.get("corrupted_marker_drift_detected")),
                "render_export_stable": bool(roughcut.get("render_export_stable")),
                "roughcut_sidecar_stable": bool(roughcut.get("roughcut_sidecar_stable")),
            },
            "render_export_parity": {
                "stable": bool(render_export.get("stable")),
                "storage_clean": bool(render_export.get("storage_clean")),
                "invalid_duration_count": render_export.get("invalid_duration_count"),
                "non_monotonic_count": render_export.get("non_monotonic_count"),
                "overlap_count": render_export.get("overlap_count"),
                "max_active_segments": render_export.get("max_active_segments"),
            },
        },
        "decision_matrix": _decision_matrix(audit),
        "remaining_blockers": [
            "owner_approval_for_exact_canonical_load_owner_change",
            "legacy_project_compatibility_proof_for_real_projects",
            "direct_srt_and_roughcut_precedence_proof_after_any_load_owner_change",
            "render_export_parity_after_any_load_owner_change",
            "rollback_commit_boundary_before_any_disk_format_change",
        ],
        "not_included": [
            "runtime_load_owner_change",
            "persisted_nle_project_state",
            "nle_snapshot_as_canonical_load_source",
            "top_level_nle_as_canonical_load_owner",
            "legacy_editor_state_removal",
            "per_pixel_drag_writes",
            "ui_layout_or_label_change",
            "stt_or_cache_default_change",
            "app_store_packaging_signing_upload_or_submission",
        ],
        "interpretation": (
            "This packet converts the existing NLE persistence audit into an owner-review blocker map. "
            "It confirms that shadow NLE metadata is present and parity gates pass, while canonical load "
            "ownership remains legacy_editor_state and full NLE disk-format cutover is still blocked."
        ),
    }
    return packet


def build_review_packet(
    *,
    root: Path = ROOT,
    output_dir: str | Path | None = None,
    audit_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    audit_dir = _resolve(root, audit_output_dir or DEFAULT_AUDIT_DIR)
    audit = build_nle_persistence_cutover_report(output_dir=audit_dir)
    write_nle_persistence_cutover_report(audit_dir, audit)
    return build_review_packet_from_audit(
        audit,
        root=root,
        output_dir=output_dir,
        audit_dir=audit_dir,
    )


def render_markdown(packet: dict[str, Any]) -> str:
    evidence = packet.get("evidence_summary") if isinstance(packet.get("evidence_summary"), dict) else {}
    top_level = evidence.get("top_level_nle_shadow") if isinstance(evidence.get("top_level_nle_shadow"), dict) else {}
    render_export = evidence.get("render_export_parity") if isinstance(evidence.get("render_export_parity"), dict) else {}
    lines = [
        "# NLE Canonical Load Owner Review Packet",
        "",
        "This is an owner-review blocker map. It is not an NLE disk-format cutover.",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Not runtime change: `{packet.get('not_runtime_change')}`",
        f"- Canonical load owner unchanged: `{packet.get('canonical_load_owner_unchanged')}`",
        f"- Current canonical load owner: `{packet.get('current_canonical_load_owner')}`",
        f"- Canonical load owner change allowed by this packet: `{packet.get('canonical_load_owner_change_allowed')}`",
        f"- Disk format cutover allowed by this packet: `{packet.get('disk_format_cutover_allowed')}`",
        f"- Source audit dir: `{packet.get('source_audit_dir')}`",
        "",
        "## Evidence Summary",
        "",
        f"- Prep ready: `{evidence.get('prep_ready')}`",
        f"- Persistence cutover ready: `{evidence.get('persistence_cutover_ready')}`",
        f"- Top-level NLE shadow ready: `{evidence.get('top_level_nle_shadow_ready')}`",
        f"- Operation roundtrip all passed: `{evidence.get('operation_roundtrip_all_passed')}`",
        f"- Operation roundtrip family count: `{evidence.get('operation_roundtrip_family_count')}`",
        f"- Render/export parity passed: `{evidence.get('render_export_parity_passed')}`",
        f"- Shadow schema/role: `{top_level.get('shadow_schema')}` / `{top_level.get('shadow_role')}`",
        f"- Shadow canonical load owner: `{top_level.get('canonical_load_owner')}`",
        f"- Runtime project state on disk: `{top_level.get('runtime_project_state_persisted')}`",
        f"- Render/export final invalid/non-monotonic/overlap: `{render_export.get('invalid_duration_count')}` / `{render_export.get('non_monotonic_count')}` / `{render_export.get('overlap_count')}`",
        f"- Render/export max active: `{render_export.get('max_active_segments')}`",
        "",
        "## Decision Matrix",
        "",
        "| Candidate | Current Owner | Target Owner | Evidence Ready | Owner Approval Required | Canonical Change Allowed |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in packet.get("decision_matrix") or []:
        lines.append(
            "| {label} | `{current_owner}` | `{target_owner}` | `{evidence_ready}` | `{owner_approval_required}` | `{canonical_change_allowed}` |".format(
                label=row.get("label"),
                current_owner=row.get("current_owner"),
                target_owner=row.get("target_owner"),
                evidence_ready=row.get("evidence_ready"),
                owner_approval_required=row.get("owner_approval_required"),
                canonical_change_allowed=row.get("canonical_change_allowed"),
            )
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{item}`" for item in evidence.get("blockers") or [])
    lines.extend(["", "## Remaining Blockers", ""])
    lines.extend(f"- `{item}`" for item in packet.get("remaining_blockers") or [])
    lines.extend(["", "## Not Included", ""])
    lines.extend(f"- `{item}`" for item in packet.get("not_included") or [])
    lines.extend(["", packet.get("interpretation") or "", ""])
    return "\n".join(lines)


def write_review_packet(packet: dict[str, Any], output_dir: str | Path | None = None) -> list[Path]:
    output_path = _resolve(Path(packet["root"]), output_dir or packet["output_dir"])
    packet = dict(packet)
    packet["output_dir"] = str(output_path)
    written = [
        output_path / "nle_canonical_load_owner_review_packet.json",
        output_path / "nle_canonical_load_owner_review_packet.md",
        output_path / "decision_matrix.json",
    ]
    _write_json(written[0], packet)
    _write_text(written[1], render_markdown(packet))
    _write_json(written[2], packet["decision_matrix"])
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--audit-output-dir", default=DEFAULT_AUDIT_DIR)
    args = parser.parse_args(argv)

    packet = build_review_packet(output_dir=args.output_dir, audit_output_dir=args.audit_output_dir)
    written = write_review_packet(packet, args.output_dir)
    print(
        json.dumps(
            {
                "output_dir": str(_resolve(ROOT, args.output_dir)),
                "source_audit_dir": packet["source_audit_dir"],
                "status": packet["status"],
                "canonical_load_owner_unchanged": packet["canonical_load_owner_unchanged"],
                "canonical_load_owner_change_allowed": packet["canonical_load_owner_change_allowed"],
                "disk_format_cutover_allowed": packet["disk_format_cutover_allowed"],
                "written": [str(path) for path in written],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
