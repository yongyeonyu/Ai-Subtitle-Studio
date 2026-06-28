from __future__ import annotations

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from tools.audit_cut_boundary_detector_evidence_robustness import build_detector_evidence_robustness_audit


def test_detector_evidence_robustness_classifies_weak_target_without_threshold_relaxation(tmp_path: Path) -> None:
    dark = np.zeros((120, 160, 3), dtype=np.uint8)
    weak = dark.copy()
    weak[2:6, 2:6, :] = 8
    strong = dark.copy()
    strong[:, :80, :] = 255
    frame_map = {
        10: dark,
        11: weak,
        20: dark,
        21: strong,
    }

    audit = build_detector_evidence_robustness_audit(
        frame_map,
        pairs=[(10, 11), (20, 21)],
        modes=["fast4", "full9"],
        widths=[160, 320],
        output_dir=tmp_path,
    )

    assert audit["runtime_change_allowed"] is False
    assert audit["threshold_relaxation_allowed"] is False
    assert audit["weak_visual_change_count"] == 1
    assert audit["detector_tuning_candidate_count"] == 0
    assert audit["detected_target_count"] == 1
    assert audit["pairs"][0]["classification"] == "weak_visual_change_not_threshold_candidate"
    assert audit["pairs"][1]["classification"] == "visual_detection_available"
    assert (tmp_path / "cut_boundary_detector_evidence_robustness.json").is_file()
    assert (tmp_path / "cut_boundary_detector_evidence_robustness.md").is_file()


def test_detector_evidence_robustness_markdown_keeps_guardrails(tmp_path: Path) -> None:
    dark = np.zeros((90, 120, 3), dtype=np.uint8)
    weak = dark.copy()
    weak[1:4, 1:4, :] = 6

    build_detector_evidence_robustness_audit(
        {1: dark, 2: weak},
        pairs=[(1, 2)],
        modes=["fast4"],
        widths=[120],
        output_dir=tmp_path,
    )

    markdown = (tmp_path / "cut_boundary_detector_evidence_robustness.md").read_text(encoding="utf-8")
    assert "Detector Evidence Robustness" in markdown
    assert "Weak visual change count: `1`" in markdown
    assert "Threshold relaxation allowed: `False`" in markdown
    assert "weak_visual_change_not_threshold_candidate" in markdown
    assert "Do not apply `threshold_relaxation`" in markdown
    assert "Do not apply `ui_or_qml_change`" in markdown
