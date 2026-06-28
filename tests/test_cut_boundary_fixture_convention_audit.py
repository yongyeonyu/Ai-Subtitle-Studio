from __future__ import annotations

from pathlib import Path

from tools.audit_cut_boundary_fixture_convention import build_fixture_convention_audit


def _window(
    target: int,
    *,
    classification: str,
    expected_left: int,
    expected_right: int,
    strongest_left: int,
    strongest_right: int,
    strongest_detected: bool,
) -> dict[str, object]:
    return {
        "target_frame": target,
        "classification": classification,
        "expected_transition": {
            "left_frame": expected_left,
            "right_frame": expected_right,
        },
        "strongest_transition": {
            "left_frame": strongest_left,
            "right_frame": strongest_right,
        },
        "strongest_offset_from_target": strongest_right - target,
        "target_detected": classification == "target_transition_detected",
        "strongest_detected": strongest_detected,
        "target_detection_gap": classification != "target_transition_detected",
    }


def _semantics_payload(*windows: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "ai_subtitle_studio.cut_boundary_frame_semantics_audit.v1",
        "media_path": "/fixture.mp4",
        "blocked_runtime_changes": ["threshold_relaxation"],
        "windows": list(windows),
    }


def test_fixture_convention_audit_flags_neighbor_before_target(tmp_path: Path) -> None:
    target = 2677
    audit = build_fixture_convention_audit(
        _semantics_payload(
            _window(
                target,
                classification="detected_neighbor_before_target",
                expected_left=2676,
                expected_right=2677,
                strongest_left=2675,
                strongest_right=2676,
                strongest_detected=True,
            )
        ),
        pair_metrics_by_target={
            target: {
                "expected_pair_metrics": {
                    "available": True,
                    "left_frame": 2676,
                    "right_frame": 2677,
                    "mean_abs_delta": 3.2,
                    "max_abs_delta": 30,
                    "changed_pixel_ratio": 0.1,
                },
                "strongest_pair_metrics": {
                    "available": True,
                    "left_frame": 2675,
                    "right_frame": 2676,
                    "mean_abs_delta": 61.4,
                    "max_abs_delta": 255,
                    "changed_pixel_ratio": 0.92,
                },
            }
        },
        contact_sheets_by_target={target: "target_2677_frame_contact_sheet.png"},
        output_dir=tmp_path,
    )
    row = audit["windows"][0]

    assert audit["fixture_label_or_boundary_convention_review_required"] is True
    assert audit["label_or_boundary_convention_review_count"] == 1
    assert audit["detector_evidence_required_count"] == 0
    assert row["expected_pair"] == "2676->2677"
    assert row["strongest_pair"] == "2675->2676"
    assert row["strongest_to_expected_mean_delta_ratio"] > 10
    assert row["next_action"] == "verify_fixture_label_or_boundary_frame_convention_before_threshold_tuning"


def test_fixture_convention_audit_keeps_plain_detection_gap_as_detector_work(tmp_path: Path) -> None:
    target = 2766
    audit = build_fixture_convention_audit(
        _semantics_payload(
            _window(
                target,
                classification="target_detection_gap",
                expected_left=2765,
                expected_right=2766,
                strongest_left=2768,
                strongest_right=2769,
                strongest_detected=False,
            )
        ),
        output_dir=tmp_path,
    )
    row = audit["windows"][0]

    assert audit["fixture_label_or_boundary_convention_review_required"] is False
    assert audit["label_or_boundary_convention_review_count"] == 0
    assert audit["detector_evidence_required_count"] == 1
    assert row["detector_evidence_required"] is True
    assert row["next_action"] == "improve_detector_evidence_or_fixture_truth_before_threshold_tuning"


def test_fixture_convention_markdown_lists_contact_sheet_and_guardrails(tmp_path: Path) -> None:
    target = 2677
    build_fixture_convention_audit(
        _semantics_payload(
            _window(
                target,
                classification="detected_neighbor_before_target",
                expected_left=2676,
                expected_right=2677,
                strongest_left=2675,
                strongest_right=2676,
                strongest_detected=True,
            )
        ),
        contact_sheets_by_target={target: "target_2677_frame_contact_sheet.png"},
        output_dir=tmp_path,
    )

    markdown = (tmp_path / "cut_boundary_fixture_convention_audit.md").read_text(encoding="utf-8")
    assert "Cut Boundary Fixture Convention Audit" in markdown
    assert "target_2677_frame_contact_sheet.png" in markdown
    assert "Do not apply `threshold_relaxation`" in markdown
    assert "Do not apply `ui_or_qml_change`" in markdown
