from __future__ import annotations

from pathlib import Path

from tools.audit_cut_boundary_frame_semantics import build_frame_semantics_audit


def _row(left: int, right: int, *, detected: bool, score: float) -> dict[str, object]:
    return {
        "left_frame": left,
        "right_frame": right,
        "candidate_frame": right,
        "candidate_sec": right / 60,
        "candidate_detected": detected,
        "score": score,
        "region_hits": 4 if detected else 0,
        "pixel_ratio": 0.8 if detected else 0.02,
        "edge_ratio": 0.2 if detected else 0.03,
        "motion_jump": 60.0 if detected else 0.0,
        "backend": "test",
        "metrics_backend": "test",
    }


def _source_window(target: int, rows: list[dict[str, object]], *, target_detected: bool) -> dict[str, object]:
    ranked = sorted(rows, key=lambda row: (float(row["score"]), int(row["right_frame"])), reverse=True)
    target_row = next(row for row in rows if int(row["right_frame"]) == target)
    target_rank = next(index for index, row in enumerate(ranked, start=1) if int(row["right_frame"]) == target)
    best = ranked[0]
    return {
        "target_frame": target,
        "target_row": target_row,
        "target_detected": target_detected,
        "target_score": float(target_row["score"]),
        "target_rank_by_score": target_rank,
        "target_is_best": target_rank == 1,
        "best_frame": int(best["right_frame"]),
        "best_score": float(best["score"]),
        "best_detected": bool(best["candidate_detected"]),
        "ranked_candidates": ranked,
    }


def _source_payload(window: dict[str, object]) -> dict[str, object]:
    return {
        "schema": "ai_subtitle_studio.cut_boundary_visual_window_audit.v1",
        "media_path": "/fixture.mp4",
        "target_frames": [window["target_frame"]],
        "strict_targets_detected": bool(window["target_detected"]),
        "blocked_runtime_changes": ["threshold_relaxation"],
        "windows": [window],
    }


def test_frame_semantics_audit_accepts_detected_target_transition(tmp_path: Path) -> None:
    window = _source_window(
        10,
        [_row(8, 9, detected=False, score=1.0), _row(9, 10, detected=True, score=70.0)],
        target_detected=True,
    )
    audit = build_frame_semantics_audit(_source_payload(window), source_path=tmp_path / "source.json", output_dir=tmp_path)

    row = audit["windows"][0]
    assert audit["frame_semantics_review_required"] is False
    assert audit["semantic_mismatch_count"] == 0
    assert audit["target_detection_gap_count"] == 0
    assert row["classification"] == "target_transition_detected"
    assert row["expected_transition"]["left_frame"] == 9
    assert row["expected_transition"]["right_frame"] == 10
    assert (tmp_path / "cut_boundary_frame_semantics_audit.json").is_file()
    assert (tmp_path / "cut_boundary_frame_semantics_audit.md").is_file()


def test_frame_semantics_audit_flags_detected_neighbor_before_target(tmp_path: Path) -> None:
    window = _source_window(
        2677,
        [_row(2675, 2676, detected=True, score=71.932), _row(2676, 2677, detected=False, score=1.997)],
        target_detected=False,
    )
    audit = build_frame_semantics_audit(_source_payload(window), output_dir=tmp_path)

    row = audit["windows"][0]
    assert audit["frame_semantics_review_required"] is True
    assert audit["semantic_mismatch_count"] == 1
    assert audit["target_detection_gap_count"] == 1
    assert audit["detected_neighbor_conflict_count"] == 1
    assert row["classification"] == "detected_neighbor_before_target"
    assert row["strongest_offset_from_target"] == -1
    assert row["next_action"] == "verify_fixture_label_or_boundary_frame_convention_before_threshold_tuning"


def test_frame_semantics_markdown_keeps_runtime_guardrails(tmp_path: Path) -> None:
    window = _source_window(
        2766,
        [_row(2765, 2766, detected=False, score=2.059), _row(2768, 2769, detected=False, score=2.715)],
        target_detected=False,
    )
    audit = build_frame_semantics_audit(_source_payload(window), output_dir=tmp_path)

    markdown = (tmp_path / "cut_boundary_frame_semantics_audit.md").read_text(encoding="utf-8")
    assert audit["detector_tuning_candidate_count"] == 1
    assert "Cut Boundary Frame Semantics Audit" in markdown
    assert "Frame semantics review required: `True`" in markdown
    assert "target_detection_gap" in markdown
    assert "Do not apply `threshold_relaxation`" in markdown
    assert "Do not apply `ui_or_qml_change`" in markdown
