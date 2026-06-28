from __future__ import annotations

from pathlib import Path

from core.project.nle_dual_write import CUT_MARKER_POINT_EVIDENCE_POLICY
from tools.audit_nle_cut_marker_point_projection import (
    TARGET_FRAMES,
    build_nle_cut_marker_point_projection_audit,
)


def test_nle_cut_marker_point_projection_audit_passes_and_blocks_clip_span_mapping(tmp_path: Path) -> None:
    audit = build_nle_cut_marker_point_projection_audit(output_dir=tmp_path)

    assert audit["passed"] is True
    assert audit["project_lane"] == "AI Subtitle Studio"
    assert audit["target_frames"] == list(TARGET_FRAMES)
    assert audit["observed_frames"] == [2766, 2676]
    assert audit["marker_projection_policy"] == CUT_MARKER_POINT_EVIDENCE_POLICY
    assert audit["confirmed_cut_markers_are_point_evidence"] is True
    assert audit["clip_span_mapping_allowed"] is False
    assert audit["span_leak_count"] == 0
    assert audit["clip_boundaries_unchanged"] is True
    assert audit["projection_gate"]["invalid_duration_count"] == 0
    assert audit["projection_gate"]["non_monotonic_count"] == 0
    assert audit["projection_gate"]["overlap_count"] == 0
    assert audit["projection_gate"]["max_active_segments"] == 1
    assert audit["operation_metadata"]["clip_span_mapping_allowed"] is False
    assert audit["runtime_metadata"]["dual_write_marker_clip_span_mapping_allowed"] is False
    assert "clip_span_mapping_for_cut_marker_not_allowed" in audit["blocked_scope"]
    assert audit["nas_required_for_runtime_media_acceptance"] is True
    assert (tmp_path / "nle_cut_marker_point_projection.json").is_file()
    assert (tmp_path / "nle_cut_marker_point_projection.md").is_file()


def test_nle_cut_marker_point_projection_markdown_keeps_ai_subtitle_studio_lane(tmp_path: Path) -> None:
    build_nle_cut_marker_point_projection_audit(output_dir=tmp_path)

    markdown = (tmp_path / "nle_cut_marker_point_projection.md").read_text(encoding="utf-8")
    assert "Project lane: `AI Subtitle Studio`" in markdown
    assert "Target frames: `2766,2676`" in markdown
    assert "Confirmed and provisional cut markers are point evidence." in markdown
    assert "must not mutate clip boundaries" in markdown
    assert "clip_span_mapping_for_cut_marker_not_allowed" in markdown
