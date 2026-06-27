#!/usr/bin/env python3
"""Summarize stage and memory variance across benchmark result artifacts."""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path
from typing import Any


PRESSURE_ORDER = {"unknown": 0, "normal": 1, "warning": 2, "critical": 3}
DEFAULT_STAGES = (
    "stt_primary_transcribe",
    "stt2_selective_recheck",
    "word_precision",
    "subtitle_postprocess",
)
DEFAULT_DURATION_SLACK_SEC = 0.25


def _safe_float(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def _safe_int(value: Any) -> int | None:
    if not isinstance(value, int):
        return None
    return int(value)


def _round(value: Any, digits: int = 6) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    return round(number, digits)


def _numeric_summary(values: list[float]) -> dict[str, Any]:
    clean = [float(value) for value in values if isinstance(value, (int, float))]
    if not clean:
        return {"count": 0, "avg": None, "min": None, "max": None, "range": None, "list": []}
    minimum = min(clean)
    maximum = max(clean)
    return {
        "count": len(clean),
        "avg": round(sum(clean) / len(clean), 6),
        "min": round(minimum, 6),
        "max": round(maximum, 6),
        "range": round(maximum - minimum, 6),
        "list": [round(value, 6) for value in clean],
    }


def _pressure_stage(value: Any) -> str:
    stage = str(value or "").strip().lower()
    if stage in {"normal", "warning", "critical"}:
        return stage
    return "unknown"


def _worst_pressure(stages: list[str]) -> str:
    if not stages:
        return "unknown"
    return max((_pressure_stage(stage) for stage in stages), key=lambda item: PRESSURE_ORDER.get(item, 0))


def _stage_summary(result: dict[str, Any], stage: str) -> dict[str, Any]:
    summary = dict(result.get("stage_wall_clock_summary") or {})
    stages = dict(summary.get("stage_summaries") or {})
    return dict(stages.get(stage) or {})


def _first_span(result: dict[str, Any], stage: str) -> dict[str, Any]:
    summary = dict(result.get("stage_wall_clock_summary") or {})
    for span in list(summary.get("spans") or []):
        if isinstance(span, dict) and span.get("stage") == stage:
            return dict(span)
    return {}


def _detail_span(result: dict[str, Any], detail_stage: str) -> dict[str, Any]:
    summary = dict(result.get("stage_wall_clock_summary") or {})
    for span in list(summary.get("spans") or []):
        if not isinstance(span, dict):
            continue
        if span.get("stage") == "subtitle_postprocess_detail" and span.get("detail_stage") == detail_stage:
            return dict(span)
    return {}


def _memory_pressure(result: dict[str, Any]) -> dict[str, Any]:
    stages: list[str] = []
    summary = dict(result.get("stage_wall_clock_summary") or {})
    for span in list(summary.get("spans") or []):
        if not isinstance(span, dict):
            continue
        for key in ("resource_pressure_stage", "pressure_stage", "memory_pressure_stage"):
            if span.get(key):
                stages.append(_pressure_stage(span.get(key)))
    return {
        "stages": stages,
        "worst": _worst_pressure(stages),
        "counts": dict(Counter(stages)),
    }


def _cache_flags(result: dict[str, Any]) -> dict[str, Any]:
    stt1 = _first_span(result, "stt_primary_transcribe") or _first_span(result, "stt_primary_collect_transcribe")
    stt2 = _first_span(result, "stt2_selective_recheck")
    word = _first_span(result, "word_precision")
    proofread = _detail_span(result, "proofread_dictionary_llm")
    high_context = _detail_span(result, "high_context_boundary")
    return {
        "stt_primary": {
            "enabled": stt1.get("collect_cache_enabled"),
            "hit": stt1.get("collect_cache_hit"),
            "write": stt1.get("collect_cache_write"),
            "provider_called": stt1.get("collect_provider_called"),
            "collect_elapsed_sec": _round(stt1.get("collect_elapsed_sec")),
            "setup_elapsed_sec": _round(stt1.get("setup_elapsed_sec")),
        },
        "stt2_recheck": {
            "enabled": stt2.get("collect_cache_enabled"),
            "hit": stt2.get("collect_cache_hit"),
            "write": stt2.get("collect_cache_write"),
            "provider_called": stt2.get("collect_provider_called"),
            "collect_elapsed_sec": _round(stt2.get("collect_elapsed_sec")),
            "prepare_elapsed_sec": _round(stt2.get("prepare_elapsed_sec")),
        },
        "word_precision": {
            "enabled": word.get("collect_cache_enabled"),
            "hit": word.get("collect_cache_hit"),
            "write": word.get("collect_cache_write"),
            "provider_called": word.get("collect_provider_called"),
            "collect_elapsed_sec": _round(word.get("collect_elapsed_sec")),
            "prepare_elapsed_sec": _round(word.get("prepare_elapsed_sec")),
        },
        "macro_proofread": {
            "hit_groups": _safe_int(proofread.get("llm_macro_response_cache_hit_group_count")),
            "write_groups": _safe_int(proofread.get("llm_macro_response_cache_write_group_count")),
            "provider_called_groups": _safe_int(proofread.get("llm_macro_provider_called_group_count")),
            "elapsed_sec": _round(proofread.get("detail_elapsed_sec")),
        },
        "high_context": {
            "enabled": high_context.get("high_context_boundary_enabled"),
            "keep_cache_enabled": high_context.get("high_context_boundary_keep_cache_enabled"),
            "hit_count": _safe_int(high_context.get("high_context_boundary_keep_cache_hit_count")),
            "miss_count": _safe_int(high_context.get("high_context_boundary_keep_cache_miss_count")),
            "write_count": _safe_int(high_context.get("high_context_boundary_keep_cache_write_count")),
            "llm_call_count": _safe_int(high_context.get("high_context_boundary_llm_call_count")),
            "changed_pair_count": _safe_int(high_context.get("high_context_boundary_changed_pair_count")),
            "elapsed_sec": _round(high_context.get("high_context_boundary_elapsed_sec")),
        },
    }


def _extract_result(path: Path, payload: dict[str, Any], result: dict[str, Any], index: int) -> dict[str, Any]:
    native_segments = dict(result.get("native_segments_summary") or {})
    native_global = dict(result.get("native_global_canvas_summary") or {})
    quality = dict(result.get("quality") or {})
    duration_sec = _round(payload.get("duration_sec"))
    last_end = _round(native_segments.get("last_end"))
    beyond_duration: float | None = None
    if duration_sec is not None and last_end is not None:
        beyond_duration = round(max(0.0, float(last_end) - float(duration_sec)), 6)
    stage_totals: dict[str, Any] = {}
    for stage in DEFAULT_STAGES:
        data = _stage_summary(result, stage)
        stage_totals[stage] = {
            "total_elapsed_sec": _round(data.get("total_elapsed_sec")),
            "max_elapsed_sec": _round(data.get("max_elapsed_sec")),
            "collect_elapsed_sec": _round(data.get("total_collect_elapsed_sec")),
            "prepare_elapsed_sec": _round(data.get("total_prepare_elapsed_sec")),
            "setup_elapsed_sec": _round(data.get("total_setup_elapsed_sec")),
            "detail_top_elapsed_sec": _round(data.get("total_detail_top_elapsed_sec")),
        }
    pressure = _memory_pressure(result)
    return {
        "run_id": path.parent.name if path.name == "benchmark_results.json" else f"{path.stem}:{index}",
        "path": str(path),
        "result_index": index,
        "name": str(result.get("name") or ""),
        "description": str(result.get("description") or ""),
        "media": str(payload.get("media") or ""),
        "reference_srt": str(payload.get("reference_srt") or ""),
        "duration_sec": duration_sec,
        "elapsed_sec": _round(result.get("elapsed_sec")),
        "raw_segments": _safe_int(result.get("raw_segments")),
        "final_segments": _safe_int(result.get("final_segments")),
        "reference_segments": _safe_int(quality.get("reference_segments")),
        "quality_score": _round(quality.get("quality_score"), 3),
        "text_score": _round(quality.get("text_score"), 3),
        "timing_mae_sec": _round(quality.get("timing_mae_sec"), 4),
        "final_gates": {
            "invalid_duration_count": _safe_int(native_segments.get("invalid_duration_count")),
            "non_monotonic_count": _safe_int(native_segments.get("non_monotonic_count")),
            "overlap_count": _safe_int(native_segments.get("overlap_count")),
            "stable_for_save_reopen": native_segments.get("stable_for_save_reopen"),
            "last_end": last_end,
            "duration_bound_sec": duration_sec,
            "last_end_beyond_duration_sec": beyond_duration,
            "duration_slack_sec": DEFAULT_DURATION_SLACK_SEC,
            "last_end_within_duration_bound": (
                beyond_duration <= DEFAULT_DURATION_SLACK_SEC if beyond_duration is not None else None
            ),
            "global_canvas_max_active_segments": _safe_int(native_global.get("max_active_segments")),
            "stable_for_global_canvas": native_global.get("stable_for_global_canvas"),
        },
        "memory_pressure": pressure,
        "cache": _cache_flags(result),
        "stage_totals": stage_totals,
    }


def load_runs(paths: list[Path]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("results") or []
        if not isinstance(results, list):
            continue
        for index, result in enumerate(results):
            if isinstance(result, dict):
                runs.append(_extract_result(path, payload, result, index))
    return runs


def build_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed_values = [value for run in runs if (value := run.get("elapsed_sec")) is not None]
    pressure_counts = Counter(str((run.get("memory_pressure") or {}).get("worst") or "unknown") for run in runs)
    stage_variance: dict[str, Any] = {}
    for stage in DEFAULT_STAGES:
        values = [
            float(stage_data["total_elapsed_sec"])
            for run in runs
            if (stage_data := (run.get("stage_totals") or {}).get(stage))
            and stage_data.get("total_elapsed_sec") is not None
        ]
        stage_variance[stage] = _numeric_summary(values)

    final_gate_all = {
        "invalid_duration_count_zero": all((run.get("final_gates") or {}).get("invalid_duration_count") == 0 for run in runs),
        "non_monotonic_count_zero": all((run.get("final_gates") or {}).get("non_monotonic_count") == 0 for run in runs),
        "overlap_count_zero": all((run.get("final_gates") or {}).get("overlap_count") == 0 for run in runs),
        "global_canvas_max_active_lte_one": all(
            ((run.get("final_gates") or {}).get("global_canvas_max_active_segments") or 0) <= 1 for run in runs
        ),
        "last_end_within_duration_bound": all(
            (run.get("final_gates") or {}).get("last_end_within_duration_bound") is not False for run in runs
        ),
    }
    return {
        "schema": "ai_subtitle_studio.stage_variance_summary.v1",
        "note": "Analysis-only summary from existing benchmark artifacts. It does not change runtime behavior or approve production cache defaults.",
        "run_count": len(runs),
        "elapsed_sec": _numeric_summary(elapsed_values),
        "pressure_worst_counts": dict(pressure_counts),
        "stage_variance": stage_variance,
        "final_gate_all": final_gate_all,
        "runs": runs,
    }


def _markdown_table(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    sep = ["---"] * len(header)
    lines = ["| " + " | ".join(str(item) for item in header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    runs = list(summary.get("runs") or [])
    stage_rows: list[list[Any]] = [["stage", "avg_sec", "min_sec", "max_sec", "range_sec"]]
    for stage, data in dict(summary.get("stage_variance") or {}).items():
        stage_rows.append([stage, data.get("avg"), data.get("min"), data.get("max"), data.get("range")])

    run_rows: list[list[Any]] = [[
        "run_id",
        "elapsed",
        "quality",
        "final",
        "worst_pressure",
        "stt1_hit/provider",
        "stt2_hit/provider",
        "word_hit/provider",
        "macro_hit/provider",
    ]]
    for run in runs:
        cache = dict(run.get("cache") or {})
        stt1 = dict(cache.get("stt_primary") or {})
        stt2 = dict(cache.get("stt2_recheck") or {})
        word = dict(cache.get("word_precision") or {})
        macro = dict(cache.get("macro_proofread") or {})
        run_rows.append([
            run.get("run_id"),
            run.get("elapsed_sec"),
            run.get("quality_score"),
            run.get("final_segments"),
            (run.get("memory_pressure") or {}).get("worst"),
            f"{stt1.get('hit')}/{stt1.get('provider_called')}",
            f"{stt2.get('hit')}/{stt2.get('provider_called')}",
            f"{word.get('hit')}/{word.get('provider_called')}",
            f"{macro.get('hit_groups')}/{macro.get('provider_called_groups')}",
        ])

    gates = dict(summary.get("final_gate_all") or {})
    return "\n".join([
        "# Stage Variance Summary",
        "",
        "## Scope",
        "",
        "- Analysis-only summary from existing benchmark artifacts.",
        "- No runtime behavior, STT policy, cache defaults, subtitle timing, save/load, render/export, or UI changed.",
        "- NAS/real-media backfill is still required before production speed claims.",
        "",
        "## Aggregate",
        "",
        f"- Run count: `{summary.get('run_count')}`",
        f"- Elapsed summary: `{summary.get('elapsed_sec')}`",
        f"- Worst memory-pressure counts: `{summary.get('pressure_worst_counts')}`",
        f"- Final gate all-pass: `{gates}`",
        "",
        "## Stage Variance",
        "",
        _markdown_table(stage_rows),
        "",
        "## Runs",
        "",
        _markdown_table(run_rows),
        "",
        "## Interpretation Guard",
        "",
        "- Treat cache-hit deltas as generated/synthetic artifact evidence only unless the input paths are representative real-media benchmark runs.",
        "- Do not enable `stt_recheck_collect_cache_enabled` or `stt_primary_collect_cache_enabled` by default from this report.",
        "- Use this report to choose the next measurement target, not as a subtitle-quality acceptance gate.",
        "",
    ])


def _expand_inputs(inputs: list[str], globs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in inputs:
        paths.append(Path(value))
    for pattern in globs:
        for item in glob.glob(pattern):
            paths.append(Path(item))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            unique.append(path)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], help="benchmark_results.json path")
    parser.add_argument("--glob", action="append", default=[], help="glob for benchmark_results.json files")
    parser.add_argument("--output-dir", required=True, help="directory for summary JSON and Markdown")
    args = parser.parse_args(argv)

    paths = _expand_inputs(args.input, args.glob)
    if not paths:
        parser.error("at least one existing --input or --glob match is required")

    runs = load_runs(paths)
    summary = build_summary(runs)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stage_variance_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "stage_variance_summary.md").write_text(render_markdown(summary), encoding="utf-8")
    print(output_dir / "stage_variance_summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
