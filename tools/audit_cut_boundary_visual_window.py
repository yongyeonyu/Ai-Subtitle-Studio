#!/usr/bin/env python3
"""Rank visual cut evidence around fixed target boundary frames."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cut_boundary_auto_scan import precise_cut_boundary_timing, resolve_pioneer_pipe_fps, source_fps_parts
from core.frame_time import sec_to_frame
from core.native_json import dumps_json_bytes
from core.visual_cut_jump import build_visual_cut_sample, score_visual_cut_pair
from tools.verify_cut_boundary_source_fps_scout import _parse_ratio, _probe_video, _read_gray_frames


def _parse_targets(text: str) -> list[int]:
    out: list[int] = []
    for chunk in str(text or "").split(","):
        item = chunk.strip()
        if item:
            out.append(int(item))
    return out


def _settings(pipe_max_fps: float) -> dict[str, Any]:
    return {
        "scan_cut_pioneer_pipe_source_fps_enabled": True,
        "scan_cut_pioneer_pipe_source_max_fps": float(pipe_max_fps or 60.0),
        "scan_cut_pioneer_pipe_score_threshold": 40.0,
        "scan_cut_pioneer_pipe_region_threshold": 18.0,
        "scan_cut_pioneer_pipe_regions_required": 2,
        "scan_cut_pioneer_pipe_pixel_ratio_threshold": 0.18,
        "scan_cut_pioneer_pipe_motion_threshold": 6.0,
    }


def _score_transition(
    *,
    left_frame: int,
    right_frame: int,
    left,
    right,
    cv2_mod,
    width: int,
    fps: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    score_threshold = float(settings["scan_cut_pioneer_pipe_score_threshold"])
    region_hits_threshold = int(settings["scan_cut_pioneer_pipe_regions_required"])
    pixel_ratio_threshold = float(settings["scan_cut_pioneer_pipe_pixel_ratio_threshold"])
    motion_jump_threshold = float(settings["scan_cut_pioneer_pipe_motion_threshold"])
    left_sample = build_visual_cut_sample(left, cv2_mod, mode="fast4", width=width, settings=settings)
    right_sample = build_visual_cut_sample(right, cv2_mod, mode="fast4", width=width, settings=settings)
    metrics = score_visual_cut_pair(left_sample, right_sample, cv2_mod, settings=settings, region_threshold=18.0)
    score = float(metrics.get("score", 0.0) or 0.0)
    region_hits = int(metrics.get("region_hits", 0) or 0)
    pixel_ratio = float(metrics.get("pixel_ratio", 0.0) or 0.0)
    motion_jump = float(metrics.get("motion_jump", 0.0) or 0.0)
    detected = (
        score >= score_threshold
        and region_hits >= region_hits_threshold
        and (pixel_ratio >= pixel_ratio_threshold or motion_jump >= motion_jump_threshold)
    )
    timing = precise_cut_boundary_timing(right_frame / fps, 0.0, fps, sec_to_frame)
    return {
        "left_frame": int(left_frame),
        "right_frame": int(right_frame),
        "candidate_frame": int(timing.get("timeline_frame") or 0),
        "candidate_sec": float(timing.get("timeline_sec") or 0.0),
        "candidate_detected": bool(detected),
        "score": round(score, 3),
        "region_hits": region_hits,
        "pixel_ratio": round(pixel_ratio, 6),
        "edge_ratio": round(float(metrics.get("edge_ratio", 0.0) or 0.0), 6),
        "motion_jump": round(motion_jump, 3),
        "flow_residual": round(float(metrics.get("flow_residual", 0.0) or 0.0), 3),
        "flow_mag": round(float(metrics.get("flow_mean", 0.0) or 0.0), 3),
        "flow_coherence": round(float(metrics.get("flow_coherence", 0.0) or 0.0), 6),
        "backend": str(metrics.get("backend", "") or ""),
        "metrics_backend": str(metrics.get("metrics_backend", "") or ""),
    }


def audit_visual_windows(
    media_path: Path,
    *,
    target_frames: list[int],
    radius: int,
    width: int,
    height: int,
    output_dir: Path,
    pipe_max_fps: float = 60.0,
    probe_timeout_sec: float = 120.0,
    frame_extract_timeout_sec: float = 180.0,
    fps_override: float = 0.0,
) -> dict[str, Any]:
    import cv2

    started = time.time()
    radius = max(1, int(radius or 3))
    info = _probe_video(media_path, timeout_sec=probe_timeout_sec, fps_override=fps_override)
    fps = float(info["fps"] or fps_override or 0.0)
    settings = _settings(pipe_max_fps)
    pipe_fps = resolve_pioneer_pipe_fps(settings, source_fps=fps, fallback_fps=1.0)
    needed = sorted(
        {
            frame
            for target in target_frames
            for candidate in range(int(target) - radius, int(target) + radius + 1)
            for frame in (candidate - 1, candidate)
            if frame >= 0
        }
    )
    frame_map = _read_gray_frames(
        media_path,
        needed,
        width=width,
        height=height,
        timeout_sec=frame_extract_timeout_sec,
    )
    windows: list[dict[str, Any]] = []
    for target in target_frames:
        rows: list[dict[str, Any]] = []
        missing_pairs: list[dict[str, int]] = []
        for candidate in range(int(target) - radius, int(target) + radius + 1):
            left_frame = candidate - 1
            right_frame = candidate
            left = frame_map.get(left_frame)
            right = frame_map.get(right_frame)
            if left is None or right is None:
                missing_pairs.append({"left_frame": left_frame, "right_frame": right_frame})
                continue
            row = _score_transition(
                left_frame=left_frame,
                right_frame=right_frame,
                left=left,
                right=right,
                cv2_mod=cv2,
                width=width,
                fps=fps,
                settings=settings,
            )
            rows.append(row)
        ranked = sorted(rows, key=lambda row: (float(row.get("score") or 0.0), int(row.get("right_frame") or 0)), reverse=True)
        target_row = next((row for row in rows if int(row.get("right_frame") or -1) == int(target)), None)
        target_rank = 0
        for index, row in enumerate(ranked, start=1):
            if int(row.get("right_frame") or -1) == int(target):
                target_rank = index
                break
        best = dict(ranked[0]) if ranked else {}
        windows.append(
            {
                "target_frame": int(target),
                "window_radius": radius,
                "candidate_count": len(rows),
                "missing_pair_count": len(missing_pairs),
                "missing_pairs": missing_pairs,
                "target_row": dict(target_row or {}),
                "target_detected": bool((target_row or {}).get("candidate_detected")),
                "target_score": float((target_row or {}).get("score") or 0.0),
                "target_rank_by_score": int(target_rank),
                "best_frame": int(best.get("right_frame") or 0),
                "best_score": float(best.get("score") or 0.0),
                "best_detected": bool(best.get("candidate_detected")),
                "ranked_candidates": ranked,
                "target_is_best": bool(target_rank == 1),
            }
        )
    strict_targets_detected = all(bool(window.get("target_detected")) for window in windows) if windows else False
    target_best_count = sum(1 for window in windows if bool(window.get("target_is_best")))
    manifest = {
        "schema": "ai_subtitle_studio.cut_boundary_visual_window_audit.v1",
        "note": "Read-only audit. It ranks visual transition evidence and does not change runtime detector thresholds or subtitle policy.",
        "media_path": str(media_path),
        "media": info,
        "settings": settings,
        "pipe_fps": pipe_fps,
        "pipe_fps_num": source_fps_parts(pipe_fps)[0],
        "pipe_fps_den": source_fps_parts(pipe_fps)[1],
        "scale": {"width": width, "height": height},
        "target_frames": [int(frame) for frame in target_frames],
        "window_radius": radius,
        "strict_targets_detected": strict_targets_detected,
        "target_best_count": target_best_count,
        "target_count": len(windows),
        "runtime_change_allowed": False,
        "blocked_runtime_changes": [
            "threshold_relaxation",
            "subtitle_quality_policy_change",
            "stt_policy_change",
            "ui_or_qml_change",
            "persisted_nle_disk_fields",
            "app_store_work",
        ],
        "windows": windows,
        "elapsed_sec": round(time.time() - started, 3),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cut_boundary_visual_window_audit.json"
    md_path = output_dir / "cut_boundary_visual_window_audit.md"
    json_path.write_bytes(dumps_json_bytes(manifest, indent=2, sort_keys=True, append_newline=True))
    manifest["artifact_path"] = str(json_path)
    _write_markdown(md_path, manifest)
    return manifest


def _write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cut Boundary Visual Window Audit",
        "",
        f"- Strict targets detected: `{bool(manifest.get('strict_targets_detected'))}`",
        f"- Target best count: `{manifest.get('target_best_count')}/{manifest.get('target_count')}`",
        f"- Media: `{manifest.get('media_path')}`",
        f"- Pipe fps: `{manifest.get('pipe_fps')}` (`{manifest.get('pipe_fps_num')}/{manifest.get('pipe_fps_den')}`)",
        f"- Window radius: `{manifest.get('window_radius')}`",
        f"- Runtime change allowed: `{bool(manifest.get('runtime_change_allowed'))}`",
        f"- Elapsed: `{manifest.get('elapsed_sec')}`",
        "",
        "## Targets",
        "",
        "| Target | Target detected | Target rank | Target score | Best frame | Best score | Best detected | Missing pairs |",
        "| --- | --- | ---: | ---: | --- | ---: | --- | ---: |",
    ]
    for window in list(manifest.get("windows") or []):
        if not isinstance(window, dict):
            continue
        lines.append(
            "| {target} | {detected} | {rank} | {target_score} | {best_frame} | {best_score} | {best_detected} | {missing} |".format(
                target=window.get("target_frame"),
                detected=bool(window.get("target_detected")),
                rank=window.get("target_rank_by_score"),
                target_score=window.get("target_score"),
                best_frame=window.get("best_frame"),
                best_score=window.get("best_score"),
                best_detected=bool(window.get("best_detected")),
                missing=window.get("missing_pair_count"),
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(manifest.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank visual transition evidence around target cut-boundary frames.")
    parser.add_argument("media", type=Path)
    parser.add_argument("--targets", default="2766,2677")
    parser.add_argument("--radius", type=int, default=3)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=180)
    parser.add_argument("--pipe-max-fps", type=float, default=60.0)
    parser.add_argument("--fps-override", default="")
    parser.add_argument("--probe-timeout-sec", type=float, default=120.0)
    parser.add_argument("--frame-extract-timeout-sec", type=float, default=180.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = audit_visual_windows(
        args.media,
        target_frames=_parse_targets(args.targets),
        radius=max(1, int(args.radius or 3)),
        width=max(64, min(960, int(args.width or 320))),
        height=max(36, min(540, int(args.height or 180))),
        output_dir=args.output_dir,
        pipe_max_fps=float(args.pipe_max_fps or 60.0),
        probe_timeout_sec=float(args.probe_timeout_sec or 120.0),
        frame_extract_timeout_sec=float(args.frame_extract_timeout_sec or 180.0),
        fps_override=_parse_ratio(args.fps_override),
    )
    print(dumps_json_bytes(manifest, indent=2, sort_keys=True).decode("utf-8"))
    return 0 if manifest.get("strict_targets_detected") else 1


if __name__ == "__main__":
    raise SystemExit(main())
