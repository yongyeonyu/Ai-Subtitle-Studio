#!/usr/bin/env python3
"""Audit STT worker timeout evidence from benchmark result artifacts."""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return int(value)
    try:
        return int(value)
    except Exception:
        return default


def _round(value: Any, digits: int = 6) -> float:
    return round(_safe_float(value), digits)


def _best_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("ranked_results")
    if not isinstance(rows, list) or not rows:
        rows = payload.get("results")
    return [dict(row) for row in list(rows or []) if isinstance(row, dict)]


def _spans(row: dict[str, Any]) -> list[dict[str, Any]]:
    summary = dict(row.get("stage_wall_clock_summary") or {})
    return [dict(span) for span in list(summary.get("spans") or []) if isinstance(span, dict)]


def _timeout_like_word_precision(span: dict[str, Any]) -> bool:
    if span.get("stage") != "word_precision_collect_transcribe":
        return False
    status = str(span.get("status") or "").strip().lower()
    backend = str(span.get("backend") or "").strip().lower()
    received = _safe_int(span.get("received_chunks"), 0)
    timeout_sec = _safe_float(span.get("worker_silence_timeout_sec"), 0.0)
    elapsed = _safe_float(span.get("elapsed_sec"), 0.0)
    return (
        status in {"failed", "timeout", "aborted"}
        and "whisperkit" in backend
        and received == 0
        and timeout_sec > 0.0
        and elapsed >= max(0.0, timeout_sec - 1.0)
    )


def _final_gates(row: dict[str, Any]) -> dict[str, Any]:
    final = dict(row.get("native_segments_summary") or {})
    global_canvas = dict(row.get("native_global_canvas_summary") or {})
    return {
        "invalid_duration_count": _safe_int(final.get("invalid_duration_count")),
        "non_monotonic_count": _safe_int(final.get("non_monotonic_count")),
        "overlap_count": _safe_int(final.get("overlap_count")),
        "stable_for_save_reopen": final.get("stable_for_save_reopen"),
        "last_end": _round(final.get("last_end")),
        "short_segment_count": _safe_int(final.get("short_segment_count")),
        "long_segment_count": _safe_int(final.get("long_segment_count")),
        "global_canvas_max_active_segments": _safe_int(global_canvas.get("max_active_segments")),
        "stable_for_global_canvas": global_canvas.get("stable_for_global_canvas"),
    }


def _quality(row: dict[str, Any]) -> dict[str, Any]:
    quality = dict(row.get("quality") or {})
    return {
        "quality_score": _round(quality.get("quality_score"), 3),
        "text_score": _round(quality.get("text_score"), 3),
        "timing_mae_sec": _round(quality.get("timing_mae_sec"), 4),
        "reference_segments": _safe_int(quality.get("reference_segments")),
    }


