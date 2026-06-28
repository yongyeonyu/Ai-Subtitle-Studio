import json
import tempfile
from pathlib import Path

from tools.audit_nle_runtime_owner_map import (
    BLOCKED_CANDIDATES,
    COMMIT_BOUNDARY_GUARDS,
    OWNER_EVIDENCE,
    build_nle_runtime_owner_map_report,
    write_nle_runtime_owner_map_report,
)


def test_nle_runtime_owner_map_audit_covers_current_release_commit_sources():
    report = build_nle_runtime_owner_map_report()

    assert report["runtime_owner_map_ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["owner_count"] == len(OWNER_EVIDENCE)
    assert report["covered_owner_count"] == report["owner_count"]
    assert report["missing_owner_count"] == 0
    assert report["commit_boundary_guard_count"] == len(COMMIT_BOUNDARY_GUARDS)
    assert report["covered_commit_boundary_guard_count"] == report["commit_boundary_guard_count"]
    assert report["missing_commit_boundary_guard_count"] == 0
    assert set(report["operation_family_counts"]) == {
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
        "roughcut_range_edit",
    }
    assert report["operation_family_counts"]["caption_text_edit"] >= 6
    assert report["operation_family_counts"]["caption_move"] >= 5
    assert all(owner["status"] == "covered" for owner in report["owners"])
    assert all(not owner["missing_evidence"] for owner in report["owners"])
    assert all(guard["status"] == "covered" for guard in report["commit_boundary_guards"])
    assert all(not guard["missing_evidence"] for guard in report["commit_boundary_guards"])


def test_nle_runtime_owner_map_audit_keeps_blocked_boundaries_explicit():
    report = build_nle_runtime_owner_map_report()
    blocked = {item["candidate_id"]: item for item in report["blocked_candidates"]}

    assert len(blocked) == len(BLOCKED_CANDIDATES)
    assert blocked["persisted_nle_project_fields"]["status"] == "blocked_owner_approval_required"
    assert blocked["per_pixel_drag_nle_writes"]["status"] == "blocked_by_taption_contract"
    assert blocked["qml_or_gpu_timeline_surface_default"]["status"] == "blocked_by_source_app_contract"
    assert report["next_gate"]["status"] == "fresh_owner_map_ready"
    assert "prove_no_per_pixel_nle_write" in report["next_gate"]["required_before_new_runtime_adoption"]
    assert "prove_save_reopen_identity_preserved" in report["next_gate"]["required_before_new_runtime_adoption"]


def test_nle_runtime_owner_map_audit_writes_json_and_markdown_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_runtime_owner_map_report()
        write_nle_runtime_owner_map_report(output_dir, report)

        json_path = output_dir / "nle_runtime_owner_map_audit.json"
        markdown_path = output_dir / "nle_runtime_owner_map_audit.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

    assert saved["schema"] == report["schema"]
    assert markdown.startswith("# NLE Runtime Owner Map Audit")
    assert "## Owner Evidence Matrix" in markdown
    assert "## Commit Boundary Guards" in markdown
    assert "| timeline_center_drag_preview_only_until_release | taption_preview_only_until_release_commit | timeline_body_drag | covered |" in markdown
    assert "| caption_move_center | caption_move | timeline_body_drag | covered |" in markdown
    assert "| caption_text_speaker_change | caption_text_edit | speaker_edit | covered |" in markdown
    assert "| marker_edit_provisional_cut_boundary | marker_edit | provisional_cut_boundary | covered |" in markdown
    assert "## Blocked Candidates" in markdown
