#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from benchmark_subtitle_pipeline_variants import (  # noqa: E402
    _base_benchmark_settings,
    _load_vad,
    _rank_rows,
    _slim_segments_for_artifact,
    clip_reference,
    parse_srt,
    patched_subtitle_settings,
    score_against_reference,
)
from core.engine import subtitle_engine  # noqa: E402
from core.llm.ollama_provider import (  # noqa: E402
    ensure_ollama_server,
    shutdown_local_ollama_runtime,
    stop_local_llm_models,
)
from core.runtime import config  # noqa: E402


DEFAULT_SOURCE_BENCH = (
    ROOT
    / ".codex_work/benchmarks/subtitle_pipeline_variants/20260510_021810/benchmark_results.json"
)
DEFAULT_RAW_SEGMENTS = (
    ROOT
    / ".codex_work/benchmarks/subtitle_pipeline_variants/20260510_021810/"
    / "ffmpeg_ten_vad_balanced/ffmpeg_ten_vad_balanced__phase3_parallel_full_llm/raw_segments.json"
)
DEFAULT_MODELS = ("exaone3.5:2.4b", "exaone3.5:7.8b", "gemma4:e2b", "gemma4:e4b")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value or "").strip())
    return text.strip("_") or "model"


def _ollama_models() -> set[str]:
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
    except Exception:
        return set()
    models: set[str] = set()
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.add(parts[0])
    return models


def _benchmark_settings(model: str) -> dict[str, Any]:
    settings = _base_benchmark_settings("mlx-large-v3")
    settings.update(
        {
            "selected_model": model,
            "llm_confidence_gate_enabled": False,
            "llm_threads": 1,
            "llm_workers": 1,
            "llm_threads_auto_enabled": False,
            "llm_workers_auto_enabled": False,
            "local_ollama_llm_max_workers": 1,
            "subtitle_llm_macro_chunk_enabled": True,
            "subtitle_llm_macro_chunk_min_rows": 10,
            "subtitle_llm_macro_chunk_max_rows": 15,
            "subtitle_llm_macro_chunk_use_cut_boundaries": True,
            "runtime_quality_self_review_enabled": True,
            "subtitle_context_consistency_enabled": True,
            "subtitle_auto_review_enabled": True,
        }
    )
    return settings


def _count_llm_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    called = 0
    macro_rows = 0
    reasons: dict[str, int] = {}
    for row in rows:
        policy = row.get("_llm_macro_chunk_policy")
        if isinstance(policy, dict):
            macro_rows += 1
            if policy.get("llm_called"):
                called += 1
            reason = str(policy.get("reason") or "").strip()
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        gate = row.get("_llm_gate_policy")
        if isinstance(gate, dict):
            reason = str(gate.get("reason") or "").strip()
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "macro_policy_rows": macro_rows,
        "llm_called_rows": called,
        "policy_reasons": dict(sorted(reasons.items(), key=lambda item: item[1], reverse=True)[:8]),
    }


