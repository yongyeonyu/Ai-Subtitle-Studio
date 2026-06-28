from __future__ import annotations

from pathlib import Path

from tools.audit_cut_boundary_preserved_marker_policy import (
    SPLIT_SNAP_GUARD_TEST,
    build_preserved_marker_policy_audit,
)


def _source_scout_payload() -> dict:
    return {
        "schema": "ai_subtitle_studio.cut_boundary_source_fps_scout.v1",
        "media_path": "fixture.mp4",
        "pairs": [
            {
                "left_frame": 2765,
                "right_frame": 2766,
                "candidate_frame": 2766,
                "visual_candidate_status": "preserved_only",
                "acceptance_basis": "preserved",
                "frame_preserved": True,
                "candidate_detected": False,
            },
            {
                "left_frame": 2675,
                "right_frame": 2676,
                "candidate_frame": 2676,
                "visual_candidate_status": "detected",
                "acceptance_basis": "detected",
                "frame_preserved": True,
                "candidate_detected": True,
            },
        ],
    }


def _robustness_payload(*, first_classification: str = "weak_visual_change_not_threshold_candidate") -> dict:
    return {
        "schema": "ai_subtitle_studio.cut_boundary_detector_evidence_robustness.v1",
        "media_path": "fixture.mp4",
        "pairs": [
            {
                "target_frame": 2766,
                "classification": first_classification,
                "detected_any_mode": False,
                "best": {
                    "score": 3.812,
                    "region_hits": 0,
                    "pixel_ratio": 0.034849,
                    "motion_jump": 1.315,
                },
            },
            {
                "target_frame": 2676,
                "classification": "visual_detection_available",
                "detected_any_mode": True,
                "best": {
                    "score": 72.293,
                    "region_hits": 4,
                    "pixel_ratio": 0.884247,
                    "motion_jump": 65.37,
                },
            },
        ],
    }


def test_preserved_marker_policy_promotes_weak_preserved_frame_to_marker_policy(tmp_path: Path) -> None:
    audit = build_preserved_marker_policy_audit(
        _source_scout_payload(),
        _robustness_payload(),
        source_fps_scout_path=Path("source_fps_scout.json"),
        detector_robustness_path=Path("robustness.json"),
        output_dir=tmp_path,
    )

    assert audit["passed"] is True
    assert audit["preserved_marker_policy_required"] is True
    assert audit["preserved_marker_frames"] == [2766]
    assert audit["visual_marker_frames"] == [2676]
    assert audit["review_required_frames"] == []
    assert audit["threshold_relaxation_allowed"] is False
    assert audit["runtime_change_allowed"] is False
    assert audit["cut_boundary_marker_contract"]["confirmed_cuts_are_point_evidence"] is True
    assert audit["cut_boundary_marker_contract"]["marker_not_clip_span"] is True
    assert audit["final_subtitle_guard"]["split_snap_guard_test"] == SPLIT_SNAP_GUARD_TEST
    markers = {row["target_frame"]: row for row in audit["markers"]}
    assert markers[2766]["marker_policy"] == "preserved_marker_required"
    assert markers[2676]["marker_policy"] == "visual_marker_confirmed"
    assert (tmp_path / "cut_boundary_preserved_marker_policy.json").is_file()
    assert (tmp_path / "cut_boundary_preserved_marker_policy.md").is_file()


def test_preserved_marker_policy_blocks_detector_tuning_review_as_incomplete(tmp_path: Path) -> None:
    audit = build_preserved_marker_policy_audit(
        _source_scout_payload(),
        _robustness_payload(first_classification="detector_tuning_candidate"),
        output_dir=tmp_path,
    )

    assert audit["passed"] is False
    assert audit["review_required_frames"] == [2766]
    markers = {row["target_frame"]: row for row in audit["markers"]}
    assert markers[2766]["marker_policy"] == "detector_tuning_review_required"
    assert audit["threshold_relaxation_allowed"] is False


def test_preserved_marker_policy_markdown_keeps_nle_guardrails(tmp_path: Path) -> None:
    build_preserved_marker_policy_audit(
        _source_scout_payload(),
        _robustness_payload(),
        output_dir=tmp_path,
    )

    markdown = (tmp_path / "cut_boundary_preserved_marker_policy.md").read_text(encoding="utf-8")
    assert "Preserved marker policy required: `True`" in markdown
    assert "Preserved marker frames: `2766`" in markdown
    assert "Confirmed cuts are point evidence, not clip spans." in markdown
    assert "must not lower visual detector thresholds" in markdown
    assert "Do not apply `visual_threshold_lowering_from_preserved_marker`" in markdown
    assert SPLIT_SNAP_GUARD_TEST in markdown