def _run_timeout_summary(path: Path, payload: dict[str, Any], row: dict[str, Any], index: int) -> dict[str, Any]:
    timeout_spans: list[dict[str, Any]] = []
    word_precision_timeouts: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    source_models: Counter[str] = Counter()
    fallback_models: Counter[str] = Counter()

    for span in _spans(row):
        stage = str(span.get("stage") or "")
        if stage == "stt_collect_whisperkit_fallback" and str(span.get("reason") or "") == "worker_timeout":
            label = str(span.get("label") or span.get("source_collect_label") or "unknown")
            label_counts[label] += 1
            source = str(span.get("source_model") or "")
            fallback = str(span.get("fallback_model") or "")
            if source:
                source_models[source] += 1
            if fallback:
                fallback_models[fallback] += 1
            timeout_spans.append(
                {
                    "label": label,
                    "elapsed_sec": _round(span.get("elapsed_sec")),
                    "source_model": source,
                    "fallback_model": fallback,
                    "total_chunks": _safe_int(span.get("total_chunks")),
                    "received_chunks": _safe_int(span.get("received_chunks")),
                    "processed_chunks": _safe_int(span.get("processed_chunks")),
                    "word_timestamps": bool(span.get("word_timestamps")),
                }
            )
        if _timeout_like_word_precision(span):
            word_precision_timeouts.append(
                {
                    "label": str(span.get("label") or span.get("source_collect_label") or "word_precision"),
                    "elapsed_sec": _round(span.get("elapsed_sec")),
                    "worker_silence_timeout_sec": _round(span.get("worker_silence_timeout_sec")),
                    "backend": str(span.get("backend") or ""),
                    "resolved_model": str(span.get("resolved_model") or ""),
                    "chunk_count": _safe_int(span.get("chunk_count")),
                    "received_chunks": _safe_int(span.get("received_chunks")),
                    "word_timestamps": bool(span.get("word_timestamps")),
                }
            )

    timeout_elapsed = round(sum(item["elapsed_sec"] for item in timeout_spans), 6)
    precision_timeout_elapsed = round(sum(item["elapsed_sec"] for item in word_precision_timeouts), 6)
    elapsed_sec = _round(row.get("elapsed_sec"))
    timeout_ratio = round((timeout_elapsed + precision_timeout_elapsed) / elapsed_sec, 6) if elapsed_sec > 0 else 0.0
    severe = bool(timeout_spans or word_precision_timeouts)
    return {
        "run_id": path.parent.name if path.name == "benchmark_results.json" else f"{path.stem}:{index}",
        "path": str(path),
        "result_index": index,
        "name": str(row.get("name") or ""),
        "media": str(payload.get("media") or ""),
        "reference_srt": str(payload.get("reference_srt") or ""),
        "elapsed_sec": elapsed_sec,
        "raw_segments": _safe_int(row.get("raw_segments")),
        "final_segments": _safe_int(row.get("final_segments")),
        "quality": _quality(row),
        "final_gates": _final_gates(row),
        "timeout_fallback_count": len(timeout_spans),
        "timeout_fallback_elapsed_sec": timeout_elapsed,
        "word_precision_timeout_like_count": len(word_precision_timeouts),
        "word_precision_timeout_like_elapsed_sec": precision_timeout_elapsed,
        "timeout_total_elapsed_sec": round(timeout_elapsed + precision_timeout_elapsed, 6),
        "timeout_elapsed_ratio": timeout_ratio,
        "timeout_labels": dict(label_counts),
        "source_models": dict(source_models),
        "fallback_models": dict(fallback_models),
        "timeout_spans": timeout_spans,
        "word_precision_timeout_like_spans": word_precision_timeouts,
        "timeout_evidence_present": severe,
        "recommendation": (
            "diagnose_worker_timeout_before_runtime_trim"
            if severe
            else "no_worker_timeout_evidence_in_selected_artifacts"
        ),
    }


