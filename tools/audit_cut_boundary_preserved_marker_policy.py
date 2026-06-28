#!/usr/bin/env python3
"""Audit fixed-fixture cut-boundary targets as NLE marker policy evidence."""

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
from tools.audit_cut_boundary_frame_semantics import DEFAULT_BLOCKED_RUNTIME_CHANGES


SPLIT_SNAP_GUARD_TEST = (
    "tests/test_cut_boundary_fixture_2766_2677.py::"
    "test_confirmed_fixture_cut_frames_split_snap_without_crossing_rows"
)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _blocked_changes(extra: list[str] | None = None) -> list[str]:
    blocked = list(DEFAULT_BLOCKED_RUNTIME_CHANGES)
    for item in extra or []:
        if item not in blocked:
            blocked.append(item)
    return blocked


def _source_rows(source_fps_scout: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in list(source_fps_scout.get("pairs") or []):
        if isinstance(row, dict):
            rows[_as_int(row.get("candidate_frame"))] = row
    return rows


def _robustness_rows(detector_robustness: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    for row in list(detector_robustness.get("pairs") or []):
        if isinstance(row, dict):
            rows[_as_int(row.get("target_frame"))] = row
    return rows


def _classify_marker(source_row: dict[str, Any], robust_row: dict[str, Any]) -> tuple[str, str]:
    source_status = str(source_row.get("visual_candidate_status") or "")
    robust_classification = str(robust_row.get("classification") or "")
    frame_preserved = bool(source_row.get("frame_preserved"))
    source_detected = bool(source_row.get("candidate_detected"))
    robust_detected = bool(robust_row.get("detected_any_mode"))

    if source_status == "detected" or source_detected or robust_detected:
        return ("visual_marker_confirmed", "visual_detection_available")
    if frame_preserved and source_status == "preserved_only" and robust_classification == "weak_visual_change_not_threshold_candidate":
        return ("preserved_marker_required", "weak_visual_change_preserved_frame_grid")
    if frame_preserved and source_status == "metadata_only":
        return ("metadata_marker_preservation_only", "metadata_frame_grid_preserved")
    if robust_classification == "detector_tuning_candidate":
        return ("detector_tuning_review_required", "robustness_audit_requires_review")
    if frame_preserved:
        return ("preserved_marker_review_required", "preserved_but_unclassified")
    return ("missing_marker_evidence", "frame_grid_not_preserved")


def build_preserved_marker_policy_audit(
    source_fps_scout: dict[str, Any],
    detector_robustness: dict[str, Any],
    *,
    source_fps_scout_path: Path | None = None,
    detector_robustness_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    started = time.time()
    source_by_frame = _source_rows(source_fps_scout)
    robust_by_frame = _robustness_rows(detector_robustness)
    frames = sorted(set(source_by_frame) | set(robust_by_frame))
    marker_rows: list[dict[str, Any]] = []

    for frame in frames:
        source_row = source_by_frame.get(frame, {})
        robust_row = robust_by_frame.get(frame, {})
        policy, reason = _classify_marker(source_row, robust_row)
        best = robust_row.get("best") if isinstance(robust_row.get("best"), dict) else {}
        marker_rows.append(
            {
                "target_frame": int(frame),
                "source_pair": f"{_as_int(source_row.get('left_frame'))}:{_as_int(source_row.get('right_frame'))}",
                "source_status": str(source_row.get("visual_candidate_status") or ""),
                "source_acceptance_basis": str(source_row.get("acceptance_basis") or ""),
                "frame_preserved": bool(source_row.get("frame_preserved")),
                "source_candidate_detected": bool(source_row.get("candidate_detected")),
                "detector_classification": str(robust_row.get("classification") or ""),
                "detected_any_mode": bool(robust_row.get("detected_any_mode")),
                "best_score": float(best.get("score", 0.0) or 0.0),
                "best_region_hits": int(best.get("region_hits", 0) or 0),
                "best_pixel_ratio": float(best.get("pixel_ratio", 0.0) or 0.0),
                "best_motion_jump": float(best.get("motion_jump", 0.0) or 0.0),
                "marker_policy": policy,
                "policy_reason": reason,
            }
        )

    preserved_rows = [row for row in marker_rows if row["marker_policy"] == "preserved_marker_required"]
    visual_rows = [row for row in marker_rows if row["marker_policy"] == "visual_marker_confirmed"]
    metadata_rows = [row for row in marker_rows if row["marker_policy"] == "metadata_marker_preservation_only"]
    review_rows = [
        row
        for row in marker_rows
        if row["marker_policy"] in {"detector_tuning_review_required", "preserved_marker_review_required", "missing_marker_evidence"}
    ]
    all_markers_owned = bool(marker_rows) and not review_rows
    blocked = _blocked_changes(
        [
            "clip_span_mapping_for_point_marker",
            "per_pixel_nle_writes",
            "visual_threshold_lowering_from_preserved_marker",
        ]
    )
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_preserved_marker_policy.v1",
        "note": "Read-only audit. It turns fixed-fixture source-fps preservation plus detector robustness evidence into explicit NLE marker policy.",
        "source_fps_scout_path": str(source_fps_scout_path or ""),
        "detector_robustness_path": str(detector_robustness_path or ""),
        "media_path": str(source_fps_scout.get("media_path") or detector_robustness.get("media_path") or ""),
        "target_frames": [int(row["target_frame"]) for row in marker_rows],
        "visual_marker_frames": [int(row["target_frame"]) for row in visual_rows],
        "preserved_marker_frames": [int(row["target_frame"]) for row in preserved_rows],
        "metadata_marker_frames": [int(row["target_frame"]) for row in metadata_rows],
        "review_required_frames": [int(row["target_frame"]) for row in review_rows],
        "marker_policy_required": bool(preserved_rows or metadata_rows),
        "preserved_marker_policy_required": bool(preserved_rows),
        "visual_marker_count": len(visual_rows),
        "preserved_marker_count": len(preserved_rows),
        "metadata_marker_count": len(metadata_rows),
        "review_required_count": len(review_rows),
        "all_target_frames_have_marker_policy": all_markers_owned,
        "passed": all_markers_owned,
        "runtime_change_allowed": False,
        "threshold_relaxation_allowed": False,
        "subtitle_quality_policy_change_allowed": False,
        "stt_policy_change_allowed": False,
        "persisted_nle_disk_fields_allowed": False,
        "cut_boundary_marker_contract": {
            "confirmed_cuts_are_point_evidence": True,
            "marker_not_clip_span": True,
            "marker_can_force_subtitle_split_or_snap": True,
            "per_pixel_nle_writes_allowed": False,
        },
        "final_subtitle_guard": {
            "invalid_duration_count_required": 0,
            "non_monotonic_count_required": 0,
            "overlap_count_required": 0,
            "global_max_active_required": 1,
            "no_rows_cross_confirmed_markers": True,
            "split_snap_guard_test": SPLIT_SNAP_GUARD_TEST,
        },
        "blocked_runtime_changes": blocked,
        "markers": marker_rows,
        "elapsed_sec": round(time.time() - started, 3),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "cut_boundary_preserved_marker_policy.json"
        md_path = output_dir / "cut_boundary_preserved_marker_policy.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Preserved Marker Policy Audit",
        "",
        f"- Passed: `{bool(manifest.get('passed'))}`",
        f"- Marker policy required: `{bool(manifest.get('marker_policy_required'))}`",
        f"- Preserved marker policy required: `{bool(manifest.get('preserved_marker_policy_required'))}`",
        f"- Visual marker frames: `{','.join(str(frame) for frame in manifest.get('visual_marker_frames', []))}`",
        f"- Preserved marker frames: `{','.join(str(frame) for frame in manifest.get('preserved_marker_frames', []))}`",
        f"- Review required frames: `{','.join(str(frame) for frame in manifest.get('review_required_frames', []))}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- Threshold relaxation allowed: `{bool(manifest.get('threshold_relaxation_allowed'))}`",
        f"- Source-fps scout: `{manifest.get('source_fps_scout_path')}`",
        f"- Detector robustness: `{manifest.get('detector_robustness_path')}`",
        "",
        "## Marker Contract",
        "",
        "- Confirmed cuts are point evidence, not clip spans.",
        "- Preserved marker evidence can force subtitle split/snap, but must not lower visual detector thresholds.",
        "- Runtime NLE writes stay at release/commit boundaries, not per pixel.",
        f"- Split/snap guard: `{(manifest.get('final_subtitle_guard') or {}).get('split_snap_guard_test')}`",
        "",
        "## Targets",
        "",
        "| Frame | Policy | Source status | Detector classification | Best score | Best hits | Reason |",
        "| ---: | --- | --- | --- | ---: | ---: | --- |",
    ]
    for row in list(manifest.get("markers") or []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {frame} | {policy} | {source_status} | {detector} | {score} | {hits} | {reason} |".format(
                frame=row.get("target_frame"),
                policy=row.get("marker_policy"),
                source_status=row.get("source_status"),
                detector=row.get("detector_classification"),
                score=row.get("best_score"),
                hits=row.get("best_region_hits"),
                reason=row.get("policy_reason"),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build preserved-marker policy evidence from fixed-fixture audits.")
    parser.add_argument("--source-fps-scout", type=Path, required=True)
    parser.add_argument("--detector-robustness", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_payload = json.loads(args.source_fps_scout.read_text(encoding="utf-8"))
    robustness_payload = json.loads(args.detector_robustness.read_text(encoding="utf-8"))
    manifest = build_preserved_marker_policy_audit(
        source_payload,
        robustness_payload,
        source_fps_scout_path=args.source_fps_scout,
        detector_robustness_path=args.detector_robustness,
        output_dir=args.output_dir,
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0 if bool(manifest.get("passed")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
