#!/usr/bin/env python3
"""Classify frame-semantics gaps from a visual cut-boundary window audit."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_json import dumps_json_bytes

DEFAULT_BLOCKED_RUNTIME_CHANGES = [
    "threshold_relaxation",
    "subtitle_quality_policy_change",
    "stt_policy_change",
    "ui_or_qml_change",
    "persisted_nle_disk_fields",
    "app_store_work",
]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    return bool(value)


def _target_row(window: dict[str, Any]) -> dict[str, Any]:
    row = window.get("target_row")
    return dict(row) if isinstance(row, dict) else {}


def _best_row(window: dict[str, Any]) -> dict[str, Any]:
    rows = window.get("ranked_candidates")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and _as_int(row.get("right_frame")) == _as_int(window.get("best_frame")):
                return dict(row)
    best_frame = _as_int(window.get("best_frame"))
    return {
        "left_frame": best_frame - 1 if best_frame else 0,
        "right_frame": best_frame,
        "candidate_detected": _as_bool(window.get("best_detected")),
        "score": _as_float(window.get("best_score")),
    }


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "left_frame": _as_int(row.get("left_frame")),
        "right_frame": _as_int(row.get("right_frame")),
        "candidate_frame": _as_int(row.get("candidate_frame") or row.get("right_frame")),
        "candidate_sec": _as_float(row.get("candidate_sec")),
        "detected": _as_bool(row.get("candidate_detected")),
        "score": _as_float(row.get("score")),
        "region_hits": _as_int(row.get("region_hits")),
        "pixel_ratio": _as_float(row.get("pixel_ratio")),
        "edge_ratio": _as_float(row.get("edge_ratio")),
        "motion_jump": _as_float(row.get("motion_jump")),
        "backend": str(row.get("backend") or ""),
        "metrics_backend": str(row.get("metrics_backend") or ""),
    }


def _classify_window(window: dict[str, Any]) -> dict[str, Any]:
    target = _as_int(window.get("target_frame"))
    target_detected = _as_bool(window.get("target_detected"))
    best_frame = _as_int(window.get("best_frame"))
    best_detected = _as_bool(window.get("best_detected"))
    offset = best_frame - target if best_frame else 0
    target = max(0, target)
    target_row = _target_row(window)
    best_row = _best_row(window)
    detected_neighbor_conflict = bool(best_detected and best_frame and best_frame != target and not target_detected)
    target_detection_gap = not target_detected
    if target_detected and best_frame == target:
        classification = "target_transition_detected"
        next_action = "no_frame_semantics_review_required"
    elif detected_neighbor_conflict and offset < 0:
        classification = "detected_neighbor_before_target"
        next_action = "verify_fixture_label_or_boundary_frame_convention_before_threshold_tuning"
    elif detected_neighbor_conflict and offset > 0:
        classification = "detected_neighbor_after_target"
        next_action = "verify_fixture_label_or_decoder_frame_index_before_threshold_tuning"
    elif target_detection_gap:
        classification = "target_detection_gap"
        next_action = "improve_detector_evidence_or_fixture_truth_before_threshold_tuning"
    else:
        classification = "target_not_best_but_detected"
        next_action = "review_rank_gap_before_threshold_tuning"
    frame_semantics_review_required = classification in {
        "detected_neighbor_before_target",
        "detected_neighbor_after_target",
    }
    detector_tuning_candidate = bool(target_detection_gap and not frame_semantics_review_required)
    return {
        "target_frame": target,
        "expected_transition": {
            "left_frame": target - 1 if target > 0 else 0,
            "right_frame": target,
            "boundary_frame": target,
            "semantic": "boundary_frame_is_transition_right_frame",
        },
        "target_transition": _row_summary(target_row),
        "target_detected": target_detected,
        "target_rank_by_score": _as_int(window.get("target_rank_by_score")),
        "target_score": _as_float(window.get("target_score")),
        "strongest_transition": _row_summary(best_row),
        "strongest_frame": best_frame,
        "strongest_detected": best_detected,
        "strongest_offset_from_target": offset,
        "target_is_best": _as_bool(window.get("target_is_best")),
        "detected_neighbor_conflict": detected_neighbor_conflict,
        "target_detection_gap": target_detection_gap,
        "frame_semantics_review_required": frame_semantics_review_required,
        "detector_tuning_candidate": detector_tuning_candidate,
        "classification": classification,
        "next_action": next_action,
    }


def build_frame_semantics_audit(
    visual_window_audit: dict[str, Any],
    *,
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    windows = [
        _classify_window(window)
        for window in list(visual_window_audit.get("windows") or [])
        if isinstance(window, dict)
    ]
    blocked = list(visual_window_audit.get("blocked_runtime_changes") or [])
    for item in DEFAULT_BLOCKED_RUNTIME_CHANGES:
        if item not in blocked:
            blocked.append(item)
    semantic_mismatch_count = sum(1 for row in windows if row.get("frame_semantics_review_required"))
    target_detection_gap_count = sum(1 for row in windows if row.get("target_detection_gap"))
    detected_neighbor_conflict_count = sum(1 for row in windows if row.get("detected_neighbor_conflict"))
    detector_tuning_candidate_count = sum(1 for row in windows if row.get("detector_tuning_candidate"))
    review_required = bool(semantic_mismatch_count or target_detection_gap_count)
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_frame_semantics_audit.v1",
        "note": "Read-only audit. It classifies target-frame versus strongest-transition semantics from an existing visual-window audit.",
        "source_visual_window_audit_path": str(source_path) if source_path else "",
        "source_schema": str(visual_window_audit.get("schema") or ""),
        "media_path": str(visual_window_audit.get("media_path") or ""),
        "target_frames": [int(frame) for frame in list(visual_window_audit.get("target_frames") or [])],
        "strict_targets_detected": bool(visual_window_audit.get("strict_targets_detected")),
        "frame_semantics_review_required": review_required,
        "semantic_mismatch_count": semantic_mismatch_count,
        "target_detection_gap_count": target_detection_gap_count,
        "detected_neighbor_conflict_count": detected_neighbor_conflict_count,
        "detector_tuning_candidate_count": detector_tuning_candidate_count,
        "runtime_change_allowed": False,
        "blocked_runtime_changes": blocked,
        "windows": windows,
        "elapsed_sec": round(time.time() - started, 3),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "cut_boundary_frame_semantics_audit.json"
        md_path = output_dir / "cut_boundary_frame_semantics_audit.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Frame Semantics Audit",
        "",
        f"- Frame semantics review required: `{bool(manifest.get('frame_semantics_review_required'))}`",
        f"- Semantic mismatch count: `{manifest.get('semantic_mismatch_count')}`",
        f"- Target detection gap count: `{manifest.get('target_detection_gap_count')}`",
        f"- Detected neighbor conflict count: `{manifest.get('detected_neighbor_conflict_count')}`",
        f"- Detector tuning candidate count: `{manifest.get('detector_tuning_candidate_count')}`",
        f"- Strict targets detected in source audit: `{bool(manifest.get('strict_targets_detected'))}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- Source audit: `{manifest.get('source_visual_window_audit_path')}`",
        f"- Media: `{manifest.get('media_path')}`",
        "",
        "## Targets",
        "",
        "| Target | Expected transition | Target detected | Target rank | Strongest transition | Offset | Strongest detected | Classification | Next action |",
        "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- |",
    ]
    for row in list(manifest.get("windows") or []):
        if not isinstance(row, dict):
            continue
        expected = row.get("expected_transition") or {}
        strongest = row.get("strongest_transition") or {}
        lines.append(
            "| {target} | {expected_left}->{expected_right} | {target_detected} | {rank} | {best_left}->{best_right} | {offset} | {best_detected} | {classification} | {next_action} |".format(
                target=row.get("target_frame"),
                expected_left=expected.get("left_frame"),
                expected_right=expected.get("right_frame"),
                target_detected=bool(row.get("target_detected")),
                rank=row.get("target_rank_by_score"),
                best_left=strongest.get("left_frame"),
                best_right=strongest.get("right_frame"),
                offset=row.get("strongest_offset_from_target"),
                best_detected=bool(row.get("strongest_detected")),
                classification=row.get("classification"),
                next_action=row.get("next_action"),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify frame semantics from a cut-boundary visual-window audit JSON.")
    parser.add_argument("visual_window_audit_json", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_path = args.visual_window_audit_json
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    manifest = build_frame_semantics_audit(payload, source_path=source_path, output_dir=args.output_dir)
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 1 if manifest.get("frame_semantics_review_required") else 0


if __name__ == "__main__":
    raise SystemExit(main())
