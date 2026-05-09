from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.native_cut_boundary import interval_overlaps
from core.performance import apple_silicon_runtime_profile, hardware_profile
from core.runtime.multi_process import apply_apple_m_subtitle_pipeline_plan
from core.settings_profiles import materialize_user_settings


def _cpu_probe(iterations: int) -> float:
    value = 0.0
    for index in range(max(1, int(iterations))):
        value += math.sin(index * 0.001) * math.cos(index * 0.0007)
    return value


def _bench_process_fanout(worker_counts: list[int], *, iterations: int) -> list[dict]:
    results: list[dict] = []
    for workers in worker_counts:
        workers = max(1, int(workers))
        started = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            list(pool.map(_cpu_probe, [iterations] * workers))
        elapsed = max(0.000001, time.perf_counter() - started)
        results.append(
            {
                "workers": workers,
                "elapsed_sec": round(elapsed, 4),
                "jobs_per_sec": round(workers / elapsed, 4),
            }
        )
    return results


def _bench_native_overlap(repeats: int) -> dict:
    starts = [index * 0.72 for index in range(2500)]
    ends = [start + 0.55 for start in starts]
    vad_starts = [index * 0.36 for index in range(5200)]
    vad_ends = [start + 0.22 for start in vad_starts]
    interval_overlaps(starts[:20], ends[:20], vad_starts[:80], vad_ends[:80])
    started = time.perf_counter()
    for _ in range(max(1, int(repeats))):
        values = interval_overlaps(starts, ends, vad_starts, vad_ends)
    elapsed = max(0.000001, time.perf_counter() - started)
    return {
        "segments": len(starts),
        "vad_segments": len(vad_starts),
        "repeats": int(repeats),
        "elapsed_sec": round(elapsed, 4),
        "calls_per_sec": round(float(repeats) / elapsed, 4),
        "sample_overlap": round(float((values or [0.0])[0]), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Apple Silicon chip-aware scheduler allocation.")
    parser.add_argument("--iterations", type=int, default=180_000, help="CPU fanout loop iterations per worker.")
    parser.add_argument("--overlap-repeats", type=int, default=5, help="Native overlap benchmark repeats.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON.")
    args = parser.parse_args()

    settings = materialize_user_settings({})
    planned = apply_apple_m_subtitle_pipeline_plan(settings)
    chip_profile = apple_silicon_runtime_profile(
        {"runtime_performance_profile": "max", "runtime_hardware_acceleration_enabled": True}
    )
    hardware = hardware_profile()
    cpu = dict(chip_profile.get("cpu") or {})
    worker_counts = sorted(
        {
            1,
            int(hardware.get("performance_cores", 1) or 1),
            int(cpu.get("balanced_workers", 1) or 1),
            int(cpu.get("wide_workers", 1) or 1),
            int(cpu.get("native_threads", os.cpu_count() or 1) or 1),
        }
    )
    payload = {
        "schema": "ai_subtitle_studio.apple_silicon_scheduler_benchmark.v1",
        "hardware": hardware,
        "chip_profile": chip_profile,
        "applied_plan": planned.get("_apple_m_pipeline_parallel_plan", {}),
        "cpu_fanout": _bench_process_fanout(worker_counts, iterations=int(args.iterations)),
        "native_overlap": _bench_native_overlap(int(args.overlap_repeats)),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