def load_audit_runs(paths: list[Path]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for index, row in enumerate(_best_rows(payload)):
            runs.append(_run_timeout_summary(path, payload, row, index))
    return runs


def build_audit(paths: list[Path]) -> dict[str, Any]:
    runs = load_audit_runs(paths)
    timeout_runs = [run for run in runs if run.get("timeout_evidence_present")]
    timeout_elapsed_values = [run["timeout_total_elapsed_sec"] for run in timeout_runs]
    return {
        "schema": "ai_subtitle_studio.stt_worker_timeout_audit.v1",
        "note": (
            "Read-only audit from benchmark artifacts. It does not change runtime behavior, "
            "quality policy, STT routing, collect-cache defaults, or UI."
        ),
        "artifact_count": len(paths),
        "run_count": len(runs),
        "timeout_run_count": len(timeout_runs),
        "timeout_detected": bool(timeout_runs),
        "timeout_total_elapsed_sec": round(sum(timeout_elapsed_values), 6),
        "max_timeout_total_elapsed_sec": round(max(timeout_elapsed_values), 6) if timeout_elapsed_values else 0.0,
        "production_change_allowed": False,
        "default_cache_promotion_allowed": False,
        "blocked_runtime_changes": [
            "model_downgrade",
            "skip_stt2",
            "skip_word_precision",
            "quality_gate_relaxation",
            "collect_cache_default_promotion",
            "ui_or_app_store_changes",
        ],
        "next_safe_actions": [
            "repeat_same_fixture_after_worker_reset_or_resource_probe",
            "compare timeout and non-timeout benchmark artifacts by stage spans",
            "inspect WhisperKit persistent worker lifecycle before changing STT policy",
        ],
        "runs": runs,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# STT Worker Timeout Audit",
        "",
        f"- Timeout detected: `{bool(audit.get('timeout_detected'))}`",
        f"- Artifact count: `{audit.get('artifact_count')}`",
        f"- Run count: `{audit.get('run_count')}`",
        f"- Timeout run count: `{audit.get('timeout_run_count')}`",
        f"- Timeout total elapsed: `{audit.get('timeout_total_elapsed_sec')}`",
        f"- Max timeout total elapsed: `{audit.get('max_timeout_total_elapsed_sec')}`",
        f"- Production change allowed: `{bool(audit.get('production_change_allowed'))}`",
        f"- Default cache promotion allowed: `{bool(audit.get('default_cache_promotion_allowed'))}`",
        "",
        "## Runs",
        "",
        "| Run | Elapsed | Timeout count | Timeout elapsed | Timeout ratio | Labels | Final gates | Quality/Text/Timing |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for run in list(audit.get("runs") or []):
        if not isinstance(run, dict):
            continue
        gates = dict(run.get("final_gates") or {})
        quality = dict(run.get("quality") or {})
        gate_text = "{}/{}/{} max_active={}".format(
            gates.get("invalid_duration_count"),
            gates.get("non_monotonic_count"),
            gates.get("overlap_count"),
            gates.get("global_canvas_max_active_segments"),
        )
        quality_text = "{}/{}/{}".format(
            quality.get("quality_score"),
            quality.get("text_score"),
            quality.get("timing_mae_sec"),
        )
        lines.append(
            "| {run_id} | {elapsed} | {count} | {timeout_elapsed} | {ratio} | {labels} | {gates} | {quality} |".format(
                run_id=run.get("run_id"),
                elapsed=run.get("elapsed_sec"),
                count=run.get("timeout_fallback_count", 0) + run.get("word_precision_timeout_like_count", 0),
                timeout_elapsed=run.get("timeout_total_elapsed_sec"),
                ratio=run.get("timeout_elapsed_ratio"),
                labels=json.dumps(run.get("timeout_labels") or {}, ensure_ascii=False),
                gates=gate_text,
                quality=quality_text,
            )
        )
    lines.extend(["", "## Guardrails", ""])
    for item in list(audit.get("blocked_runtime_changes") or []):
        lines.append(f"- Do not apply `{item}` from this audit alone.")
    lines.extend(["", "## Next Safe Actions", ""])
    for item in list(audit.get("next_safe_actions") or []):
        lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def _expand_paths(inputs: list[str], globs: list[str]) -> list[Path]:
    paths: list[Path] = [Path(item) for item in inputs]
    for pattern in globs:
        paths.extend(Path(item) for item in glob.glob(pattern))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path)
        if marker in seen or not path.exists():
            continue
        seen.add(marker)
        unique.append(path)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit STT worker timeout evidence in benchmark artifacts.")
    parser.add_argument("paths", nargs="*", help="benchmark_results.json paths")
    parser.add_argument("--glob", action="append", default=[], help="Additional benchmark_results.json glob")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    paths = _expand_paths(list(args.paths or []), list(args.glob or []))
    audit = build_audit(paths)
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stt_worker_timeout_audit.json"
    md_path = output_dir / "stt_worker_timeout_audit.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "timeout_detected": audit["timeout_detected"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
