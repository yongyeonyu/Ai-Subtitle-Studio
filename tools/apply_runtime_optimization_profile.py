from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.optimization.profile_store import save_optimization_profile
from core.optimization.types import OptimizationProfile


def _read_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def _best_stt_model(payload: dict[str, Any]) -> str:
    stt = dict(payload.get("stt") or {})
    models = list(stt.get("models") or stt.get("model_benchmarks") or payload.get("stt_models") or [])
    valid = [row for row in models if isinstance(row, dict)]
    if not valid:
        return ""
    valid.sort(key=lambda row: (float(row.get("cer", row.get("error", 1.0)) or 1.0), float(row.get("elapsed_sec", 999999.0) or 999999.0)))
    return str(valid[0].get("model") or valid[0].get("name") or "").strip()


def _best_native_threads(payload: dict[str, Any]) -> int | None:
    stt = dict(payload.get("stt") or {})
    rows = [
        row
        for row in list(stt.get("native_threads") or payload.get("stt_primary") or [])
        if isinstance(row, dict)
    ]
    if not rows:
        return None
    rows.sort(key=lambda row: float(row.get("elapsed_sec", 999999.0) or 999999.0))
    try:
        return int(rows[0].get("threads") or rows[0].get("native_threads") or 0)
    except Exception:
        return None


def build_profile_from_benchmark(payload: dict[str, Any]) -> OptimizationProfile:
    selected_backends: dict[str, str] = {
        "cut_boundary": "opencv_proxy_fast",
        "audio_extract": "ffmpeg_direct_chunks",
        "vad": "ten_vad",
        "editor": "compact_scenegraph",
    }
    selected_models: dict[str, str] = {}
    stt_model = _best_stt_model(payload)
    if stt_model:
        selected_models["stt"] = stt_model
        selected_backends["stt"] = "mlx" if "mlx" in stt_model.lower() else "faster_whisper"
    return OptimizationProfile(
        selected_backends=selected_backends,
        selected_models=selected_models,
        benchmarks=[payload],
        quality_gates={
            "stt": {"max_cer_regression_pp": 0.3, "max_timing_mae_regression_ms": 50.0},
            "vad": {"max_missed_speech_delta": 0.0},
            "cut_boundary": {"max_missed_cut_delta": 0.0},
            "editor": {"min_ui_frame_time_improvement_ratio": 0.30},
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply AI Subtitle Studio runtime optimization profile.")
    parser.add_argument(
        "--benchmark-json",
        default=str(Path(".codex_work") / "hw_bench" / "hw_resource_benchmark_latest.json"),
        help="Benchmark JSON generated from the local test-video run.",
    )
    args = parser.parse_args()
    path = os.path.abspath(args.benchmark_json)
    payload = _read_json(path)
    profile = build_profile_from_benchmark(payload)
    threads = _best_native_threads(payload)
    if threads:
        profile.selected_backends["native_threads"] = str(threads)
    save_optimization_profile(profile)
    print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
