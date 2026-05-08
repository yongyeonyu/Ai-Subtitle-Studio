from __future__ import annotations

"""Benchmark follower dense-flow cut validation on short video windows."""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cut_boundary_auto_verify import build_strict_verify_helpers
from core.settings_profiles import CUT_BOUNDARY_DEFAULTS


def _build_dense_flow_helper():
    return build_strict_verify_helpers(
        {
            "normalize_cut_boundary_level": lambda level: str(level or "medium"),
            "get_level_positions": lambda scan_profile, sample_positions: tuple(sample_positions or (0,)),
            "_auto_capture_verify_maps": lambda *args, **kwargs: ({}, {}),
            "_auto_gray_delta": lambda *args, **kwargs: (0.0, 0, []),
            "_auto_color_avg_delta": lambda *args, **kwargs: (0.0, 0, []),
            "_auto_gray_delta_mps": lambda *args, **kwargs: (0.0, 0, []),
            "_auto_color_avg_delta_mps": lambda *args, **kwargs: (0.0, 0, []),
            "_mps_available": lambda: False,
        }
    )["_auto_dense_flow_cut_check"]


def _parse_windows(raw: str, *, duration_sec: float) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for token in str(raw or "0:60").split(","):
        text = token.strip()
        if not text:
            continue
        if ":" in text:
            start_text, length_text = text.split(":", 1)
            start = max(0.0, float(start_text or 0.0))
            length = max(1.0, float(length_text or 60.0))
        else:
            start = max(0.0, float(text or 0.0))
            length = 60.0
        if duration_sec > 0.0:
            start = min(start, max(0.0, duration_sec - 1.0))
            length = min(length, max(1.0, duration_sec - start))
        windows.append((start, length))
    return windows or [(0.0, min(60.0, duration_sec or 60.0))]


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    timings = [float(row.get("elapsed_ms") or 0.0) for row in rows]
    rejected = [row for row in rows if not row.get("passed", True)]
    backend_counts: dict[str, int] = {}
    for row in rows:
        for key, value in dict(row.get("backend_counts") or {}).items():
            backend_counts[str(key)] = backend_counts.get(str(key), 0) + int(value or 0)
    return {
        "samples": len(rows),
        "accepted": len(rows) - len(rejected),
        "rejected": len(rejected),
        "avg_ms": round(statistics.fmean(timings), 4) if timings else 0.0,
        "p95_ms": round(statistics.quantiles(timings, n=20)[-1], 4) if len(timings) >= 20 else round(max(timings or [0.0]), 4),
        "avg_motion_score": round(statistics.fmean(float(row.get("motion_score") or 0.0) for row in rows), 4) if rows else 0.0,
        "avg_diff": round(statistics.fmean(float(row.get("diff") or 0.0) for row in rows), 4) if rows else 0.0,
        "backend_counts": backend_counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="Video path to benchmark.")
    parser.add_argument("--windows", default="0:60", help="Comma-separated start:length windows in seconds, e.g. 0:60,300:60.")
    parser.add_argument("--candidate-step-sec", type=float, default=2.0, help="Dense-flow sample interval inside each window.")
    parser.add_argument("--max-candidates", type=int, default=160)
    parser.add_argument("--json-output", default="", help="Optional JSON output path.")
    parser.add_argument("--backend", default="dis", choices=["dis", "farneback"], help="OpenCV optical-flow backend preference.")
    args = parser.parse_args()

    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        raise SystemExit(f"video not found: {video}")

    try:
        import cv2
    except Exception as exc:
        raise SystemExit(f"OpenCV unavailable: {exc}") from exc

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration_sec = frame_count / fps if fps > 0.0 and frame_count > 0 else 0.0
    helper = _build_dense_flow_helper()
    settings = dict(CUT_BOUNDARY_DEFAULTS)
    settings["scan_cut_dense_flow_backend"] = args.backend

    rows: list[dict[str, Any]] = []
    step = max(0.2, float(args.candidate_step_sec or 2.0))
    for window_start, window_len in _parse_windows(args.windows, duration_sec=duration_sec):
        cursor = float(window_start)
        end = min(float(window_start + window_len), duration_sec or float(window_start + window_len))
        while cursor < end and len(rows) < max(1, int(args.max_candidates or 160)):
            frame = max(1, min(frame_count - 2, int(round(cursor * fps)))) if frame_count > 2 else 0
            t0 = time.perf_counter()
            result = helper(cap, cv2, frame=frame, frame_count=frame_count, settings=settings)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            row = {
                "sec": round(cursor, 3),
                "frame": int(frame),
                "elapsed_ms": round(elapsed_ms, 4),
                **dict(result or {}),
            }
            rows.append(row)
            cursor += step

    cap.release()
    payload = {
        "schema": "ai_subtitle_studio.cut_dense_flow_benchmark.v1",
        "video": str(video),
        "fps": round(fps, 6),
        "frame_count": frame_count,
        "duration_sec": round(duration_sec, 3),
        "windows": [{"start": start, "length": length} for start, length in _parse_windows(args.windows, duration_sec=duration_sec)],
        "candidate_step_sec": step,
        "settings": {
            key: settings[key]
            for key in sorted(settings)
            if key.startswith("scan_cut_dense_flow") or key == "scan_cut_follower_dense_flow_enabled"
        },
        "summary": _summary(rows),
        "samples": rows,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.json_output:
        target = Path(args.json_output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
