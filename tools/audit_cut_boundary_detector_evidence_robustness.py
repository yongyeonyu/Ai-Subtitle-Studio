#!/usr/bin/env python3
"""Audit whether weak fixed-fixture cut targets are detector-tuning candidates."""

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
from core.visual_cut_jump import build_visual_cut_sample, score_visual_cut_pair
from tools.audit_cut_boundary_frame_semantics import DEFAULT_BLOCKED_RUNTIME_CHANGES


DEFAULT_SETTINGS = {
    "scan_cut_pioneer_pipe_score_threshold": 40.0,
    "scan_cut_pioneer_pipe_region_threshold": 18.0,
    "scan_cut_pioneer_pipe_regions_required": 2,
    "scan_cut_pioneer_pipe_pixel_ratio_threshold": 0.18,
    "scan_cut_pioneer_pipe_motion_threshold": 6.0,
}


def _parse_pairs(text: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for chunk in str(text or "").split(","):
        raw = chunk.strip()
        if not raw:
            continue
        left, right = raw.split(":", 1)
        pairs.append((int(left), int(right)))
    return pairs


def _parse_csv(text: str, *, item_type=str) -> list[Any]:
    out: list[Any] = []
    for chunk in str(text or "").split(","):
        raw = chunk.strip()
        if raw:
            out.append(item_type(raw))
    return out


def _read_bgr_frames(media_path: Path, frames: list[int]) -> dict[int, Any]:
    import cv2

    cap = cv2.VideoCapture(str(media_path))
    out: dict[int, Any] = {}
    try:
        if cap is None or not cap.isOpened():
            return out
        for frame_no in sorted(set(int(frame) for frame in frames)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_no))
            ok, frame = cap.read()
            if ok and frame is not None:
                out[int(frame_no)] = frame.copy()
    finally:
        try:
            cap.release()
        except Exception:
            pass
    return out


def _thresholds(settings: dict[str, Any]) -> dict[str, float | int]:
    return {
        "score": max(8.0, float(settings.get("scan_cut_pioneer_pipe_score_threshold", 40.0) or 40.0)),
        "region_hits": max(1, int(settings.get("scan_cut_pioneer_pipe_regions_required", 2) or 2)),
        "pixel_ratio": max(0.04, float(settings.get("scan_cut_pioneer_pipe_pixel_ratio_threshold", 0.18) or 0.18)),
        "motion_jump": max(1.0, float(settings.get("scan_cut_pioneer_pipe_motion_threshold", 6.0) or 6.0)),
        "region_score": max(4.0, float(settings.get("scan_cut_pioneer_pipe_region_threshold", 18.0) or 18.0)),
    }


def _detected(metrics: dict[str, Any], thresholds: dict[str, float | int]) -> bool:
    score = float(metrics.get("score", 0.0) or 0.0)
    region_hits = int(metrics.get("region_hits", 0) or 0)
    pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
    motion_jump = float(metrics.get("motion_jump", 0.0) or 0.0)
    return bool(
        score >= float(thresholds["score"])
        and region_hits >= int(thresholds["region_hits"])
        and (pixel_ratio >= float(thresholds["pixel_ratio"]) or motion_jump >= float(thresholds["motion_jump"]))
    )


def _classify_pair(best: dict[str, Any], *, detected_any_mode: bool, thresholds: dict[str, float | int]) -> str:
    if detected_any_mode:
        return "visual_detection_available"
    best_score = float(best.get("score", 0.0) or 0.0)
    best_hits = int(best.get("region_hits", 0) or 0)
    best_pixel = float(best.get("pixel_ratio", 0.0) or 0.0)
    best_motion = float(best.get("motion_jump", 0.0) or 0.0)
    if (
        best_score < float(thresholds["score"]) * 0.25
        and best_hits == 0
        and best_pixel < float(thresholds["pixel_ratio"]) * 0.5
        and best_motion < float(thresholds["motion_jump"]) * 0.5
    ):
        return "weak_visual_change_not_threshold_candidate"
    return "detector_tuning_candidate"