def _run_model(
    model: str,
    *,
    raw_rows: list[dict[str, Any]],
    vad_rows: list[dict[str, Any]],
    reference: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    settings = _benchmark_settings(model)
    model_dir = output_dir / _safe_slug(model)
    model_dir.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "name": f"llm_model__{model}",
        "phase": "llm_model_actual",
        "description": "Same 3-minute STT/VAD candidates; only subtitle LLM model changes.",
        "method": "fixed_stt_lora_deep_forced_llm_macro",
        "run_llm": True,
        "selected_model": model,
        "raw_segments": len(raw_rows),
        "llm_macro_groups_estimated": max(
            1,
            math.ceil(
                len(raw_rows)
                / max(1, int(settings.get("subtitle_llm_macro_chunk_max_rows", 15) or 15))
            ),
        ),
        "error": "",
        "settings": {
            "selected_model": model,
            "llm_confidence_gate_enabled": settings.get("llm_confidence_gate_enabled"),
            "subtitle_llm_macro_chunk_enabled": settings.get("subtitle_llm_macro_chunk_enabled"),
            "subtitle_llm_macro_chunk_min_rows": settings.get("subtitle_llm_macro_chunk_min_rows"),
            "subtitle_llm_macro_chunk_max_rows": settings.get("subtitle_llm_macro_chunk_max_rows"),
            "local_ollama_llm_max_workers": settings.get("local_ollama_llm_max_workers"),
        },
    }
    final_rows: list[dict[str, Any]] = []
    cleanup_elapsed = 0.0
    started = time.perf_counter()
    try:
        stop_local_llm_models()
        with patched_subtitle_settings(settings, model):
            final_rows = subtitle_engine.optimize_segments([dict(item) for item in raw_rows], vad_segments=vad_rows)
    except Exception as exc:
        row["error"] = str(exc)
    optimize_elapsed = time.perf_counter() - started
    cleanup_started = time.perf_counter()
    try:
        stop_local_llm_models([model], log_context="LLM benchmark")
    except Exception:
        pass
    cleanup_elapsed = time.perf_counter() - cleanup_started
    total_elapsed = optimize_elapsed + cleanup_elapsed
    row.update(
        {
            "elapsed_sec": round(total_elapsed, 3),
            "optimize_elapsed_sec": round(optimize_elapsed, 3),
            "cleanup_elapsed_sec": round(cleanup_elapsed, 3),
            "final_segments": len(final_rows),
            "llm_policy": _count_llm_rows(final_rows),
            "quality": score_against_reference(final_rows, reference) if final_rows else {},
        }
    )
    (model_dir / "output_segments.json").write_text(
        json.dumps(_slim_segments_for_artifact(final_rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return row


def _write_markdown(payload: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# Actual LLM Model Benchmark",
        "",
        f"- Source benchmark: `{payload.get('source_benchmark')}`",
        f"- Raw segments: `{payload.get('raw_segments_path')}`",
        f"- Reference: `{payload.get('reference_srt')}`",
        f"- Span: {payload.get('start_sec')}s ~ {payload.get('end_sec')}s",
        f"- Created: {payload.get('created_at')}",
        "",
        "| Rank | Model | Time(s) | Optimize(s) | Quality | Q+Speed | Segs | CER | Similarity | Timing MAE | LLM Groups | Error |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload.get("ranked_results") or []:
        q = dict(row.get("quality") or {})
        lines.append(
            "| {rank} | `{model}` | {elapsed:.3f} | {optimize:.3f} | {quality:.3f} | {combo:.3f} | {segs} | {cer:.4f} | {sim:.4f} | {timing:.3f} | {llm_rows} | {error} |".format(
                rank=row.get("rank", ""),
                model=row.get("selected_model", ""),
                elapsed=float(row.get("elapsed_sec", 0.0) or 0.0),
                optimize=float(row.get("optimize_elapsed_sec", 0.0) or 0.0),
                quality=float(q.get("quality_score", 0.0) or 0.0),
                combo=float(row.get("quality_speed_score", 0.0) or 0.0),
                segs=row.get("final_segments", 0),
                cer=float(q.get("cer", 0.0) or 0.0),
                sim=float(q.get("global_text_similarity", 0.0) or 0.0),
                timing=float(q.get("timing_mae_sec", 0.0) or 0.0),
                llm_rows=int(row.get("llm_macro_groups_estimated", 0) or 0),
                error=str(row.get("error") or "").replace("|", "/")[:90],
            )
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- The LLM confidence gate is disabled here, so these are real model calls on macro chunks.")
    lines.append("- STT, FFmpeg, VAD, LoRA and Deep inputs are fixed from the previous 3-minute benchmark.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_vad_rows(source_payload: dict[str, Any], audio_profile: str) -> list[dict[str, Any]]:
    for row in source_payload.get("audio_extracts") or []:
        if str(row.get("profile") or "") != audio_profile:
            continue
        chunk_dir = Path(str(row.get("audio_chunk_dir") or ""))
        if chunk_dir.exists():
            return _load_vad(chunk_dir)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark actual subtitle LLM model variants on fixed STT rows.")
    parser.add_argument("--source-benchmark", type=Path, default=DEFAULT_SOURCE_BENCH)
    parser.add_argument("--raw-segments", type=Path, default=DEFAULT_RAW_SEGMENTS)
    parser.add_argument("--audio-profile", default="ffmpeg_ten_vad_balanced")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".codex_work/benchmarks/llm_model_variants")
    parser.add_argument("--shutdown-ollama", action="store_true", default=True)
    args = parser.parse_args()

    source_payload = _read_json(args.source_benchmark)
    reference_srt = Path(str(source_payload.get("reference_srt") or ""))
    if not reference_srt.exists():
        raise FileNotFoundError(reference_srt)
    raw_rows = [dict(item) for item in _read_json(args.raw_segments) if isinstance(item, dict)]
    start_sec = float(source_payload.get("start_sec", 0.0) or 0.0)
    end_sec = float(source_payload.get("end_sec", 180.0) or 180.0)
    reference_rows = clip_reference(parse_srt(reference_srt), start_sec, end_sec)
    vad_rows = _resolve_vad_rows(source_payload, args.audio_profile)
    ensure_ollama_server(wait_sec=4.0)
    installed = _ollama_models()

    output_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    try:
        for model in args.models:
            item = {"selected_model": model, "name": f"llm_model__{model}", "phase": "llm_model_actual"}
            if model not in installed:
                item.update(
                    {
                        "description": "Model is not installed in Ollama.",
                        "method": "fixed_stt_lora_deep_forced_llm_macro",
                        "run_llm": True,
                        "elapsed_sec": 0.0,
                        "optimize_elapsed_sec": 0.0,
                        "cleanup_elapsed_sec": 0.0,
                        "raw_segments": len(raw_rows),
                        "final_segments": 0,
                        "error": "ollama_model_not_installed",
                        "quality": {},
                    }
                )
                results.append(item)
                continue
            print(f"[LLM benchmark] {model}", flush=True)
            results.append(
                _run_model(
                    model,
                    raw_rows=raw_rows,
                    vad_rows=vad_rows,
                    reference=reference_rows,
                    output_dir=output_dir,
                )
            )
    finally:
        if args.shutdown_ollama:
            shutdown_local_ollama_runtime(args.models, log_context="LLM benchmark", timeout_sec=0.8)

    ranked = _rank_rows(results)
    payload = {
        "schema": "ai_subtitle_studio.llm_model_variant_benchmark.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_benchmark": str(args.source_benchmark),
        "raw_segments_path": str(args.raw_segments),
        "audio_profile": args.audio_profile,
        "reference_srt": str(reference_srt),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "raw_segments": len(raw_rows),
        "reference_segments": len(reference_rows),
        "installed_models": sorted(installed),
        "results": results,
        "ranked_results": ranked,
        "app_settings_dir": str(config.DATASET_DIR),
    }
    json_path = output_dir / "benchmark_results.json"
    md_path = output_dir / "benchmark_results.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, md_path)
    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
