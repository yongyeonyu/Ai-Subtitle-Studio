from __future__ import annotations

from pathlib import Path

from tools.audit_cut_boundary_fixture_target_correction import build_fixture_target_correction_audit


def _fixture_convention_payload() -> dict[str, object]:
    return {
        "schema": "ai_subtitle_studio.cut_boundary_fixture_convention_audit.v1",
        "media_path": "/fixture.mp4",
        "blocked_runtime_changes": ["threshold_relaxation"],
        "windows": [
            {
                "target_frame": 2766,
                "classification": "target_detection_gap",
                "expected_pair": "2765->2766",
                "strongest_pair": "2768->2769",
                "strongest_detected": False,
                "detector_evidence_required": True,
                "label_or_boundary_convention_review_required": False,
                "expected_pair_metrics": {"mean_abs_delta": 2.5},
                "strongest_pair_metrics": {"mean_abs_delta": 3.2},
                "strongest_to_expected_mean_delta_ratio": 1.28,
            },
            {
                "target_frame": 2677,
                "classification": "detected_neighbor_before_target",
                "expected_pair": "2676->2677",
                "strongest_pair": "2675->2676",
                "strongest_detected": True,
                "detector_evidence_required": False,
                "label_or_boundary_convention_review_required": True,
                "expected_pair_metrics": {"mean_abs_delta": 2.381499},
                "strongest_pair_metrics": {"mean_abs_delta": 72.849699},
                "strongest_to_expected_mean_delta_ratio": 30.589851,
            },
        ],
    }


def test_fixture_target_correction_rewrites_late_target_to_strongest_boundary(tmp_path: Path) -> None:
    audit = build_fixture_target_correction_audit(
        _fixture_convention_payload(),
        source_path=tmp_path / "convention.json",
        output_dir=tmp_path,
    )

    assert audit["target_correction_required"] is True
    assert audit["target_correction_count"] == 1
    assert audit["detector_evidence_required_count"] == 1
    assert audit["corrected_target_frames"] == [2766, 2676]
    assert audit["corrected_target_frames_csv"] == "2766,2676"
    assert audit["corrected_source_fps_pairs_csv"] == "2765:2766,2675:2676"
    corrected = audit["windows"][1]
    assert corrected["original_target_frame"] == 2677
    assert corrected["corrected_target_frame"] == 2676
    assert corrected["correction_status"] == "corrected_to_strongest_detected_boundary"
    assert (tmp_path / "cut_boundary_fixture_target_correction.json").is_file()
    assert (tmp_path / "cut_boundary_fixture_target_correction.md").is_file()


def test_fixture_target_correction_markdown_keeps_guardrails(tmp_path: Path) -> None:
    build_fixture_target_correction_audit(_fixture_convention_payload(), output_dir=tmp_path)

    markdown = (tmp_path / "cut_boundary_fixture_target_correction.md").read_text(encoding="utf-8")
    assert "Cut Boundary Fixture Target Correction" in markdown
    assert "Corrected target frames: `2766,2676`" in markdown
    assert "2676->2677" in markdown
    assert "2675->2676" in markdown
    assert "Do not apply `threshold_relaxation`" in markdown
    assert "Do not apply `ui_or_qml_change`" in markdown
