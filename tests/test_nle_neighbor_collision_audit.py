import json
import tempfile
from pathlib import Path

from tools.audit_nle_neighbor_collision import (
    build_nle_neighbor_collision_report,
    write_nle_neighbor_collision_report,
)


def test_nle_neighbor_collision_audit_covers_reject_and_trim_paths():
    report = build_nle_neighbor_collision_report()

    assert report["ready"] is True
    assert report["runtime_change_applied"] is False
    assert report["ui_change_applied"] is False
    assert report["persisted_nle_fields_changed"] is False
    assert report["stt_or_cache_default_changed"] is False
    assert report["acceptance_gate"]["final_overlap_count"] == 0
    assert report["acceptance_gate"]["rejected_collision_must_not_mutate_project"] is True
    assert report["acceptance_gate"]["nas_heydealer_required_for_release_regression"] is False
    checks = {row["name"]: row for row in report["checks"]}
    assert set(checks) == {
        "resize_split_required_guard_present",
        "move_commit_routes_through_operation_validation",
        "caption_move_overlap_rejected_without_mutation",
        "caption_move_commit_overlap_rejected_without_mutation",
        "caption_resize_split_required_neighbor_collision_rejected_without_mutation",
        "caption_resize_partial_neighbor_collision_trims_to_shared_boundary",
    }
    assert all(row["passed"] for row in checks.values())
    assert "nle_caption_resize_split_required" in checks[
        "caption_resize_split_required_neighbor_collision_rejected_without_mutation"
    ]["detail"]["error"]


def test_nle_neighbor_collision_audit_writes_reports():
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        report = build_nle_neighbor_collision_report()
        write_nle_neighbor_collision_report(output_dir, report)

        json_path = output_dir / "nle_neighbor_collision_guard.json"
        markdown_path = output_dir / "nle_neighbor_collision_guard.md"
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")

        assert saved["schema"] == report["schema"]
        assert markdown.startswith("# NLE Neighbor Collision Guard Audit")
        assert "Ready: `True`" in markdown
        assert "| caption_move_commit_overlap_rejected_without_mutation | True |" in markdown
        assert "Rejected collision must not mutate project: `True`" in markdown