def build_detector_evidence_robustness_audit(
    frame_map: dict[int, Any],
    *,
    pairs: list[tuple[int, int]],
    modes: list[str],
    widths: list[int],
    settings: dict[str, Any] | None = None,
    media_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    import cv2

    started = time.time()
    merged_settings = dict(DEFAULT_SETTINGS)
    merged_settings.update(settings or {})
    thresholds = _thresholds(merged_settings)
    pair_reports: list[dict[str, Any]] = []

    for left_frame, right_frame in pairs:
        rows: list[dict[str, Any]] = []
        left = frame_map.get(int(left_frame))
        right = frame_map.get(int(right_frame))
        for mode in modes:
            for width in widths:
                if left is None or right is None:
                    metrics = {
                        "score": 0.0,
                        "region_hits": 0,
                        "pixel_ratio": 0.0,
                        "edge_ratio": 0.0,
                        "motion_jump": 0.0,
                        "backend": "frame_missing",
                    }
                    detected = False
                else:
                    prev_sample = build_visual_cut_sample(left, cv2, mode=mode, width=int(width), settings=merged_settings)
                    next_sample = build_visual_cut_sample(right, cv2, mode=mode, width=int(width), settings=merged_settings)
                    metrics = score_visual_cut_pair(
                        prev_sample,
                        next_sample,
                        cv2,
                        settings=merged_settings,
                        region_threshold=float(thresholds["region_score"]),
                    )
                    detected = _detected(metrics, thresholds)
                rows.append(
                    {
                        "mode": str(mode),
                        "width": int(width),
                        "detected": bool(detected),
                        "score": round(float(metrics.get("score", 0.0) or 0.0), 3),
                        "region_hits": int(metrics.get("region_hits", 0) or 0),
                        "gray_mean": round(float(metrics.get("gray_mean", 0.0) or 0.0), 4),
                        "pixel_ratio": round(float(metrics.get("pixel_ratio", 0.0) or 0.0), 6),
                        "edge_ratio": round(float(metrics.get("edge_ratio", 0.0) or 0.0), 6),
                        "motion_jump": round(float(metrics.get("motion_jump", 0.0) or 0.0), 4),
                        "backend": str(metrics.get("backend", "") or ""),
                        "metrics_backend": str(metrics.get("metrics_backend", "") or ""),
                    }
                )
        best = max(rows, key=lambda row: float(row.get("score", 0.0) or 0.0), default={})
        detected_any = any(bool(row.get("detected")) for row in rows)
        classification = _classify_pair(best, detected_any_mode=detected_any, thresholds=thresholds)
        pair_reports.append(
            {
                "left_frame": int(left_frame),
                "right_frame": int(right_frame),
                "target_frame": int(right_frame),
                "frame_available": bool(left is not None and right is not None),
                "detected_any_mode": bool(detected_any),
                "classification": classification,
                "best": best,
                "rows": rows,
            }
        )

    weak_count = sum(1 for row in pair_reports if row.get("classification") == "weak_visual_change_not_threshold_candidate")
    tuning_count = sum(1 for row in pair_reports if row.get("classification") == "detector_tuning_candidate")
    detected_count = sum(1 for row in pair_reports if row.get("classification") == "visual_detection_available")
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_detector_evidence_robustness.v1",
        "note": "Read-only audit. It checks whether missed fixed-fixture targets are plausible detector-threshold candidates across scorer modes and widths.",
        "media_path": str(media_path or ""),
        "target_frames": [int(pair[1]) for pair in pairs],
        "source_fps_pairs": [f"{int(pair[0])}:{int(pair[1])}" for pair in pairs],
        "modes": list(modes),
        "widths": [int(width) for width in widths],
        "thresholds": thresholds,
        "detected_target_count": detected_count,
        "weak_visual_change_count": weak_count,
        "detector_tuning_candidate_count": tuning_count,
        "runtime_change_allowed": False,
        "threshold_relaxation_allowed": False,
        "blocked_runtime_changes": list(DEFAULT_BLOCKED_RUNTIME_CHANGES),
        "pairs": pair_reports,
        "elapsed_sec": round(time.time() - started, 3),
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "cut_boundary_detector_evidence_robustness.json"
        md_path = output_dir / "cut_boundary_detector_evidence_robustness.md"
        json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
        manifest["artifact_path"] = str(json_path)
        _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Detector Evidence Robustness Audit",
        "",
        f"- Detected target count: `{manifest.get('detected_target_count')}`",
        f"- Weak visual change count: `{manifest.get('weak_visual_change_count')}`",
        f"- Detector tuning candidate count: `{manifest.get('detector_tuning_candidate_count')}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- Threshold relaxation allowed: `{bool(manifest.get('threshold_relaxation_allowed'))}`",
        f"- Target frames: `{','.join(str(frame) for frame in manifest.get('target_frames', []))}`",
        f"- Modes: `{','.join(str(mode) for mode in manifest.get('modes', []))}`",
        f"- Widths: `{','.join(str(width) for width in manifest.get('widths', []))}`",
        f"- Media: `{manifest.get('media_path')}`",
        "",
        "## Pairs",
        "",
        "| Target | Classification | Detected any mode | Best mode | Best width | Best score | Best hits | Best pixel | Best motion |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for pair in list(manifest.get("pairs") or []):
        if not isinstance(pair, dict):
            continue
        best = pair.get("best") if isinstance(pair.get("best"), dict) else {}
        lines.append(
            "| {target} | {classification} | {detected} | {mode} | {width} | {score} | {hits} | {pixel} | {motion} |".format(
                target=pair.get("target_frame"),
                classification=pair.get("classification"),
                detected=bool(pair.get("detected_any_mode")),
                mode=best.get("mode", ""),
                width=best.get("width", ""),
                score=best.get("score", ""),
                hits=best.get("region_hits", ""),
                pixel=best.get("pixel_ratio", ""),
                motion=best.get("motion_jump", ""),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit detector evidence robustness for fixed cut-boundary target frames.")
    parser.add_argument("media", type=Path)
    parser.add_argument("--pairs", default="2765:2766,2675:2676")
    parser.add_argument("--modes", default="fast4,cross5,full9")
    parser.add_argument("--widths", default="320,480,960,1920")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    pairs = _parse_pairs(args.pairs)
    modes = [str(mode) for mode in _parse_csv(args.modes, item_type=str)]
    widths = [int(width) for width in _parse_csv(args.widths, item_type=int)]
    frame_map = _read_bgr_frames(args.media, [frame for pair in pairs for frame in pair])
    manifest = build_detector_evidence_robustness_audit(
        frame_map,
        pairs=pairs,
        modes=modes,
        widths=widths,
        media_path=args.media,
        output_dir=args.output_dir,
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
