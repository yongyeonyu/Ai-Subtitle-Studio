#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from statistics import mean
from pathlib import Path
from typing import Any

from core.audio.audio_runtime_services import memory_pressure_stage_details_from_snapshot

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_TOOL = ROOT / "tools" / "benchmark_subtitle_pipeline_variants.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PRESET_VARIANTS: dict[str, list[str]] = {
    "baseline_same_slice": ["stt_original_selective_no_llm"],
    "apple_case1_timing": ["apple_case1_high_selective_timing_priority"],
    "apple_case2_timing": ["apple_case2_high_selective_timing_priority"],
    "apple_case2_selective": ["apple_case2_high_selective"],
    "apple_compare_triplet": [
        "stt_original_selective_no_llm",
        "apple_case1_high_selective_timing_priority",
        "apple_case2_high_selective",
    ],
}
DEFAULT_MATRIX_PRESETS: list[str] = [
    "baseline_same_slice",
    "apple_case1_timing",
    "apple_case2_timing",
]
DEFAULT_ACCEPTED_BASELINE_JSON = (
    ROOT / ".codex_work" / "benchmarks" / "subtitle_pipeline_variants" / "20260602_034322" / "benchmark_results.json"
)
DEFAULT_ACCEPTED_CASE1_JSON = (
    ROOT / ".codex_work" / "benchmarks" / "subtitle_pipeline_variants" / "20260602_080210_685563_22342" / "benchmark_results.json"
)
DEFAULT_ACCEPTED_CASE2_JSON = (
    ROOT / ".codex_work" / "benchmarks" / "subtitle_pipeline_variants" / "20260602_104005_026621_11559" / "benchmark_results.json"
)


def _server_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("AI_SUBTITLE_SERVER_MODE", "1")
    env.setdefault("AI_SUBTITLE_SERVER_NO_UI", "1")
    env.setdefault("AI_SUBTITLE_STUDIO_QA_USE_SOURCE", "0")
    return env


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run AI Subtitle Studio subtitle benchmarks without launching the UI."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    benchmark = sub.add_parser("benchmark", help="Run the existing benchmark tool in no-UI mode.")
    benchmark.add_argument("--media", required=True)
    benchmark.add_argument("--reference-srt", required=True)
    benchmark.add_argument("--start-sec", type=float, default=0.0)
    benchmark.add_argument("--duration-sec", type=float, default=30.0)
    benchmark.add_argument("--suite", default="variants")
    benchmark.add_argument("--stt-profile", default="current")
    benchmark.add_argument("--ranking-policy", default="timing_priority_speed_weighted")
    benchmark.add_argument("--llm-model", default="")
    benchmark.add_argument("--cached-raw-segments", default="")
    benchmark.add_argument("--keep-artifacts", action="store_true")
    benchmark.add_argument("--variants", nargs="*", default=[])

    probe = sub.add_parser("probe-apple", help="Probe current Apple Speech runtime support.")
    probe.add_argument("--locale", default="ko-KR")

    preset = sub.add_parser("benchmark-preset", help="Run a named no-UI Apple/baseline benchmark preset.")
    preset.add_argument("--preset", choices=sorted(PRESET_VARIANTS), required=True)
    preset.add_argument("--media", required=True)
    preset.add_argument("--reference-srt", required=True)
    preset.add_argument("--start-sec", type=float, default=0.0)
    preset.add_argument("--duration-sec", type=float, default=30.0)
    preset.add_argument("--suite", default="variants")
    preset.add_argument("--stt-profile", default="current")
    preset.add_argument("--ranking-policy", default="timing_priority_speed_weighted")
    preset.add_argument("--llm-model", default="")
    preset.add_argument("--cached-raw-segments", default="")
    preset.add_argument("--keep-artifacts", action="store_true")

    repeat = sub.add_parser("repeat-preset", help="Run a named preset multiple times and summarize the variance.")
    repeat.add_argument("--preset", choices=sorted(PRESET_VARIANTS), required=True)
    repeat.add_argument("--media", required=True)
    repeat.add_argument("--reference-srt", required=True)
    repeat.add_argument("--start-sec", type=float, default=0.0)
    repeat.add_argument("--duration-sec", type=float, default=30.0)
    repeat.add_argument("--suite", default="variants")
    repeat.add_argument("--stt-profile", default="current")
    repeat.add_argument("--ranking-policy", default="timing_priority_speed_weighted")
    repeat.add_argument("--llm-model", default="")
    repeat.add_argument("--cached-raw-segments", default="")
    repeat.add_argument("--keep-artifacts", action="store_true")
    repeat.add_argument("--repeat", type=int, default=3)

    matrix = sub.add_parser(
        "matrix-preset",
        help="Run multiple named presets sequentially in no-UI mode and emit compact winner/delta summaries.",
    )
    matrix.add_argument("--presets", nargs="+", choices=sorted(PRESET_VARIANTS), default=list(DEFAULT_MATRIX_PRESETS))
    matrix.add_argument("--media", required=True)
    matrix.add_argument("--reference-srt", required=True)
    matrix.add_argument("--start-sec", type=float, default=0.0)
    matrix.add_argument("--duration-sec", type=float, default=30.0)
    matrix.add_argument("--suite", default="variants")
    matrix.add_argument("--stt-profile", default="current")
    matrix.add_argument("--ranking-policy", default="timing_priority_speed_weighted")
    matrix.add_argument("--llm-model", default="")
    matrix.add_argument("--cached-raw-segments", default="")
    matrix.add_argument("--keep-artifacts", action="store_true")

    matrix_repeat = sub.add_parser(
        "matrix-repeat",
        help="Run multiple named presets sequentially, repeating each preset, and emit aggregate no-UI comparisons.",
    )
    matrix_repeat.add_argument("--presets", nargs="+", choices=sorted(PRESET_VARIANTS), default=list(DEFAULT_MATRIX_PRESETS))
    matrix_repeat.add_argument("--media", required=True)
    matrix_repeat.add_argument("--reference-srt", required=True)
    matrix_repeat.add_argument("--start-sec", type=float, default=0.0)
    matrix_repeat.add_argument("--duration-sec", type=float, default=30.0)
    matrix_repeat.add_argument("--suite", default="variants")
    matrix_repeat.add_argument("--stt-profile", default="current")
    matrix_repeat.add_argument("--ranking-policy", default="timing_priority_speed_weighted")
    matrix_repeat.add_argument("--llm-model", default="")
    matrix_repeat.add_argument("--cached-raw-segments", default="")
    matrix_repeat.add_argument("--keep-artifacts", action="store_true")
    matrix_repeat.add_argument("--repeat", type=int, default=2)

    summary = sub.add_parser("artifact-summary", help="Summarize a benchmark result artifact as compact JSON.")
    summary.add_argument("--json", required=True)

    compare = sub.add_parser("compare-artifacts", help="Compare two benchmark result artifacts with compact deltas.")
    compare.add_argument("--baseline-json", required=True)
    compare.add_argument("--candidate-json", required=True)

    compare_current = sub.add_parser(
        "compare-current-vs-accepted",
        help="Compare one current artifact against the accepted baseline/case1/case2 artifact from no-UI server mode.",
    )
    compare_current.add_argument("--current-json", required=True)
    compare_current.add_argument("--accepted-target", choices=["baseline", "case1", "case2"])
    compare_current.add_argument("--accepted-json", default="")
    compare_current.add_argument("--accepted-label", default="")
    compare_current.add_argument("--baseline-json", default=str(DEFAULT_ACCEPTED_BASELINE_JSON))
    compare_current.add_argument("--case1-json", default=str(DEFAULT_ACCEPTED_CASE1_JSON))
    compare_current.add_argument("--case2-json", default=str(DEFAULT_ACCEPTED_CASE2_JSON))

    plan = sub.add_parser(
        "next-owner-plan",
        help="Generate the next bounded no-UI experiment shortlist from an artifact or accepted target.",
    )
    plan.add_argument("--artifact-json", default="")
    plan.add_argument("--accepted-target", choices=["baseline", "case1", "case2"])
    plan.add_argument("--baseline-json", default=str(DEFAULT_ACCEPTED_BASELINE_JSON))
    plan.add_argument("--case1-json", default=str(DEFAULT_ACCEPTED_CASE1_JSON))
    plan.add_argument("--case2-json", default=str(DEFAULT_ACCEPTED_CASE2_JSON))

    standings = sub.add_parser(
        "accepted-standings",
        help="Summarize the current accepted baseline/case1/case2 no-UI benchmark artifacts as one compact JSON report.",
    )
    standings.add_argument("--baseline-json", default=str(DEFAULT_ACCEPTED_BASELINE_JSON))
    standings.add_argument("--case1-json", default=str(DEFAULT_ACCEPTED_CASE1_JSON))
    standings.add_argument("--case2-json", default=str(DEFAULT_ACCEPTED_CASE2_JSON))

    return parser


def _benchmark_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(BENCHMARK_TOOL),
        "--media",
        str(args.media),
        "--reference-srt",
        str(args.reference_srt),
        "--start-sec",
        str(float(args.start_sec)),
        "--duration-sec",
        str(float(args.duration_sec)),
        "--suite",
        str(args.suite),
        "--stt-profile",
        str(args.stt_profile),
        "--ranking-policy",
        str(args.ranking_policy),
    ]
    if str(args.llm_model or "").strip():
        command.extend(["--llm-model", str(args.llm_model).strip()])
    if str(args.cached_raw_segments or "").strip():
        command.extend(["--cached-raw-segments", str(args.cached_raw_segments).strip()])
    if bool(args.keep_artifacts):
        command.append("--keep-artifacts")
    variants = [str(item or "").strip() for item in list(args.variants or []) if str(item or "").strip()]
    if variants:
        command.append("--variants")
        command.extend(variants)
    return command


def _run_benchmark(args: argparse.Namespace) -> int:
    command = _benchmark_command(args)
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        env=_server_env(),
        text=True,
        capture_output=True,
    )
    payload: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "command": command,
        "cwd": str(ROOT),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return int(proc.returncode)


def _preset_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        media=args.media,
        reference_srt=args.reference_srt,
        start_sec=float(args.start_sec),
        duration_sec=float(args.duration_sec),
        suite=str(args.suite),
        stt_profile=str(args.stt_profile),
        ranking_policy=str(args.ranking_policy),
        llm_model=str(args.llm_model or ""),
        cached_raw_segments=str(args.cached_raw_segments or ""),
        keep_artifacts=bool(args.keep_artifacts),
        variants=list(PRESET_VARIANTS[str(args.preset)]),
    )


def _run_benchmark_preset(args: argparse.Namespace) -> int:
    payload = _run_preset_once_payload(
        preset_name=str(args.preset),
        media=str(args.media),
        reference_srt=str(args.reference_srt),
        start_sec=float(args.start_sec),
        duration_sec=float(args.duration_sec),
        suite=str(args.suite),
        stt_profile=str(args.stt_profile),
        ranking_policy=str(args.ranking_policy),
        llm_model=str(args.llm_model or ""),
        cached_raw_segments=str(args.cached_raw_segments or ""),
        keep_artifacts=bool(args.keep_artifacts),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def _extract_trailing_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    decoder = json.JSONDecoder()
    for index in range(len(raw)):
        if raw[index] != "{":
            continue
        try:
            payload, end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and raw[index + end :].strip() == "":
            return payload
    raise ValueError("trailing_json_object_not_found")


def _extract_recheck_source_counts(text: str) -> dict[str, int] | None:
    raw = str(text or "")
    matches = re.findall(
        r"후보 source low_score=(\d+)\s+missing_voice=(\d+)\s+route_hint=(\d+)\s+merged=(\d+)",
        raw,
    )
    if not matches:
        return None
    low_score, missing_voice, route_hint, merged = matches[-1]
    return {
        "low_score": int(low_score),
        "missing_voice": int(missing_voice),
        "route_hint": int(route_hint),
        "merged": int(merged),
    }


def _load_ranked_rows(json_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return list(payload.get("ranked_results") or payload.get("results") or [])


def _compact_row_summary(row: dict[str, Any]) -> dict[str, Any]:
    quality = dict(row.get("quality") or {})
    settings = dict(row.get("settings") or {})
    stt_summary = dict(row.get("native_stt_segments_summary") or {})
    return {
        "name": row.get("name"),
        "elapsed_sec": row.get("elapsed_sec"),
        "quality_score": quality.get("quality_score"),
        "timing_priority_quality_score": quality.get("timing_priority_quality_score"),
        "timing_mae_sec": quality.get("timing_mae_sec"),
        "rank": row.get("rank"),
        "error": row.get("error") or "",
        "selected_whisper_model": settings.get("selected_whisper_model"),
        "selected_whisper_model_secondary": settings.get("selected_whisper_model_secondary"),
        "word_precision_count": stt_summary.get("word_precision_count"),
        "stt2_selected_count": stt_summary.get("stt2_selected_count"),
        "recheck_applied_count": stt_summary.get("recheck_applied_count"),
        "stt2_coverage_ratio": stt_summary.get("stt2_coverage_ratio"),
        "secondary_hint_count": stt_summary.get("secondary_hint_count"),
        "source_switch_count": stt_summary.get("source_switch_count"),
        "stt1_selected_count": stt_summary.get("stt1_selected_count"),
        "segment_count": stt_summary.get("segment_count"),
    }


def _artifact_raw_segments_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "raw_segments.json"


def _artifact_output_segments_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "output_segments.json"


def _artifact_stage_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "stage_trace.json"


def _artifact_stage_runtime_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "stage_runtime_trace.json"


def _artifact_major_runtime_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "major_runtime_trace.json"


def _artifact_selective_ensemble_runtime_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "selective_ensemble_runtime_trace.json"


def _artifact_word_precision_runtime_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "word_precision_runtime_trace.json"


def _artifact_final_cleanup_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "final_cleanup_trace.json"


def _artifact_trim_recent_overlap_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "trim_recent_overlap_trace.json"


def _artifact_no_llm_raw_restore_trace_path(json_path: Path, winner_name: str) -> Path:
    return json_path.parent / str(winner_name or "").strip() / "no_llm_raw_restore_trace.json"


def _compact_artifact_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        start = round(float(item.get("start", 0.0) or 0.0), 3)
        end = round(float(item.get("end", start) or start), 3)
        selective_word_timestamps = dict(dict(item.get("asr_metadata") or {}).get("selective_word_timestamps") or {})
        compact.append(
            {
                "start": start,
                "end": end,
                "duration_sec": round(max(0.0, end - start), 3),
                "text": str(item.get("text") or "").strip(),
                "stt_word_precision_applied": bool(item.get("stt_word_precision_applied")),
                "stt_word_precision_split_applied": bool(item.get("stt_word_precision_split_applied")),
                "precision_range_start": round(float(selective_word_timestamps.get("range_start", 0.0) or 0.0), 3)
                if selective_word_timestamps.get("range_start") is not None
                else None,
                "precision_range_end": round(float(selective_word_timestamps.get("range_end", 0.0) or 0.0), 3)
                if selective_word_timestamps.get("range_end") is not None
                else None,
                "precision_source": str(selective_word_timestamps.get("source") or "").strip(),
                "precision_reject_reason": str(selective_word_timestamps.get("reject_reason") or "").strip(),
                "precision_reject_detail": dict(selective_word_timestamps.get("reject_detail") or {}),
            }
        )
    return compact


def _artifact_raw_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if not raw_path.exists():
        return None
    try:
        raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw_rows, list):
        return None
    return _compact_artifact_rows(raw_rows)


def _artifact_output_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    output_path = _artifact_output_segments_path(json_path, winner_name)
    if not output_path.exists():
        return None
    try:
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(output_rows, list):
        return None
    return _compact_artifact_rows(output_rows)


def _artifact_stt_anchor_guard_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    output_path = _artifact_output_segments_path(json_path, winner_name)
    if not output_path.exists():
        return None
    try:
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(output_rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in output_rows:
        if not isinstance(item, dict):
            continue
        guard_policy = dict(item.get("_final_stt_anchor_guard_policy") or {})
        trim_policy = dict(item.get("_final_stt_anchor_trim_policy") or {})
        if not guard_policy and not trim_policy:
            continue
        start = round(float(item.get("start", 0.0) or 0.0), 3)
        end = round(float(item.get("end", start) or start), 3)
        compact.append(
            {
                "start": start,
                "end": end,
                "duration_sec": round(max(0.0, end - start), 3),
                "text": str(item.get("text") or "").strip(),
                "guard_action": str(guard_policy.get("action") or "").strip(),
                "guard_source": str(guard_policy.get("source") or "").strip(),
                "trim_action": str(trim_policy.get("action") or "").strip(),
                "trim_inserted_text": str(trim_policy.get("inserted_text") or "").strip(),
            }
        )
    return compact


def _artifact_final_transcript_integrity_policy(json_path: Path, row: dict[str, Any]) -> dict[str, Any] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    output_path = _artifact_output_segments_path(json_path, winner_name)
    if not output_path.exists():
        return None
    try:
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(output_rows, list):
        return None
    for item in output_rows:
        if not isinstance(item, dict):
            continue
        policy = dict(item.get("_final_transcript_integrity_policy") or {})
        if not policy:
            continue
        return {
            "task": str(policy.get("task") or "").strip(),
            "accepted": bool(policy.get("accepted")),
            "reason": str(policy.get("reason") or "").strip(),
            "fallback": str(policy.get("fallback") or "").strip(),
            "source_segments": int(policy.get("source_segments") or 0),
            "final_segments": int(policy.get("final_segments") or 0),
            "source_compact_len": policy.get("source_compact_len"),
            "candidate_compact_len": policy.get("candidate_compact_len"),
            "similarity": policy.get("similarity"),
            "length_delta_ratio": policy.get("length_delta_ratio"),
        }
    return None


def _artifact_common_split_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    output_path = _artifact_output_segments_path(json_path, winner_name)
    if not output_path.exists():
        return None
    try:
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(output_rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in output_rows:
        if not isinstance(item, dict):
            continue
        policy = dict(item.get("_common_split_guard_policy") or {})
        if not policy:
            continue
        start = round(float(item.get("start", 0.0) or 0.0), 3)
        end = round(float(item.get("end", start) or start), 3)
        source_start = round(float(policy.get("source_start", start) or start), 3)
        source_end = round(float(policy.get("source_end", end) or end), 3)
        compact.append(
            {
                "start": start,
                "end": end,
                "duration_sec": round(max(0.0, end - start), 3),
                "text": str(item.get("text") or "").strip(),
                "action": str(policy.get("action") or "").strip(),
                "split_index": int(policy.get("split_index")) if policy.get("split_index") is not None else None,
                "split_count": int(policy.get("split_count")) if policy.get("split_count") is not None else None,
                "source_start": source_start,
                "source_end": source_end,
                "source_duration_sec": round(max(0.0, source_end - source_start), 3),
            }
        )
    return compact


def _artifact_missing_common_split_groups(common_split_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not common_split_rows:
        return []
    grouped: dict[tuple[float, float, int], dict[str, Any]] = {}
    for row in common_split_rows:
        if not isinstance(row, dict):
            continue
        split_count = row.get("split_count")
        split_index = row.get("split_index")
        source_start = row.get("source_start")
        source_end = row.get("source_end")
        if split_count is None or split_index is None or source_start is None or source_end is None:
            continue
        try:
            split_count_i = int(split_count)
            split_index_i = int(split_index)
            source_start_f = round(float(source_start), 3)
            source_end_f = round(float(source_end), 3)
        except Exception:
            continue
        if split_count_i <= 1:
            continue
        key = (source_start_f, source_end_f, split_count_i)
        group = grouped.setdefault(
            key,
            {
                "source_start": source_start_f,
                "source_end": source_end_f,
                "source_duration_sec": round(max(0.0, source_end_f - source_start_f), 3),
                "split_count": split_count_i,
                "observed_split_indexes": [],
                "sample_texts": [],
            },
        )
        observed = group["observed_split_indexes"]
        if split_index_i not in observed:
            observed.append(split_index_i)
        text = str(row.get("text") or "").strip()
        if text and text not in group["sample_texts"]:
            group["sample_texts"].append(text)
    compact: list[dict[str, Any]] = []
    for group in grouped.values():
        observed = sorted(int(item) for item in list(group.get("observed_split_indexes") or []))
        expected = list(range(int(group["split_count"])))
        missing = [item for item in expected if item not in observed]
        compact.append(
            {
                "source_start": group["source_start"],
                "source_end": group["source_end"],
                "source_duration_sec": group["source_duration_sec"],
                "split_count": group["split_count"],
                "observed_split_indexes": observed,
                "missing_split_indexes": missing,
                "observed_count": len(observed),
                "sample_texts": list(group["sample_texts"])[:5],
            }
        )
    compact.sort(key=lambda item: (item["source_start"], item["source_end"]))
    return compact


def _artifact_gap_owner_groups(
    common_split_rows: list[dict[str, Any]] | None,
    reference_gap_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not common_split_rows:
        return []
    grouped: dict[tuple[float, float], dict[str, Any]] = {}
    for row in list(common_split_rows or []):
        if not isinstance(row, dict):
            continue
        source_start = row.get("source_start")
        source_end = row.get("source_end")
        if source_start is None or source_end is None:
            source_start = row.get("start")
            source_end = row.get("end")
        try:
            source_start_f = round(float(source_start), 3)
            source_end_f = round(float(source_end), 3)
        except Exception:
            continue
        key = (source_start_f, source_end_f)
        group = grouped.setdefault(
            key,
            {
                "source_start": source_start_f,
                "source_end": source_end_f,
                "source_duration_sec": round(max(0.0, source_end_f - source_start_f), 3),
                "actions": [],
                "split_count": row.get("split_count"),
                "sample_texts": [],
                "reference_gap_rows": [],
                "reference_gap_count": 0,
                "reference_gap_total_duration_sec": 0.0,
            },
        )
        action = str(row.get("action") or "").strip()
        if action and action not in group["actions"]:
            group["actions"].append(action)
        if group.get("split_count") is None and row.get("split_count") is not None:
            group["split_count"] = row.get("split_count")
        text = str(row.get("text") or "").strip()
        if text and text not in group["sample_texts"]:
            group["sample_texts"].append(text)
    for gap in list(reference_gap_rows or []):
        if not isinstance(gap, dict):
            continue
        try:
            gap_start = round(float(gap.get("start", 0.0) or 0.0), 3)
            gap_end = round(float(gap.get("end", gap_start) or gap_start), 3)
        except Exception:
            continue
        overlap_hit: dict[str, Any] | None = None
        overlap_sec_best = 0.0
        for group in grouped.values():
            overlap_sec = max(
                0.0,
                min(float(group["source_end"]), gap_end) - max(float(group["source_start"]), gap_start),
            )
            if overlap_sec > overlap_sec_best:
                overlap_hit = group
                overlap_sec_best = overlap_sec
        if overlap_hit is None or overlap_sec_best <= 0.0:
            continue
        gap_text = str(gap.get("text") or "").strip()
        overlap_hit["reference_gap_rows"].append(
            {
                "start": gap_start,
                "end": gap_end,
                "duration_sec": round(max(0.0, gap_end - gap_start), 3),
                "text": gap_text,
                "overlap_sec": round(overlap_sec_best, 3),
                "best_overlap_ratio": gap.get("best_overlap_ratio"),
            }
        )
        overlap_hit["reference_gap_count"] += 1
        overlap_hit["reference_gap_total_duration_sec"] = round(
            float(overlap_hit.get("reference_gap_total_duration_sec") or 0.0)
            + max(0.0, gap_end - gap_start),
            3,
        )
    compact: list[dict[str, Any]] = []
    for group in grouped.values():
        if int(group.get("reference_gap_count") or 0) <= 0:
            continue
        compact.append(
            {
                "source_start": group["source_start"],
                "source_end": group["source_end"],
                "source_duration_sec": group["source_duration_sec"],
                "actions": list(group["actions"]),
                "split_count": group.get("split_count"),
                "sample_texts": list(group["sample_texts"])[:5],
                "reference_gap_count": int(group["reference_gap_count"] or 0),
                "reference_gap_total_duration_sec": round(float(group["reference_gap_total_duration_sec"] or 0.0), 3),
                "reference_gap_rows": list(group["reference_gap_rows"])[:8],
            }
        )
    compact.sort(
        key=lambda item: (
            -int(item.get("reference_gap_count") or 0),
            -float(item.get("reference_gap_total_duration_sec") or 0.0),
            float(item.get("source_start") or 0.0),
        )
    )
    return compact


def _raw_restore_group_class(group: dict[str, Any] | None) -> str:
    item = dict(group or {})
    singleton_count = int(item.get("singleton_word_text_count") or 0)
    phrase_count = int(item.get("phrase_word_text_count") or 0)
    if singleton_count > 0 and phrase_count == 0:
        return "all_singleton"
    if singleton_count > 0 and phrase_count > 0:
        return "mixed"
    if phrase_count > 0:
        return "all_phrase"
    return ""


def _artifact_span_owner_flow(
    common_split_rows: list[dict[str, Any]] | None,
    missing_common_split_groups: list[dict[str, Any]] | None,
    raw_restore_restore_groups: list[dict[str, Any]] | None,
    trim_recent_overlap_trace: list[dict[str, Any]] | None,
    gap_owner_groups: list[dict[str, Any]] | None,
    stage_trace: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    if not common_split_rows:
        return []
    missing_map = {
        (
            round(float(item.get("source_start", 0.0) or 0.0), 3),
            round(float(item.get("source_end", 0.0) or 0.0), 3),
        ): dict(item)
        for item in list(missing_common_split_groups or [])
        if isinstance(item, dict)
    }
    gap_map = {
        (
            round(float(item.get("source_start", 0.0) or 0.0), 3),
            round(float(item.get("source_end", 0.0) or 0.0), 3),
        ): dict(item)
        for item in list(gap_owner_groups or [])
        if isinstance(item, dict)
    }
    restore_groups = [dict(item) for item in list(raw_restore_restore_groups or []) if isinstance(item, dict)]
    trim_rows = [dict(item) for item in list(trim_recent_overlap_trace or []) if isinstance(item, dict)]
    pre_cleanup_rows = []
    preferred_stage_names = (
        "pre_cleanup_review",
        "final_integrity_guard",
        "deep_split",
    )
    for stage_name in preferred_stage_names:
        for item in list(stage_trace or []):
            if not isinstance(item, dict):
                continue
            if str(item.get("stage") or "").strip() != stage_name:
                continue
            rows = [dict(row) for row in list(item.get("rows") or []) if isinstance(row, dict)]
            if not rows:
                continue
            pre_cleanup_rows = rows
            break
        if pre_cleanup_rows:
            break
    grouped: dict[tuple[float, float], dict[str, Any]] = {}
    for row in list(common_split_rows or []):
        if not isinstance(row, dict):
            continue
        try:
            source_start = round(float(row.get("source_start", row.get("start", 0.0)) or 0.0), 3)
            source_end = round(float(row.get("source_end", row.get("end", source_start)) or source_start), 3)
        except Exception:
            continue
        key = (source_start, source_end)
        group = grouped.setdefault(
            key,
            {
                "source_start": source_start,
                "source_end": source_end,
                "source_duration_sec": round(max(0.0, source_end - source_start), 3),
                "actions": [],
                "split_count": row.get("split_count"),
                "sample_texts": [],
                "common_split_output_count": 0,
            },
        )
        action = str(row.get("action") or "").strip()
        if action and action not in group["actions"]:
            group["actions"].append(action)
        if group.get("split_count") is None and row.get("split_count") is not None:
            group["split_count"] = row.get("split_count")
        text = str(row.get("text") or "").strip()
        if text and text not in group["sample_texts"]:
            group["sample_texts"].append(text)
        group["common_split_output_count"] += 1
    compact: list[dict[str, Any]] = []
    for key, group in grouped.items():
        source_start, source_end = key
        sample_texts = list(group.get("sample_texts") or [])
        split_count = group.get("split_count")
        missing = missing_map.get(key) or {}
        gap_group = gap_map.get(key) or {}
        matched_restore_group = None
        for restore_group in restore_groups:
            if restore_group.get("split_count") != split_count:
                continue
            raw_text = str(restore_group.get("raw_text") or "").strip()
            if raw_text and raw_text in sample_texts:
                matched_restore_group = restore_group
                break
        trim_matches = []
        for item in trim_rows:
            if item.get("split_count") != split_count:
                continue
            if str(item.get("text") or "").strip() not in sample_texts:
                continue
            trim_matches.append(item)
        pre_cleanup_matches = []
        for item in pre_cleanup_rows:
            try:
                item_source_start = round(float(item.get("source_start", item.get("start", 0.0)) or 0.0), 3)
                item_source_end = round(float(item.get("source_end", item.get("end", item_source_start)) or item_source_start), 3)
            except Exception:
                continue
            if (item_source_start, item_source_end) != key:
                continue
            pre_cleanup_matches.append(
                {
                    "start": round(float(item.get("start", 0.0) or 0.0), 3),
                    "end": round(float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0) or 0.0), 3),
                    "duration_sec": round(float(item.get("duration_sec", 0.0) or 0.0), 3),
                    "text": str(item.get("text") or "").strip(),
                    "split_index": item.get("split_index"),
                    "split_count": item.get("split_count"),
                    "raw_text": str(item.get("raw_text") or "").strip(),
                    "word_text": str(item.get("word_text") or "").strip(),
                    "raw_lock_reason": str(item.get("raw_lock_reason") or "").strip(),
                }
            )
        trim_decision_counts = {"keep": 0, "trim": 0, "drop": 0}
        trim_drop_indexes: list[int] = []
        trim_keep_indexes: list[int] = []
        trim_trim_indexes: list[int] = []
        for item in trim_matches:
            decision = str(item.get("decision") or "").strip()
            if decision in trim_decision_counts:
                trim_decision_counts[decision] += 1
            split_index = item.get("split_index")
            if split_index is None:
                continue
            try:
                split_index_i = int(split_index)
            except Exception:
                continue
            if decision == "drop" and split_index_i not in trim_drop_indexes:
                trim_drop_indexes.append(split_index_i)
            elif decision == "keep" and split_index_i not in trim_keep_indexes:
                trim_keep_indexes.append(split_index_i)
            elif decision == "trim" and split_index_i not in trim_trim_indexes:
                trim_trim_indexes.append(split_index_i)
        compact.append(
            {
                "source_start": source_start,
                "source_end": source_end,
                "source_duration_sec": group["source_duration_sec"],
                "actions": list(group.get("actions") or []),
                "split_count": split_count,
                "sample_texts": sample_texts[:5],
                "common_split_output_count": int(group.get("common_split_output_count") or 0),
                "observed_split_indexes": list(missing.get("observed_split_indexes") or []),
                "missing_split_indexes": list(missing.get("missing_split_indexes") or []),
                "raw_restore_group": {
                    "present": bool(matched_restore_group),
                    "class": _raw_restore_group_class(matched_restore_group),
                    "restored_split_indexes": list((matched_restore_group or {}).get("restored_split_indexes") or []),
                    "restored_count": int((matched_restore_group or {}).get("restored_count") or 0),
                    "has_digit_word_text": bool((matched_restore_group or {}).get("has_digit_word_text")),
                    "singleton_word_text_count": int((matched_restore_group or {}).get("singleton_word_text_count") or 0),
                    "phrase_word_text_count": int((matched_restore_group or {}).get("phrase_word_text_count") or 0),
                },
                "trim_recent_overlap": {
                    "decision_counts": trim_decision_counts,
                    "drop_split_indexes": sorted(trim_drop_indexes),
                    "keep_split_indexes": sorted(trim_keep_indexes),
                    "trim_split_indexes": sorted(trim_trim_indexes),
                },
                "reference_gap_count": int(gap_group.get("reference_gap_count") or 0),
                "reference_gap_total_duration_sec": round(float(gap_group.get("reference_gap_total_duration_sec") or 0.0), 3),
                "reference_gap_rows": list(gap_group.get("reference_gap_rows") or [])[:8],
                "pre_cleanup_rows": pre_cleanup_matches[:8],
            }
        )
    compact.sort(
        key=lambda item: (
            -float(item.get("reference_gap_total_duration_sec") or 0.0),
            -int(item.get("reference_gap_count") or 0),
            float(item.get("source_start") or 0.0),
        )
    )
    return compact


def _artifact_stage_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_stage_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows: list[dict[str, Any]] = []
        for raw_row in list(item.get("rows") or []):
            if not isinstance(raw_row, dict):
                continue
            rows.append(
                {
                    "start": round(float(raw_row.get("start", 0.0) or 0.0), 3),
                    "end": round(float(raw_row.get("end", 0.0) or 0.0), 3),
                    "duration_sec": round(float(raw_row.get("duration_sec", 0.0) or 0.0), 3),
                    "text": str(raw_row.get("text") or "").strip(),
                    "split_index": raw_row.get("split_index"),
                    "split_count": raw_row.get("split_count"),
                    "source_start": raw_row.get("source_start"),
                    "source_end": raw_row.get("source_end"),
                    "selected_source": str(raw_row.get("selected_source") or "").strip(),
                    "has_common_split_policy": bool(raw_row.get("has_common_split_policy")),
                    "raw_lock_reason": str(raw_row.get("raw_lock_reason") or "").strip(),
                    "restored_after_postprocess": bool(raw_row.get("restored_after_postprocess")),
                    "raw_text": str(raw_row.get("raw_text") or "").strip(),
                    "word_text": str(raw_row.get("word_text") or "").strip(),
                }
            )
        compact.append(
            {
                "stage": str(item.get("stage") or "").strip(),
                "stage_label": str(item.get("stage_label") or "").strip(),
                "segment_count": int(item.get("segment_count") or 0),
                "sample_texts": [str(text).strip() for text in list(item.get("sample_texts") or [])[:5]],
                "first_start": item.get("first_start"),
                "last_end": item.get("last_end"),
                "rows": rows,
            }
        )
    return compact


def _artifact_stage_runtime_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_stage_runtime_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        rows = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "stage": str(item.get("stage") or "").strip(),
                "stage_label": str(item.get("stage_label") or "").strip(),
                "segment_count": int(item.get("segment_count") or 0),
                "since_first_ms": round(float(item.get("since_first_ms", 0.0) or 0.0), 3),
                "since_previous_ms": (
                    round(float(item.get("since_previous_ms", 0.0) or 0.0), 3)
                    if item.get("since_previous_ms") is not None
                    else None
                ),
            }
        )
    return compact


def _artifact_major_runtime_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_major_runtime_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        rows = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "phase": str(item.get("phase") or "").strip(),
                "elapsed_ms": round(float(item.get("elapsed_ms", 0.0) or 0.0), 3),
                "since_start_ms": round(float(item.get("since_start_ms", 0.0) or 0.0), 3),
                "row_count": int(item.get("row_count", 0) or 0) if item.get("row_count") is not None else None,
            }
        )
    return compact


def _artifact_selective_ensemble_runtime_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_selective_ensemble_runtime_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        rows = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        collect_runtime_info = dict(item.get("collect_runtime_info") or {})
        collect_runtime_info_payload = None
        if collect_runtime_info:
            resource_snapshot = dict(collect_runtime_info.get("resource_snapshot") or {})
            collect_runtime_info_payload = {
                "model": str(collect_runtime_info.get("model") or "").strip(),
                "cache_key": str(collect_runtime_info.get("cache_key") or "").strip(),
                "reuse_enabled": bool(collect_runtime_info.get("reuse_enabled")),
                "worker_source": str(collect_runtime_info.get("worker_source") or "").strip(),
                "transient_worker": bool(collect_runtime_info.get("transient_worker")),
                "native_memory_snapshot_force_refresh": bool(
                    collect_runtime_info.get("native_memory_snapshot_force_refresh")
                ),
                "preexisting_child_processor_count": int(
                    collect_runtime_info.get("preexisting_child_processor_count", 0) or 0
                ),
                "preexisting_cached_worker_count": int(
                    collect_runtime_info.get("preexisting_cached_worker_count", 0) or 0
                ),
                "preexisting_busy_worker_count": int(
                    collect_runtime_info.get("preexisting_busy_worker_count", 0) or 0
                ),
                "preexisting_alive_owner_runtime_count": int(
                    collect_runtime_info.get("preexisting_alive_owner_runtime_count", 0) or 0
                ),
                "preexisting_alive_child_runtime_count": int(
                    collect_runtime_info.get("preexisting_alive_child_runtime_count", 0) or 0
                ),
                "preexisting_alive_cached_worker_count": int(
                    collect_runtime_info.get("preexisting_alive_cached_worker_count", 0) or 0
                ),
                "preexisting_alive_runtime_total_count": int(
                    collect_runtime_info.get("preexisting_alive_runtime_total_count", 0) or 0
                ),
                "pressure_stage": str(collect_runtime_info.get("pressure_stage") or "").strip(),
                "allow_collect_worker_reuse": bool(collect_runtime_info.get("allow_collect_worker_reuse")),
                "duration_first_submission_enabled": bool(
                    collect_runtime_info.get("duration_first_submission_enabled")
                ),
                "submission_order_indices": [
                    int(idx) for idx in list(collect_runtime_info.get("submission_order_indices") or [])
                ],
                "submitted_chunk_paths": [
                    str(path or "").strip()
                    for path in list(collect_runtime_info.get("submitted_chunk_paths") or [])
                ],
                "submitted_chunk_durations_sec": [
                    round(float(value or 0.0), 3)
                    for value in list(collect_runtime_info.get("submitted_chunk_durations_sec") or [])
                ],
                "submitted_chunk_offsets_sec": [
                    round(float(value or 0.0), 3)
                    for value in list(collect_runtime_info.get("submitted_chunk_offsets_sec") or [])
                ],
                "completed_chunk_paths": [
                    str(path or "").strip()
                    for path in list(collect_runtime_info.get("completed_chunk_paths") or [])
                ],
                "completed_chunk_elapsed_ms": [
                    round(float(value or 0.0), 3)
                    for value in list(collect_runtime_info.get("completed_chunk_elapsed_ms") or [])
                ],
                "emitted_chunk_paths": [
                    str(path or "").strip()
                    for path in list(collect_runtime_info.get("emitted_chunk_paths") or [])
                ],
                "emitted_chunk_elapsed_ms": [
                    round(float(value or 0.0), 3)
                    for value in list(collect_runtime_info.get("emitted_chunk_elapsed_ms") or [])
                ],
                "stt_benchmark_plan": (
                    {
                        "requested_model": str(
                            dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("requested_model") or ""
                        ).strip(),
                        "active_backend": str(
                            dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("active_backend") or ""
                        ).strip(),
                        "active_model": str(
                            dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("active_model") or ""
                        ).strip(),
                        "active_reason": str(
                            dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("active_reason") or ""
                        ).strip(),
                        "challengers": [
                            {
                                "backend": str(dict(challenger or {}).get("backend") or "").strip(),
                                "model": str(dict(challenger or {}).get("model") or "").strip(),
                                "reason": str(dict(challenger or {}).get("reason") or "").strip(),
                            }
                            for challenger in list(
                                dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("challengers") or []
                            )
                            if isinstance(challenger, dict)
                        ],
                        "vad_challenger": (
                            {
                                "provider": str(
                                    dict(
                                        dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get(
                                            "vad_challenger"
                                        )
                                        or {}
                                    ).get("provider")
                                    or ""
                                ).strip(),
                                "reason": str(
                                    dict(
                                        dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get(
                                            "vad_challenger"
                                        )
                                        or {}
                                    ).get("reason")
                                    or ""
                                ).strip(),
                            }
                            if isinstance(
                                dict(collect_runtime_info.get("stt_benchmark_plan") or {}).get("vad_challenger"),
                                dict,
                            )
                            else None
                        ),
                    }
                    if isinstance(collect_runtime_info.get("stt_benchmark_plan"), dict)
                    else None
                ),
                "resource_snapshot": (
                    {
                        "available_memory_ratio": round(
                            float(resource_snapshot.get("available_memory_ratio", 0.0) or 0.0),
                            4,
                        )
                        if resource_snapshot.get("available_memory_ratio") is not None
                        else None,
                        "compressed_memory_ratio": round(
                            float(resource_snapshot.get("compressed_memory_ratio", 0.0) or 0.0),
                            4,
                        )
                        if resource_snapshot.get("compressed_memory_ratio") is not None
                        else None,
                        "process_rss_bytes": int(resource_snapshot.get("process_rss_bytes", 0) or 0)
                        if resource_snapshot.get("process_rss_bytes") is not None
                        else None,
                        "memory_pressure_stage": str(resource_snapshot.get("memory_pressure_stage") or "").strip(),
                    }
                    if resource_snapshot
                    else None
                ),
            }
        compact.append(
            {
                "phase": str(item.get("phase") or "").strip(),
                "elapsed_ms": round(float(item.get("elapsed_ms", 0.0) or 0.0), 3),
                "row_count": int(item.get("row_count", 0) or 0) if item.get("row_count") is not None else None,
                "model": str(item.get("model") or "").strip(),
                "adjusted_count": int(item.get("adjusted_count", 0) or 0)
                if item.get("adjusted_count") is not None
                else None,
                "collect_runtime_info_found": bool(item.get("collect_runtime_info_found")),
                "collect_runtime_info": collect_runtime_info_payload,
                "recheck_plan_source_counts": (
                    {
                        "low_score": int(dict(item.get("recheck_plan_source_counts") or {}).get("low_score", 0) or 0),
                        "missing_voice": int(
                            dict(item.get("recheck_plan_source_counts") or {}).get("missing_voice", 0) or 0
                        ),
                        "route_hint": int(
                            dict(item.get("recheck_plan_source_counts") or {}).get("route_hint", 0) or 0
                        ),
                        "merged": int(dict(item.get("recheck_plan_source_counts") or {}).get("merged", 0) or 0),
                    }
                    if isinstance(item.get("recheck_plan_source_counts"), dict)
                    else None
                ),
                "raw_range_count": int(item.get("raw_range_count", 0) or 0)
                if item.get("raw_range_count") is not None
                else None,
                "range_count": int(item.get("range_count", 0) or 0)
                if item.get("range_count") is not None
                else None,
                "prepared_clip_count": int(item.get("prepared_clip_count", 0) or 0)
                if item.get("prepared_clip_count") is not None
                else None,
                "collected_segment_count": int(item.get("collected_segment_count", 0) or 0)
                if item.get("collected_segment_count") is not None
                else None,
                "applied_range_count": int(item.get("applied_range_count", 0) or 0)
                if item.get("applied_range_count") is not None
                else None,
                "skipped_range_count": int(item.get("skipped_range_count", 0) or 0)
                if item.get("skipped_range_count") is not None
                else None,
                "applied_segment_count": int(item.get("applied_segment_count", 0) or 0)
                if item.get("applied_segment_count") is not None
                else None,
                "retained_primary_segment_count": int(item.get("retained_primary_segment_count", 0) or 0)
                if item.get("retained_primary_segment_count") is not None
                else None,
                "annotate_error": str(item.get("annotate_error") or "").strip(),
            }
        )
    return compact


def _artifact_word_precision_runtime_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_word_precision_runtime_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        rows = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        collect_runtime_info = dict(item.get("collect_runtime_info") or {})
        resource_snapshot = dict(collect_runtime_info.get("resource_snapshot") or {})
        compact.append(
            {
                "phase": str(item.get("phase") or "").strip(),
                "elapsed_ms": round(float(item.get("elapsed_ms", 0.0) or 0.0), 3),
                "segment_count": int(item.get("segment_count", 0) or 0)
                if item.get("segment_count") is not None
                else None,
                "range_count": int(item.get("range_count", 0) or 0)
                if item.get("range_count") is not None
                else None,
                "prepared_clip_count": int(item.get("prepared_clip_count", 0) or 0)
                if item.get("prepared_clip_count") is not None
                else None,
                "prepared_total_clip_duration_sec": round(float(item.get("prepared_total_clip_duration_sec", 0.0) or 0.0), 3)
                if item.get("prepared_total_clip_duration_sec") is not None
                else None,
                "prepared_max_clip_duration_sec": round(float(item.get("prepared_max_clip_duration_sec", 0.0) or 0.0), 3)
                if item.get("prepared_max_clip_duration_sec") is not None
                else None,
                    "prepared_clip_rows": [
                        {
                            "path": str((clip or {}).get("path") or "").strip(),
                            "start": round(float((clip or {}).get("start", 0.0) or 0.0), 3),
                            "end": round(float((clip or {}).get("end", 0.0) or 0.0), 3),
                            "duration_sec": round(float((clip or {}).get("duration_sec", 0.0) or 0.0), 3),
                            "source_chunk_path": str((clip or {}).get("source_chunk_path") or "").strip(),
                            "source_chunk_start": round(float((clip or {}).get("source_chunk_start", 0.0) or 0.0), 3)
                            if (clip or {}).get("source_chunk_start") is not None
                            else None,
                            "source_chunk_duration_sec": round(
                                float((clip or {}).get("source_chunk_duration_sec", 0.0) or 0.0),
                                3,
                            )
                            if (clip or {}).get("source_chunk_duration_sec") is not None
                            else None,
                            "local_start": round(float((clip or {}).get("local_start", 0.0) or 0.0), 3)
                            if (clip or {}).get("local_start") is not None
                            else None,
                            "local_end": round(float((clip or {}).get("local_end", 0.0) or 0.0), 3)
                            if (clip or {}).get("local_end") is not None
                            else None,
                            "padding_sec": round(float((clip or {}).get("padding_sec", 0.0) or 0.0), 3)
                            if (clip or {}).get("padding_sec") is not None
                            else None,
                            "primary_text": str((clip or {}).get("primary_text") or "").strip(),
                            "secondary_text": str((clip or {}).get("secondary_text") or "").strip(),
                            "best_original_score": round(float((clip or {}).get("best_original_score", 0.0) or 0.0), 3),
                            "collected_segment_count": int((clip or {}).get("collected_segment_count", 0) or 0)
                            if (clip or {}).get("collected_segment_count") is not None
                            else None,
                            "collected_text_segment_count": int((clip or {}).get("collected_text_segment_count", 0) or 0)
                            if (clip or {}).get("collected_text_segment_count") is not None
                            else None,
                            "collected_total_duration_sec": round(
                                float((clip or {}).get("collected_total_duration_sec", 0.0) or 0.0),
                                3,
                            )
                            if (clip or {}).get("collected_total_duration_sec") is not None
                            else None,
                            "collected_sample_texts": [
                                str(text or "").strip()
                                for text in list((clip or {}).get("collected_sample_texts") or [])
                            ],
                        }
                        for clip in list(item.get("prepared_clip_rows") or [])
                        if isinstance(clip, dict)
                    ],
                "collected_segment_count": int(item.get("collected_segment_count", 0) or 0)
                if item.get("collected_segment_count") is not None
                else None,
                "collect_owner_bound": bool(item.get("collect_owner_bound")),
                "collect_owner_type": str(item.get("collect_owner_type") or "").strip(),
                "collect_runtime_info_found": bool(item.get("collect_runtime_info_found")),
                "collect_runtime_info": (
                    {
                        "model": str(collect_runtime_info.get("model") or "").strip(),
                        "cache_key": str(collect_runtime_info.get("cache_key") or "").strip(),
                        "reuse_enabled": bool(collect_runtime_info.get("reuse_enabled")),
                        "worker_source": str(collect_runtime_info.get("worker_source") or "").strip(),
                        "transient_worker": bool(collect_runtime_info.get("transient_worker")),
                        "pressure_stage": str(collect_runtime_info.get("pressure_stage") or "").strip(),
                        "allow_collect_worker_reuse": bool(
                            collect_runtime_info.get("allow_collect_worker_reuse")
                        ),
                        "preexisting_child_processor_count": int(
                            collect_runtime_info.get("preexisting_child_processor_count", 0) or 0
                        ),
                        "preexisting_cached_worker_count": int(
                            collect_runtime_info.get("preexisting_cached_worker_count", 0) or 0
                        ),
                        "preexisting_busy_worker_count": int(
                            collect_runtime_info.get("preexisting_busy_worker_count", 0) or 0
                        ),
                        "preexisting_alive_owner_runtime_count": int(
                            collect_runtime_info.get("preexisting_alive_owner_runtime_count", 0) or 0
                        ),
                        "preexisting_alive_child_runtime_count": int(
                            collect_runtime_info.get("preexisting_alive_child_runtime_count", 0) or 0
                        ),
                        "preexisting_alive_cached_worker_count": int(
                            collect_runtime_info.get("preexisting_alive_cached_worker_count", 0) or 0
                        ),
                        "preexisting_alive_runtime_total_count": int(
                            collect_runtime_info.get("preexisting_alive_runtime_total_count", 0) or 0
                        ),
                        "resource_snapshot": (
                            {
                                "available_memory_ratio": round(
                                    float(resource_snapshot.get("available_memory_ratio", 0.0) or 0.0),
                                    4,
                                )
                                if resource_snapshot.get("available_memory_ratio") is not None
                                else None,
                                "compressed_memory_ratio": round(
                                    float(resource_snapshot.get("compressed_memory_ratio", 0.0) or 0.0),
                                    4,
                                )
                                if resource_snapshot.get("compressed_memory_ratio") is not None
                                else None,
                                "process_rss_bytes": int(resource_snapshot.get("process_rss_bytes", 0) or 0)
                                if resource_snapshot.get("process_rss_bytes") is not None
                                else None,
                                "memory_pressure_stage": str(resource_snapshot.get("memory_pressure_stage") or "").strip(),
                            }
                            if resource_snapshot
                            else None
                        ),
                        "pressure_stage_source": str(collect_runtime_info.get("pressure_stage_source") or "").strip(),
                        "pressure_stage_trigger_reason": str(
                            collect_runtime_info.get("pressure_stage_trigger_reason") or ""
                        ).strip(),
                        "duration_first_submission_enabled": bool(
                            collect_runtime_info.get("duration_first_submission_enabled")
                        ),
                        "submission_order_indices": [
                            int(idx) for idx in list(collect_runtime_info.get("submission_order_indices") or [])
                        ],
                        "submitted_chunk_paths": [
                            str(path or "").strip()
                            for path in list(collect_runtime_info.get("submitted_chunk_paths") or [])
                        ],
                        "submitted_chunk_durations_sec": [
                            round(float(value or 0.0), 3)
                            for value in list(collect_runtime_info.get("submitted_chunk_durations_sec") or [])
                        ],
                        "submitted_chunk_offsets_sec": [
                            round(float(value or 0.0), 3)
                            for value in list(collect_runtime_info.get("submitted_chunk_offsets_sec") or [])
                        ],
                        "completed_chunk_paths": [
                            str(path or "").strip()
                            for path in list(collect_runtime_info.get("completed_chunk_paths") or [])
                        ],
                        "completed_chunk_elapsed_ms": [
                            round(float(value or 0.0), 3)
                            for value in list(collect_runtime_info.get("completed_chunk_elapsed_ms") or [])
                        ],
                        "emitted_chunk_paths": [
                            str(path or "").strip()
                            for path in list(collect_runtime_info.get("emitted_chunk_paths") or [])
                        ],
                        "emitted_chunk_elapsed_ms": [
                            round(float(value or 0.0), 3)
                            for value in list(collect_runtime_info.get("emitted_chunk_elapsed_ms") or [])
                        ],
                    }
                    if isinstance(item.get("collect_runtime_info"), dict)
                    else None
                ),
                "collect_clip_rows": [
                    {
                        "path": str((clip or {}).get("path") or "").strip(),
                        "start": round(float((clip or {}).get("start", 0.0) or 0.0), 3),
                        "end": round(float((clip or {}).get("end", 0.0) or 0.0), 3),
                        "duration_sec": round(float((clip or {}).get("duration_sec", 0.0) or 0.0), 3),
                        "source_chunk_path": str((clip or {}).get("source_chunk_path") or "").strip(),
                        "source_chunk_start": round(float((clip or {}).get("source_chunk_start", 0.0) or 0.0), 3)
                        if (clip or {}).get("source_chunk_start") is not None
                        else None,
                        "source_chunk_duration_sec": round(
                            float((clip or {}).get("source_chunk_duration_sec", 0.0) or 0.0),
                            3,
                        )
                        if (clip or {}).get("source_chunk_duration_sec") is not None
                        else None,
                        "local_start": round(float((clip or {}).get("local_start", 0.0) or 0.0), 3)
                        if (clip or {}).get("local_start") is not None
                        else None,
                        "local_end": round(float((clip or {}).get("local_end", 0.0) or 0.0), 3)
                        if (clip or {}).get("local_end") is not None
                        else None,
                        "padding_sec": round(float((clip or {}).get("padding_sec", 0.0) or 0.0), 3)
                        if (clip or {}).get("padding_sec") is not None
                        else None,
                        "primary_text": str((clip or {}).get("primary_text") or "").strip(),
                        "merged_clip_count": int((clip or {}).get("merged_clip_count", 0) or 0)
                        if (clip or {}).get("merged_clip_count") is not None
                        else None,
                        "collected_segment_count": int((clip or {}).get("collected_segment_count", 0) or 0)
                        if (clip or {}).get("collected_segment_count") is not None
                        else None,
                        "collected_text_segment_count": int((clip or {}).get("collected_text_segment_count", 0) or 0)
                        if (clip or {}).get("collected_text_segment_count") is not None
                        else None,
                        "collected_total_duration_sec": round(
                            float((clip or {}).get("collected_total_duration_sec", 0.0) or 0.0),
                            3,
                        )
                        if (clip or {}).get("collected_total_duration_sec") is not None
                        else None,
                        "collected_sample_texts": [
                            str(text or "").strip()
                            for text in list((clip or {}).get("collected_sample_texts") or [])
                        ],
                    }
                    for clip in list(item.get("collect_clip_rows") or [])
                    if isinstance(clip, dict)
                ],
                "applied_count": int(item.get("applied_count", 0) or 0)
                if item.get("applied_count") is not None
                else None,
                "result_segment_count": int(item.get("result_segment_count", 0) or 0)
                if item.get("result_segment_count") is not None
                else None,
                "annotate_error": str(item.get("annotate_error") or "").strip(),
            }
        )
    return compact


def _artifact_final_cleanup_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_final_cleanup_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        rows: list[dict[str, Any]] = []
        for raw_row in list(item.get("rows") or []):
            if not isinstance(raw_row, dict):
                continue
            rows.append(
                {
                    "start": round(float(raw_row.get("start", 0.0) or 0.0), 3),
                    "end": round(float(raw_row.get("end", 0.0) or 0.0), 3),
                    "duration_sec": round(float(raw_row.get("duration_sec", 0.0) or 0.0), 3),
                    "text": str(raw_row.get("text") or "").strip(),
                    "split_index": raw_row.get("split_index"),
                    "split_count": raw_row.get("split_count"),
                    "source_start": raw_row.get("source_start"),
                    "source_end": raw_row.get("source_end"),
                    "selected_source": str(raw_row.get("selected_source") or "").strip(),
                    "cleanup_action": str(raw_row.get("cleanup_action") or "").strip(),
                }
            )
        compact.append(
            {
                "stage": str(item.get("stage") or "").strip(),
                "step": str(item.get("step") or "").strip(),
                "segment_count": int(item.get("segment_count") or 0),
                "changed": int(item.get("changed") or 0),
                "sample_texts": [str(text).strip() for text in list(item.get("sample_texts") or [])[:5]],
                "rows": rows,
            }
        )
    return compact


def _artifact_no_llm_raw_restore_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_no_llm_raw_restore_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "step": str(item.get("step") or "").strip(),
                "decision": str(item.get("decision") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "start": round(float(item.get("start", 0.0) or 0.0), 3),
                "end": round(float(item.get("end", 0.0) or 0.0), 3),
                "duration_sec": round(float(item.get("duration_sec", 0.0) or 0.0), 3),
                "text": str(item.get("text") or "").strip(),
                "split_index": item.get("split_index"),
                "split_count": item.get("split_count"),
                "has_common_split_policy": bool(item.get("has_common_split_policy")),
                "raw_lock_reason": str(item.get("raw_lock_reason") or "").strip(),
                "restored_after_postprocess": bool(item.get("restored_after_postprocess")),
                "raw_text": str(item.get("raw_text") or "").strip(),
                "word_text": str(item.get("word_text") or "").strip(),
                "selected_source": str(item.get("selected_source") or "").strip(),
                "anchor_text": str(item.get("anchor_text") or "").strip(),
                "similarity": item.get("similarity"),
            }
        )
    return compact


def _artifact_trim_recent_overlap_trace(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    trace_path = _artifact_trim_recent_overlap_trace_path(json_path, winner_name)
    if not trace_path.exists():
        return None
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, list):
        return None
    compact: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "stage": str(item.get("stage") or "").strip(),
                "decision": str(item.get("decision") or "").strip(),
                "reason": str(item.get("reason") or "").strip(),
                "start": round(float(item.get("start", 0.0) or 0.0), 3),
                "end": round(float(item.get("end", 0.0) or 0.0), 3),
                "duration_sec": round(float(item.get("duration_sec", 0.0) or 0.0), 3),
                "text": str(item.get("text") or "").strip(),
                "trimmed_text": str(item.get("trimmed_text") or "").strip(),
                "previous_text": str(item.get("previous_text") or "").strip(),
                "prefix_overlap": int(item.get("prefix_overlap") or 0),
                "suffix_overlap": int(item.get("suffix_overlap") or 0),
                "split_index": item.get("split_index"),
                "split_count": item.get("split_count"),
                "has_common_split_policy": bool(item.get("has_common_split_policy")),
                "token_count": int(item.get("token_count") or 0),
                "previous_token_count": int(item.get("previous_token_count") or 0),
            }
        )
    return compact


def _artifact_raw_restore_restore_groups(trace_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not trace_rows:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for item in trace_rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("step") or "").strip() != "raw_restore":
            continue
        if str(item.get("decision") or "").strip() != "restore":
            continue
        raw_text = str(item.get("raw_text") or "").strip()
        if not raw_text:
            continue
        group = grouped.setdefault(
            raw_text,
            {
                "raw_text": raw_text,
                "split_count": item.get("split_count"),
                "restored_split_indexes": [],
                "restored_word_texts": [],
                "restored_count": 0,
                "has_digit_word_text": False,
                "singleton_word_text_count": 0,
                "phrase_word_text_count": 0,
            },
        )
        split_index = item.get("split_index")
        if split_index is not None and split_index not in group["restored_split_indexes"]:
            group["restored_split_indexes"].append(split_index)
        word_text = str(item.get("word_text") or "").strip()
        if word_text and word_text not in group["restored_word_texts"]:
            group["restored_word_texts"].append(word_text)
        tokens = [token for token in word_text.split() if token]
        if len(tokens) <= 1:
            group["singleton_word_text_count"] += 1
        else:
            group["phrase_word_text_count"] += 1
        if any(char.isdigit() for char in word_text):
            group["has_digit_word_text"] = True
        group["restored_count"] += 1
    compact: list[dict[str, Any]] = []
    for group in grouped.values():
        indexes = sorted(int(item) for item in list(group.get("restored_split_indexes") or []))
        compact.append(
            {
                "raw_text": group["raw_text"],
                "split_count": group.get("split_count"),
                "restored_split_indexes": indexes,
                "restored_count": int(group.get("restored_count") or 0),
                "has_digit_word_text": bool(group.get("has_digit_word_text")),
                "singleton_word_text_count": int(group.get("singleton_word_text_count") or 0),
                "phrase_word_text_count": int(group.get("phrase_word_text_count") or 0),
                "restored_word_texts": list(group.get("restored_word_texts") or [])[:8],
            }
        )
    compact.sort(key=lambda item: (int(item.get("restored_count") or 0) * -1, str(item.get("raw_text") or "")))
    return compact


def _raw_restore_group_classification_counts(groups: list[dict[str, Any]] | None) -> dict[str, int]:
    counts = {
        "all_singleton": 0,
        "mixed": 0,
        "all_phrase": 0,
        "has_digit_word_text": 0,
    }
    for item in list(groups or []):
        if not isinstance(item, dict):
            continue
        singleton_count = int(item.get("singleton_word_text_count") or 0)
        phrase_count = int(item.get("phrase_word_text_count") or 0)
        if singleton_count > 0 and phrase_count == 0:
            counts["all_singleton"] += 1
        elif singleton_count > 0 and phrase_count > 0:
            counts["mixed"] += 1
        elif phrase_count > 0:
            counts["all_phrase"] += 1
        if bool(item.get("has_digit_word_text")):
            counts["has_digit_word_text"] += 1
    return counts


def _artifact_reference_rows(json_path: Path) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    reference_srt = str(payload.get("reference_srt") or "").strip()
    if not reference_srt:
        return None
    reference_path = Path(reference_srt).expanduser()
    if not reference_path.is_absolute():
        reference_path = (ROOT / reference_path).resolve()
    if not reference_path.exists():
        return None
    try:
        from tools.subtitle_benchmark_scoring import clip_reference, parse_srt

        start_sec = float(payload.get("start_sec", 0.0) or 0.0)
        end_sec = float(payload.get("end_sec", start_sec) or start_sec)
        reference_rows = clip_reference(parse_srt(reference_path), start_sec, end_sec)
    except Exception:
        return None
    return _compact_artifact_rows(reference_rows)


def _settings_with_variant_overrides(row: dict[str, Any]) -> dict[str, Any]:
    settings = dict(row.get("settings") or {})
    if (
        "stt_whisper_primary_metadata_only_low_score_recheck_requires_secondary_signal" in settings
        and "stt_whisper_primary_metadata_only_low_score_recheck_skip_max_duration_sec" in settings
        and "stt_whisper_primary_metadata_only_low_score_recheck_skip_min_vad_score" in settings
    ):
        return settings
    try:
        from tools.benchmark_subtitle_pipeline_variants import _base_benchmark_settings, benchmark_variants

        by_name = {variant.name: variant for variant in benchmark_variants(_base_benchmark_settings("current"))}
        variant = by_name.get(str(row.get("name") or "").strip())
        if variant is not None:
            settings.update(dict(getattr(variant, "overrides", {}) or {}))
    except Exception:
        pass
    return settings


def _low_score_diagnostics(json_path: Path, row: dict[str, Any]) -> dict[str, Any] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if not raw_path.exists():
        return None
    try:
        raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw_rows, list):
        return None
    from core.audio import stt_recheck_service
    settings = _settings_with_variant_overrides(row)
    threshold = float(settings.get("stt_low_score_recheck_threshold") or 78.0)
    max_duration = float(settings.get("stt_whisper_primary_metadata_only_low_score_recheck_skip_max_duration_sec") or 2.2)
    min_vad = float(settings.get("stt_whisper_primary_metadata_only_low_score_recheck_skip_min_vad_score") or 95.0)
    metadata_flags = {"no_speech_prob_missing", "avg_logprob_missing", "word_confidence_missing"}
    total = 0
    metadata_only = 0
    digits = 0
    low_vad = 0
    short_stable_metadata_only = 0
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        try:
            score = float(item.get("stt_score"))
        except Exception:
            continue
        if score > threshold:
            continue
        total += 1
        text = str(item.get("text") or "").strip()
        flags = {str(flag) for flag in (item.get("stt_score_flags") or ())}
        duration = max(0.0, float(item.get("end", 0.0) or 0.0) - float(item.get("start", 0.0) or 0.0))
        vad_score = float((item.get("quality") or {}).get("vad_alignment_score") or 100.0)
        is_metadata_only = bool(flags) and flags.issubset(metadata_flags)
        if is_metadata_only:
            metadata_only += 1
        if any(char.isdigit() for char in text):
            digits += 1
        if vad_score < min_vad:
            low_vad += 1
        if is_metadata_only and not any(char.isdigit() for char in text) and duration <= max_duration and vad_score >= min_vad:
            short_stable_metadata_only += 1
    surviving_ranges = stt_recheck_service.primary_low_score_recheck_ranges(
        raw_rows,
        settings,
        score_fn=lambda seg: seg.get("stt_score", 0.0),
        apply_budget=False,
    )
    surviving_primary_low_score_rows = len(surviving_ranges)
    surviving_digit_rows = 0
    surviving_low_vad_rows = 0
    surviving_other_rows = 0
    for item in surviving_ranges:
        primary = dict(item.primary or {})
        text = str(primary.get("text") or "").strip()
        vad_score = float((primary.get("quality") or {}).get("vad_alignment_score") or 100.0)
        is_digit = any(char.isdigit() for char in text)
        is_low_vad = vad_score < min_vad
        if is_digit:
            surviving_digit_rows += 1
        if is_low_vad:
            surviving_low_vad_rows += 1
        if not is_digit and not is_low_vad:
            surviving_other_rows += 1
    return {
        "threshold": threshold,
        "total_low_score_rows": total,
        "metadata_only_rows": metadata_only,
        "digit_rows": digits,
        "low_vad_rows": low_vad,
        "short_stable_metadata_only_rows": short_stable_metadata_only,
        "surviving_primary_low_score_rows": surviving_primary_low_score_rows,
        "skipped_metadata_only_primary_low_score_rows": max(0, total - surviving_primary_low_score_rows),
        "surviving_digit_rows": surviving_digit_rows,
        "surviving_low_vad_rows": surviving_low_vad_rows,
        "surviving_other_rows": surviving_other_rows,
    }


def _artifact_primary_recheck_plan_counts(json_path: Path, row: dict[str, Any]) -> dict[str, int] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if not raw_path.exists():
        return None
    try:
        raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw_rows, list):
        return None
    from core.audio import stt_recheck_service

    settings = _settings_with_variant_overrides(row)
    plan = stt_recheck_service.selective_secondary_recheck_plan(
        primary_segments=raw_rows,
        vad_segments=[],
        settings=settings,
        score_fn=lambda seg: seg.get("stt_score", 0.0),
        chunk_path_for_time=lambda _t: "",
    )
    return {
        "low_score": len(plan.get("low_score") or ()),
        "missing_voice": len(plan.get("missing_voice") or ()),
        "route_hint": len(plan.get("route_hint") or ()),
        "merged": len(plan.get("merged") or ()),
        "ranges": len(plan.get("ranges") or ()),
    }


def _serialize_recheck_range(item: Any) -> dict[str, Any]:
    primary = dict(getattr(item, "primary", {}) or {})
    secondary = dict(getattr(item, "secondary", {}) or {})
    primary_text = str(getattr(item, "primary_text", "") or "").strip()
    secondary_text = str(getattr(item, "secondary_text", "") or "").strip()
    primary_flags = [str(flag) for flag in (primary.get("stt_score_flags") or ())]
    primary_vad_score = float((primary.get("quality") or {}).get("vad_alignment_score") or 100.0)
    return {
        "start": round(float(getattr(item, "start", 0.0) or 0.0), 3),
        "end": round(float(getattr(item, "end", 0.0) or 0.0), 3),
        "duration_sec": round(
            max(0.0, float(getattr(item, "end", 0.0) or 0.0) - float(getattr(item, "start", 0.0) or 0.0)),
            3,
        ),
        "primary_text": primary_text,
        "secondary_text": secondary_text,
        "primary_score": round(float(getattr(item, "primary_score", 0.0) or 0.0), 2),
        "secondary_score": round(float(getattr(item, "secondary_score", 0.0) or 0.0), 2),
        "primary_flags": primary_flags,
        "primary_vad_alignment_score": round(primary_vad_score, 3),
        "primary_has_digits": any(char.isdigit() for char in primary_text),
    }


def _artifact_primary_recheck_plan_rows(json_path: Path, row: dict[str, Any]) -> dict[str, list[dict[str, Any]]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if not raw_path.exists():
        return None
    try:
        raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw_rows, list):
        return None
    from core.audio import stt_recheck_service

    settings = _settings_with_variant_overrides(row)
    plan = stt_recheck_service.selective_secondary_recheck_plan(
        primary_segments=raw_rows,
        vad_segments=[],
        settings=settings,
        score_fn=lambda seg: seg.get("stt_score", 0.0),
        chunk_path_for_time=lambda _t: "",
    )
    payload: dict[str, list[dict[str, Any]]] = {}
    for key in ("low_score", "missing_voice", "route_hint", "merged", "ranges"):
        ranges = list(plan.get(key) or ())
        payload[key] = [_serialize_recheck_range(item) for item in ranges]
    return payload


def _artifact_word_precision_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if not raw_path.exists():
        return None
    try:
        raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw_rows, list):
        return None
    from core.audio import stt_recheck_service
    from core.audio.transcribe_policy_helpers import (
        segment_has_score,
        segment_needs_word_precision,
        segment_score_100,
    )

    settings = _settings_with_variant_overrides(row)
    ranges = stt_recheck_service.word_precision_ranges(
        raw_rows,
        settings,
        needs_precision_fn=segment_needs_word_precision,
        score_fn=segment_score_100,
        has_score_fn=segment_has_score,
    )
    return [_serialize_recheck_range(item) for item in ranges]


def _artifact_applied_word_precision_rows(json_path: Path, row: dict[str, Any]) -> list[dict[str, Any]] | None:
    winner_name = str(row.get("name") or "").strip()
    if not winner_name:
        return None
    output_path = _artifact_output_segments_path(json_path, winner_name)
    if not output_path.exists():
        return None
    try:
        output_rows = json.loads(output_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(output_rows, list):
        return None
    raw_applied_rows: list[dict[str, Any]] = []
    raw_path = _artifact_raw_segments_path(json_path, winner_name)
    if raw_path.exists():
        try:
            raw_rows = json.loads(raw_path.read_text(encoding="utf-8"))
        except Exception:
            raw_rows = None
        if isinstance(raw_rows, list):
            raw_applied_rows = [
                item
                for item in _compact_artifact_rows(raw_rows)
                if bool(item.get("stt_word_precision_applied")) or bool(item.get("stt_word_precision_split_applied"))
            ]
    selected: list[dict[str, Any]] = []
    for item in output_rows:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("stt_word_precision_applied")) and not bool(item.get("stt_word_precision_split_applied")):
            continue
        selective_word_timestamps = dict(dict(item.get("asr_metadata") or {}).get("selective_word_timestamps") or {})
        precision_range_start = selective_word_timestamps.get("range_start")
        precision_range_end = selective_word_timestamps.get("range_end")
        derived_match_text = ""
        derived_match_overlap_ratio = 0.0
        if precision_range_start is None or precision_range_end is None:
            output_compact = {
                "start": round(float(item.get("start", 0.0) or 0.0), 3),
                "end": round(float(item.get("end", 0.0) or 0.0), 3),
                "text": str(item.get("text") or "").strip(),
            }
            best_match: dict[str, Any] | None = None
            for raw_item in raw_applied_rows:
                overlap_sec = _row_overlap_sec(output_compact, raw_item)
                output_duration = max(
                    0.001,
                    float(output_compact.get("end", 0.0) or 0.0) - float(output_compact.get("start", 0.0) or 0.0),
                )
                raw_duration = max(
                    0.001,
                    float(raw_item.get("end", 0.0) or 0.0) - float(raw_item.get("start", 0.0) or 0.0),
                )
                overlap_ratio = overlap_sec / max(0.001, min(output_duration, raw_duration))
                if best_match is None or overlap_ratio > derived_match_overlap_ratio:
                    best_match = raw_item
                    derived_match_overlap_ratio = overlap_ratio
            if best_match is not None and derived_match_overlap_ratio >= 0.5:
                derived_match_text = str(best_match.get("text") or "").strip()
                if precision_range_start is None:
                    precision_range_start = best_match.get("precision_range_start")
                if precision_range_end is None:
                    precision_range_end = best_match.get("precision_range_end")
                if not str(selective_word_timestamps.get("source") or "").strip():
                    selective_word_timestamps["source"] = best_match.get("precision_source")
        selected.append(
            {
                "start": round(float(item.get("start", 0.0) or 0.0), 3),
                "end": round(float(item.get("end", 0.0) or 0.0), 3),
                "duration_sec": round(
                    max(0.0, float(item.get("end", 0.0) or 0.0) - float(item.get("start", 0.0) or 0.0)),
                    3,
                ),
                "text": str(item.get("text") or "").strip(),
                "stt_word_precision_applied": bool(item.get("stt_word_precision_applied")),
                "stt_word_precision_split_applied": bool(item.get("stt_word_precision_split_applied")),
                "precision_range_start": round(float(precision_range_start or 0.0), 3)
                if precision_range_start is not None
                else None,
                "precision_range_end": round(float(precision_range_end or 0.0), 3)
                if precision_range_end is not None
                else None,
                "precision_source": str(selective_word_timestamps.get("source") or "").strip(),
                "precision_range_derived": bool(derived_match_text),
                "precision_match_text": derived_match_text,
                "precision_match_overlap_ratio": round(derived_match_overlap_ratio, 3) if derived_match_text else 0.0,
            }
        )
    return selected


def _row_overlap_sec(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_start = float(left.get("start", 0.0) or 0.0)
    left_end = float(left.get("end", left_start) or left_start)
    right_start = float(right.get("start", 0.0) or 0.0)
    right_end = float(right.get("end", right_start) or right_start)
    return max(0.0, min(left_end, right_end) - max(left_start, right_start))


def _artifact_gap_rows(
    primary_rows: list[dict[str, Any]] | None,
    secondary_rows: list[dict[str, Any]] | None,
    *,
    min_overlap_ratio: float = 0.35,
) -> list[dict[str, Any]] | None:
    if primary_rows is None or secondary_rows is None:
        return None
    gaps: list[dict[str, Any]] = []
    for item in primary_rows:
        start = float(item.get("start", 0.0) or 0.0)
        end = float(item.get("end", start) or start)
        duration = max(0.001, end - start)
        best_overlap = 0.0
        for other in secondary_rows:
            best_overlap = max(best_overlap, _row_overlap_sec(item, other))
        if (best_overlap / duration) >= min_overlap_ratio:
            continue
        gaps.append(
            {
                **item,
                "best_overlap_sec": round(best_overlap, 3),
                "best_overlap_ratio": round(best_overlap / duration, 3),
            }
        )
    return gaps


def _artifact_applied_word_precision_clip_rows(
    clip_rows: list[dict[str, Any]] | None,
    applied_rows: list[dict[str, Any]] | None,
    raw_rows: list[dict[str, Any]] | None = None,
    output_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    clips = [dict(item) for item in list(clip_rows or []) if isinstance(item, dict)]
    applied = [dict(item) for item in list(applied_rows or []) if isinstance(item, dict)]
    raw = [dict(item) for item in list(raw_rows or []) if isinstance(item, dict)]
    outputs = [dict(item) for item in list(output_rows or []) if isinstance(item, dict)]
    enriched: list[dict[str, Any]] = []
    for clip in clips:
        clip_start = float(clip.get("start", 0.0) or 0.0)
        clip_end = float(clip.get("end", clip_start) or clip_start)
        clip_duration = max(0.001, clip_end - clip_start)
        best_overlap_ratio = 0.0
        matched_text = ""
        matched_output: dict[str, Any] | None = None
        matched_raw: dict[str, Any] | None = None
        best_output_overlap_ratio = 0.0
        best_raw_overlap_ratio = 0.0
        for row in applied:
            row_start = float(row.get("start", 0.0) or 0.0)
            row_end = float(row.get("end", row_start) or row_start)
            row_duration = max(0.001, row_end - row_start)
            overlap = max(0.0, min(clip_end, row_end) - max(clip_start, row_start))
            overlap_ratio = overlap / max(0.001, min(clip_duration, row_duration))
            if overlap_ratio > best_overlap_ratio:
                best_overlap_ratio = overlap_ratio
                matched_text = str(row.get("text") or "").strip()
        for row in outputs:
            row_start = float(row.get("start", 0.0) or 0.0)
            row_end = float(row.get("end", row_start) or row_start)
            row_duration = max(0.001, row_end - row_start)
            overlap = max(0.0, min(clip_end, row_end) - max(clip_start, row_start))
            overlap_ratio = overlap / max(0.001, min(clip_duration, row_duration))
            if overlap_ratio > best_output_overlap_ratio:
                best_output_overlap_ratio = overlap_ratio
                matched_output = row
        for row in raw:
            row_start = float(row.get("start", 0.0) or 0.0)
            row_end = float(row.get("end", row_start) or row_start)
            row_duration = max(0.001, row_end - row_start)
            overlap = max(0.0, min(clip_end, row_end) - max(clip_start, row_start))
            overlap_ratio = overlap / max(0.001, min(clip_duration, row_duration))
            if overlap_ratio > best_raw_overlap_ratio:
                best_raw_overlap_ratio = overlap_ratio
                matched_raw = row
        item = dict(clip)
        item["best_applied_overlap_ratio"] = round(best_overlap_ratio, 3)
        item["matched_applied_text"] = matched_text
        item["likely_applied"] = best_overlap_ratio >= 0.5
        if not item["likely_applied"] and isinstance(matched_output, dict):
            item["matched_output_text"] = str(matched_output.get("text") or "").strip()
        if not item["likely_applied"] and isinstance(matched_raw, dict):
            item["precision_reject_reason"] = str(matched_raw.get("precision_reject_reason") or "").strip()
            item["precision_reject_detail"] = dict(matched_raw.get("precision_reject_detail") or {})
        enriched.append(item)
    return enriched


def _apply_collect_submission_order(
    clip_rows: list[dict[str, Any]] | None,
    runtime_trace: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in list(clip_rows or []) if isinstance(item, dict)]
    if not rows:
        return []
    collect_info: dict[str, Any] = {}
    for item in list(runtime_trace or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("phase") or "").strip() != "collect_segments":
            continue
        collect_info = dict(item.get("collect_runtime_info") or {})
        if collect_info:
            break
    submitted_paths = [str(path or "").strip() for path in list(collect_info.get("submitted_chunk_paths") or [])]
    submitted_durations = [float(item or 0.0) for item in list(collect_info.get("submitted_chunk_durations_sec") or [])]
    submitted_offsets = [float(item or 0.0) for item in list(collect_info.get("submitted_chunk_offsets_sec") or [])]
    completed_paths = [str(path or "").strip() for path in list(collect_info.get("completed_chunk_paths") or [])]
    completed_elapsed = [float(item or 0.0) for item in list(collect_info.get("completed_chunk_elapsed_ms") or [])]
    emitted_paths = [str(path or "").strip() for path in list(collect_info.get("emitted_chunk_paths") or [])]
    emitted_elapsed = [float(item or 0.0) for item in list(collect_info.get("emitted_chunk_elapsed_ms") or [])]
    path_to_index = {path: idx for idx, path in enumerate(submitted_paths) if path}
    path_to_completion_index = {path: idx for idx, path in enumerate(completed_paths) if path}
    path_to_emission_index = {path: idx for idx, path in enumerate(emitted_paths) if path}
    for row in rows:
        path = str(row.get("path") or "").strip()
        submission_index = path_to_index.get(path)
        completion_index = path_to_completion_index.get(path)
        emission_index = path_to_emission_index.get(path)
        row["submission_index"] = int(submission_index) if submission_index is not None else None
        if submission_index is not None and 0 <= submission_index < len(submitted_durations):
            row["submitted_chunk_duration_sec"] = round(float(submitted_durations[submission_index]), 3)
        else:
            row["submitted_chunk_duration_sec"] = None
        if submission_index is not None and 0 <= submission_index < len(submitted_offsets):
            row["submitted_chunk_offset_sec"] = round(float(submitted_offsets[submission_index]), 3)
        else:
            row["submitted_chunk_offset_sec"] = None
        row["completion_order_index"] = int(completion_index) if completion_index is not None else None
        if completion_index is not None and 0 <= completion_index < len(completed_elapsed):
            row["completed_chunk_elapsed_ms"] = round(float(completed_elapsed[completion_index]), 3)
        else:
            row["completed_chunk_elapsed_ms"] = None
        row["emission_order_index"] = int(emission_index) if emission_index is not None else None
        if emission_index is not None and 0 <= emission_index < len(emitted_elapsed):
            row["emitted_chunk_elapsed_ms"] = round(float(emitted_elapsed[emission_index]), 3)
        else:
            row["emitted_chunk_elapsed_ms"] = None
        if row["completion_order_index"] is None and row["emission_order_index"] is not None:
            row["completion_order_index"] = row["emission_order_index"]
        if row["completed_chunk_elapsed_ms"] is None and row["emitted_chunk_elapsed_ms"] is not None:
            row["completed_chunk_elapsed_ms"] = row["emitted_chunk_elapsed_ms"]
        if "duration_first_submission_enabled" in collect_info:
            row["duration_first_submission_enabled"] = bool(collect_info.get("duration_first_submission_enabled"))
    return rows


def _is_pure_numeric_text(text: str) -> bool:
    compact = "".join(str(text or "").split())
    if not compact or not any(char.isdigit() for char in compact):
        return False
    return all(char.isdigit() or char in ".,:/+-" for char in compact)


def _artifact_word_precision_overlap_group_clip_roles(
    clip_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for clip in clip_rows:
        text = str(clip.get("primary_text") or "").strip()
        secondary_text = str(clip.get("secondary_text") or "").strip()
        duration_sec = round(float(clip.get("duration_sec", 0.0) or 0.0), 3)
        collected_total_duration_sec = (
            round(float(clip.get("collected_total_duration_sec", 0.0) or 0.0), 3)
            if clip.get("collected_total_duration_sec") is not None
            else None
        )
        roles.append(
            {
                "primary_text": text,
                "secondary_text": secondary_text,
                "start": round(float(clip.get("start", 0.0) or 0.0), 3),
                "end": round(float(clip.get("end", clip.get("start", 0.0)) or clip.get("start", 0.0)), 3),
                "duration_sec": duration_sec,
                "likely_applied": bool(clip.get("likely_applied")),
                "role": "applied" if bool(clip.get("likely_applied")) else "non_applied",
                "pure_numeric": _is_pure_numeric_text(text),
                "has_digits": any(char.isdigit() for char in text),
                "has_secondary_text": bool(secondary_text),
                "best_applied_overlap_ratio": round(float(clip.get("best_applied_overlap_ratio", 0.0) or 0.0), 3),
                "matched_applied_text": str(clip.get("matched_applied_text") or "").strip(),
                "matched_output_text": str(clip.get("matched_output_text") or "").strip(),
                "precision_reject_reason": str(clip.get("precision_reject_reason") or "").strip(),
                "precision_reject_detail": dict(clip.get("precision_reject_detail") or {}),
                "submission_index": int(clip.get("submission_index"))
                if clip.get("submission_index") is not None
                else None,
                "submitted_chunk_duration_sec": round(float(clip.get("submitted_chunk_duration_sec", 0.0) or 0.0), 3)
                if clip.get("submitted_chunk_duration_sec") is not None
                else None,
                "submitted_chunk_offset_sec": round(float(clip.get("submitted_chunk_offset_sec", 0.0) or 0.0), 3)
                if clip.get("submitted_chunk_offset_sec") is not None
                else None,
                "completion_order_index": int(clip.get("completion_order_index"))
                if clip.get("completion_order_index") is not None
                else None,
                "completed_chunk_elapsed_ms": round(float(clip.get("completed_chunk_elapsed_ms", 0.0) or 0.0), 3)
                if clip.get("completed_chunk_elapsed_ms") is not None
                else None,
                "emission_order_index": int(clip.get("emission_order_index"))
                if clip.get("emission_order_index") is not None
                else None,
                "emitted_chunk_elapsed_ms": round(float(clip.get("emitted_chunk_elapsed_ms", 0.0) or 0.0), 3)
                if clip.get("emitted_chunk_elapsed_ms") is not None
                else None,
                "duration_first_submission_enabled": bool(clip.get("duration_first_submission_enabled"))
                if clip.get("duration_first_submission_enabled") is not None
                else None,
                "collected_segment_count": int(clip.get("collected_segment_count", 0) or 0)
                if clip.get("collected_segment_count") is not None
                else None,
                "collected_total_duration_sec": collected_total_duration_sec,
                "collected_duration_ratio": round(
                    float(collected_total_duration_sec or 0.0) / max(0.001, duration_sec),
                    3,
                )
                if collected_total_duration_sec is not None
                else None,
            }
        )
    roles.sort(
        key=lambda item: (
            item.get("likely_applied"),
            -float(item.get("completed_chunk_elapsed_ms", 0.0) or 0.0),
            -float(item.get("collected_total_duration_sec", 0.0) or 0.0),
            -float(item.get("duration_sec", 0.0) or 0.0),
            float(item.get("start", 0.0) or 0.0),
            str(item.get("primary_text") or ""),
        )
    )
    return roles


def _artifact_word_precision_chunk_groups(
    clip_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for clip in list(clip_rows or []):
        if not isinstance(clip, dict):
            continue
        source_chunk_path = str(clip.get("source_chunk_path") or "").strip()
        key = source_chunk_path or "__unknown__"
        group = groups.setdefault(
            key,
            {
                "source_chunk_path": source_chunk_path,
                "source_chunk_start": clip.get("source_chunk_start"),
                "source_chunk_duration_sec": clip.get("source_chunk_duration_sec"),
                "clip_count": 0,
                "applied_clip_count": 0,
                "non_applied_clip_count": 0,
                "total_clip_duration_sec": 0.0,
                "non_applied_clip_duration_sec": 0.0,
                "collected_segment_count": 0,
                "non_applied_collected_segment_count": 0,
                "sample_texts": [],
            },
        )
        group["clip_count"] += 1
        duration_sec = float(clip.get("duration_sec", 0.0) or 0.0)
        group["total_clip_duration_sec"] = round(float(group["total_clip_duration_sec"]) + duration_sec, 3)
        collected_count = int(clip.get("collected_segment_count", 0) or 0)
        group["collected_segment_count"] += collected_count
        likely_applied = bool(clip.get("likely_applied"))
        if likely_applied:
            group["applied_clip_count"] += 1
        else:
            group["non_applied_clip_count"] += 1
            group["non_applied_clip_duration_sec"] = round(
                float(group["non_applied_clip_duration_sec"]) + duration_sec,
                3,
            )
            group["non_applied_collected_segment_count"] += collected_count
        text = str(clip.get("primary_text") or "").strip()
        if text and text not in group["sample_texts"]:
            group["sample_texts"].append(text)
    rows = list(groups.values())
    for row in rows:
        row["sample_texts"] = list(row.get("sample_texts") or [])[:3]
    rows.sort(
        key=lambda item: (
            -float(item.get("non_applied_clip_duration_sec", 0.0) or 0.0),
            -int(item.get("non_applied_clip_count", 0) or 0),
            str(item.get("source_chunk_path") or ""),
        )
    )
    return rows


def _artifact_word_precision_overlap_groups(
    clip_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in list(clip_rows or []) if isinstance(item, dict)]
    if not rows:
        return []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        source_chunk_path = str(row.get("source_chunk_path") or "").strip()
        grouped.setdefault(source_chunk_path or "__unknown__", []).append(row)
    clusters: list[dict[str, Any]] = []
    for source_chunk_path, chunk_rows in grouped.items():
        chunk_rows.sort(
            key=lambda item: (
                float(item.get("start", 0.0) or 0.0),
                float(item.get("end", item.get("start", 0.0)) or item.get("start", 0.0)),
            )
        )
        current_rows: list[dict[str, Any]] = []
        current_end = 0.0
        for row in chunk_rows:
            row_start = float(row.get("start", 0.0) or 0.0)
            row_end = max(row_start, float(row.get("end", row_start) or row_start))
            if not current_rows or row_start <= current_end:
                current_rows.append(row)
                current_end = max(current_end, row_end)
                continue
            clusters.append(_build_word_precision_overlap_group(source_chunk_path, current_rows))
            current_rows = [row]
            current_end = row_end
        if current_rows:
            clusters.append(_build_word_precision_overlap_group(source_chunk_path, current_rows))
    clusters.sort(
        key=lambda item: (
            -float(item.get("max_non_applied_completed_chunk_elapsed_ms", 0.0) or 0.0),
            -float(item.get("non_applied_collected_total_duration_sec", 0.0) or 0.0),
            -float(item.get("non_applied_clip_duration_sec", 0.0) or 0.0),
            -float(item.get("collected_total_duration_sec", 0.0) or 0.0),
            -float(item.get("cluster_span_sec", 0.0) or 0.0),
            -int(item.get("clip_count", 0) or 0),
            str(item.get("source_chunk_path") or ""),
            float(item.get("cluster_start", 0.0) or 0.0),
        )
    )
    return clusters


def _artifact_word_precision_low_yield_clip_rows(
    overlap_groups: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in list(overlap_groups or []):
        if not isinstance(group, dict):
            continue
        for clip in list(group.get("clip_roles") or []):
            if not isinstance(clip, dict):
                continue
            if bool(clip.get("likely_applied")):
                continue
            if bool(clip.get("pure_numeric")) or bool(clip.get("has_digits")):
                continue
            collected_total_duration_sec = float(clip.get("collected_total_duration_sec", 0.0) or 0.0)
            if collected_total_duration_sec <= 0.0:
                continue
            best_applied_overlap_ratio = float(clip.get("best_applied_overlap_ratio", 0.0) or 0.0)
            if best_applied_overlap_ratio >= 0.4:
                continue
            entry = dict(clip)
            entry["cluster_start"] = group.get("cluster_start")
            entry["cluster_end"] = group.get("cluster_end")
            entry["cluster_span_sec"] = group.get("cluster_span_sec")
            entry["cluster_sample_texts"] = list(group.get("sample_texts") or [])
            entry["collect_waste_score"] = round(
                collected_total_duration_sec * max(0.0, 1.0 - best_applied_overlap_ratio),
                3,
            )
            rows.append(entry)
    rows.sort(
        key=lambda item: (
            -float(item.get("collect_waste_score", 0.0) or 0.0),
            -float(item.get("collected_total_duration_sec", 0.0) or 0.0),
            float(item.get("best_applied_overlap_ratio", 0.0) or 0.0),
            str(item.get("primary_text") or ""),
        )
    )
    return rows


def _range_overlap_ratio(
    start_a: float,
    end_a: float,
    start_b: float,
    end_b: float,
) -> float:
    overlap = max(0.0, min(end_a, end_b) - max(start_a, start_b))
    span = max(end_a, end_b) - min(start_a, start_b)
    if span <= 0.0:
        return 0.0
    return round(overlap / span, 6)


def _pressure_snapshot_trigger_reasons(
    snapshot: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> list[str]:
    data = dict(snapshot or {})
    settings = dict(settings or {})
    if not data:
        return []

    def _setting_float(key: str, fallback: float) -> float:
        try:
            value = settings.get(key, fallback)
            if value is None or value == "":
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback

    threshold_payload = _pressure_snapshot_threshold_payload(settings)
    warning_ratio = float(threshold_payload["available_memory_warning_ratio_threshold"])
    critical_ratio = float(threshold_payload["available_memory_critical_ratio_threshold"])
    warning_reserve_gb = float(threshold_payload["available_memory_warning_reserve_gb_threshold"])
    critical_reserve_gb = float(threshold_payload["available_memory_critical_reserve_gb_threshold"])
    warning_compressed_ratio = float(threshold_payload["compressed_memory_warning_ratio_threshold"])
    critical_compressed_ratio = float(threshold_payload["compressed_memory_critical_ratio_threshold"])

    available_ratio = float(data.get("available_memory_ratio", 1.0) or 1.0)
    available_gb = float(data.get("available_memory_bytes", 0.0) or 0.0) / float(1024 ** 3)
    compressed_ratio = float(data.get("compressed_memory_ratio", 0.0) or 0.0)

    reasons: list[str] = []
    if available_ratio <= critical_ratio:
        reasons.append("critical_available_memory_ratio")
    if available_gb > 0.0 and available_gb <= critical_reserve_gb:
        reasons.append("critical_available_memory_reserve_gb")
    if compressed_ratio >= critical_compressed_ratio:
        reasons.append("critical_compressed_memory_ratio")
    if not reasons:
        if compressed_ratio >= warning_compressed_ratio:
            reasons.append("warning_compressed_memory_ratio")
        if available_ratio <= warning_ratio:
            reasons.append("warning_available_memory_ratio")
        if available_gb > 0.0 and available_gb <= warning_reserve_gb:
            reasons.append("warning_available_memory_reserve_gb")
    return reasons


def _pressure_snapshot_threshold_payload(settings: dict[str, Any] | None = None) -> dict[str, float]:
    settings = dict(settings or {})

    def _setting_float(key: str, fallback: float) -> float:
        try:
            value = settings.get(key, fallback)
            if value is None or value == "":
                return fallback
            return float(value)
        except (TypeError, ValueError):
            return fallback

    warning_ratio = _setting_float(
        "runtime_memory_warning_ratio",
        _setting_float("macos_memory_warning_ratio", 0.20),
    )
    critical_ratio = _setting_float(
        "runtime_memory_critical_ratio",
        _setting_float("macos_memory_critical_ratio", 0.12),
    )
    warning_reserve_gb = _setting_float("macos_memory_warning_reserve_gb", 3.0)
    critical_reserve_gb = _setting_float("macos_memory_critical_reserve_gb", 1.5)
    warning_compressed_ratio = _setting_float(
        "runtime_memory_warning_compressed_ratio",
        _setting_float("macos_memory_warning_compressed_ratio", 0.22),
    )
    critical_compressed_ratio = _setting_float(
        "runtime_memory_critical_compressed_ratio",
        _setting_float("macos_memory_critical_compressed_ratio", 0.30),
    )
    if warning_ratio <= critical_ratio:
        warning_ratio, critical_ratio = critical_ratio, warning_ratio
    if warning_reserve_gb <= critical_reserve_gb:
        warning_reserve_gb, critical_reserve_gb = critical_reserve_gb, warning_reserve_gb
    if warning_compressed_ratio <= critical_compressed_ratio:
        warning_compressed_ratio, critical_compressed_ratio = critical_compressed_ratio, warning_compressed_ratio
    return {
        "available_memory_warning_ratio_threshold": round(warning_ratio, 4),
        "available_memory_critical_ratio_threshold": round(critical_ratio, 4),
        "available_memory_warning_reserve_gb_threshold": round(warning_reserve_gb, 3),
        "available_memory_critical_reserve_gb_threshold": round(critical_reserve_gb, 3),
        "compressed_memory_warning_ratio_threshold": round(warning_compressed_ratio, 4),
        "compressed_memory_critical_ratio_threshold": round(critical_compressed_ratio, 4),
    }


def _pressure_snapshot_headroom_payload(
    snapshot: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    data = dict(snapshot or {})
    threshold_payload = _pressure_snapshot_threshold_payload(settings)
    available_ratio = data.get("available_memory_ratio")
    compressed_ratio = data.get("compressed_memory_ratio")

    available_critical_headroom = None
    compressed_critical_headroom = None
    if available_ratio is not None:
        try:
            available_critical_headroom = round(
                float(available_ratio or 0.0)
                - float(threshold_payload["available_memory_critical_ratio_threshold"]),
                4,
            )
        except (TypeError, ValueError):
            available_critical_headroom = None
    if compressed_ratio is not None:
        try:
            compressed_critical_headroom = round(
                float(threshold_payload["compressed_memory_critical_ratio_threshold"])
                - float(compressed_ratio or 0.0),
                4,
            )
        except (TypeError, ValueError):
            compressed_critical_headroom = None

    return {
        **threshold_payload,
        "available_memory_critical_headroom": available_critical_headroom,
        "compressed_memory_critical_headroom": compressed_critical_headroom,
    }


def _pressure_reason_stage(reasons: list[str] | None) -> str:
    normalized = [
        str(item).strip().lower()
        for item in list(reasons or [])
        if str(item).strip()
    ]
    if any(item.startswith("critical_") for item in normalized):
        return "critical"
    if any(item.startswith("warning_") for item in normalized):
        return "warning"
    return ""


def _pressure_stage_reason_mismatch_payload(stage: Any, reasons: list[str] | None) -> dict[str, Any]:
    native_stage = str(stage or "").strip().lower()
    reason_stage = _pressure_reason_stage(reasons)
    mismatch = bool(native_stage and reason_stage and native_stage != reason_stage)
    mismatch_kind = f"native_{native_stage}_raw_{reason_stage}" if mismatch else ""
    return {
        "reason_stage": reason_stage,
        "mismatch": mismatch,
        "mismatch_kind": mismatch_kind,
    }


def _matched_overlap_group(
    accepted_group: dict[str, Any],
    current_groups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    accepted_source = str(accepted_group.get("source_chunk_path") or "").strip()
    accepted_start = float(accepted_group.get("cluster_start", 0.0) or 0.0)
    accepted_end = max(accepted_start, float(accepted_group.get("cluster_end", accepted_start) or accepted_start))
    accepted_texts = {
        str(item).strip()
        for item in list(accepted_group.get("sample_texts") or [])
        if str(item).strip()
    }
    best_group: dict[str, Any] | None = None
    best_score: tuple[float, int, float] | None = None
    for candidate in current_groups:
        current_source = str(candidate.get("source_chunk_path") or "").strip()
        if accepted_source and current_source and accepted_source != current_source:
            continue
        current_start = float(candidate.get("cluster_start", 0.0) or 0.0)
        current_end = max(current_start, float(candidate.get("cluster_end", current_start) or current_start))
        overlap_ratio = _range_overlap_ratio(accepted_start, accepted_end, current_start, current_end)
        if overlap_ratio <= 0.0:
            continue
        current_texts = {
            str(item).strip()
            for item in list(candidate.get("sample_texts") or [])
            if str(item).strip()
        }
        shared_texts = len(accepted_texts & current_texts)
        score = (
            overlap_ratio,
            shared_texts,
            -abs(float(candidate.get("cluster_span_sec", 0.0) or 0.0) - float(accepted_group.get("cluster_span_sec", 0.0) or 0.0)),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_group = candidate
    return best_group


def _word_precision_submission_delta_rows(
    accepted_groups: list[dict[str, Any]] | None,
    current_groups: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    accepted_rows = [dict(item) for item in list(accepted_groups or []) if isinstance(item, dict)]
    current_rows = [dict(item) for item in list(current_groups or []) if isinstance(item, dict)]
    if not accepted_rows or not current_rows:
        return []
    delta_rows: list[dict[str, Any]] = []
    for accepted_group in accepted_rows:
        current_group = _matched_overlap_group(accepted_group, current_rows)
        if not isinstance(current_group, dict):
            continue
        current_roles = [
            dict(item)
            for item in list(current_group.get("clip_roles") or [])
            if isinstance(item, dict)
        ]
        accepted_roles = [
            dict(item)
            for item in list(accepted_group.get("clip_roles") or [])
            if isinstance(item, dict) and not bool(item.get("likely_applied"))
        ]
        accepted_roles.sort(
            key=lambda item: (
                -float(item.get("collected_total_duration_sec", 0.0) or 0.0),
                -float(item.get("duration_sec", 0.0) or 0.0),
                str(item.get("primary_text") or ""),
            )
        )
        for accepted_role in accepted_roles[:2]:
            primary_text = str(accepted_role.get("primary_text") or "").strip()
            if not primary_text:
                continue
            matched_current = next(
                (
                    item
                    for item in current_roles
                    if str(item.get("primary_text") or "").strip() == primary_text
                    and bool(item.get("likely_applied")) == bool(accepted_role.get("likely_applied"))
                ),
                None,
            )
            if not isinstance(matched_current, dict):
                continue
            accepted_submission = accepted_role.get("submission_index")
            current_submission = matched_current.get("submission_index")
            delta_rows.append(
                {
                    "cluster_start": accepted_group.get("cluster_start"),
                    "cluster_end": accepted_group.get("cluster_end"),
                    "primary_text": primary_text,
                    "pure_numeric": bool(accepted_role.get("pure_numeric")),
                    "accepted_submission_index": accepted_submission,
                    "current_submission_index": current_submission,
                    "submission_index_delta": _round_delta(current_submission, accepted_submission),
                    "accepted_submitted_chunk_offset_sec": accepted_role.get("submitted_chunk_offset_sec"),
                    "current_submitted_chunk_offset_sec": matched_current.get("submitted_chunk_offset_sec"),
                    "accepted_collected_total_duration_sec": accepted_role.get("collected_total_duration_sec"),
                    "current_collected_total_duration_sec": matched_current.get("collected_total_duration_sec"),
                }
            )
    delta_rows.sort(
        key=lambda item: (
            -abs(float(item.get("submission_index_delta", 0.0) or 0.0)),
            -float(item.get("accepted_collected_total_duration_sec", 0.0) or 0.0),
            str(item.get("primary_text") or ""),
        )
    )
    return delta_rows


def _build_word_precision_overlap_group(
    source_chunk_path: str,
    clip_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    start = min(float(item.get("start", 0.0) or 0.0) for item in clip_rows)
    end = max(float(item.get("end", start) or start) for item in clip_rows)
    non_applied_rows = [item for item in clip_rows if not bool(item.get("likely_applied"))]
    applied_rows = [item for item in clip_rows if bool(item.get("likely_applied"))]
    sample_texts: list[str] = []
    for item in clip_rows:
        text = str(item.get("primary_text") or "").strip()
        if text and text not in sample_texts:
            sample_texts.append(text)
    clip_roles = _artifact_word_precision_overlap_group_clip_roles(clip_rows)
    max_completed_chunk_elapsed_ms = round(
        max((float(item.get("completed_chunk_elapsed_ms", 0.0) or 0.0) for item in clip_roles), default=0.0),
        3,
    )
    max_non_applied_completed_chunk_elapsed_ms = round(
        max(
            (
                float(item.get("completed_chunk_elapsed_ms", 0.0) or 0.0)
                for item in clip_roles
                if str(item.get("role") or "") == "non_applied"
            ),
            default=0.0,
        ),
        3,
    )
    return {
        "source_chunk_path": source_chunk_path if source_chunk_path != "__unknown__" else "",
        "source_chunk_start": clip_rows[0].get("source_chunk_start"),
        "source_chunk_duration_sec": clip_rows[0].get("source_chunk_duration_sec"),
        "cluster_start": round(start, 3),
        "cluster_end": round(end, 3),
        "cluster_span_sec": round(max(0.0, end - start), 3),
        "clip_count": len(clip_rows),
        "applied_clip_count": len(applied_rows),
        "non_applied_clip_count": len(non_applied_rows),
        "total_clip_duration_sec": round(
            sum(float(item.get("duration_sec", 0.0) or 0.0) for item in clip_rows),
            3,
        ),
        "non_applied_clip_duration_sec": round(
            sum(float(item.get("duration_sec", 0.0) or 0.0) for item in non_applied_rows),
            3,
        ),
        "collected_total_duration_sec": round(
            sum(float(item.get("collected_total_duration_sec", 0.0) or 0.0) for item in clip_rows),
            3,
        ),
        "non_applied_collected_total_duration_sec": round(
            sum(float(item.get("collected_total_duration_sec", 0.0) or 0.0) for item in non_applied_rows),
            3,
        ),
        "collected_segment_count": sum(int(item.get("collected_segment_count", 0) or 0) for item in clip_rows),
        "non_applied_collected_segment_count": sum(
            int(item.get("collected_segment_count", 0) or 0) for item in non_applied_rows
        ),
        "max_completed_chunk_elapsed_ms": max_completed_chunk_elapsed_ms,
        "max_non_applied_completed_chunk_elapsed_ms": max_non_applied_completed_chunk_elapsed_ms,
        "sample_texts": sample_texts[:4],
        "clip_roles": clip_roles,
    }


def _runtime_policy_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    settings = dict(row.get("settings") or {})
    keys = [
        "stt_word_timestamps_precision_threshold",
        "stt_word_timestamps_precision_max_segments",
        "stt_word_timestamps_precision_max_audio_sec",
        "stt_word_timestamp_worker_response_timeout_sec",
        "stt_word_timestamp_worker_straggler_timeout_sec",
        "stt_word_timestamp_worker_straggler_max_missing_chunks",
        "stt_word_timestamp_worker_straggler_min_received_ratio",
        "stt_recheck_worker_response_timeout_sec",
        "stt_recheck_worker_straggler_timeout_sec",
        "stt_recheck_worker_straggler_max_missing_chunks",
        "stt_recheck_worker_straggler_min_received_ratio",
        "stt_low_score_recheck_threshold",
        "stt_low_score_recheck_max_segments",
        "stt_low_score_recheck_max_audio_sec",
        "stt_low_score_recheck_padding_sec",
    ]
    snapshot: dict[str, Any] = {}
    for key in keys:
        if key in settings:
            snapshot[key] = settings.get(key)
    return snapshot


def _runtime_stage_budget(compact: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    plan_counts = dict(compact.get("artifact_primary_recheck_plan_counts") or {})
    precision_rows = list(compact.get("artifact_word_precision_rows") or [])
    applied_precision_rows = list(compact.get("artifact_applied_word_precision_rows") or [])
    common_split_rows = list(compact.get("artifact_common_split_rows") or [])
    missing_common_split_groups = list(compact.get("artifact_missing_common_split_groups") or [])
    gap_owner_groups = list(compact.get("artifact_gap_owner_groups") or [])
    span_owner_flow = list(compact.get("artifact_span_owner_flow") or [])
    restore_groups = list(compact.get("artifact_raw_restore_restore_groups") or [])
    restore_group_class_counts = _raw_restore_group_classification_counts(restore_groups)
    trim_trace = list(compact.get("artifact_trim_recent_overlap_trace") or [])
    stage_trace = list(compact.get("artifact_stage_trace") or [])
    stage_runtime_trace = list(compact.get("artifact_stage_runtime_trace") or [])
    major_runtime_trace = list(compact.get("artifact_major_runtime_trace") or [])
    selective_runtime_trace = list(compact.get("artifact_selective_ensemble_runtime_trace") or [])
    word_precision_runtime_trace = list(compact.get("artifact_word_precision_runtime_trace") or [])
    final_cleanup_trace = list(compact.get("artifact_final_cleanup_trace") or [])
    anchor_guard_rows = list(compact.get("artifact_stt_anchor_guard_rows") or [])
    final_integrity_policy = dict(compact.get("artifact_final_transcript_integrity_policy") or {})

    trim_decisions = {
        "keep": 0,
        "trim": 0,
        "drop": 0,
    }
    for item in trim_trace:
        decision = str((item or {}).get("decision") or "").strip()
        if decision in trim_decisions:
            trim_decisions[decision] += 1

    stage_segment_counts: dict[str, int] = {}
    for item in stage_trace:
        stage = str((item or {}).get("stage") or "").strip()
        if stage:
            stage_segment_counts[stage] = int((item or {}).get("segment_count") or 0)

    cleanup_step_counts: dict[str, int] = {}
    cleanup_step_changes: dict[str, int] = {}
    for item in final_cleanup_trace:
        step = str((item or {}).get("step") or "").strip()
        if step:
            cleanup_step_counts[step] = int((item or {}).get("segment_count") or 0)
            cleanup_step_changes[step] = int((item or {}).get("changed") or 0)

    stage_runtime_ms_by_stage: dict[str, float] = {}
    slowest_stage_name = ""
    slowest_stage_ms: float | None = None
    stage_runtime_total_ms: float | None = None
    for item in stage_runtime_trace:
        stage = str((item or {}).get("stage") or "").strip()
        stage_ms_raw = (item or {}).get("since_previous_ms")
        if not stage:
            continue
        stage_ms = round(float(stage_ms_raw or 0.0), 3) if stage_ms_raw is not None else 0.0
        stage_runtime_ms_by_stage[stage] = stage_ms
        if slowest_stage_ms is None or stage_ms > slowest_stage_ms:
            slowest_stage_ms = stage_ms
            slowest_stage_name = stage
        since_first = (item or {}).get("since_first_ms")
        if since_first is not None:
            stage_runtime_total_ms = round(float(since_first or 0.0), 3)

    major_runtime_ms_by_phase: dict[str, float] = {}
    slowest_major_phase_name = ""
    slowest_major_phase_ms: float | None = None
    major_runtime_total_ms: float | None = None
    for item in major_runtime_trace:
        phase = str((item or {}).get("phase") or "").strip()
        phase_ms_raw = (item or {}).get("elapsed_ms")
        if not phase:
            continue
        phase_ms = round(float(phase_ms_raw or 0.0), 3) if phase_ms_raw is not None else 0.0
        major_runtime_ms_by_phase[phase] = phase_ms
        if slowest_major_phase_ms is None or phase_ms > slowest_major_phase_ms:
            slowest_major_phase_ms = phase_ms
            slowest_major_phase_name = phase
        since_start = (item or {}).get("since_start_ms")
        if since_start is not None:
            major_runtime_total_ms = round(float(since_start or 0.0), 3)

    major_wallclock_gap_ms: float | None = None
    try:
        elapsed_sec = float(row.get("elapsed_sec", 0.0) or 0.0)
        if major_runtime_total_ms is not None:
            major_wallclock_gap_ms = round(max(0.0, (elapsed_sec * 1000.0) - float(major_runtime_total_ms)), 3)
    except Exception:
        major_wallclock_gap_ms = None

    selective_runtime_ms_by_phase: dict[str, float] = {}
    slowest_selective_phase_name = ""
    slowest_selective_phase_ms: float | None = None
    selective_runtime_total_ms = 0.0
    primary_collect_pressure_stage = ""
    primary_collect_worker_source = ""
    primary_collect_reuse_enabled: bool | None = None
    primary_collect_duration_first_submission_enabled: bool | None = None
    primary_collect_submitted_chunk_count: int | None = None
    primary_collect_submitted_total_duration_sec: float | None = None
    primary_collect_preexisting_alive_runtime_total_count: int | None = None
    primary_collect_pressure_stage_source = ""
    primary_collect_pressure_stage_trigger_reason = ""
    primary_collect_max_completed_chunk_elapsed_ms: float | None = None
    primary_collect_max_emitted_chunk_elapsed_ms: float | None = None
    primary_collect_active_backend = ""
    primary_collect_active_model = ""
    primary_collect_active_reason = ""
    primary_collect_challenger_count: int | None = None
    primary_collect_vad_challenger_provider = ""
    secondary_recheck_raw_range_count: int | None = None
    secondary_recheck_range_count: int | None = None
    secondary_recheck_prepared_clip_count: int | None = None
    secondary_recheck_collected_segment_count: int | None = None
    secondary_recheck_applied_range_count: int | None = None
    secondary_recheck_skipped_range_count: int | None = None
    secondary_recheck_applied_segment_count: int | None = None
    secondary_recheck_retained_primary_segment_count: int | None = None
    secondary_recheck_low_score_source_count: int | None = None
    secondary_recheck_missing_voice_source_count: int | None = None
    secondary_recheck_route_hint_source_count: int | None = None
    secondary_recheck_merged_source_count: int | None = None
    secondary_recheck_collect_pressure_stage = ""
    secondary_recheck_collect_worker_source = ""
    secondary_recheck_collect_reuse_enabled: bool | None = None
    secondary_recheck_collect_pressure_stage_source = ""
    secondary_recheck_collect_pressure_stage_trigger_reason = ""
    secondary_recheck_collect_submitted_chunk_count: int | None = None
    for item in selective_runtime_trace:
        phase = str((item or {}).get("phase") or "").strip()
        phase_ms_raw = (item or {}).get("elapsed_ms")
        if not phase:
            continue
        phase_ms = round(float(phase_ms_raw or 0.0), 3) if phase_ms_raw is not None else 0.0
        selective_runtime_ms_by_phase[phase] = phase_ms
        selective_runtime_total_ms = round(selective_runtime_total_ms + phase_ms, 3)
        if slowest_selective_phase_ms is None or phase_ms > slowest_selective_phase_ms:
            slowest_selective_phase_ms = phase_ms
            slowest_selective_phase_name = phase
        collect_runtime_info = dict((item or {}).get("collect_runtime_info") or {})
        if phase == "primary_collect" and collect_runtime_info:
            primary_collect_pressure_stage = str(collect_runtime_info.get("pressure_stage") or "").strip().lower()
            primary_collect_worker_source = str(collect_runtime_info.get("worker_source") or "").strip()
            primary_collect_reuse_enabled = bool(collect_runtime_info.get("reuse_enabled"))
            primary_collect_duration_first_submission_enabled = bool(
                collect_runtime_info.get("duration_first_submission_enabled")
            )
            primary_collect_submitted_chunk_count = len(list(collect_runtime_info.get("submitted_chunk_paths") or []))
            primary_collect_submitted_total_duration_sec = round(
                sum(
                    float(item or 0.0)
                    for item in list(collect_runtime_info.get("submitted_chunk_durations_sec") or [])
                ),
                3,
            )
            primary_collect_preexisting_alive_runtime_total_count = int(
                collect_runtime_info.get("preexisting_alive_runtime_total_count", 0) or 0
            )
            primary_collect_max_completed_chunk_elapsed_ms = round(
                max(
                    (
                        float(item or 0.0)
                        for item in list(collect_runtime_info.get("completed_chunk_elapsed_ms") or [])
                    ),
                    default=0.0,
                ),
                3,
            )
            primary_collect_max_emitted_chunk_elapsed_ms = round(
                max(
                    (
                        float(item or 0.0)
                        for item in list(collect_runtime_info.get("emitted_chunk_elapsed_ms") or [])
                    ),
                    default=0.0,
                ),
                3,
            )
            stt_benchmark_plan = dict(collect_runtime_info.get("stt_benchmark_plan") or {})
            if stt_benchmark_plan:
                primary_collect_active_backend = str(stt_benchmark_plan.get("active_backend") or "").strip()
                primary_collect_active_model = str(stt_benchmark_plan.get("active_model") or "").strip()
                primary_collect_active_reason = str(stt_benchmark_plan.get("active_reason") or "").strip()
                primary_collect_challenger_count = len(list(stt_benchmark_plan.get("challengers") or []))
                primary_collect_vad_challenger_provider = str(
                    dict(stt_benchmark_plan.get("vad_challenger") or {}).get("provider") or ""
                ).strip()
            resource_snapshot = dict(collect_runtime_info.get("resource_snapshot") or {})
            if resource_snapshot:
                stage_details = memory_pressure_stage_details_from_snapshot(
                    resource_snapshot,
                    dict(row.get("settings") or {}),
                )
                primary_collect_pressure_stage_source = str(stage_details.get("source") or "").strip()
                primary_collect_pressure_stage_trigger_reason = str(stage_details.get("trigger_reason") or "").strip()
        if phase == "secondary_low_score_recheck":
            source_counts = dict((item or {}).get("recheck_plan_source_counts") or {})
            secondary_recheck_low_score_source_count = int(source_counts.get("low_score", 0) or 0)
            secondary_recheck_missing_voice_source_count = int(source_counts.get("missing_voice", 0) or 0)
            secondary_recheck_route_hint_source_count = int(source_counts.get("route_hint", 0) or 0)
            secondary_recheck_merged_source_count = int(source_counts.get("merged", 0) or 0)
            secondary_recheck_raw_range_count = int((item or {}).get("raw_range_count", 0) or 0)
            secondary_recheck_range_count = int((item or {}).get("range_count", 0) or 0)
            secondary_recheck_prepared_clip_count = int((item or {}).get("prepared_clip_count", 0) or 0)
            secondary_recheck_collected_segment_count = int((item or {}).get("collected_segment_count", 0) or 0)
            secondary_recheck_applied_range_count = int((item or {}).get("applied_range_count", 0) or 0)
            secondary_recheck_skipped_range_count = int((item or {}).get("skipped_range_count", 0) or 0)
            secondary_recheck_applied_segment_count = int((item or {}).get("applied_segment_count", 0) or 0)
            secondary_recheck_retained_primary_segment_count = int(
                (item or {}).get("retained_primary_segment_count", 0) or 0
            )
            if collect_runtime_info:
                secondary_recheck_collect_pressure_stage = str(
                    collect_runtime_info.get("pressure_stage") or ""
                ).strip().lower()
                secondary_recheck_collect_worker_source = str(
                    collect_runtime_info.get("worker_source") or ""
                ).strip()
                secondary_recheck_collect_reuse_enabled = bool(collect_runtime_info.get("reuse_enabled"))
                secondary_recheck_collect_submitted_chunk_count = len(
                    list(collect_runtime_info.get("submitted_chunk_paths") or [])
                )
                resource_snapshot = dict(collect_runtime_info.get("resource_snapshot") or {})
                if resource_snapshot:
                    stage_details = memory_pressure_stage_details_from_snapshot(
                        resource_snapshot,
                        dict(row.get("settings") or {}),
                    )
                    secondary_recheck_collect_pressure_stage_source = str(
                        stage_details.get("source") or ""
                    ).strip()
                    secondary_recheck_collect_pressure_stage_trigger_reason = str(
                        stage_details.get("trigger_reason") or ""
                    ).strip()

    word_precision_runtime_ms_by_phase: dict[str, float] = {}
    slowest_word_precision_phase_name = ""
    slowest_word_precision_phase_ms: float | None = None
    word_precision_runtime_total_ms = 0.0
    word_precision_clip_count = 0
    word_precision_applied_clip_count = 0
    word_precision_non_applied_clip_count = 0
    word_precision_total_clip_duration_sec = 0.0
    word_precision_non_applied_clip_duration_sec = 0.0
    word_precision_max_clip_duration_sec = 0.0
    word_precision_collected_segment_count = 0
    word_precision_non_applied_collected_segment_count = 0
    word_precision_source_chunk_count = 0
    word_precision_collect_clip_count = 0
    word_precision_overlap_group_count = 0
    word_precision_non_applied_overlap_group_count = 0
    word_precision_max_overlap_group_span_sec = 0.0
    word_precision_overlap_group_collected_duration_sec = 0.0
    word_precision_non_applied_overlap_group_collected_duration_sec = 0.0
    word_precision_max_overlap_group_collected_duration_sec = 0.0
    word_precision_low_yield_clip_count = 0
    word_precision_low_yield_clip_collected_duration_sec = 0.0
    word_precision_max_low_yield_clip_waste_score = 0.0
    word_precision_collect_pressure_stage = ""
    word_precision_collect_worker_source = ""
    word_precision_collect_owner_type = ""
    word_precision_collect_reuse_enabled: bool | None = None
    word_precision_collect_allow_worker_reuse: bool | None = None
    word_precision_collect_transient_worker: bool | None = None
    word_precision_collect_pressure_stage_source = ""
    word_precision_collect_pressure_stage_trigger_reason = ""
    word_precision_collect_available_memory_ratio: float | None = None
    word_precision_collect_compressed_memory_ratio: float | None = None
    word_precision_collect_process_rss_bytes: int | None = None
    word_precision_collect_available_memory_critical_ratio_threshold: float | None = None
    word_precision_collect_available_memory_critical_headroom: float | None = None
    word_precision_collect_compressed_memory_critical_ratio_threshold: float | None = None
    word_precision_collect_compressed_memory_critical_headroom: float | None = None
    word_precision_collect_pressure_reasons: list[str] = []
    word_precision_collect_pressure_reason_stage = ""
    word_precision_collect_pressure_stage_reason_mismatch = False
    word_precision_collect_pressure_stage_reason_mismatch_kind = ""
    word_precision_collect_duration_first_submission_enabled: bool | None = None
    word_precision_collect_submitted_chunk_count = 0
    word_precision_collect_preexisting_child_processor_count = 0
    word_precision_collect_preexisting_cached_worker_count = 0
    word_precision_collect_preexisting_busy_worker_count = 0
    word_precision_collect_preexisting_alive_owner_runtime_count = 0
    word_precision_collect_preexisting_alive_child_runtime_count = 0
    word_precision_collect_preexisting_alive_cached_worker_count = 0
    word_precision_collect_preexisting_alive_runtime_total_count = 0
    word_precision_max_completed_chunk_elapsed_ms: float | None = None
    word_precision_max_non_applied_completed_chunk_elapsed_ms: float | None = None
    clip_rows_with_applied = _artifact_applied_word_precision_clip_rows(
        compact.get("artifact_word_precision_clip_rows"),
        applied_precision_rows,
        compact.get("artifact_raw_rows"),
        compact.get("artifact_output_rows"),
    )
    chunk_groups = _artifact_word_precision_chunk_groups(clip_rows_with_applied)
    overlap_groups = _artifact_word_precision_overlap_groups(clip_rows_with_applied)
    low_yield_clip_rows = _artifact_word_precision_low_yield_clip_rows(overlap_groups)
    for item in word_precision_runtime_trace:
        phase = str((item or {}).get("phase") or "").strip()
        phase_ms_raw = (item or {}).get("elapsed_ms")
        if not phase:
            continue
        phase_ms = round(float(phase_ms_raw or 0.0), 3) if phase_ms_raw is not None else 0.0
        word_precision_runtime_ms_by_phase[phase] = phase_ms
        word_precision_runtime_total_ms = round(word_precision_runtime_total_ms + phase_ms, 3)
        if slowest_word_precision_phase_ms is None or phase_ms > slowest_word_precision_phase_ms:
            slowest_word_precision_phase_ms = phase_ms
            slowest_word_precision_phase_name = phase
        if phase == "collect_segments":
            word_precision_collect_clip_count = len(list((item or {}).get("collect_clip_rows") or []))
            collect_runtime_info = dict((item or {}).get("collect_runtime_info") or {})
            word_precision_collect_pressure_stage = str(collect_runtime_info.get("pressure_stage") or "").strip().lower()
            word_precision_collect_worker_source = str(collect_runtime_info.get("worker_source") or "").strip()
            word_precision_collect_owner_type = str((item or {}).get("collect_owner_type") or "").strip()
            if collect_runtime_info:
                word_precision_collect_reuse_enabled = bool(collect_runtime_info.get("reuse_enabled"))
                word_precision_collect_allow_worker_reuse = bool(collect_runtime_info.get("allow_collect_worker_reuse"))
                word_precision_collect_transient_worker = bool(collect_runtime_info.get("transient_worker"))
                word_precision_collect_preexisting_child_processor_count = int(
                    collect_runtime_info.get("preexisting_child_processor_count", 0) or 0
                )
                word_precision_collect_preexisting_cached_worker_count = int(
                    collect_runtime_info.get("preexisting_cached_worker_count", 0) or 0
                )
                word_precision_collect_preexisting_busy_worker_count = int(
                    collect_runtime_info.get("preexisting_busy_worker_count", 0) or 0
                )
                word_precision_collect_preexisting_alive_owner_runtime_count = int(
                    collect_runtime_info.get("preexisting_alive_owner_runtime_count", 0) or 0
                )
                word_precision_collect_preexisting_alive_child_runtime_count = int(
                    collect_runtime_info.get("preexisting_alive_child_runtime_count", 0) or 0
                )
                word_precision_collect_preexisting_alive_cached_worker_count = int(
                    collect_runtime_info.get("preexisting_alive_cached_worker_count", 0) or 0
                )
                word_precision_collect_preexisting_alive_runtime_total_count = int(
                    collect_runtime_info.get("preexisting_alive_runtime_total_count", 0) or 0
                )
                resource_snapshot = dict(collect_runtime_info.get("resource_snapshot") or {})
                if resource_snapshot:
                    stage_details = memory_pressure_stage_details_from_snapshot(
                        resource_snapshot,
                        dict(row.get("settings") or {}),
                    )
                    word_precision_collect_pressure_stage_source = str(
                        stage_details.get("source") or ""
                    ).strip()
                    word_precision_collect_pressure_stage_trigger_reason = str(
                        stage_details.get("trigger_reason") or ""
                    ).strip()
                    headroom_payload = _pressure_snapshot_headroom_payload(
                        resource_snapshot,
                        dict(row.get("settings") or {}),
                    )
                    if resource_snapshot.get("available_memory_ratio") is not None:
                        word_precision_collect_available_memory_ratio = round(
                            float(resource_snapshot.get("available_memory_ratio", 0.0) or 0.0),
                            4,
                        )
                    if resource_snapshot.get("compressed_memory_ratio") is not None:
                        word_precision_collect_compressed_memory_ratio = round(
                            float(resource_snapshot.get("compressed_memory_ratio", 0.0) or 0.0),
                            4,
                        )
                    if resource_snapshot.get("process_rss_bytes") is not None:
                        word_precision_collect_process_rss_bytes = int(
                            resource_snapshot.get("process_rss_bytes", 0) or 0
                        )
                    if headroom_payload.get("available_memory_critical_ratio_threshold") is not None:
                        word_precision_collect_available_memory_critical_ratio_threshold = round(
                            float(headroom_payload.get("available_memory_critical_ratio_threshold", 0.0) or 0.0),
                            4,
                        )
                    if headroom_payload.get("available_memory_critical_headroom") is not None:
                        word_precision_collect_available_memory_critical_headroom = round(
                            float(headroom_payload.get("available_memory_critical_headroom", 0.0) or 0.0),
                            4,
                        )
                    if headroom_payload.get("compressed_memory_critical_ratio_threshold") is not None:
                        word_precision_collect_compressed_memory_critical_ratio_threshold = round(
                            float(headroom_payload.get("compressed_memory_critical_ratio_threshold", 0.0) or 0.0),
                            4,
                        )
                    if headroom_payload.get("compressed_memory_critical_headroom") is not None:
                        word_precision_collect_compressed_memory_critical_headroom = round(
                            float(headroom_payload.get("compressed_memory_critical_headroom", 0.0) or 0.0),
                            4,
                        )
                    word_precision_collect_pressure_reasons = _pressure_snapshot_trigger_reasons(
                        resource_snapshot,
                        dict(row.get("settings") or {}),
                    )
                    mismatch_payload = _pressure_stage_reason_mismatch_payload(
                        word_precision_collect_pressure_stage,
                        word_precision_collect_pressure_reasons,
                    )
                    word_precision_collect_pressure_reason_stage = str(
                        mismatch_payload.get("reason_stage") or ""
                    ).strip()
                    word_precision_collect_pressure_stage_reason_mismatch = bool(
                        mismatch_payload.get("mismatch")
                    )
                    word_precision_collect_pressure_stage_reason_mismatch_kind = str(
                        mismatch_payload.get("mismatch_kind") or ""
                    ).strip()
                if "duration_first_submission_enabled" in collect_runtime_info:
                    word_precision_collect_duration_first_submission_enabled = bool(
                        collect_runtime_info.get("duration_first_submission_enabled")
                    )
                word_precision_collect_submitted_chunk_count = len(
                    list(collect_runtime_info.get("submitted_chunk_paths") or [])
                )
        if phase == "prepare_clips":
            clip_rows = clip_rows_with_applied
            if word_precision_collect_clip_count <= 0:
                word_precision_collect_clip_count = len(clip_rows)
            word_precision_clip_count = len(clip_rows)
            word_precision_applied_clip_count = sum(1 for clip in clip_rows if bool((clip or {}).get("likely_applied")))
            word_precision_non_applied_clip_count = sum(
                1 for clip in clip_rows if not bool((clip or {}).get("likely_applied"))
            )
            word_precision_total_clip_duration_sec = round(
                float((item or {}).get("prepared_total_clip_duration_sec", 0.0) or 0.0),
                3,
            )
            word_precision_non_applied_clip_duration_sec = round(
                sum(float((clip or {}).get("duration_sec", 0.0) or 0.0) for clip in clip_rows if not bool((clip or {}).get("likely_applied"))),
                3,
            )
            word_precision_max_clip_duration_sec = round(
                float((item or {}).get("prepared_max_clip_duration_sec", 0.0) or 0.0),
                3,
            )
            word_precision_collected_segment_count = sum(
                int((clip or {}).get("collected_segment_count", 0) or 0) for clip in clip_rows
            )
            word_precision_non_applied_collected_segment_count = sum(
                int((clip or {}).get("collected_segment_count", 0) or 0)
                for clip in clip_rows
                if not bool((clip or {}).get("likely_applied"))
            )
            word_precision_source_chunk_count = len(chunk_groups)
            word_precision_overlap_group_count = len(overlap_groups)
            word_precision_non_applied_overlap_group_count = sum(
                1 for group in overlap_groups if int((group or {}).get("non_applied_clip_count", 0) or 0) > 0
            )
            word_precision_max_overlap_group_span_sec = round(
                max((float((group or {}).get("cluster_span_sec", 0.0) or 0.0) for group in overlap_groups), default=0.0),
                3,
            )
            word_precision_overlap_group_collected_duration_sec = round(
                sum(float((group or {}).get("collected_total_duration_sec", 0.0) or 0.0) for group in overlap_groups),
                3,
            )
            word_precision_non_applied_overlap_group_collected_duration_sec = round(
                sum(
                    float((group or {}).get("non_applied_collected_total_duration_sec", 0.0) or 0.0)
                    for group in overlap_groups
                ),
                3,
            )
            word_precision_max_overlap_group_collected_duration_sec = round(
                max(
                    (
                        float((group or {}).get("collected_total_duration_sec", 0.0) or 0.0)
                        for group in overlap_groups
                    ),
                    default=0.0,
                ),
                3,
            )
            word_precision_max_completed_chunk_elapsed_ms = round(
                max(
                    (
                        float((group or {}).get("max_completed_chunk_elapsed_ms", 0.0) or 0.0)
                        for group in overlap_groups
                    ),
                    default=0.0,
                ),
                3,
            )
            word_precision_max_non_applied_completed_chunk_elapsed_ms = round(
                max(
                    (
                        float((group or {}).get("max_non_applied_completed_chunk_elapsed_ms", 0.0) or 0.0)
                        for group in overlap_groups
                    ),
                    default=0.0,
                ),
                3,
            )
            word_precision_low_yield_clip_count = len(low_yield_clip_rows)
            word_precision_low_yield_clip_collected_duration_sec = round(
                sum(float((clip or {}).get("collected_total_duration_sec", 0.0) or 0.0) for clip in low_yield_clip_rows),
                3,
            )
            word_precision_max_low_yield_clip_waste_score = round(
                max(
                    (
                        float((clip or {}).get("collect_waste_score", 0.0) or 0.0)
                        for clip in low_yield_clip_rows
                    ),
                    default=0.0,
                ),
                3,
            )

    return {
        "precision_candidate_count": len(precision_rows),
        "precision_applied_count": len(applied_precision_rows),
        "recheck_low_score_count": int(plan_counts.get("low_score") or 0),
        "recheck_missing_voice_count": int(plan_counts.get("missing_voice") or 0),
        "recheck_route_hint_count": int(plan_counts.get("route_hint") or 0),
        "recheck_merged_count": int(plan_counts.get("merged") or 0),
        "recheck_range_count": int(plan_counts.get("ranges") or 0),
        "common_split_output_count": len(common_split_rows),
        "missing_common_split_group_count": len(missing_common_split_groups),
        "gap_owner_group_count": len(gap_owner_groups),
        "span_owner_flow_count": len(span_owner_flow),
        "raw_restore_restore_group_count": len(restore_groups),
        "raw_restore_restore_group_class_counts": restore_group_class_counts,
        "stt_anchor_guard_row_count": len(anchor_guard_rows),
        "stt_anchor_guard_trim_row_count": sum(1 for item in anchor_guard_rows if str((item or {}).get("trim_action") or "").strip()),
        "final_transcript_integrity_accepted": bool(final_integrity_policy.get("accepted")) if final_integrity_policy else None,
        "trim_recent_overlap_decisions": trim_decisions,
        "stage_segment_counts": stage_segment_counts,
        "stage_runtime_count": len(stage_runtime_trace),
        "stage_runtime_total_ms": stage_runtime_total_ms,
        "stage_runtime_ms_by_stage": stage_runtime_ms_by_stage,
        "slowest_stage_name": slowest_stage_name,
        "slowest_stage_ms": round(slowest_stage_ms, 3) if slowest_stage_ms is not None else None,
        "major_runtime_count": len(major_runtime_trace),
        "major_runtime_total_ms": major_runtime_total_ms,
        "major_runtime_ms_by_phase": major_runtime_ms_by_phase,
        "slowest_major_phase_name": slowest_major_phase_name,
        "slowest_major_phase_ms": round(slowest_major_phase_ms, 3) if slowest_major_phase_ms is not None else None,
        "major_wallclock_gap_ms": major_wallclock_gap_ms,
        "selective_runtime_count": len(selective_runtime_trace),
        "selective_runtime_total_ms": round(selective_runtime_total_ms, 3) if selective_runtime_trace else None,
        "selective_runtime_ms_by_phase": selective_runtime_ms_by_phase,
        "slowest_selective_phase_name": slowest_selective_phase_name,
        "slowest_selective_phase_ms": round(slowest_selective_phase_ms, 3)
        if slowest_selective_phase_ms is not None
        else None,
        "primary_collect_pressure_stage": primary_collect_pressure_stage if selective_runtime_trace else "",
        "primary_collect_worker_source": primary_collect_worker_source if selective_runtime_trace else "",
        "primary_collect_reuse_enabled": primary_collect_reuse_enabled if selective_runtime_trace else None,
        "primary_collect_duration_first_submission_enabled": (
            primary_collect_duration_first_submission_enabled if selective_runtime_trace else None
        ),
        "primary_collect_submitted_chunk_count": primary_collect_submitted_chunk_count if selective_runtime_trace else None,
        "primary_collect_submitted_total_duration_sec": (
            primary_collect_submitted_total_duration_sec if selective_runtime_trace else None
        ),
        "primary_collect_preexisting_alive_runtime_total_count": (
            primary_collect_preexisting_alive_runtime_total_count if selective_runtime_trace else None
        ),
        "primary_collect_pressure_stage_source": primary_collect_pressure_stage_source if selective_runtime_trace else "",
        "primary_collect_pressure_stage_trigger_reason": (
            primary_collect_pressure_stage_trigger_reason if selective_runtime_trace else ""
        ),
        "primary_collect_max_completed_chunk_elapsed_ms": (
            primary_collect_max_completed_chunk_elapsed_ms if selective_runtime_trace else None
        ),
        "primary_collect_max_emitted_chunk_elapsed_ms": (
            primary_collect_max_emitted_chunk_elapsed_ms if selective_runtime_trace else None
        ),
        "primary_collect_active_backend": primary_collect_active_backend if selective_runtime_trace else "",
        "primary_collect_active_model": primary_collect_active_model if selective_runtime_trace else "",
        "primary_collect_active_reason": primary_collect_active_reason if selective_runtime_trace else "",
        "primary_collect_challenger_count": primary_collect_challenger_count if selective_runtime_trace else None,
        "primary_collect_vad_challenger_provider": (
            primary_collect_vad_challenger_provider if selective_runtime_trace else ""
        ),
        "secondary_recheck_low_score_source_count": secondary_recheck_low_score_source_count if selective_runtime_trace else None,
        "secondary_recheck_missing_voice_source_count": (
            secondary_recheck_missing_voice_source_count if selective_runtime_trace else None
        ),
        "secondary_recheck_route_hint_source_count": (
            secondary_recheck_route_hint_source_count if selective_runtime_trace else None
        ),
        "secondary_recheck_merged_source_count": secondary_recheck_merged_source_count if selective_runtime_trace else None,
        "secondary_recheck_raw_range_count": secondary_recheck_raw_range_count if selective_runtime_trace else None,
        "secondary_recheck_range_count": secondary_recheck_range_count if selective_runtime_trace else None,
        "secondary_recheck_prepared_clip_count": secondary_recheck_prepared_clip_count if selective_runtime_trace else None,
        "secondary_recheck_collected_segment_count": (
            secondary_recheck_collected_segment_count if selective_runtime_trace else None
        ),
        "secondary_recheck_applied_range_count": secondary_recheck_applied_range_count if selective_runtime_trace else None,
        "secondary_recheck_skipped_range_count": secondary_recheck_skipped_range_count if selective_runtime_trace else None,
        "secondary_recheck_applied_segment_count": (
            secondary_recheck_applied_segment_count if selective_runtime_trace else None
        ),
        "secondary_recheck_retained_primary_segment_count": (
            secondary_recheck_retained_primary_segment_count if selective_runtime_trace else None
        ),
        "secondary_recheck_collect_pressure_stage": secondary_recheck_collect_pressure_stage if selective_runtime_trace else "",
        "secondary_recheck_collect_worker_source": secondary_recheck_collect_worker_source if selective_runtime_trace else "",
        "secondary_recheck_collect_reuse_enabled": (
            secondary_recheck_collect_reuse_enabled if selective_runtime_trace else None
        ),
        "secondary_recheck_collect_pressure_stage_source": (
            secondary_recheck_collect_pressure_stage_source if selective_runtime_trace else ""
        ),
        "secondary_recheck_collect_pressure_stage_trigger_reason": (
            secondary_recheck_collect_pressure_stage_trigger_reason if selective_runtime_trace else ""
        ),
        "secondary_recheck_collect_submitted_chunk_count": (
            secondary_recheck_collect_submitted_chunk_count if selective_runtime_trace else None
        ),
        "word_precision_runtime_count": len(word_precision_runtime_trace),
        "word_precision_runtime_total_ms": round(word_precision_runtime_total_ms, 3)
        if word_precision_runtime_trace
        else None,
        "word_precision_runtime_ms_by_phase": word_precision_runtime_ms_by_phase,
        "word_precision_clip_count": word_precision_clip_count,
        "word_precision_applied_clip_count": word_precision_applied_clip_count,
        "word_precision_non_applied_clip_count": word_precision_non_applied_clip_count,
        "word_precision_collected_segment_count": word_precision_collected_segment_count,
        "word_precision_non_applied_collected_segment_count": word_precision_non_applied_collected_segment_count,
        "word_precision_source_chunk_count": word_precision_source_chunk_count,
        "word_precision_collect_clip_count": word_precision_collect_clip_count,
        "word_precision_overlap_group_count": word_precision_overlap_group_count,
        "word_precision_non_applied_overlap_group_count": word_precision_non_applied_overlap_group_count,
        "word_precision_max_overlap_group_span_sec": word_precision_max_overlap_group_span_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_overlap_group_collected_duration_sec": word_precision_overlap_group_collected_duration_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_non_applied_overlap_group_collected_duration_sec": word_precision_non_applied_overlap_group_collected_duration_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_max_overlap_group_collected_duration_sec": word_precision_max_overlap_group_collected_duration_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_max_completed_chunk_elapsed_ms": word_precision_max_completed_chunk_elapsed_ms
        if word_precision_runtime_trace
        else None,
        "word_precision_max_non_applied_completed_chunk_elapsed_ms": word_precision_max_non_applied_completed_chunk_elapsed_ms
        if word_precision_runtime_trace
        else None,
        "word_precision_low_yield_clip_count": word_precision_low_yield_clip_count if word_precision_runtime_trace else None,
        "word_precision_low_yield_clip_collected_duration_sec": word_precision_low_yield_clip_collected_duration_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_max_low_yield_clip_waste_score": word_precision_max_low_yield_clip_waste_score
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_pressure_stage": word_precision_collect_pressure_stage if word_precision_runtime_trace else "",
        "word_precision_collect_worker_source": word_precision_collect_worker_source if word_precision_runtime_trace else "",
        "word_precision_collect_owner_type": word_precision_collect_owner_type if word_precision_runtime_trace else "",
        "word_precision_collect_reuse_enabled": word_precision_collect_reuse_enabled
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_allow_worker_reuse": word_precision_collect_allow_worker_reuse
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_transient_worker": word_precision_collect_transient_worker
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_pressure_stage_source": word_precision_collect_pressure_stage_source
        if word_precision_runtime_trace
        else "",
        "word_precision_collect_pressure_stage_trigger_reason": word_precision_collect_pressure_stage_trigger_reason
        if word_precision_runtime_trace
        else "",
        "word_precision_collect_available_memory_ratio": word_precision_collect_available_memory_ratio
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_compressed_memory_ratio": word_precision_collect_compressed_memory_ratio
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_process_rss_bytes": word_precision_collect_process_rss_bytes
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_available_memory_critical_ratio_threshold": word_precision_collect_available_memory_critical_ratio_threshold
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_available_memory_critical_headroom": word_precision_collect_available_memory_critical_headroom
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_compressed_memory_critical_ratio_threshold": word_precision_collect_compressed_memory_critical_ratio_threshold
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_compressed_memory_critical_headroom": word_precision_collect_compressed_memory_critical_headroom
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_pressure_reasons": word_precision_collect_pressure_reasons
        if word_precision_runtime_trace
        else [],
        "word_precision_collect_pressure_reason_stage": word_precision_collect_pressure_reason_stage
        if word_precision_runtime_trace
        else "",
        "word_precision_collect_pressure_stage_reason_mismatch": word_precision_collect_pressure_stage_reason_mismatch
        if word_precision_runtime_trace
        else False,
        "word_precision_collect_pressure_stage_reason_mismatch_kind": word_precision_collect_pressure_stage_reason_mismatch_kind
        if word_precision_runtime_trace
        else "",
        "word_precision_collect_duration_first_submission_enabled": word_precision_collect_duration_first_submission_enabled
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_submitted_chunk_count": word_precision_collect_submitted_chunk_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_child_processor_count": word_precision_collect_preexisting_child_processor_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_cached_worker_count": word_precision_collect_preexisting_cached_worker_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_busy_worker_count": word_precision_collect_preexisting_busy_worker_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_alive_owner_runtime_count": word_precision_collect_preexisting_alive_owner_runtime_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_alive_child_runtime_count": word_precision_collect_preexisting_alive_child_runtime_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_alive_cached_worker_count": word_precision_collect_preexisting_alive_cached_worker_count
        if word_precision_runtime_trace
        else None,
        "word_precision_collect_preexisting_alive_runtime_total_count": word_precision_collect_preexisting_alive_runtime_total_count
        if word_precision_runtime_trace
        else None,
        "word_precision_total_clip_duration_sec": word_precision_total_clip_duration_sec if word_precision_runtime_trace else None,
        "word_precision_non_applied_clip_duration_sec": word_precision_non_applied_clip_duration_sec
        if word_precision_runtime_trace
        else None,
        "word_precision_max_clip_duration_sec": word_precision_max_clip_duration_sec if word_precision_runtime_trace else None,
        "slowest_word_precision_phase_name": slowest_word_precision_phase_name,
        "slowest_word_precision_phase_ms": round(slowest_word_precision_phase_ms, 3)
        if slowest_word_precision_phase_ms is not None
        else None,
        "final_cleanup_step_counts": cleanup_step_counts,
        "final_cleanup_step_changes": cleanup_step_changes,
        "runtime_policy_snapshot": _runtime_policy_snapshot(row),
    }


def _artifact_summary_payload(json_path: Path) -> dict[str, Any]:
    ranked = _load_ranked_rows(json_path)
    compact_rows: list[dict[str, Any]] = []
    artifact_reference_rows = _artifact_reference_rows(json_path)
    for row in ranked:
        compact = _compact_row_summary(row)
        diagnostics = _low_score_diagnostics(json_path, row)
        if diagnostics:
            compact["low_score_diagnostics"] = diagnostics
        artifact_plan_counts = _artifact_primary_recheck_plan_counts(json_path, row)
        if artifact_plan_counts:
            compact["artifact_primary_recheck_plan_counts"] = artifact_plan_counts
        artifact_plan_rows = _artifact_primary_recheck_plan_rows(json_path, row)
        if artifact_plan_rows:
            compact["artifact_primary_recheck_plan_rows"] = artifact_plan_rows
        precision_rows = _artifact_word_precision_rows(json_path, row)
        if precision_rows is not None:
            compact["artifact_word_precision_rows"] = precision_rows
        applied_precision_rows = _artifact_applied_word_precision_rows(json_path, row)
        if applied_precision_rows is not None:
            compact["artifact_applied_word_precision_rows"] = applied_precision_rows
        artifact_raw_rows = _artifact_raw_rows(json_path, row)
        if artifact_raw_rows is not None:
            compact["artifact_raw_rows"] = artifact_raw_rows
        artifact_output_rows = _artifact_output_rows(json_path, row)
        if artifact_output_rows is not None:
            compact["artifact_output_rows"] = artifact_output_rows
        artifact_stt_anchor_guard_rows = _artifact_stt_anchor_guard_rows(json_path, row)
        if artifact_stt_anchor_guard_rows is not None:
            compact["artifact_stt_anchor_guard_rows"] = artifact_stt_anchor_guard_rows
        artifact_final_transcript_integrity_policy = _artifact_final_transcript_integrity_policy(json_path, row)
        if artifact_final_transcript_integrity_policy is not None:
            compact["artifact_final_transcript_integrity_policy"] = artifact_final_transcript_integrity_policy
        artifact_common_split_rows = _artifact_common_split_rows(json_path, row)
        if artifact_common_split_rows is not None:
            compact["artifact_common_split_rows"] = artifact_common_split_rows
            compact["artifact_missing_common_split_groups"] = _artifact_missing_common_split_groups(artifact_common_split_rows)
        artifact_stage_trace = _artifact_stage_trace(json_path, row)
        if artifact_stage_trace is not None:
            compact["artifact_stage_trace"] = artifact_stage_trace
        artifact_stage_runtime_trace = _artifact_stage_runtime_trace(json_path, row)
        if artifact_stage_runtime_trace is not None:
            compact["artifact_stage_runtime_trace"] = artifact_stage_runtime_trace
        artifact_major_runtime_trace = _artifact_major_runtime_trace(json_path, row)
        if artifact_major_runtime_trace is not None:
            compact["artifact_major_runtime_trace"] = artifact_major_runtime_trace
        artifact_selective_ensemble_runtime_trace = _artifact_selective_ensemble_runtime_trace(json_path, row)
        if artifact_selective_ensemble_runtime_trace is not None:
            compact["artifact_selective_ensemble_runtime_trace"] = artifact_selective_ensemble_runtime_trace
        artifact_word_precision_runtime_trace = _artifact_word_precision_runtime_trace(json_path, row)
        if artifact_word_precision_runtime_trace is not None:
            compact["artifact_word_precision_runtime_trace"] = artifact_word_precision_runtime_trace
            clip_rows_from_collect = None
            collect_clip_rows_from_collect = None
            for trace_row in artifact_word_precision_runtime_trace:
                phase = str((trace_row or {}).get("phase") or "").strip()
                if phase == "collect_segments" and list((trace_row or {}).get("prepared_clip_rows") or []):
                    clip_rows_from_collect = list((trace_row or {}).get("prepared_clip_rows") or [])
                if phase == "collect_segments" and list((trace_row or {}).get("collect_clip_rows") or []):
                    collect_clip_rows_from_collect = list((trace_row or {}).get("collect_clip_rows") or [])
                if phase == "prepare_clips":
                    compact["artifact_word_precision_clip_rows"] = _artifact_applied_word_precision_clip_rows(
                        _apply_collect_submission_order(
                            list((trace_row or {}).get("prepared_clip_rows") or []),
                            artifact_word_precision_runtime_trace,
                        ),
                        compact.get("artifact_applied_word_precision_rows"),
                        compact.get("artifact_raw_rows"),
                        compact.get("artifact_output_rows"),
                    )
            if clip_rows_from_collect is not None:
                compact["artifact_word_precision_clip_rows"] = _artifact_applied_word_precision_clip_rows(
                    _apply_collect_submission_order(clip_rows_from_collect, artifact_word_precision_runtime_trace),
                    compact.get("artifact_applied_word_precision_rows"),
                    compact.get("artifact_raw_rows"),
                    compact.get("artifact_output_rows"),
                )
            if collect_clip_rows_from_collect is not None:
                compact["artifact_word_precision_collect_clip_rows"] = collect_clip_rows_from_collect
        if compact.get("artifact_word_precision_clip_rows") is not None:
            compact["artifact_word_precision_chunk_groups"] = _artifact_word_precision_chunk_groups(
                compact.get("artifact_word_precision_clip_rows")
            )
            compact["artifact_word_precision_overlap_groups"] = _artifact_word_precision_overlap_groups(
                compact.get("artifact_word_precision_clip_rows")
            )
            compact["artifact_word_precision_low_yield_clip_rows"] = _artifact_word_precision_low_yield_clip_rows(
                compact.get("artifact_word_precision_overlap_groups")
            )
        artifact_final_cleanup_trace = _artifact_final_cleanup_trace(json_path, row)
        if artifact_final_cleanup_trace is not None:
            compact["artifact_final_cleanup_trace"] = artifact_final_cleanup_trace
        artifact_no_llm_raw_restore_trace = _artifact_no_llm_raw_restore_trace(json_path, row)
        if artifact_no_llm_raw_restore_trace is not None:
            compact["artifact_no_llm_raw_restore_trace"] = artifact_no_llm_raw_restore_trace
            compact["artifact_raw_restore_restore_groups"] = _artifact_raw_restore_restore_groups(
                artifact_no_llm_raw_restore_trace
            )
        artifact_trim_recent_overlap_trace = _artifact_trim_recent_overlap_trace(json_path, row)
        if artifact_trim_recent_overlap_trace is not None:
            compact["artifact_trim_recent_overlap_trace"] = artifact_trim_recent_overlap_trace
        if artifact_reference_rows is not None:
            compact["artifact_reference_rows"] = artifact_reference_rows
        reference_gap_rows = _artifact_gap_rows(artifact_reference_rows, artifact_output_rows)
        if reference_gap_rows is not None:
            compact["artifact_reference_gap_rows"] = reference_gap_rows
            compact["artifact_gap_owner_groups"] = _artifact_gap_owner_groups(
                artifact_common_split_rows,
                reference_gap_rows,
            )
        compact["artifact_span_owner_flow"] = _artifact_span_owner_flow(
            artifact_common_split_rows,
            compact.get("artifact_missing_common_split_groups"),
            compact.get("artifact_raw_restore_restore_groups"),
            artifact_trim_recent_overlap_trace,
            compact.get("artifact_gap_owner_groups"),
            artifact_stage_trace,
        )
        output_gap_rows = _artifact_gap_rows(artifact_output_rows, artifact_reference_rows)
        if output_gap_rows is not None:
            compact["artifact_output_gap_rows"] = output_gap_rows
        compact["runtime_stage_budget"] = _runtime_stage_budget(compact, row)
        compact_rows.append(compact)
    best = compact_rows[0] if compact_rows else None
    return {
        "ok": True,
        "json": str(json_path),
        "row_count": len(compact_rows),
        "winner": best,
        "rows": compact_rows,
    }


def _run_repeat_preset(args: argparse.Namespace) -> int:
    repeat = max(1, int(args.repeat or 1))
    runs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for attempt in range(1, repeat + 1):
        benchmark_args = _preset_namespace(args)
        command = _benchmark_command(benchmark_args)
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            env=_server_env(),
            text=True,
            capture_output=True,
        )
        envelope = {
            "attempt": attempt,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "command": command,
        }
        if proc.returncode != 0:
            envelope["stdout"] = proc.stdout
            envelope["stderr"] = proc.stderr
            failures.append(envelope)
            continue
        try:
            payload = _extract_trailing_json_object(proc.stdout)
            artifact_path = Path(str((payload or {}).get("json") or "")).expanduser()
            summary = _artifact_summary_payload(artifact_path)
            runs.append(
                {
                    **envelope,
                    "artifact_json": str(artifact_path),
                    "winner": dict(summary.get("winner") or {}),
                }
            )
        except Exception as exc:
            envelope["stdout"] = proc.stdout
            envelope["stderr"] = proc.stderr
            envelope["error"] = f"summary_parse_failed:{exc}"
            failures.append(envelope)
    elapsed_values = [float((run.get("winner") or {}).get("elapsed_sec") or 0.0) for run in runs if run.get("winner")]
    quality_values = [float((run.get("winner") or {}).get("quality_score") or 0.0) for run in runs if run.get("winner")]
    timing_values = [
        float((run.get("winner") or {}).get("timing_priority_quality_score") or 0.0)
        for run in runs
        if run.get("winner")
    ]
    mae_values = [float((run.get("winner") or {}).get("timing_mae_sec") or 0.0) for run in runs if run.get("winner")]
    payload = {
        "ok": len(runs) == repeat and not failures,
        "preset": str(args.preset),
        "requested_repeat": repeat,
        "completed_runs": len(runs),
        "failed_runs": len(failures),
        "runs": runs,
        "failures": failures,
        "aggregate": {
            "elapsed_sec": _aggregate_metric(elapsed_values),
            "quality_score": _aggregate_metric(quality_values),
            "timing_priority_quality_score": _aggregate_metric(timing_values),
            "timing_mae_sec": _aggregate_metric(mae_values),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _run_preset_once_payload(
    *,
    preset_name: str,
    media: str,
    reference_srt: str,
    start_sec: float,
    duration_sec: float,
    suite: str,
    stt_profile: str,
    ranking_policy: str,
    llm_model: str,
    cached_raw_segments: str,
    keep_artifacts: bool,
) -> dict[str, Any]:
    benchmark_args = _preset_namespace(
        argparse.Namespace(
            preset=preset_name,
            media=media,
            reference_srt=reference_srt,
            start_sec=float(start_sec),
            duration_sec=float(duration_sec),
            suite=str(suite),
            stt_profile=str(stt_profile),
            ranking_policy=str(ranking_policy),
            llm_model=str(llm_model or ""),
            cached_raw_segments=str(cached_raw_segments or ""),
            keep_artifacts=bool(keep_artifacts),
        )
    )
    command = _benchmark_command(benchmark_args)
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        env=_server_env(),
        text=True,
        capture_output=True,
    )
    payload: dict[str, Any] = {
        "preset": preset_name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "command": command,
    }
    if proc.returncode != 0:
        payload["stdout"] = proc.stdout
        payload["stderr"] = proc.stderr
        return payload
    try:
        envelope = _extract_trailing_json_object(proc.stdout)
        artifact_path = Path(str((envelope or {}).get("json") or "")).expanduser()
        summary = _artifact_summary_payload(artifact_path)
        recheck_source_counts = _extract_recheck_source_counts(proc.stdout)
        winner = dict(summary.get("winner") or {})
        if recheck_source_counts:
            winner["recheck_source_counts"] = recheck_source_counts
        payload["artifact_json"] = str(artifact_path)
        payload["winner"] = winner
        return payload
    except Exception as exc:
        payload["stdout"] = proc.stdout
        payload["stderr"] = proc.stderr
        payload["error"] = f"summary_parse_failed:{exc}"
        payload["ok"] = False
        return payload


def _run_matrix_preset(args: argparse.Namespace) -> int:
    presets = [str(item or "").strip() for item in list(args.presets or []) if str(item or "").strip()]
    if not presets:
        presets = list(DEFAULT_MATRIX_PRESETS)
    runs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for preset_name in presets:
        run = _run_preset_once_payload(
            preset_name=preset_name,
            media=str(args.media),
            reference_srt=str(args.reference_srt),
            start_sec=float(args.start_sec),
            duration_sec=float(args.duration_sec),
            suite=str(args.suite),
            stt_profile=str(args.stt_profile),
            ranking_policy=str(args.ranking_policy),
            llm_model=str(args.llm_model or ""),
            cached_raw_segments=str(args.cached_raw_segments or ""),
            keep_artifacts=bool(args.keep_artifacts),
        )
        if not run.get("ok"):
            failures.append(run)
            continue
        runs.append(run)
    baseline = runs[0] if runs else None
    baseline_winner = dict((baseline or {}).get("winner") or {})
    comparisons: list[dict[str, Any]] = []
    for run in runs[1:]:
        winner = dict(run.get("winner") or {})
        comparisons.append(
            {
                "baseline_preset": (baseline or {}).get("preset"),
                "candidate_preset": run.get("preset"),
                "baseline_json": (baseline or {}).get("artifact_json"),
                "candidate_json": run.get("artifact_json"),
                "deltas": {
                    "elapsed_sec_delta": _round_delta(winner.get("elapsed_sec"), baseline_winner.get("elapsed_sec")),
                    "quality_score_delta": _round_delta(
                        winner.get("quality_score"), baseline_winner.get("quality_score")
                    ),
                    "timing_priority_quality_score_delta": _round_delta(
                        winner.get("timing_priority_quality_score"),
                        baseline_winner.get("timing_priority_quality_score"),
                    ),
                    "timing_mae_sec_delta": _round_delta(
                        winner.get("timing_mae_sec"), baseline_winner.get("timing_mae_sec")
                    ),
                },
            }
        )
    payload = {
        "ok": len(runs) == len(presets) and not failures,
        "presets": presets,
        "baseline_preset": (baseline or {}).get("preset"),
        "runs": runs,
        "failures": failures,
        "comparisons_vs_first": comparisons,
        "winner_by_timing_priority_quality": _best_run(
            runs,
            score_key="timing_priority_quality_score",
            prefer_lower_elapsed=True,
        ),
        "winner_by_speed": _best_run(
            runs,
            score_key="elapsed_sec",
            prefer_lower_elapsed=False,
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _run_matrix_repeat(args: argparse.Namespace) -> int:
    presets = [str(item or "").strip() for item in list(args.presets or []) if str(item or "").strip()]
    if not presets:
        presets = list(DEFAULT_MATRIX_PRESETS)
    repeat = max(1, int(args.repeat or 1))
    per_preset_runs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for preset_name in presets:
        runs: list[dict[str, Any]] = []
        for attempt in range(1, repeat + 1):
            run = _run_preset_once_payload(
                preset_name=preset_name,
                media=str(args.media),
                reference_srt=str(args.reference_srt),
                start_sec=float(args.start_sec),
                duration_sec=float(args.duration_sec),
                suite=str(args.suite),
                stt_profile=str(args.stt_profile),
                ranking_policy=str(args.ranking_policy),
                llm_model=str(args.llm_model or ""),
                cached_raw_segments=str(args.cached_raw_segments or ""),
                keep_artifacts=bool(args.keep_artifacts),
            )
            run["attempt"] = attempt
            if not run.get("ok"):
                failures.append(run)
                continue
            runs.append(run)
        elapsed_values = [float((run.get("winner") or {}).get("elapsed_sec") or 0.0) for run in runs if run.get("winner")]
        quality_values = [float((run.get("winner") or {}).get("quality_score") or 0.0) for run in runs if run.get("winner")]
        timing_values = [
            float((run.get("winner") or {}).get("timing_priority_quality_score") or 0.0)
            for run in runs
            if run.get("winner")
        ]
        mae_values = [float((run.get("winner") or {}).get("timing_mae_sec") or 0.0) for run in runs if run.get("winner")]
        summary = {
            "preset": preset_name,
            "requested_repeat": repeat,
            "completed_runs": len(runs),
            "runs": runs,
            "aggregate": {
                "elapsed_sec": _aggregate_metric(elapsed_values),
                "quality_score": _aggregate_metric(quality_values),
                "timing_priority_quality_score": _aggregate_metric(timing_values),
                "timing_mae_sec": _aggregate_metric(mae_values),
            },
            "best_run_by_timing_priority_quality": _best_attempt_from_runs(runs, "timing_priority_quality_score"),
            "best_run_by_speed": _best_attempt_from_runs(runs, "elapsed_sec"),
        }
        per_preset_runs.append(summary)
    baseline = per_preset_runs[0] if per_preset_runs else None
    base_elapsed = ((baseline or {}).get("aggregate") or {}).get("elapsed_sec", {}).get("mean")
    base_quality = ((baseline or {}).get("aggregate") or {}).get("quality_score", {}).get("mean")
    base_timing = ((baseline or {}).get("aggregate") or {}).get("timing_priority_quality_score", {}).get("mean")
    base_mae = ((baseline or {}).get("aggregate") or {}).get("timing_mae_sec", {}).get("mean")
    comparisons: list[dict[str, Any]] = []
    for summary in per_preset_runs[1:]:
        aggregate = dict(summary.get("aggregate") or {})
        comparisons.append(
            {
                "baseline_preset": (baseline or {}).get("preset"),
                "candidate_preset": summary.get("preset"),
                "deltas": {
                    "elapsed_sec_mean_delta": _round_delta((aggregate.get("elapsed_sec") or {}).get("mean"), base_elapsed),
                    "quality_score_mean_delta": _round_delta((aggregate.get("quality_score") or {}).get("mean"), base_quality),
                    "timing_priority_quality_score_mean_delta": _round_delta(
                        (aggregate.get("timing_priority_quality_score") or {}).get("mean"),
                        base_timing,
                    ),
                    "timing_mae_sec_mean_delta": _round_delta((aggregate.get("timing_mae_sec") or {}).get("mean"), base_mae),
                },
            }
        )
    payload = {
        "ok": not failures and all(int((item.get("completed_runs") or 0)) == repeat for item in per_preset_runs),
        "presets": presets,
        "repeat": repeat,
        "baseline_preset": (baseline or {}).get("preset"),
        "per_preset": per_preset_runs,
        "failures": failures,
        "comparisons_vs_first_mean": comparisons,
        "winner_by_mean_timing_priority_quality": _best_preset_summary(per_preset_runs, "timing_priority_quality_score"),
        "winner_by_mean_speed": _best_preset_summary(per_preset_runs, "elapsed_sec", speed_metric=True),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def _aggregate_metric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None, "spread": None}
    return {
        "count": len(values),
        "mean": round(mean(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "spread": round(max(values) - min(values), 6),
    }


def _run_compare_artifacts(args: argparse.Namespace) -> int:
    baseline = _artifact_summary_payload(Path(str(args.baseline_json)).expanduser())
    candidate = _artifact_summary_payload(Path(str(args.candidate_json)).expanduser())
    base = dict(baseline.get("winner") or {})
    cand = dict(candidate.get("winner") or {})
    deltas = {
        "elapsed_sec_delta": _round_delta(cand.get("elapsed_sec"), base.get("elapsed_sec")),
        "quality_score_delta": _round_delta(cand.get("quality_score"), base.get("quality_score")),
        "timing_priority_quality_score_delta": _round_delta(
            cand.get("timing_priority_quality_score"), base.get("timing_priority_quality_score")
        ),
        "timing_mae_sec_delta": _round_delta(cand.get("timing_mae_sec"), base.get("timing_mae_sec")),
        "word_precision_count_delta": _round_delta(cand.get("word_precision_count"), base.get("word_precision_count")),
        "stt2_selected_count_delta": _round_delta(cand.get("stt2_selected_count"), base.get("stt2_selected_count")),
        "recheck_applied_count_delta": _round_delta(
            cand.get("recheck_applied_count"), base.get("recheck_applied_count")
        ),
        "stt2_coverage_ratio_delta": _round_delta(cand.get("stt2_coverage_ratio"), base.get("stt2_coverage_ratio")),
    }
    payload = {
        "ok": True,
        "baseline": {"json": str(args.baseline_json), "winner": base},
        "candidate": {"json": str(args.candidate_json), "winner": cand},
        "deltas": deltas,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _accepted_json_map(args: argparse.Namespace) -> dict[str, Path]:
    return {
        "baseline": Path(str(args.baseline_json)).expanduser(),
        "case1": Path(str(args.case1_json)).expanduser(),
        "case2": Path(str(args.case2_json)).expanduser(),
    }


def _resolve_compare_current_accepted_source(args: argparse.Namespace) -> tuple[str, Path]:
    accepted_json_override = str(getattr(args, "accepted_json", "") or "").strip()
    accepted_label_override = str(getattr(args, "accepted_label", "") or "").strip()
    accepted_target = str(getattr(args, "accepted_target", "") or "").strip()
    if accepted_json_override:
        accepted_json = Path(accepted_json_override).expanduser()
        accepted_label = accepted_label_override or accepted_target or accepted_json.stem or "accepted"
        return accepted_label, accepted_json
    if not accepted_target:
        raise ValueError("compare-current-vs-accepted requires --accepted-target or --accepted-json")
    accepted_map = _accepted_json_map(args)
    return accepted_target, accepted_map[accepted_target]


def _resolve_plan_source(args: argparse.Namespace) -> tuple[str, Path]:
    artifact_json = str(getattr(args, "artifact_json", "") or "").strip()
    if artifact_json:
        target = str(getattr(args, "accepted_target", "") or "").strip() or "artifact"
        return target, Path(artifact_json).expanduser()
    accepted_target = str(getattr(args, "accepted_target", "") or "").strip()
    if not accepted_target:
        raise ValueError("next-owner-plan requires --artifact-json or --accepted-target")
    accepted_map = _accepted_json_map(args)
    return accepted_target, accepted_map[accepted_target]


_OWNER_HINT_FILE_MAP: dict[str, list[str]] = {
    "primary_collect_path": [
        "core/audio/media_processor_transcribe.py",
        "core/audio/media_processor_transcribe_run.py",
        "core/audio/stt_backend_router.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "primary_collect_completion_latency": [
        "core/audio/media_processor_transcribe.py",
        "core/audio/media_processor_transcribe_run.py",
        "core/audio/stt_backend_router.py",
    ],
    "secondary_recheck_path": [
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "available_memory_snapshot_volatility": [
        "core/audio/audio_runtime_services.py",
        "core/performance.py",
        "core/audio/media_processor_transcribe.py",
    ],
    "native_pressure_stage_source": [
        "core/native_macos_memory.py",
        "core/performance.py",
        "core/audio/audio_runtime_services.py",
    ],
    "pressure_stage_reason_mismatch": [
        "core/audio/audio_runtime_services.py",
        "core/performance.py",
        "core/audio/media_processor_transcribe.py",
    ],
    "critical_pressure_collect_policy": [
        "core/audio/audio_runtime_services.py",
        "core/audio/media_processor_transcribe.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "critical_pressure_snapshot_thresholds": [
        "core/audio/audio_runtime_services.py",
        "core/performance.py",
        "core/audio/media_processor_transcribe.py",
    ],
    "precision_candidates": [
        "core/audio/transcribe_policy_helpers.py",
        "core/audio/media_processor_overlap.py",
    ],
    "precision_applied": [
        "core/audio/transcribe_policy_helpers.py",
        "core/audio/media_processor_overlap.py",
    ],
    "precision_overlap_groups": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "precision_apply_gate_non_split_owner": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "collect_path_non_skip_owner": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "collect_path_non_padding_owner": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "precision_candidate_truncation": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "precision_candidate_text_artifact": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/transcribe_policy_helpers.py",
    ],
    "precision_collect_order": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_policy.py",
        "core/audio/media_processor_transcribe_recheck.py",
    ],
    "recheck_ranges": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "common_split": [
        "tools/benchmark_subtitle_pipeline_variants.py",
        "core/engine/subtitle_engine.py",
    ],
    "missing_common_split_groups": [
        "tools/benchmark_subtitle_pipeline_variants.py",
        "core/engine/subtitle_engine.py",
        "core/engine/subtitle_final_integrity.py",
    ],
    "gap_owner_groups": [
        "tools/benchmark_subtitle_pipeline_variants.py",
        "core/engine/subtitle_engine.py",
        "core/engine/subtitle_final_integrity.py",
    ],
    "raw_restore_restore_groups": [
        "core/engine/subtitle_stt_candidate_selection.py",
    ],
    "trim_recent_overlap": [
        "core/engine/subtitle_final_integrity.py",
    ],
    "stt_anchor_guard": [
        "core/engine/subtitle_final_integrity.py",
    ],
    "final_transcript_integrity": [
        "core/engine/subtitle_final_integrity.py",
        "core/engine/subtitle_accuracy_pipeline.py",
    ],
    "output_gap_rows": [
        "core/engine/subtitle_final_integrity.py",
        "core/engine/subtitle_text_policy.py",
    ],
    "reference_gap_rows": [
        "core/engine/subtitle_final_integrity.py",
        "core/engine/subtitle_accuracy_pipeline.py",
    ],
    "major_runtime_transcribe": [
        "core/audio/media_processor_transcribe_run.py",
        "core/audio/stt_backend_router.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "major_runtime_recheck": [
        "core/audio/stt_recheck_service.py",
        "core/audio/media_processor_transcribe_recheck.py",
        "core/audio/media_processor_transcribe_policy.py",
    ],
    "major_runtime_precision": [
        "core/audio/transcribe_policy_helpers.py",
        "core/audio/media_processor_overlap.py",
        "core/audio/media_processor_transcribe_recheck.py",
    ],
    "major_runtime_postprocess": [
        "core/engine/subtitle_engine.py",
        "core/engine/subtitle_final_integrity.py",
    ],
    "major_runtime_release": [
        "core/audio/media_processor.py",
        "core/audio/media_processor_transcribe_run.py",
    ],
}


def _nonzero_delta(value: Any) -> bool:
    try:
        return value is not None and abs(float(value)) > 0.0
    except Exception:
        return False


def _hot_owner_hints_from_runtime_budget_delta(runtime_budget_delta: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    scalar_map = {
        "precision_candidate_count_delta": "precision_candidates",
        "precision_applied_count_delta": "precision_applied",
        "word_precision_overlap_group_count_delta": "precision_overlap_groups",
        "word_precision_non_applied_overlap_group_count_delta": "precision_overlap_groups",
        "word_precision_max_overlap_group_span_sec_delta": "precision_overlap_groups",
        "word_precision_overlap_group_collected_duration_sec_delta": "precision_overlap_groups",
        "word_precision_non_applied_overlap_group_collected_duration_sec_delta": "precision_overlap_groups",
        "word_precision_max_overlap_group_collected_duration_sec_delta": "precision_overlap_groups",
        "recheck_range_count_delta": "recheck_ranges",
        "common_split_output_count_delta": "common_split",
        "missing_common_split_group_count_delta": "missing_common_split_groups",
        "gap_owner_group_count_delta": "gap_owner_groups",
        "raw_restore_restore_group_count_delta": "raw_restore_restore_groups",
        "reference_gap_row_count_delta": "reference_gap_rows",
        "output_gap_row_count_delta": "output_gap_rows",
    }
    for delta_key, hint in scalar_map.items():
        if _nonzero_delta(runtime_budget_delta.get(delta_key)):
            hints.append(hint)

    trim_deltas = dict(runtime_budget_delta.get("trim_recent_overlap_decision_deltas") or {})
    if any(_nonzero_delta(value) for value in trim_deltas.values()):
        hints.append("trim_recent_overlap")
    raw_restore_group_class_deltas = dict(runtime_budget_delta.get("raw_restore_restore_group_class_count_deltas") or {})
    if any(_nonzero_delta(value) for value in raw_restore_group_class_deltas.values()):
        hints.append("raw_restore_restore_groups")
    if _nonzero_delta(runtime_budget_delta.get("stt_anchor_guard_row_count_delta")):
        hints.append("stt_anchor_guard")
    if _nonzero_delta(runtime_budget_delta.get("stt_anchor_guard_trim_row_count_delta")):
        hints.append("stt_anchor_guard")
    if runtime_budget_delta.get("final_transcript_integrity_accepted") != runtime_budget_delta.get(
        "current_final_transcript_integrity_accepted"
    ):
        hints.append("final_transcript_integrity")
    major_phase_deltas = dict(runtime_budget_delta.get("major_runtime_phase_ms_deltas") or {})
    if any(_nonzero_delta(value) for value in major_phase_deltas.values()):
        major_keys = set(major_phase_deltas)
        if any("transcribe" in key for key in major_keys):
            hints.append("major_runtime_transcribe")
        if any("recheck" in key for key in major_keys):
            hints.append("major_runtime_recheck")
        if any("precision" in key for key in major_keys):
            hints.append("major_runtime_precision")
        if any("postprocess" in key for key in major_keys):
            hints.append("major_runtime_postprocess")
        if any("release_runtime_models" in key for key in major_keys):
            hints.append("major_runtime_release")
    selective_phase_deltas = dict(runtime_budget_delta.get("selective_runtime_phase_ms_deltas") or {})
    if any(_nonzero_delta(value) for value in selective_phase_deltas.values()):
        selective_keys = set(selective_phase_deltas)
        if any("collect" in key for key in selective_keys):
            hints.append("major_runtime_transcribe")
        if any("recheck" in key for key in selective_keys):
            hints.append("major_runtime_recheck")
        if any("precision" in key for key in selective_keys):
            hints.append("major_runtime_precision")
        if any("vad_align" in key for key in selective_keys):
            hints.append("major_runtime_postprocess")
    primary_collect_phase_delta = float(
        (dict(runtime_budget_delta.get("selective_runtime_phase_ms_deltas") or {}).get("primary_collect", 0.0) or 0.0)
    )
    primary_collect_submitted_chunk_count = int(runtime_budget_delta.get("primary_collect_submitted_chunk_count") or 0)
    current_primary_collect_submitted_chunk_count = int(
        runtime_budget_delta.get("current_primary_collect_submitted_chunk_count") or 0
    )
    primary_collect_submitted_total_duration_sec_delta = float(
        runtime_budget_delta.get("primary_collect_submitted_total_duration_sec_delta") or 0.0
    )
    primary_collect_completion_latency_delta = float(
        runtime_budget_delta.get("primary_collect_max_completed_chunk_elapsed_ms_delta") or 0.0
    )
    primary_collect_word_precision_runtime_delta = float(
        runtime_budget_delta.get("word_precision_runtime_total_ms_delta") or 0.0
    )
    primary_collect_shape_static = bool(runtime_budget_delta.get("primary_collect_shape_static"))
    primary_collect_state_static = bool(runtime_budget_delta.get("primary_collect_state_static"))
    primary_collect_completion_latency_dominates = bool(
        runtime_budget_delta.get("primary_collect_completion_latency_dominates")
    )
    if (
        abs(primary_collect_phase_delta) >= 1000.0
        and primary_collect_submitted_chunk_count == current_primary_collect_submitted_chunk_count == 1
        and abs(primary_collect_submitted_total_duration_sec_delta) <= 0.001
        and abs(primary_collect_completion_latency_delta) >= 1000.0
    ):
        hints.append("primary_collect_completion_latency")
    word_precision_phase_deltas = dict(runtime_budget_delta.get("word_precision_runtime_phase_ms_deltas") or {})
    if any(_nonzero_delta(value) for value in word_precision_phase_deltas.values()):
        hints.append("major_runtime_precision")
    if _nonzero_delta(runtime_budget_delta.get("word_precision_submission_index_changed_count")):
        hints.append("precision_collect_order")
    accepted_collect_stage = str(runtime_budget_delta.get("word_precision_collect_pressure_stage") or "").strip().lower()
    current_collect_stage = str(runtime_budget_delta.get("current_word_precision_collect_pressure_stage") or "").strip().lower()
    accepted_collect_stage_source = str(
        runtime_budget_delta.get("word_precision_collect_pressure_stage_source") or ""
    ).strip()
    current_collect_stage_source = str(
        runtime_budget_delta.get("current_word_precision_collect_pressure_stage_source") or ""
    ).strip()
    accepted_collect_trigger_reason = str(
        runtime_budget_delta.get("word_precision_collect_pressure_stage_trigger_reason") or ""
    ).strip()
    current_collect_trigger_reason = str(
        runtime_budget_delta.get("current_word_precision_collect_pressure_stage_trigger_reason") or ""
    ).strip()
    current_preexisting_alive_runtime_total_count = int(
        runtime_budget_delta.get("current_word_precision_collect_preexisting_alive_runtime_total_count") or 0
    )
    accepted_preexisting_alive_runtime_total_count = int(
        runtime_budget_delta.get("word_precision_collect_preexisting_alive_runtime_total_count") or 0
    )
    accepted_worker_source = str(runtime_budget_delta.get("word_precision_collect_worker_source") or "").strip()
    current_worker_source = str(runtime_budget_delta.get("current_word_precision_collect_worker_source") or "").strip()
    accepted_reuse_enabled = runtime_budget_delta.get("word_precision_collect_reuse_enabled")
    current_reuse_enabled = runtime_budget_delta.get("current_word_precision_collect_reuse_enabled")
    accepted_pressure_reasons = [
        str(item).strip()
        for item in list(runtime_budget_delta.get("word_precision_collect_pressure_reasons") or [])
        if str(item).strip()
    ]
    current_pressure_reasons = [
        str(item).strip()
        for item in list(runtime_budget_delta.get("current_word_precision_collect_pressure_reasons") or [])
        if str(item).strip()
    ]
    added_pressure_reasons = [
        reason for reason in current_pressure_reasons if reason not in accepted_pressure_reasons
    ]
    removed_pressure_reasons = [
        reason for reason in accepted_pressure_reasons if reason not in current_pressure_reasons
    ]
    collect_segments_delta = float(
        (
            dict(runtime_budget_delta.get("word_precision_runtime_phase_ms_deltas") or {}).get("collect_segments", 0.0)
            or 0.0
        )
    )
    native_collect_state_static = (
        accepted_collect_stage == current_collect_stage
        and accepted_collect_stage == "critical"
        and accepted_collect_stage_source.startswith("native_")
        and current_collect_stage_source == accepted_collect_stage_source
        and accepted_collect_trigger_reason == current_collect_trigger_reason
        and accepted_worker_source == current_worker_source == "transient_child_worker"
        and bool(accepted_reuse_enabled) is False
        and bool(current_reuse_enabled) is False
        and accepted_pressure_reasons == current_pressure_reasons
        and not added_pressure_reasons
        and not removed_pressure_reasons
        and accepted_preexisting_alive_runtime_total_count == 0
        and current_preexisting_alive_runtime_total_count == 0
        and abs(collect_segments_delta) <= 250.0
    )
    if "critical_available_memory_ratio" in added_pressure_reasons:
        hints.append("available_memory_snapshot_volatility")
    if current_collect_stage == "critical" and current_worker_source == "transient_child_worker" and current_preexisting_alive_runtime_total_count > 0:
        hints.append("precollect_worker_residency")
    if (
        current_collect_stage == "critical"
        and current_collect_stage_source.startswith("native_")
        and not native_collect_state_static
    ):
        hints.append("native_pressure_stage_source")
    if runtime_budget_delta.get("current_word_precision_collect_pressure_stage_reason_mismatch"):
        hints.append("pressure_stage_reason_mismatch")
    if accepted_pressure_reasons != current_pressure_reasons and current_pressure_reasons:
        hints.append("critical_pressure_snapshot_thresholds")
    if (
        accepted_collect_stage != current_collect_stage
        or accepted_worker_source != current_worker_source
        or accepted_reuse_enabled != current_reuse_enabled
        or accepted_collect_stage_source != current_collect_stage_source
        or accepted_collect_trigger_reason != current_collect_trigger_reason
        or accepted_pressure_reasons != current_pressure_reasons
    ):
        hints.append("critical_pressure_collect_policy")

    ordered: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        if hint not in seen:
            seen.add(hint)
            ordered.append(hint)
    if (
        primary_collect_shape_static
        and primary_collect_state_static
        and primary_collect_completion_latency_dominates
        and "primary_collect_completion_latency" in ordered
        and abs(primary_collect_completion_latency_delta)
        > max(1000.0, abs(primary_collect_word_precision_runtime_delta))
    ):
        ordered = ["primary_collect_completion_latency"] + [
            hint for hint in ordered if hint != "primary_collect_completion_latency"
        ]
    return ordered


def _owner_file_shortlist_from_hints(hints: list[str]) -> list[dict[str, Any]]:
    file_to_reasons: dict[str, list[str]] = {}
    for hint in hints:
        for path in _OWNER_HINT_FILE_MAP.get(hint, []):
            reasons = file_to_reasons.setdefault(path, [])
            if hint not in reasons:
                reasons.append(hint)
    return [
        {
            "file": path,
            "reasons": reasons,
        }
        for path, reasons in file_to_reasons.items()
    ]


def _case2_specific_overlap_owner_hints_from_experiments(
    recommended_experiments: list[dict[str, Any]],
) -> list[str]:
    allowed = {
        "precision_apply_gate_non_split_owner",
        "collect_path_non_skip_owner",
        "collect_path_non_padding_owner",
    }
    ordered: list[str] = []
    seen: set[str] = set()
    for experiment in recommended_experiments:
        subclips = [
            dict(subclip)
            for subclip in list(experiment.get("recommended_subclips") or [])
            if isinstance(subclip, dict)
        ]
        for subclip in subclips:
            preferred = str(subclip.get("preferred_next_experiment_family") or "").strip()
            if preferred not in allowed or preferred in seen:
                continue
            seen.add(preferred)
            ordered.append(preferred)
            break
    return ordered


def _resolved_next_owner_target_label(target_label: str, winner: dict[str, Any]) -> str:
    normalized_target = str(target_label or "").strip().lower()
    if normalized_target and normalized_target != "artifact":
        return normalized_target
    winner_name = str(winner.get("name") or "").strip().lower()
    if winner_name.startswith("apple_case2_"):
        return "case2"
    if winner_name.startswith("apple_case1_"):
        return "case1"
    return normalized_target


_CASE2_SUBCLIP_REJECTION_HINTS: dict[str, dict[str, Any]] = {
    "80으로 크루즈 컨트롤 걸었고요": {
        "known_rejected_experiment_families": [
            "precision_apply_gate_prefix_tail_split",
            "longer_digit_phrase_collect_padding_restore",
        ],
        "avoid_notes": [
            "prefix-tail split inside the precision apply gate exploded segment churn and collapsed timing quality",
            "restoring collect padding for the longer 80-prefix digit phrase regressed runtime and quality while reintroducing broad segment churn",
        ],
        "preferred_next_experiment_family": "precision_apply_gate_non_split_owner",
    },
    "11.4": {
        "known_rejected_experiment_families": [
            "duplicate_pure_numeric_local_padding_tightening",
            "digit_edge_clip",
            "overlapping_phrase_neighbor_pure_numeric_skip",
            "phrase_linked_pure_numeric_collect_prioritization",
            "precision_edge_shift_threshold_relaxation",
            "edge_safe_alternate_digit_candidate",
            "numeric_spacing_artifact_edge_shift_relaxation",
        ],
        "avoid_notes": [
            "11.4 pure-numeric local padding tightening regressed runtime",
            "digit edge clipping kept the same precision-applied count and reject shape while regressing runtime",
            "11.4 pure-numeric overlap skip was unstable in repeat",
            "phrase-linked pure-numeric collect prioritization did not move live submission order after the swift duration-first offset fix and regressed runtime",
            "broad edge-shift threshold relaxation increased applied precision count but regressed quality/timing and triggered source-preservation rollback",
            "edge-safe alternate digit candidate fallback kept the same precision-applied count and reject shape while regressing runtime",
            "numeric spacing artifact edge-shift relaxation collapsed into source-preservation rollback and broad segment churn",
        ],
        "preferred_next_experiment_family": "collect_path_non_skip_owner",
    },
    "17.8에서 연비가 안 바뀌는데": {
        "known_rejected_experiment_families": [
            "digit_edge_clip",
            "selective_secondary_overlap_precision_skip",
            "metadata_only_long_digit_phrase_skip",
            "metadata_only_long_digit_phrase_local_padding_tightening",
            "long_metadata_only_digit_phrase_collect_defer",
            "long_digit_leading_leftpad",
            "precision_edge_shift_threshold_relaxation",
            "edge_safe_alternate_digit_candidate",
        ],
        "avoid_notes": [
            "digit edge clipping kept the same precision-applied count and reject shape while regressing runtime",
            "selective-secondary overlap precision skip did not reduce prepared precision clips and stayed in the same collect-timeout band",
            "long digit-phrase precision skip was unstable in repeat",
            "long digit-phrase local padding tightening regressed collect runtime",
            "long digit-phrase collect defer moved live submission order after the swift duration-first offset fix but still regressed runtime",
            "long digit-leading left prepad collapsed back into broad segment churn and source-preservation rollback",
            "broad edge-shift threshold relaxation increased applied precision count but regressed quality/timing and triggered source-preservation rollback",
            "edge-safe alternate digit candidate fallback kept the same precision-applied count and reject shape while regressing runtime",
        ],
        "preferred_next_experiment_family": "collect_path_non_padding_owner",
    },
    "계속 17.8인데": {
        "known_rejected_experiment_families": [
            "digit_edge_clip",
            "selective_secondary_overlap_precision_skip",
            "same_numeric_neighbor_short_digit_phrase_skip",
            "short_digit_phrase_collect_prioritization",
            "precision_edge_shift_threshold_relaxation",
            "numeric_core_digit_phrase_edge_shift_salvage",
            "edge_safe_alternate_digit_candidate",
        ],
        "avoid_notes": [
            "digit edge clipping kept the same precision-applied count and reject shape while regressing runtime",
            "selective-secondary overlap precision skip did not reduce prepared precision clips and stayed in the same collect-timeout band",
            "short digit-phrase same-neighbor skip regressed runtime",
            "short digit-phrase collect prioritization looked faster in one-shot after the swift duration-first offset fix but did not change live submission order and made word precision runtime worse",
            "broad edge-shift threshold relaxation increased applied precision count but regressed quality/timing and triggered source-preservation rollback",
            "narrow numeric-core digit-phrase edge-shift salvage applied the intended row but still regressed quality/timing and runtime",
            "edge-safe alternate digit candidate fallback kept the same precision-applied count and reject shape while regressing runtime",
        ],
        "preferred_next_experiment_family": "collect_path_non_skip_owner",
    },
    "유지가 되고 있고요": {
        "known_rejected_experiment_families": [
            "low_vad_nondigit_precision_skip",
            "low_vad_nondigit_collect_defer",
            "low_vad_phrase_full_speech_filter",
            "low_vad_nondigit_collect_tail_padding_restore",
            "precision_edge_shift_threshold_relaxation",
        ],
        "avoid_notes": [
            "broad low-vad nondigit precision skip reduced workload but still regressed runtime",
            "low-vad nondigit collect-defer looked faster in one-shot but did not change live submission order",
            "low-vad phrase full speech filter collapsed back into broad segment churn and source-preservation rollback",
            "low-vad nondigit right-tail padding restore collapsed back into broad segment churn and source-preservation rollback",
            "broad edge-shift threshold relaxation increased applied precision count but regressed quality/timing and triggered source-preservation rollback",
        ],
        "preferred_next_experiment_family": "collect_path_non_skip_owner",
    },
    "변화가 없네": {
        "known_rejected_experiment_families": [
            "low_vad_nondigit_precision_skip",
            "low_vad_nondigit_collect_defer",
            "low_vad_phrase_full_speech_filter",
            "low_vad_nondigit_collect_tail_padding_restore",
            "precision_edge_shift_threshold_relaxation",
        ],
        "avoid_notes": [
            "broad low-vad nondigit precision skip reduced workload but still regressed runtime",
            "low-vad nondigit collect-defer looked faster in one-shot but did not change live submission order",
            "low-vad phrase full speech filter collapsed back into broad segment churn and source-preservation rollback",
            "low-vad nondigit right-tail padding restore collapsed back into broad segment churn and source-preservation rollback",
            "broad edge-shift threshold relaxation increased applied precision count but regressed quality/timing and triggered source-preservation rollback",
        ],
        "preferred_next_experiment_family": "collect_path_non_skip_owner",
    },
}

_CASE2_GLOBAL_REJECTION_HINTS: dict[str, Any] = {
    "known_rejected_experiment_families": [
        "native_pressure_stage_source",
        "critical_pressure_snapshot_thresholds",
        "critical_pressure_collect_policy",
        "precollect_full_cleanup",
        "precollect_vad_release",
        "explicit_precision_model_override",
        "duration_first_submission_off",
        "same_source_chunk_precision_collect_reuse",
        "precision_pass_without_rescue_whisper_worker_options",
    ],
    "avoid_notes": [
        "native pressure snapshot source and threshold retuning have already been narrowed enough; prefer remaining collect-path owners first",
        "critical-pressure collect policy override changed worker path but still regressed collect runtime",
        "pre-collect cleanup or release toggles regressed wallclock badly on case2",
        "explicit precision-model overrides collapsed applied precision or exploded collect runtime",
        "duration-first submission off exploded primary collect wallclock",
        "same-source-chunk precision collect reuse regressed quality and total runtime",
        "precision pass without rescue-whisper worker options made collect slower without score gains",
    ],
}


def _normalized_precision_candidate_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _case2_precision_candidate_truncation_metrics(clip: dict[str, Any]) -> dict[str, float | str] | None:
    if not isinstance(clip, dict):
        return None
    if str(clip.get("precision_reject_reason") or "").strip() != "candidate_edge_shift_exceeded":
        return None
    reject_detail = dict(clip.get("precision_reject_detail") or {})
    candidate_text = str(reject_detail.get("candidate_text") or "").strip()
    primary_text = str(clip.get("primary_text") or "").strip()
    if not candidate_text or not primary_text:
        return None
    normalized_candidate = _normalized_precision_candidate_text(candidate_text)
    normalized_primary = _normalized_precision_candidate_text(primary_text)
    if not normalized_candidate or not normalized_primary:
        return None
    if len(normalized_candidate) >= len(normalized_primary):
        return None
    candidate_ratio = float(len(normalized_candidate)) / float(max(1, len(normalized_primary)))
    if candidate_ratio > 0.7:
        return None
    matched_output_text = str(clip.get("matched_output_text") or "").strip()
    normalized_output = _normalized_precision_candidate_text(matched_output_text)
    output_matches_primary = bool(normalized_output) and normalized_output == normalized_primary
    is_prefix = normalized_primary.startswith(normalized_candidate)
    is_substring = normalized_candidate in normalized_primary
    if not (is_prefix or is_substring):
        return None
    return {
        "candidate_text": candidate_text,
        "candidate_ratio": round(candidate_ratio, 3),
        "is_prefix": "1" if is_prefix else "0",
        "output_matches_primary": "1" if output_matches_primary else "0",
    }


def _case2_precision_candidate_text_artifact_metrics(clip: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(clip, dict):
        return None
    if str(clip.get("precision_reject_reason") or "").strip() != "candidate_edge_shift_exceeded":
        return None
    reject_detail = dict(clip.get("precision_reject_detail") or {})
    candidate_text = str(reject_detail.get("candidate_text") or "").strip()
    primary_text = str(clip.get("primary_text") or "").strip()
    if not candidate_text or not primary_text or candidate_text == primary_text:
        return None
    normalized_candidate = _normalized_precision_candidate_text(candidate_text)
    normalized_primary = _normalized_precision_candidate_text(primary_text)
    if not normalized_candidate or normalized_candidate != normalized_primary:
        return None
    candidate_has_spacing_artifact = bool(re.search(r"\s", candidate_text))
    if not candidate_has_spacing_artifact:
        return None
    matched_output_text = str(clip.get("matched_output_text") or "").strip()
    normalized_output = _normalized_precision_candidate_text(matched_output_text)
    output_matches_primary = bool(normalized_output) and normalized_output == normalized_primary
    return {
        "candidate_text": candidate_text,
        "artifact_kind": "spacing_normalization",
        "output_matches_primary": "1" if output_matches_primary else "0",
    }


def _case2_subclip_rejection_hints(primary_text: Any) -> dict[str, Any]:
    key = str(primary_text or "").strip()
    hints = dict(_CASE2_SUBCLIP_REJECTION_HINTS.get(key) or {})
    families = [
        str(item).strip()
        for item in list(hints.get("known_rejected_experiment_families") or [])
        if str(item).strip()
    ]
    notes = [
        str(item).strip()
        for item in list(hints.get("avoid_notes") or [])
        if str(item).strip()
    ]
    preferred = str(hints.get("preferred_next_experiment_family") or "").strip()
    revalidation_families = [
        str(item).strip()
        for item in list(hints.get("revalidation_candidate_experiment_families") or [])
        if str(item).strip()
    ]
    revalidation_notes = [
        str(item).strip()
        for item in list(hints.get("revalidation_notes") or [])
        if str(item).strip()
    ]
    return {
        "known_rejected_experiment_families": families,
        "avoid_notes": notes,
        "revalidation_candidate_experiment_families": revalidation_families,
        "revalidation_notes": revalidation_notes,
        "preferred_next_experiment_family": preferred,
    }


def _case2_precision_edge_shift_subclip_exhausted(clip_or_primary_text: Any) -> bool:
    clip = dict(clip_or_primary_text) if isinstance(clip_or_primary_text, dict) else {}
    primary_text = clip.get("primary_text") if clip else clip_or_primary_text
    hints = _case2_subclip_rejection_hints(primary_text)
    if list(hints.get("revalidation_candidate_experiment_families") or []):
        return False
    preferred = str(hints.get("preferred_next_experiment_family") or "").strip()
    families = [
        str(item).strip()
        for item in list(hints.get("known_rejected_experiment_families") or [])
        if str(item).strip()
    ]
    if bool(families) and preferred.startswith("collect_path_"):
        return True
    if bool(families) and preferred == "precision_apply_gate_non_split_owner":
        matched_output_text = str(clip.get("matched_output_text") or "").strip()
        primary_text_str = str(primary_text or "").strip()
        reject_detail = dict(clip.get("precision_reject_detail") or {})
        candidate_text = str(reject_detail.get("candidate_text") or "").strip()
        if (
            matched_output_text
            and primary_text_str
            and matched_output_text != primary_text_str
            and candidate_text
        ):
            return True
    return False


def _case2_precision_candidate_text_artifact_subclip_exhausted(clip_or_primary_text: Any) -> bool:
    clip = dict(clip_or_primary_text) if isinstance(clip_or_primary_text, dict) else {}
    primary_text = clip.get("primary_text") if clip else clip_or_primary_text
    hints = _case2_subclip_rejection_hints(primary_text)
    if list(hints.get("revalidation_candidate_experiment_families") or []):
        return False
    families = {
        str(item).strip()
        for item in list(hints.get("known_rejected_experiment_families") or [])
        if str(item).strip()
    }
    preferred = str(hints.get("preferred_next_experiment_family") or "").strip()
    if "numeric_spacing_artifact_edge_shift_relaxation" in families and preferred != "candidate_text_artifact_owner":
        return True
    return False


def _case2_precision_candidate_truncation_subclip_exhausted(clip_or_primary_text: Any) -> bool:
    clip = dict(clip_or_primary_text) if isinstance(clip_or_primary_text, dict) else {}
    primary_text = clip.get("primary_text") if clip else clip_or_primary_text
    hints = _case2_subclip_rejection_hints(primary_text)
    if list(hints.get("revalidation_candidate_experiment_families") or []):
        return False
    families = {
        str(item).strip()
        for item in list(hints.get("known_rejected_experiment_families") or [])
        if str(item).strip()
    }
    preferred = str(hints.get("preferred_next_experiment_family") or "").strip()
    if families and preferred not in {"", "candidate_truncation_owner", "collect_path_candidate_truncation_owner"}:
        return True
    return False


def _case2_global_rejection_hints() -> dict[str, Any]:
    families = [
        str(item).strip()
        for item in list(_CASE2_GLOBAL_REJECTION_HINTS.get("known_rejected_experiment_families") or [])
        if str(item).strip()
    ]
    notes = [
        str(item).strip()
        for item in list(_CASE2_GLOBAL_REJECTION_HINTS.get("avoid_notes") or [])
        if str(item).strip()
    ]
    return {
        "known_rejected_experiment_families": families,
        "avoid_notes": notes,
    }


def _next_owner_hints_from_summary(target_label: str, winner: dict[str, Any]) -> list[str]:
    budget = dict(winner.get("runtime_stage_budget") or {})
    hints: list[str] = []
    normalized_target = _resolved_next_owner_target_label(target_label, winner)
    if normalized_target == "case2":
        global_rejection_hints = _case2_global_rejection_hints()
        rejected_global_families = {
            str(item).strip()
            for item in list(global_rejection_hints.get("known_rejected_experiment_families") or [])
            if str(item).strip()
        }
        collect_pressure_stage = str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower()
        collect_worker_source = str(budget.get("word_precision_collect_worker_source") or "").strip()
        collect_pressure_reasons = [
            str(item).strip()
            for item in list(budget.get("word_precision_collect_pressure_reasons") or [])
            if str(item).strip()
        ]
        preexisting_alive_runtime_total_count = int(
            budget.get("word_precision_collect_preexisting_alive_runtime_total_count") or 0
        )
        collect_pressure_stage_source = str(
            budget.get("word_precision_collect_pressure_stage_source") or ""
        ).strip()
        collect_pressure_reason_mismatch = bool(
            budget.get("word_precision_collect_pressure_stage_reason_mismatch")
        )
        primary_collect_ms = float(dict(budget.get("selective_runtime_ms_by_phase") or {}).get("primary_collect", 0.0) or 0.0)
        secondary_recheck_ms = float(
            dict(budget.get("selective_runtime_ms_by_phase") or {}).get("secondary_low_score_recheck", 0.0) or 0.0
        )
        word_precision_ms = float(
            dict(budget.get("selective_runtime_ms_by_phase") or {}).get("word_precision_recheck", 0.0) or 0.0
        )
        primary_collect_submitted_chunk_count = int(budget.get("primary_collect_submitted_chunk_count") or 0)
        primary_collect_submitted_total_duration_sec = float(
            budget.get("primary_collect_submitted_total_duration_sec", 0.0) or 0.0
        )
        primary_collect_max_completed_chunk_elapsed_ms = float(
            budget.get("primary_collect_max_completed_chunk_elapsed_ms", 0.0) or 0.0
        )
        primary_collect_dominant = (
            primary_collect_ms > 0.0
            and primary_collect_ms >= max(word_precision_ms * 2.0, secondary_recheck_ms * 4.0, 10000.0)
        )
        if primary_collect_dominant:
            hints.append("primary_collect_path")
            if (
                primary_collect_submitted_chunk_count == 1
                and primary_collect_submitted_total_duration_sec > 0.0
                and primary_collect_max_completed_chunk_elapsed_ms > 0.0
            ):
                hints.append("primary_collect_completion_latency")
            hints.append("major_runtime_transcribe")
        overlap_groups = [
            dict(item)
            for item in list(winner.get("artifact_word_precision_overlap_groups") or [])
            if isinstance(item, dict)
        ]
        non_applied_reject_roles = [
            dict(clip)
            for group in overlap_groups
            for clip in list((group or {}).get("clip_roles") or [])
            if isinstance(clip, dict)
            and not bool(clip.get("likely_applied"))
            and str(clip.get("precision_reject_reason") or "").strip()
        ]
        reject_reason_counts: dict[str, int] = {}
        for clip in non_applied_reject_roles:
            reason = str(clip.get("precision_reject_reason") or "").strip()
            if not reason:
                continue
            reject_reason_counts[reason] = reject_reason_counts.get(reason, 0) + 1
        viable_edge_shift_roles = [
            dict(clip)
            for clip in non_applied_reject_roles
            if str(clip.get("precision_reject_reason") or "").strip() == "candidate_edge_shift_exceeded"
            and not _case2_precision_edge_shift_subclip_exhausted(clip)
        ]
        viable_candidate_truncation_roles = [
            dict(clip)
            for clip in non_applied_reject_roles
            if (metrics := _case2_precision_candidate_truncation_metrics(clip)) is not None
            and metrics.get("output_matches_primary") == "1"
            and not _case2_precision_candidate_truncation_subclip_exhausted(clip)
        ]
        viable_candidate_text_artifact_roles = [
            dict(clip)
            for clip in non_applied_reject_roles
            if (metrics := _case2_precision_candidate_text_artifact_metrics(clip)) is not None
            and metrics.get("output_matches_primary") == "1"
            and not _case2_precision_candidate_text_artifact_subclip_exhausted(clip)
        ]
        dominant_reject_reason = ""
        dominant_reject_count = 0
        if reject_reason_counts:
            dominant_reject_reason, dominant_reject_count = max(
                reject_reason_counts.items(),
                key=lambda item: (int(item[1]), str(item[0])),
            )
        overlap_groups_have_collected_burden = bool(overlap_groups) and any(
            float((group or {}).get("non_applied_collected_total_duration_sec", 0.0) or 0.0) > 0.0
            for group in overlap_groups
        )
        if (
            collect_pressure_stage == "critical"
            and collect_worker_source == "transient_child_worker"
            and preexisting_alive_runtime_total_count > 0
        ):
            hints.append("precollect_worker_residency")
        if (
            not primary_collect_dominant
            and
            collect_pressure_stage == "critical"
            and collect_pressure_stage_source.startswith("native_")
            and "native_pressure_stage_source" not in rejected_global_families
        ):
            hints.append("native_pressure_stage_source")
        if (
            collect_pressure_reason_mismatch
            and collect_pressure_stage == "warning"
            and "critical_available_memory_ratio" in collect_pressure_reasons
        ):
            hints.append("available_memory_snapshot_volatility")
        if collect_pressure_reason_mismatch:
            hints.append("pressure_stage_reason_mismatch")
        if (
            not primary_collect_dominant
            and
            collect_pressure_stage == "critical"
            and collect_pressure_reasons
            and "critical_pressure_snapshot_thresholds" not in rejected_global_families
        ):
            hints.extend(["critical_pressure_snapshot_thresholds", "major_runtime_precision"])
        secondary_recheck_range_count = int(budget.get("secondary_recheck_range_count") or 0)
        secondary_recheck_applied_range_count = int(budget.get("secondary_recheck_applied_range_count") or 0)
        if (
            secondary_recheck_ms > 0.0
            and secondary_recheck_range_count > 0
            and secondary_recheck_applied_range_count > 0
            and secondary_recheck_ms >= max(1000.0, word_precision_ms * 0.1)
        ):
            hints.extend(["secondary_recheck_path", "major_runtime_recheck"])
        if (
            overlap_groups_have_collected_burden
            and int(budget.get("word_precision_non_applied_overlap_group_count") or 0) > 0
        ):
            if viable_candidate_text_artifact_roles:
                hints.append("precision_candidate_text_artifact")
            if viable_candidate_truncation_roles:
                hints.append("precision_candidate_truncation")
            if (
                dominant_reject_reason == "candidate_edge_shift_exceeded"
                and viable_edge_shift_roles
            ):
                hints.append("precision_apply_gate_edge_shift")
            hints.extend(["precision_overlap_groups", "major_runtime_precision"])
            if (
                "critical_pressure_collect_policy" not in rejected_global_families
                and
                collect_pressure_stage == "critical"
                and str(budget.get("slowest_word_precision_phase_name") or "").strip().lower() == "collect_segments"
                and collect_worker_source == "transient_child_worker"
            ):
                hints.append("critical_pressure_collect_policy")
        elif (
            "critical_pressure_collect_policy" not in rejected_global_families
            and
            collect_pressure_stage == "critical"
            and str(budget.get("slowest_word_precision_phase_name") or "").strip().lower() == "collect_segments"
            and collect_worker_source == "transient_child_worker"
        ):
            hints.extend(["critical_pressure_collect_policy", "major_runtime_precision"])
        elif int(budget.get("word_precision_non_applied_overlap_group_count") or 0) > 0:
            hints.extend(["precision_overlap_groups", "major_runtime_precision"])
        elif int(budget.get("precision_candidate_count") or 0) > int(budget.get("precision_applied_count") or 0):
            hints.extend(["precision_candidates", "major_runtime_precision"])
        elif int(budget.get("recheck_range_count") or 0) > 0:
            hints.extend(["recheck_ranges", "major_runtime_recheck"])
    elif normalized_target == "case1":
        if int(budget.get("missing_common_split_group_count") or 0) > 0:
            hints.extend(["missing_common_split_groups", "common_split"])
        if int(budget.get("gap_owner_group_count") or 0) > 0:
            hints.extend(["output_gap_rows", "reference_gap_rows"])
        if int(budget.get("raw_restore_restore_group_count") or 0) > 0:
            hints.append("raw_restore_restore_groups")

    if not hints:
        major_phase = str(budget.get("slowest_major_phase_name") or "").strip().lower()
        word_precision_phase = str(budget.get("slowest_word_precision_phase_name") or "").strip().lower()
        if "precision" in major_phase or "collect" in word_precision_phase:
            hints.append("major_runtime_precision")
        elif "recheck" in major_phase:
            hints.append("major_runtime_recheck")
        elif "transcribe" in major_phase:
            hints.append("major_runtime_transcribe")
        else:
            hints.append("major_runtime_postprocess")

    ordered: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        if hint and hint not in seen:
            seen.add(hint)
            ordered.append(hint)
    return ordered


def _next_owner_plan_payload(target_label: str, summary_payload: dict[str, Any]) -> dict[str, Any]:
    winner = dict(summary_payload.get("winner") or {})
    budget = dict(winner.get("runtime_stage_budget") or {})
    hints = _next_owner_hints_from_summary(target_label, winner)
    global_rejection_hints = _case2_global_rejection_hints()
    overlap_groups = [
        dict(item)
        for item in list(winner.get("artifact_word_precision_overlap_groups") or [])
        if isinstance(item, dict)
    ]
    non_applied_reject_roles = [
        dict(clip)
        for group in overlap_groups
        for clip in list((group or {}).get("clip_roles") or [])
        if isinstance(clip, dict)
        and not bool(clip.get("likely_applied"))
        and str(clip.get("precision_reject_reason") or "").strip()
    ]
    reject_reason_counts: dict[str, int] = {}
    for clip in non_applied_reject_roles:
        reason = str(clip.get("precision_reject_reason") or "").strip()
        if not reason:
            continue
        reject_reason_counts[reason] = reject_reason_counts.get(reason, 0) + 1
    candidate_truncation_roles = [
        dict(clip)
        for clip in non_applied_reject_roles
        if (metrics := _case2_precision_candidate_truncation_metrics(clip)) is not None
        and metrics.get("output_matches_primary") == "1"
        and not _case2_precision_candidate_truncation_subclip_exhausted(clip)
    ]
    candidate_text_artifact_roles = [
        dict(clip)
        for clip in non_applied_reject_roles
        if (metrics := _case2_precision_candidate_text_artifact_metrics(clip)) is not None
        and metrics.get("output_matches_primary") == "1"
        and not _case2_precision_candidate_text_artifact_subclip_exhausted(clip)
    ]
    dominant_reject_reason = ""
    dominant_reject_count = 0
    if reject_reason_counts:
        dominant_reject_reason, dominant_reject_count = max(
            reject_reason_counts.items(),
            key=lambda item: (int(item[1]), str(item[0])),
        )
    low_yield_clip_rows = _artifact_word_precision_low_yield_clip_rows(overlap_groups)
    primary_recheck_rows = dict(winner.get("artifact_primary_recheck_plan_rows") or {})
    recommended_experiments: list[dict[str, Any]] = []
    preconditions: list[dict[str, Any]] = []
    normalized_target = _resolved_next_owner_target_label(target_label, winner)
    overlap_groups_missing_collected_burden = bool(overlap_groups) and all(
        float((group or {}).get("non_applied_collected_total_duration_sec", 0.0) or 0.0) <= 0.0
        for group in overlap_groups
    )
    overlap_groups_have_collected_burden = bool(overlap_groups) and any(
        float((group or {}).get("non_applied_collected_total_duration_sec", 0.0) or 0.0) > 0.0
        for group in overlap_groups
    )
    collect_pressure_reasons = [
        str(item).strip()
        for item in list(budget.get("word_precision_collect_pressure_reasons") or [])
        if str(item).strip()
    ]
    preexisting_alive_runtime_total_count = int(
        budget.get("word_precision_collect_preexisting_alive_runtime_total_count") or 0
    )
    collect_pressure_stage_source = str(
        budget.get("word_precision_collect_pressure_stage_source") or ""
    ).strip()
    collect_pressure_reason_stage = str(
        budget.get("word_precision_collect_pressure_reason_stage") or ""
    ).strip().lower()
    collect_pressure_reason_mismatch = bool(
        budget.get("word_precision_collect_pressure_stage_reason_mismatch")
    )
    collect_pressure_reason_mismatch_kind = str(
        budget.get("word_precision_collect_pressure_stage_reason_mismatch_kind") or ""
    ).strip()

    if normalized_target == "case2" and overlap_groups_missing_collected_burden:
        preconditions.append(
            {
                "id": "refresh_case2_collect_instrumentation",
                "why": "accepted artifact predates collected-duration overlap instrumentation, so cluster ordering is still fallback-only",
                "command": "./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py --variants apple_case2_high_selective_timing_priority --media 'test video/X5_시승기_후반.MP4' --reference-srt 'test video/X5_시승기_후반.srt' --start-sec 0 --duration-sec 30 --ranking-policy timing_priority_speed_weighted",
                "guardrails": [
                    "run_alone",
                    "no_parallel_repeats",
                    "no_ui_no_ux",
                ],
            }
        )

    if normalized_target == "case2" and overlap_groups_have_collected_burden:
        rejected_global_families = {
            str(item).strip()
            for item in list(global_rejection_hints.get("known_rejected_experiment_families") or [])
            if str(item).strip()
        }
        primary_collect_ms = float(dict(budget.get("selective_runtime_ms_by_phase") or {}).get("primary_collect", 0.0) or 0.0)
        secondary_recheck_ms = float(
            dict(budget.get("selective_runtime_ms_by_phase") or {}).get("secondary_low_score_recheck", 0.0) or 0.0
        )
        word_precision_ms = float(
            dict(budget.get("selective_runtime_ms_by_phase") or {}).get("word_precision_recheck", 0.0) or 0.0
        )
        primary_collect_submitted_chunk_count = int(budget.get("primary_collect_submitted_chunk_count") or 0)
        primary_collect_submitted_total_duration_sec = float(
            budget.get("primary_collect_submitted_total_duration_sec", 0.0) or 0.0
        )
        primary_collect_max_completed_chunk_elapsed_ms = float(
            budget.get("primary_collect_max_completed_chunk_elapsed_ms", 0.0) or 0.0
        )
        primary_collect_max_emitted_chunk_elapsed_ms = float(
            budget.get("primary_collect_max_emitted_chunk_elapsed_ms", 0.0) or 0.0
        )
        primary_collect_dominant = (
            primary_collect_ms > 0.0
            and primary_collect_ms >= max(word_precision_ms * 2.0, secondary_recheck_ms * 4.0, 10000.0)
        )
        if primary_collect_dominant:
            recommended_experiments.append(
                {
                    "id": "case2_primary_collect_path",
                    "focus": "primary_collect_path",
                    "primary_collect_elapsed_ms": round(primary_collect_ms, 3),
                    "secondary_low_score_recheck_elapsed_ms": round(secondary_recheck_ms, 3),
                    "word_precision_elapsed_ms": round(word_precision_ms, 3),
                    "primary_collect_pressure_stage": budget.get("primary_collect_pressure_stage"),
                    "primary_collect_worker_source": budget.get("primary_collect_worker_source"),
                    "primary_collect_reuse_enabled": budget.get("primary_collect_reuse_enabled"),
                    "primary_collect_duration_first_submission_enabled": budget.get(
                        "primary_collect_duration_first_submission_enabled"
                    ),
                    "primary_collect_submitted_chunk_count": primary_collect_submitted_chunk_count,
                    "primary_collect_submitted_total_duration_sec": round(
                        primary_collect_submitted_total_duration_sec,
                        3,
                    ),
                    "primary_collect_preexisting_alive_runtime_total_count": budget.get(
                        "primary_collect_preexisting_alive_runtime_total_count"
                    ),
                    "primary_collect_pressure_stage_source": budget.get("primary_collect_pressure_stage_source"),
                    "primary_collect_pressure_stage_trigger_reason": budget.get(
                        "primary_collect_pressure_stage_trigger_reason"
                    ),
                    "primary_collect_max_completed_chunk_elapsed_ms": round(
                        primary_collect_max_completed_chunk_elapsed_ms,
                        3,
                    ),
                    "primary_collect_max_emitted_chunk_elapsed_ms": round(
                        primary_collect_max_emitted_chunk_elapsed_ms,
                        3,
                    ),
                    "primary_collect_active_backend": budget.get("primary_collect_active_backend"),
                    "primary_collect_active_model": budget.get("primary_collect_active_model"),
                    "primary_collect_active_reason": budget.get("primary_collect_active_reason"),
                    "primary_collect_challenger_count": budget.get("primary_collect_challenger_count"),
                    "primary_collect_vad_challenger_provider": budget.get(
                        "primary_collect_vad_challenger_provider"
                    ),
                    "known_rejected_experiment_families": [
                        "critical_pressure_collect_policy",
                        "apple_case2_relax_compressed_memory_thresholds_for_precision_collect",
                        "case2_single_snapshot_collect_pressure_decision",
                        "case2_exact_mlx_primary_route_override",
                    ],
                    "guardrails": [
                        "diagnostic_first",
                        "no_ui_no_ux",
                        "primary_collect_only",
                        "do_not_reopen_rejected_native_pressure_threshold_branch_first",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if (
            str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower() == "critical"
            and str(budget.get("word_precision_collect_worker_source") or "").strip() == "transient_child_worker"
            and preexisting_alive_runtime_total_count > 0
        ):
            recommended_experiments.append(
                {
                    "id": "case2_precollect_worker_residency",
                    "focus": "precollect_worker_residency",
                    "collect_pressure_stage": budget.get("word_precision_collect_pressure_stage"),
                    "collect_worker_source": budget.get("word_precision_collect_worker_source"),
                    "collect_pressure_stage_source": collect_pressure_stage_source,
                    "preexisting_alive_runtime_total_count": preexisting_alive_runtime_total_count,
                    "preexisting_alive_owner_runtime_count": budget.get(
                        "word_precision_collect_preexisting_alive_owner_runtime_count"
                    ),
                    "preexisting_alive_child_runtime_count": budget.get(
                        "word_precision_collect_preexisting_alive_child_runtime_count"
                    ),
                    "preexisting_alive_cached_worker_count": budget.get(
                        "word_precision_collect_preexisting_alive_cached_worker_count"
                    ),
                    "preexisting_child_processor_count": budget.get(
                        "word_precision_collect_preexisting_child_processor_count"
                    ),
                    "preexisting_cached_worker_count": budget.get(
                        "word_precision_collect_preexisting_cached_worker_count"
                    ),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_owner_only",
                        "sequential_repeat_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if (
            not primary_collect_dominant
            and
            str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower() == "critical"
            and collect_pressure_stage_source.startswith("native_")
            and "native_pressure_stage_source" not in rejected_global_families
        ):
            recommended_experiments.append(
                {
                    "id": "case2_native_pressure_snapshot_source",
                    "focus": "native_pressure_stage_source",
                    "collect_pressure_stage": budget.get("word_precision_collect_pressure_stage"),
                    "collect_pressure_stage_source": collect_pressure_stage_source,
                    "collect_pressure_stage_trigger_reason": budget.get(
                        "word_precision_collect_pressure_stage_trigger_reason"
                    ),
                    "collect_pressure_reasons": collect_pressure_reasons,
                    "collect_available_memory_ratio": budget.get("word_precision_collect_available_memory_ratio"),
                    "collect_available_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_available_memory_critical_ratio_threshold"
                    ),
                    "collect_available_memory_critical_headroom": budget.get(
                        "word_precision_collect_available_memory_critical_headroom"
                    ),
                    "collect_compressed_memory_ratio": budget.get("word_precision_collect_compressed_memory_ratio"),
                    "collect_compressed_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_compressed_memory_critical_ratio_threshold"
                    ),
                    "collect_compressed_memory_critical_headroom": budget.get(
                        "word_precision_collect_compressed_memory_critical_headroom"
                    ),
                    "collect_process_rss_bytes": budget.get("word_precision_collect_process_rss_bytes"),
                    "known_rejected_experiment_families": [
                        "critical_pressure_collect_policy",
                        "apple_case2_relax_compressed_memory_thresholds_for_precision_collect",
                        "case2_single_snapshot_collect_pressure_decision",
                    ],
                    "guardrails": [
                        "diagnostic_first",
                        "no_ui_no_ux",
                        "native_snapshot_pipeline_only",
                        "do_not_relax_thresholds_first",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if (not primary_collect_dominant) and collect_pressure_reason_mismatch:
            mismatch_experiment_id = "case2_collect_pressure_stage_reason_mismatch"
            mismatch_focus = "pressure_stage_reason_mismatch"
            mismatch_guardrails = [
                "diagnostic_first",
                "no_ui_no_ux",
                "snapshot_vs_stage_consistency_only",
                "do_not_force_warning_policy_directly",
                "do_not_remove_existing_algorithms",
            ]
            mismatch_known_rejected = [
                "critical_pressure_collect_policy",
                "apple_case2_allow_critical_keep_warm_and_collect_reuse",
                "apple_case2_relax_compressed_memory_thresholds_for_precision_collect",
            ]
            if (
                str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower() == "warning"
                and "critical_available_memory_ratio" in collect_pressure_reasons
            ):
                mismatch_experiment_id = "case2_collect_available_memory_snapshot"
                mismatch_focus = "available_memory_snapshot_volatility"
            recommended_experiments.append(
                {
                    "id": mismatch_experiment_id,
                    "focus": mismatch_focus,
                    "collect_pressure_stage": budget.get("word_precision_collect_pressure_stage"),
                    "collect_pressure_stage_source": collect_pressure_stage_source,
                    "collect_pressure_stage_trigger_reason": budget.get(
                        "word_precision_collect_pressure_stage_trigger_reason"
                    ),
                    "collect_pressure_reason_stage": collect_pressure_reason_stage,
                    "collect_pressure_reason_mismatch_kind": collect_pressure_reason_mismatch_kind,
                    "collect_worker_source": budget.get("word_precision_collect_worker_source"),
                    "collect_pressure_reasons": collect_pressure_reasons,
                    "collect_available_memory_ratio": budget.get("word_precision_collect_available_memory_ratio"),
                    "collect_available_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_available_memory_critical_ratio_threshold"
                    ),
                    "collect_available_memory_critical_headroom": budget.get(
                        "word_precision_collect_available_memory_critical_headroom"
                    ),
                    "collect_compressed_memory_ratio": budget.get("word_precision_collect_compressed_memory_ratio"),
                    "collect_compressed_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_compressed_memory_critical_ratio_threshold"
                    ),
                    "collect_compressed_memory_critical_headroom": budget.get(
                        "word_precision_collect_compressed_memory_critical_headroom"
                    ),
                    "collect_process_rss_bytes": budget.get("word_precision_collect_process_rss_bytes"),
                    "known_rejected_experiment_families": mismatch_known_rejected,
                    "guardrails": mismatch_guardrails,
                }
            )
        if (
            not primary_collect_dominant
            and
            str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower() == "critical"
            and collect_pressure_reasons
            and "critical_pressure_snapshot_thresholds" not in rejected_global_families
        ):
            recommended_experiments.append(
                {
                    "id": "case2_collect_pressure_thresholds",
                    "focus": "critical_pressure_snapshot_thresholds",
                    "collect_pressure_stage": budget.get("word_precision_collect_pressure_stage"),
                    "collect_pressure_stage_source": collect_pressure_stage_source,
                    "collect_pressure_stage_trigger_reason": budget.get(
                        "word_precision_collect_pressure_stage_trigger_reason"
                    ),
                    "collect_worker_source": budget.get("word_precision_collect_worker_source"),
                    "collect_owner_type": budget.get("word_precision_collect_owner_type"),
                    "collect_reuse_enabled": budget.get("word_precision_collect_reuse_enabled"),
                    "collect_allow_worker_reuse": budget.get("word_precision_collect_allow_worker_reuse"),
                    "collect_pressure_reasons": collect_pressure_reasons,
                    "collect_available_memory_ratio": budget.get("word_precision_collect_available_memory_ratio"),
                    "collect_available_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_available_memory_critical_ratio_threshold"
                    ),
                    "collect_available_memory_critical_headroom": budget.get(
                        "word_precision_collect_available_memory_critical_headroom"
                    ),
                    "collect_compressed_memory_ratio": budget.get("word_precision_collect_compressed_memory_ratio"),
                    "collect_compressed_memory_critical_ratio_threshold": budget.get(
                        "word_precision_collect_compressed_memory_critical_ratio_threshold"
                    ),
                    "collect_compressed_memory_critical_headroom": budget.get(
                        "word_precision_collect_compressed_memory_critical_headroom"
                    ),
                    "collect_process_rss_bytes": budget.get("word_precision_collect_process_rss_bytes"),
                    "known_rejected_experiment_families": [
                        "critical_pressure_collect_policy",
                        "apple_case2_allow_critical_keep_warm_and_collect_reuse",
                        "apple_case2_precision_allow_critical_concurrency",
                    ],
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "thresholds_or_snapshot_only",
                        "do_not_force_warning_policy_directly",
                        "sequential_repeat_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        cluster_experiments: list[dict[str, Any]] = []
        if candidate_text_artifact_roles:
            top_text_artifact_roles = sorted(
                candidate_text_artifact_roles,
                key=lambda clip: (
                    -float((clip.get("completed_chunk_elapsed_ms") or 0.0) or 0.0),
                    float((clip.get("collected_duration_ratio") or 1.0) or 1.0),
                    str(clip.get("primary_text") or ""),
                ),
            )[:3]
            recommended_experiments.append(
                {
                    "id": "case2_precision_candidate_text_artifact",
                    "focus": "word_precision_collect_path",
                    "selection_rule": "normalized_candidate_matches_primary_but_spacing_differs",
                    "recommended_subclips": [
                        {
                            "id": f"case2_precision_candidate_text_artifact_subclip_{index}",
                            "focus": "word_precision_collect_subclip",
                            "experiment_type": "candidate_text_artifact_subclip",
                            "primary_text": clip.get("primary_text"),
                            "start": clip.get("start"),
                            "end": clip.get("end"),
                            "duration_sec": clip.get("duration_sec"),
                            "matched_output_text": clip.get("matched_output_text"),
                            "precision_reject_reason": clip.get("precision_reject_reason"),
                            "precision_reject_detail": clip.get("precision_reject_detail"),
                            "candidate_text": (_case2_precision_candidate_text_artifact_metrics(clip) or {}).get(
                                "candidate_text"
                            ),
                            "artifact_kind": (_case2_precision_candidate_text_artifact_metrics(clip) or {}).get(
                                "artifact_kind"
                            ),
                            "output_matches_primary": (
                                (_case2_precision_candidate_text_artifact_metrics(clip) or {}).get(
                                    "output_matches_primary"
                                )
                                == "1"
                            ),
                            "submission_index": clip.get("submission_index"),
                            "submitted_chunk_duration_sec": clip.get("submitted_chunk_duration_sec"),
                            "submitted_chunk_offset_sec": clip.get("submitted_chunk_offset_sec"),
                            "completion_order_index": clip.get("completion_order_index"),
                            "completed_chunk_elapsed_ms": clip.get("completed_chunk_elapsed_ms"),
                            "emission_order_index": clip.get("emission_order_index"),
                            "emitted_chunk_elapsed_ms": clip.get("emitted_chunk_elapsed_ms"),
                            "duration_first_submission_enabled": clip.get("duration_first_submission_enabled"),
                            "collected_total_duration_sec": clip.get("collected_total_duration_sec"),
                            "collected_duration_ratio": clip.get("collected_duration_ratio"),
                            "known_rejected_experiment_families": list(
                                (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                    "known_rejected_experiment_families"
                                )
                                or []
                            ),
                            "preferred_next_experiment_family": "candidate_text_artifact_owner",
                            "guardrails": [
                                "diagnostic_first",
                                "additive_only",
                                "no_ui_no_ux",
                                "single_subclip_only",
                                "do_not_remove_existing_algorithms",
                            ],
                        }
                        for index, clip in enumerate(top_text_artifact_roles, start=1)
                    ],
                    "known_rejected_experiment_families": sorted(
                        {
                            str(item).strip()
                            for clip in top_text_artifact_roles
                            for item in list(
                                (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                    "known_rejected_experiment_families"
                                )
                                or []
                            )
                            if str(item).strip()
                        }
                    ),
                    "guardrails": [
                        "diagnostic_first",
                        "additive_only",
                        "no_ui_no_ux",
                        "single_owner_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if candidate_truncation_roles:
            top_truncation_roles = sorted(
                candidate_truncation_roles,
                key=lambda clip: (
                    float((_case2_precision_candidate_truncation_metrics(clip) or {}).get("candidate_ratio") or 1.0),
                    float((clip.get("collected_duration_ratio") or 1.0) or 1.0),
                    -float((clip.get("completed_chunk_elapsed_ms") or 0.0) or 0.0),
                ),
            )[:3]
            recommended_experiments.append(
                {
                    "id": "case2_precision_candidate_truncation",
                    "focus": "word_precision_collect_path",
                    "selection_rule": "short_candidate_text_vs_primary",
                    "recommended_subclips": [
                        {
                            "id": f"case2_precision_candidate_truncation_subclip_{index}",
                            "focus": "word_precision_collect_subclip",
                            "experiment_type": "candidate_truncation_subclip",
                            "primary_text": clip.get("primary_text"),
                            "start": clip.get("start"),
                            "end": clip.get("end"),
                            "duration_sec": clip.get("duration_sec"),
                            "matched_output_text": clip.get("matched_output_text"),
                            "precision_reject_reason": clip.get("precision_reject_reason"),
                            "precision_reject_detail": clip.get("precision_reject_detail"),
                            "candidate_text": (_case2_precision_candidate_truncation_metrics(clip) or {}).get(
                                "candidate_text"
                            ),
                            "candidate_ratio": (_case2_precision_candidate_truncation_metrics(clip) or {}).get(
                                "candidate_ratio"
                            ),
                            "candidate_prefix_like": (
                                (_case2_precision_candidate_truncation_metrics(clip) or {}).get("is_prefix") == "1"
                            ),
                            "output_matches_primary": (
                                (_case2_precision_candidate_truncation_metrics(clip) or {}).get("output_matches_primary")
                                == "1"
                            ),
                            "submission_index": clip.get("submission_index"),
                            "submitted_chunk_duration_sec": clip.get("submitted_chunk_duration_sec"),
                            "submitted_chunk_offset_sec": clip.get("submitted_chunk_offset_sec"),
                            "completion_order_index": clip.get("completion_order_index"),
                            "completed_chunk_elapsed_ms": clip.get("completed_chunk_elapsed_ms"),
                            "emission_order_index": clip.get("emission_order_index"),
                            "emitted_chunk_elapsed_ms": clip.get("emitted_chunk_elapsed_ms"),
                            "duration_first_submission_enabled": clip.get("duration_first_submission_enabled"),
                            "collected_total_duration_sec": clip.get("collected_total_duration_sec"),
                            "collected_duration_ratio": clip.get("collected_duration_ratio"),
                            "known_rejected_experiment_families": list(
                                (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                    "known_rejected_experiment_families"
                                )
                                or []
                            ),
                            "preferred_next_experiment_family": str(
                                (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                    "preferred_next_experiment_family"
                                )
                                or "collect_path_candidate_truncation_owner"
                            ),
                            "guardrails": [
                                "diagnostic_first",
                                "additive_only",
                                "no_ui_no_ux",
                                "single_subclip_only",
                                "do_not_remove_existing_algorithms",
                            ],
                        }
                        for index, clip in enumerate(top_truncation_roles, start=1)
                    ],
                    "known_rejected_experiment_families": sorted(
                        {
                            str(item).strip()
                            for clip in top_truncation_roles
                            for item in list(
                                (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                    "known_rejected_experiment_families"
                                )
                                or []
                            )
                            if str(item).strip()
                        }
                    ),
                    "guardrails": [
                        "diagnostic_first",
                        "additive_only",
                        "no_ui_no_ux",
                        "single_subclip_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if dominant_reject_reason == "candidate_edge_shift_exceeded":
            top_edge_shift_roles = sorted(
                non_applied_reject_roles,
                key=lambda clip: (
                    -float((clip.get("completed_chunk_elapsed_ms") or 0.0) or 0.0),
                    -float((clip.get("collected_total_duration_sec") or 0.0) or 0.0),
                    -float((clip.get("duration_sec") or 0.0) or 0.0),
                ),
            )[:3]
            viable_top_edge_shift_roles = [
                dict(clip)
                for clip in top_edge_shift_roles
                if not _case2_precision_edge_shift_subclip_exhausted(clip)
            ]
            if viable_top_edge_shift_roles:
                recommended_experiments.append(
                    {
                        "id": "case2_precision_edge_shift_gate",
                        "focus": "precision_apply_gate_edge_shift",
                        "dominant_reject_reason": dominant_reject_reason,
                        "dominant_reject_count": dominant_reject_count,
                        "reject_reason_counts": reject_reason_counts,
                        "recommended_subclips": [
                            {
                                "id": f"case2_precision_edge_shift_subclip_{index}",
                                "focus": "word_precision_apply_gate",
                                "experiment_type": "edge_shift_threshold_subclip",
                                "primary_text": clip.get("primary_text"),
                                "start": clip.get("start"),
                                "end": clip.get("end"),
                                "duration_sec": clip.get("duration_sec"),
                                "matched_output_text": clip.get("matched_output_text"),
                                "precision_reject_reason": clip.get("precision_reject_reason"),
                                "precision_reject_detail": clip.get("precision_reject_detail"),
                                "completed_chunk_elapsed_ms": clip.get("completed_chunk_elapsed_ms"),
                                "submitted_chunk_duration_sec": clip.get("submitted_chunk_duration_sec"),
                                "submitted_chunk_offset_sec": clip.get("submitted_chunk_offset_sec"),
                                "collected_total_duration_sec": clip.get("collected_total_duration_sec"),
                                "known_rejected_experiment_families": list(
                                    (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                        "known_rejected_experiment_families"
                                    )
                                    or []
                                ),
                                "preferred_next_experiment_family": (
                                    (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                        "preferred_next_experiment_family"
                                    )
                                    or "precision_apply_gate_non_skip_owner"
                                ),
                                "guardrails": [
                                    "diagnostic_first",
                                    "additive_only",
                                    "no_ui_no_ux",
                                    "single_subclip_only",
                                    "do_not_broadly_relax_all_precision_thresholds",
                                    "do_not_remove_existing_algorithms",
                                ],
                            }
                            for index, clip in enumerate(viable_top_edge_shift_roles, start=1)
                        ],
                        "known_rejected_experiment_families": sorted(
                            {
                                str(item).strip()
                                for clip in viable_top_edge_shift_roles
                                for item in list(
                                    (_case2_subclip_rejection_hints(clip.get("primary_text")) or {}).get(
                                        "known_rejected_experiment_families"
                                    )
                                    or []
                                )
                                if str(item).strip()
                            }
                        ),
                        "guardrails": [
                            "diagnostic_first",
                            "additive_only",
                            "no_ui_no_ux",
                            "edge_shift_owner_only",
                            "do_not_broadly_relax_all_precision_thresholds",
                            "do_not_remove_existing_algorithms",
                        ],
                    }
                )
        for index, group in enumerate(overlap_groups[:2], start=1):
            top_non_applied_clip_roles = [
                dict(item)
                for item in list(group.get("clip_roles") or [])
                if isinstance(item, dict) and not bool(item.get("likely_applied"))
            ][:2]
            recommended_subclips: list[dict[str, Any]] = []
            for subclip_index, clip in enumerate(top_non_applied_clip_roles, start=1):
                experiment_type = "heavy_phrase_subclip"
                if bool(clip.get("pure_numeric")):
                    experiment_type = "duplicate_pure_numeric_subclip"
                elif bool(clip.get("has_digits")):
                    experiment_type = "digit_phrase_subclip"
                rejection_hints = _case2_subclip_rejection_hints(clip.get("primary_text"))
                recommended_subclips.append(
                    {
                        "id": f"case2_precision_cluster_{index}_subclip_{subclip_index}",
                        "focus": "word_precision_collect_subclip",
                        "experiment_type": experiment_type,
                        "primary_text": clip.get("primary_text"),
                        "start": clip.get("start"),
                        "end": clip.get("end"),
                        "duration_sec": clip.get("duration_sec"),
                        "pure_numeric": bool(clip.get("pure_numeric")),
                        "has_digits": bool(clip.get("has_digits")),
                        "matched_applied_text": clip.get("matched_applied_text"),
                        "matched_output_text": clip.get("matched_output_text"),
                        "best_applied_overlap_ratio": clip.get("best_applied_overlap_ratio"),
                        "precision_reject_reason": clip.get("precision_reject_reason"),
                        "precision_reject_detail": clip.get("precision_reject_detail"),
                        "submission_index": clip.get("submission_index"),
                        "submitted_chunk_duration_sec": clip.get("submitted_chunk_duration_sec"),
                        "submitted_chunk_offset_sec": clip.get("submitted_chunk_offset_sec"),
                        "completion_order_index": clip.get("completion_order_index"),
                        "completed_chunk_elapsed_ms": clip.get("completed_chunk_elapsed_ms"),
                        "emission_order_index": clip.get("emission_order_index"),
                        "emitted_chunk_elapsed_ms": clip.get("emitted_chunk_elapsed_ms"),
                        "duration_first_submission_enabled": clip.get("duration_first_submission_enabled"),
                        "collected_total_duration_sec": clip.get("collected_total_duration_sec"),
                        "collected_duration_ratio": clip.get("collected_duration_ratio"),
                        "known_rejected_experiment_families": list(
                            rejection_hints.get("known_rejected_experiment_families") or []
                        ),
                        "avoid_notes": list(rejection_hints.get("avoid_notes") or []),
                        "revalidation_candidate_experiment_families": list(
                            rejection_hints.get("revalidation_candidate_experiment_families") or []
                        ),
                        "revalidation_notes": list(rejection_hints.get("revalidation_notes") or []),
                        "preferred_next_experiment_family": rejection_hints.get(
                            "preferred_next_experiment_family"
                        ),
                        "guardrails": [
                            "additive_only",
                            "no_ui_no_ux",
                            "single_subclip_only",
                            "sequential_repeat_only",
                            "do_not_remove_existing_algorithms",
                        ],
                    }
                )
            cluster_experiments.append(
                {
                    "id": f"case2_precision_cluster_{index}",
                    "focus": "word_precision_collect_path",
                    "cluster_start": group.get("cluster_start"),
                    "cluster_end": group.get("cluster_end"),
                    "cluster_span_sec": group.get("cluster_span_sec"),
                    "sample_texts": list(group.get("sample_texts") or []),
                    "non_applied_clip_count": group.get("non_applied_clip_count"),
                    "applied_clip_count": group.get("applied_clip_count"),
                    "non_applied_collected_total_duration_sec": group.get("non_applied_collected_total_duration_sec"),
                    "top_non_applied_clip_roles": top_non_applied_clip_roles,
                    "recommended_subclips": recommended_subclips,
                    "known_rejected_experiment_families": sorted(
                        {
                            str(item).strip()
                            for subclip in recommended_subclips
                            for item in list(subclip.get("known_rejected_experiment_families") or [])
                            if str(item).strip()
                        }
                    ),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_cluster_only",
                        "sequential_repeat_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        if cluster_experiments:
            recommended_experiments.append(cluster_experiments[0])
        if low_yield_clip_rows:
            low_yield_subclips: list[dict[str, Any]] = []
            for subclip_index, clip in enumerate(low_yield_clip_rows[:2], start=1):
                rejection_hints = _case2_subclip_rejection_hints(clip.get("primary_text"))
                low_yield_subclips.append(
                    {
                        "id": f"case2_low_yield_collect_clip_{subclip_index}",
                        "focus": "word_precision_collect_subclip",
                        "experiment_type": "low_yield_nondigit_subclip",
                        "primary_text": clip.get("primary_text"),
                        "start": clip.get("start"),
                        "end": clip.get("end"),
                        "duration_sec": clip.get("duration_sec"),
                        "cluster_start": clip.get("cluster_start"),
                        "cluster_end": clip.get("cluster_end"),
                        "best_applied_overlap_ratio": clip.get("best_applied_overlap_ratio"),
                        "matched_output_text": clip.get("matched_output_text"),
                        "submission_index": clip.get("submission_index"),
                        "submitted_chunk_duration_sec": clip.get("submitted_chunk_duration_sec"),
                        "submitted_chunk_offset_sec": clip.get("submitted_chunk_offset_sec"),
                        "completion_order_index": clip.get("completion_order_index"),
                        "completed_chunk_elapsed_ms": clip.get("completed_chunk_elapsed_ms"),
                        "emission_order_index": clip.get("emission_order_index"),
                        "emitted_chunk_elapsed_ms": clip.get("emitted_chunk_elapsed_ms"),
                        "duration_first_submission_enabled": clip.get("duration_first_submission_enabled"),
                        "collected_total_duration_sec": clip.get("collected_total_duration_sec"),
                        "collected_duration_ratio": clip.get("collected_duration_ratio"),
                        "collect_waste_score": clip.get("collect_waste_score"),
                        "precision_reject_reason": clip.get("precision_reject_reason"),
                        "precision_reject_detail": clip.get("precision_reject_detail"),
                        "known_rejected_experiment_families": list(
                            rejection_hints.get("known_rejected_experiment_families") or []
                        ),
                        "avoid_notes": list(rejection_hints.get("avoid_notes") or []),
                        "revalidation_candidate_experiment_families": list(
                            rejection_hints.get("revalidation_candidate_experiment_families") or []
                        ),
                        "revalidation_notes": list(rejection_hints.get("revalidation_notes") or []),
                        "preferred_next_experiment_family": rejection_hints.get(
                            "preferred_next_experiment_family"
                        ),
                        "guardrails": [
                            "additive_only",
                            "no_ui_no_ux",
                            "single_subclip_only",
                            "sequential_repeat_only",
                            "do_not_remove_existing_algorithms",
                        ],
                    }
                )
            recommended_experiments.append(
                {
                    "id": "case2_low_yield_collect_clips",
                    "focus": "word_precision_collect_path",
                    "selection_rule": "non_digit_non_applied_low_overlap",
                    "clip_count": len(low_yield_subclips),
                    "total_collected_duration_sec": round(
                        sum(float(item.get("collected_total_duration_sec", 0.0) or 0.0) for item in low_yield_subclips),
                        3,
                    ),
                    "clip_roles": low_yield_clip_rows[:2],
                    "recommended_subclips": low_yield_subclips,
                    "known_rejected_experiment_families": sorted(
                        {
                            str(item).strip()
                            for subclip in low_yield_subclips
                            for item in list(subclip.get("known_rejected_experiment_families") or [])
                            if str(item).strip()
                        }
                    ),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "non_digit_only",
                        "single_subclip_only",
                        "sequential_repeat_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
        recommended_experiments.extend(cluster_experiments[1:])

        def _experiment_runtime_priority(item: dict[str, Any]) -> tuple[float, float, float, float]:
            focus = str(item.get("focus") or "").strip()
            if focus == "primary_collect_path":
                return (-5e10, -float("inf"), -float("inf"), -float("inf"))
            if focus == "secondary_recheck_path":
                return (-4e10, -float("inf"), -float("inf"), -float("inf"))
            if str(item.get("id") or "").strip() == "case2_precision_candidate_text_artifact":
                return (-3.6e10, -float("inf"), -float("inf"), -float("inf"))
            if str(item.get("id") or "").strip() == "case2_precision_candidate_truncation":
                return (-3.5e10, -float("inf"), -float("inf"), -float("inf"))
            if focus == "precision_apply_gate_edge_shift":
                return (-3e10, -float("inf"), -float("inf"), -float("inf"))
            if focus == "available_memory_snapshot_volatility":
                return (-1e13, -float("inf"), -float("inf"), -float("inf"))
            if focus == "pressure_stage_reason_mismatch":
                return (-1e12, -float("inf"), -float("inf"), -float("inf"))
            if focus == "precollect_worker_residency":
                return (-1.5e11, -float("inf"), -float("inf"), -float("inf"))
            if focus == "native_pressure_stage_source":
                return (-1e11, -float("inf"), -float("inf"), -float("inf"))
            if str(item.get("focus") or "").strip() == "critical_pressure_snapshot_thresholds":
                return (-1e10, -float("inf"), -float("inf"), -float("inf"))
            subclips = [
                dict(subclip)
                for subclip in list(item.get("recommended_subclips") or [])
                if isinstance(subclip, dict)
            ]
            clip_roles = [
                dict(clip)
                for clip in list(item.get("top_non_applied_clip_roles") or item.get("clip_roles") or [])
                if isinstance(clip, dict)
            ]
            completed_latency = max(
                [
                    float((subclip or {}).get("completed_chunk_elapsed_ms", 0.0) or 0.0)
                    for subclip in subclips
                ]
                + [
                    float((clip or {}).get("completed_chunk_elapsed_ms", 0.0) or 0.0)
                    for clip in clip_roles
                ]
                + [0.0]
            )
            emitted_latency = max(
                [
                    float((subclip or {}).get("emitted_chunk_elapsed_ms", 0.0) or 0.0)
                    for subclip in subclips
                ]
                + [
                    float((clip or {}).get("emitted_chunk_elapsed_ms", 0.0) or 0.0)
                    for clip in clip_roles
                ]
                + [0.0]
            )
            collected_burden = max(
                float(item.get("non_applied_collected_total_duration_sec", 0.0) or 0.0),
                float(item.get("total_collected_duration_sec", 0.0) or 0.0),
                max(
                    [float((subclip or {}).get("collected_total_duration_sec", 0.0) or 0.0) for subclip in subclips]
                    + [float((clip or {}).get("collected_total_duration_sec", 0.0) or 0.0) for clip in clip_roles]
                    + [0.0]
                ),
            )
            waste_score = max(
                [float((subclip or {}).get("collect_waste_score", 0.0) or 0.0) for subclip in subclips]
                + [float((clip or {}).get("collect_waste_score", 0.0) or 0.0) for clip in clip_roles]
                + [0.0]
            )
            return (
                -completed_latency,
                -emitted_latency,
                -collected_burden,
                -waste_score,
            )

        recommended_experiments = sorted(recommended_experiments, key=_experiment_runtime_priority)
    elif (
        normalized_target == "case2"
        and str(budget.get("word_precision_collect_pressure_stage") or "").strip().lower() == "critical"
        and str(budget.get("slowest_word_precision_phase_name") or "").strip().lower() == "collect_segments"
        and str(budget.get("word_precision_collect_worker_source") or "").strip() == "transient_child_worker"
    ):
        recommended_experiments.append(
            {
                "id": "case2_precision_collect_policy",
                "focus": "critical_pressure_collect_policy",
                "collect_pressure_stage": budget.get("word_precision_collect_pressure_stage"),
                "collect_worker_source": budget.get("word_precision_collect_worker_source"),
                "collect_owner_type": budget.get("word_precision_collect_owner_type"),
                "collect_reuse_enabled": budget.get("word_precision_collect_reuse_enabled"),
                "collect_allow_worker_reuse": budget.get("word_precision_collect_allow_worker_reuse"),
                "guardrails": [
                    "additive_only",
                    "no_ui_no_ux",
                    "do_not_reopen_rejected_keep_warm_branch",
                    "sequential_repeat_only",
                ],
            }
        )
    elif normalized_target == "case2" and overlap_groups:
        for index, group in enumerate(overlap_groups[:2], start=1):
            recommended_experiments.append(
                {
                    "id": f"case2_precision_cluster_{index}",
                    "focus": "word_precision_collect_path",
                    "cluster_start": group.get("cluster_start"),
                    "cluster_end": group.get("cluster_end"),
                    "cluster_span_sec": group.get("cluster_span_sec"),
                    "sample_texts": list(group.get("sample_texts") or []),
                    "non_applied_clip_count": group.get("non_applied_clip_count"),
                    "applied_clip_count": group.get("applied_clip_count"),
                    "non_applied_collected_total_duration_sec": group.get("non_applied_collected_total_duration_sec"),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_cluster_only",
                        "sequential_repeat_only",
                        "do_not_remove_existing_algorithms",
                    ],
                }
            )
    elif normalized_target == "case1":
        gap_owner_groups = [
            dict(item) for item in list(winner.get("artifact_gap_owner_groups") or []) if isinstance(item, dict)
        ]
        span_owner_flow = [
            dict(item) for item in list(winner.get("artifact_span_owner_flow") or []) if isinstance(item, dict)
        ]
        if gap_owner_groups:
            top_group = gap_owner_groups[0]
            recommended_experiments.append(
                {
                    "id": "case1_top_gap_owner",
                    "focus": "alignment_timing_allocation",
                    "source_start": top_group.get("source_start"),
                    "source_end": top_group.get("source_end"),
                    "reference_gap_count": top_group.get("reference_gap_count"),
                    "reference_gap_total_duration_sec": top_group.get("reference_gap_total_duration_sec"),
                    "sample_texts": list(top_group.get("sample_texts") or []),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_span_only",
                        "sequential_repeat_only",
                    ],
                }
            )
        elif span_owner_flow:
            top_flow = span_owner_flow[0]
            recommended_experiments.append(
                {
                    "id": "case1_top_span_owner",
                    "focus": "raw_restore_common_split_boundary",
                    "source_start": top_flow.get("source_start"),
                    "source_end": top_flow.get("source_end"),
                    "sample_texts": list(top_flow.get("sample_texts") or []),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_span_only",
                        "sequential_repeat_only",
                    ],
                }
            )

    if not recommended_experiments:
        merged_rows = [dict(item) for item in list(primary_recheck_rows.get("merged") or []) if isinstance(item, dict)]
        if merged_rows:
            top_row = merged_rows[0]
            recommended_experiments.append(
                {
                    "id": f"{normalized_target or 'artifact'}_top_recheck_row",
                    "focus": "bounded_recheck_owner",
                    "start": top_row.get("start"),
                    "end": top_row.get("end"),
                    "duration_sec": top_row.get("duration_sec"),
                    "primary_text": top_row.get("primary_text"),
                    "guardrails": [
                        "additive_only",
                        "no_ui_no_ux",
                        "single_row_only",
                        "sequential_repeat_only",
                    ],
                }
            )

    if normalized_target == "case2" and "precision_overlap_groups" in hints:
        if not any(
            hint in hints
            for hint in (
                "precision_candidate_text_artifact",
                "precision_candidate_truncation",
                "precision_apply_gate_edge_shift",
            )
        ):
            specific_overlap_owner_hints = _case2_specific_overlap_owner_hints_from_experiments(
                recommended_experiments
            )
            if specific_overlap_owner_hints:
                sharpened_hints: list[str] = []
                inserted = False
                for hint in hints:
                    if hint == "precision_overlap_groups" and not inserted:
                        sharpened_hints.extend(specific_overlap_owner_hints)
                        inserted = True
                    sharpened_hints.append(hint)
                hints = []
                seen_hints: set[str] = set()
                for hint in sharpened_hints:
                    if hint and hint not in seen_hints:
                        seen_hints.add(hint)
                        hints.append(hint)

    return {
        "ok": True,
        "target": target_label,
        "winner": winner,
        "next_owner_hints": hints,
        "preconditions": preconditions,
        "known_rejected_experiment_families": list(global_rejection_hints.get("known_rejected_experiment_families") or [])
        if _resolved_next_owner_target_label(target_label, winner) == "case2"
        else [],
        "avoid_notes": list(global_rejection_hints.get("avoid_notes") or [])
        if _resolved_next_owner_target_label(target_label, winner) == "case2"
        else [],
        "owner_file_shortlist": _owner_file_shortlist_from_hints(hints),
        "recommended_experiments": recommended_experiments,
        "artifact_runtime_stage_budget": budget,
    }


def _run_compare_current_vs_accepted(args: argparse.Namespace) -> int:
    try:
        accepted_target, accepted_json = _resolve_compare_current_accepted_source(args)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    current_json = Path(str(args.current_json)).expanduser()

    accepted = _artifact_summary_payload(accepted_json)
    current = _artifact_summary_payload(current_json)
    accepted_winner = dict(accepted.get("winner") or {})
    current_winner = dict(current.get("winner") or {})
    accepted_budget = dict(accepted_winner.get("runtime_stage_budget") or {})
    current_budget = dict(current_winner.get("runtime_stage_budget") or {})
    submission_delta_rows = _word_precision_submission_delta_rows(
        accepted_winner.get("artifact_word_precision_overlap_groups"),
        current_winner.get("artifact_word_precision_overlap_groups"),
    )
    submission_changed_count = sum(
        1
        for item in submission_delta_rows
        if _nonzero_delta(item.get("submission_index_delta"))
    )

    accepted_trim = dict(accepted_budget.get("trim_recent_overlap_decisions") or {})
    current_trim = dict(current_budget.get("trim_recent_overlap_decisions") or {})
    trim_keys = sorted(set(accepted_trim) | set(current_trim))

    accepted_stage_counts = dict(accepted_budget.get("stage_segment_counts") or {})
    current_stage_counts = dict(current_budget.get("stage_segment_counts") or {})
    stage_keys = sorted(set(accepted_stage_counts) | set(current_stage_counts))

    accepted_cleanup_changes = dict(accepted_budget.get("final_cleanup_step_changes") or {})
    current_cleanup_changes = dict(current_budget.get("final_cleanup_step_changes") or {})
    cleanup_keys = sorted(set(accepted_cleanup_changes) | set(current_cleanup_changes))

    runtime_budget_delta = {
        "precision_candidate_count_delta": _round_delta(
            current_budget.get("precision_candidate_count"),
            accepted_budget.get("precision_candidate_count"),
        ),
        "precision_applied_count_delta": _round_delta(
            current_budget.get("precision_applied_count"),
            accepted_budget.get("precision_applied_count"),
        ),
        "recheck_range_count_delta": _round_delta(
            current_budget.get("recheck_range_count"),
            accepted_budget.get("recheck_range_count"),
        ),
        "common_split_output_count_delta": _round_delta(
            current_budget.get("common_split_output_count"),
            accepted_budget.get("common_split_output_count"),
        ),
        "missing_common_split_group_count_delta": _round_delta(
            current_budget.get("missing_common_split_group_count"),
            accepted_budget.get("missing_common_split_group_count"),
        ),
        "gap_owner_group_count_delta": _round_delta(
            current_budget.get("gap_owner_group_count"),
            accepted_budget.get("gap_owner_group_count"),
        ),
        "raw_restore_restore_group_count_delta": _round_delta(
            current_budget.get("raw_restore_restore_group_count"),
            accepted_budget.get("raw_restore_restore_group_count"),
        ),
        "raw_restore_restore_group_class_count_deltas": {
            key: _round_delta(
                dict(current_budget.get("raw_restore_restore_group_class_counts") or {}).get(key),
                dict(accepted_budget.get("raw_restore_restore_group_class_counts") or {}).get(key),
            )
            for key in sorted(
                set(dict(accepted_budget.get("raw_restore_restore_group_class_counts") or {}))
                | set(dict(current_budget.get("raw_restore_restore_group_class_counts") or {}))
            )
        },
        "stt_anchor_guard_row_count_delta": _round_delta(
            current_budget.get("stt_anchor_guard_row_count"),
            accepted_budget.get("stt_anchor_guard_row_count"),
        ),
        "stt_anchor_guard_trim_row_count_delta": _round_delta(
            current_budget.get("stt_anchor_guard_trim_row_count"),
            accepted_budget.get("stt_anchor_guard_trim_row_count"),
        ),
        "final_transcript_integrity_accepted": accepted_budget.get("final_transcript_integrity_accepted"),
        "current_final_transcript_integrity_accepted": current_budget.get("final_transcript_integrity_accepted"),
        "reference_gap_row_count_delta": _round_delta(
            len(list(current_winner.get("artifact_reference_gap_rows") or [])),
            len(list(accepted_winner.get("artifact_reference_gap_rows") or [])),
        ),
        "output_gap_row_count_delta": _round_delta(
            len(list(current_winner.get("artifact_output_gap_rows") or [])),
            len(list(accepted_winner.get("artifact_output_gap_rows") or [])),
        ),
        "stage_runtime_total_ms_delta": _round_delta(
            current_budget.get("stage_runtime_total_ms"),
            accepted_budget.get("stage_runtime_total_ms"),
        ),
        "major_runtime_total_ms_delta": _round_delta(
            current_budget.get("major_runtime_total_ms"),
            accepted_budget.get("major_runtime_total_ms"),
        ),
        "selective_runtime_total_ms_delta": _round_delta(
            current_budget.get("selective_runtime_total_ms"),
            accepted_budget.get("selective_runtime_total_ms"),
        ),
        "word_precision_runtime_total_ms_delta": _round_delta(
            current_budget.get("word_precision_runtime_total_ms"),
            accepted_budget.get("word_precision_runtime_total_ms"),
        ),
        "primary_collect_submitted_chunk_count": accepted_budget.get("primary_collect_submitted_chunk_count"),
        "current_primary_collect_submitted_chunk_count": current_budget.get("primary_collect_submitted_chunk_count"),
        "primary_collect_submitted_total_duration_sec": accepted_budget.get("primary_collect_submitted_total_duration_sec"),
        "current_primary_collect_submitted_total_duration_sec": current_budget.get(
            "primary_collect_submitted_total_duration_sec"
        ),
        "primary_collect_submitted_total_duration_sec_delta": _round_delta(
            current_budget.get("primary_collect_submitted_total_duration_sec"),
            accepted_budget.get("primary_collect_submitted_total_duration_sec"),
        ),
        "primary_collect_max_completed_chunk_elapsed_ms": accepted_budget.get(
            "primary_collect_max_completed_chunk_elapsed_ms"
        ),
        "current_primary_collect_max_completed_chunk_elapsed_ms": current_budget.get(
            "primary_collect_max_completed_chunk_elapsed_ms"
        ),
        "primary_collect_max_completed_chunk_elapsed_ms_delta": _round_delta(
            current_budget.get("primary_collect_max_completed_chunk_elapsed_ms"),
            accepted_budget.get("primary_collect_max_completed_chunk_elapsed_ms"),
        ),
        "primary_collect_max_emitted_chunk_elapsed_ms": accepted_budget.get(
            "primary_collect_max_emitted_chunk_elapsed_ms"
        ),
        "current_primary_collect_max_emitted_chunk_elapsed_ms": current_budget.get(
            "primary_collect_max_emitted_chunk_elapsed_ms"
        ),
        "primary_collect_max_emitted_chunk_elapsed_ms_delta": _round_delta(
            current_budget.get("primary_collect_max_emitted_chunk_elapsed_ms"),
            accepted_budget.get("primary_collect_max_emitted_chunk_elapsed_ms"),
        ),
        "primary_collect_pressure_stage": accepted_budget.get("primary_collect_pressure_stage"),
        "current_primary_collect_pressure_stage": current_budget.get("primary_collect_pressure_stage"),
        "primary_collect_worker_source": accepted_budget.get("primary_collect_worker_source"),
        "current_primary_collect_worker_source": current_budget.get("primary_collect_worker_source"),
        "primary_collect_reuse_enabled": accepted_budget.get("primary_collect_reuse_enabled"),
        "current_primary_collect_reuse_enabled": current_budget.get("primary_collect_reuse_enabled"),
        "primary_collect_pressure_stage_source": str(
            accepted_budget.get("primary_collect_pressure_stage_source") or ""
        ).strip(),
        "current_primary_collect_pressure_stage_source": str(
            current_budget.get("primary_collect_pressure_stage_source") or ""
        ).strip(),
        "primary_collect_pressure_stage_trigger_reason": str(
            accepted_budget.get("primary_collect_pressure_stage_trigger_reason") or ""
        ).strip(),
        "current_primary_collect_pressure_stage_trigger_reason": str(
            current_budget.get("primary_collect_pressure_stage_trigger_reason") or ""
        ).strip(),
        "primary_collect_active_backend": accepted_budget.get("primary_collect_active_backend"),
        "current_primary_collect_active_backend": current_budget.get("primary_collect_active_backend"),
        "primary_collect_active_model": accepted_budget.get("primary_collect_active_model"),
        "current_primary_collect_active_model": current_budget.get("primary_collect_active_model"),
        "primary_collect_active_reason": accepted_budget.get("primary_collect_active_reason"),
        "current_primary_collect_active_reason": current_budget.get("primary_collect_active_reason"),
        "primary_collect_challenger_count": accepted_budget.get("primary_collect_challenger_count"),
        "current_primary_collect_challenger_count": current_budget.get("primary_collect_challenger_count"),
        "primary_collect_vad_challenger_provider": accepted_budget.get("primary_collect_vad_challenger_provider"),
        "current_primary_collect_vad_challenger_provider": current_budget.get(
            "primary_collect_vad_challenger_provider"
        ),
        "word_precision_clip_count_delta": _round_delta(
            current_budget.get("word_precision_clip_count"),
            accepted_budget.get("word_precision_clip_count"),
        ),
        "word_precision_applied_clip_count_delta": _round_delta(
            current_budget.get("word_precision_applied_clip_count"),
            accepted_budget.get("word_precision_applied_clip_count"),
        ),
        "word_precision_non_applied_clip_count_delta": _round_delta(
            current_budget.get("word_precision_non_applied_clip_count"),
            accepted_budget.get("word_precision_non_applied_clip_count"),
        ),
        "word_precision_collected_segment_count_delta": _round_delta(
            current_budget.get("word_precision_collected_segment_count"),
            accepted_budget.get("word_precision_collected_segment_count"),
        ),
        "word_precision_non_applied_collected_segment_count_delta": _round_delta(
            current_budget.get("word_precision_non_applied_collected_segment_count"),
            accepted_budget.get("word_precision_non_applied_collected_segment_count"),
        ),
        "word_precision_source_chunk_count_delta": _round_delta(
            current_budget.get("word_precision_source_chunk_count"),
            accepted_budget.get("word_precision_source_chunk_count"),
        ),
        "word_precision_overlap_group_count_delta": _round_delta(
            current_budget.get("word_precision_overlap_group_count"),
            accepted_budget.get("word_precision_overlap_group_count"),
        ),
        "word_precision_non_applied_overlap_group_count_delta": _round_delta(
            current_budget.get("word_precision_non_applied_overlap_group_count"),
            accepted_budget.get("word_precision_non_applied_overlap_group_count"),
        ),
        "word_precision_collect_clip_count_delta": _round_delta(
            current_budget.get("word_precision_collect_clip_count"),
            accepted_budget.get("word_precision_collect_clip_count"),
        ),
        "word_precision_max_overlap_group_span_sec_delta": _round_delta(
            current_budget.get("word_precision_max_overlap_group_span_sec"),
            accepted_budget.get("word_precision_max_overlap_group_span_sec"),
        ),
        "word_precision_overlap_group_collected_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_overlap_group_collected_duration_sec"),
            accepted_budget.get("word_precision_overlap_group_collected_duration_sec"),
        ),
        "word_precision_non_applied_overlap_group_collected_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_non_applied_overlap_group_collected_duration_sec"),
            accepted_budget.get("word_precision_non_applied_overlap_group_collected_duration_sec"),
        ),
        "word_precision_max_overlap_group_collected_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_max_overlap_group_collected_duration_sec"),
            accepted_budget.get("word_precision_max_overlap_group_collected_duration_sec"),
        ),
        "word_precision_collect_pressure_stage": accepted_budget.get("word_precision_collect_pressure_stage"),
        "current_word_precision_collect_pressure_stage": current_budget.get("word_precision_collect_pressure_stage"),
        "word_precision_collect_worker_source": accepted_budget.get("word_precision_collect_worker_source"),
        "current_word_precision_collect_worker_source": current_budget.get("word_precision_collect_worker_source"),
        "word_precision_collect_reuse_enabled": accepted_budget.get("word_precision_collect_reuse_enabled"),
        "current_word_precision_collect_reuse_enabled": current_budget.get("word_precision_collect_reuse_enabled"),
        "word_precision_collect_available_memory_ratio": accepted_budget.get(
            "word_precision_collect_available_memory_ratio"
        ),
        "current_word_precision_collect_available_memory_ratio": current_budget.get(
            "word_precision_collect_available_memory_ratio"
        ),
        "word_precision_collect_available_memory_ratio_delta": _round_delta(
            current_budget.get("word_precision_collect_available_memory_ratio"),
            accepted_budget.get("word_precision_collect_available_memory_ratio"),
        ),
        "word_precision_collect_compressed_memory_ratio": accepted_budget.get(
            "word_precision_collect_compressed_memory_ratio"
        ),
        "current_word_precision_collect_compressed_memory_ratio": current_budget.get(
            "word_precision_collect_compressed_memory_ratio"
        ),
        "word_precision_collect_compressed_memory_ratio_delta": _round_delta(
            current_budget.get("word_precision_collect_compressed_memory_ratio"),
            accepted_budget.get("word_precision_collect_compressed_memory_ratio"),
        ),
        "word_precision_collect_process_rss_bytes": accepted_budget.get(
            "word_precision_collect_process_rss_bytes"
        ),
        "current_word_precision_collect_process_rss_bytes": current_budget.get(
            "word_precision_collect_process_rss_bytes"
        ),
        "word_precision_collect_process_rss_bytes_delta": _round_delta(
            current_budget.get("word_precision_collect_process_rss_bytes"),
            accepted_budget.get("word_precision_collect_process_rss_bytes"),
        ),
        "word_precision_collect_pressure_stage_source": str(
            accepted_budget.get("word_precision_collect_pressure_stage_source") or ""
        ).strip(),
        "current_word_precision_collect_pressure_stage_source": str(
            current_budget.get("word_precision_collect_pressure_stage_source") or ""
        ).strip(),
        "word_precision_collect_pressure_stage_trigger_reason": str(
            accepted_budget.get("word_precision_collect_pressure_stage_trigger_reason") or ""
        ).strip(),
        "current_word_precision_collect_pressure_stage_trigger_reason": str(
            current_budget.get("word_precision_collect_pressure_stage_trigger_reason") or ""
        ).strip(),
        "word_precision_collect_preexisting_alive_runtime_total_count": accepted_budget.get(
            "word_precision_collect_preexisting_alive_runtime_total_count"
        ),
        "current_word_precision_collect_preexisting_alive_runtime_total_count": current_budget.get(
            "word_precision_collect_preexisting_alive_runtime_total_count"
        ),
        "word_precision_collect_preexisting_alive_runtime_total_count_delta": _round_delta(
            current_budget.get("word_precision_collect_preexisting_alive_runtime_total_count"),
            accepted_budget.get("word_precision_collect_preexisting_alive_runtime_total_count"),
        ),
        "word_precision_collect_available_memory_critical_ratio_threshold": accepted_budget.get(
            "word_precision_collect_available_memory_critical_ratio_threshold"
        ),
        "current_word_precision_collect_available_memory_critical_ratio_threshold": current_budget.get(
            "word_precision_collect_available_memory_critical_ratio_threshold"
        ),
        "word_precision_collect_available_memory_critical_ratio_threshold_delta": _round_delta(
            current_budget.get("word_precision_collect_available_memory_critical_ratio_threshold"),
            accepted_budget.get("word_precision_collect_available_memory_critical_ratio_threshold"),
        ),
        "word_precision_collect_available_memory_critical_headroom": accepted_budget.get(
            "word_precision_collect_available_memory_critical_headroom"
        ),
        "current_word_precision_collect_available_memory_critical_headroom": current_budget.get(
            "word_precision_collect_available_memory_critical_headroom"
        ),
        "word_precision_collect_available_memory_critical_headroom_delta": _round_delta(
            current_budget.get("word_precision_collect_available_memory_critical_headroom"),
            accepted_budget.get("word_precision_collect_available_memory_critical_headroom"),
        ),
        "word_precision_collect_compressed_memory_critical_ratio_threshold": accepted_budget.get(
            "word_precision_collect_compressed_memory_critical_ratio_threshold"
        ),
        "current_word_precision_collect_compressed_memory_critical_ratio_threshold": current_budget.get(
            "word_precision_collect_compressed_memory_critical_ratio_threshold"
        ),
        "word_precision_collect_compressed_memory_critical_ratio_threshold_delta": _round_delta(
            current_budget.get("word_precision_collect_compressed_memory_critical_ratio_threshold"),
            accepted_budget.get("word_precision_collect_compressed_memory_critical_ratio_threshold"),
        ),
        "word_precision_collect_compressed_memory_critical_headroom": accepted_budget.get(
            "word_precision_collect_compressed_memory_critical_headroom"
        ),
        "current_word_precision_collect_compressed_memory_critical_headroom": current_budget.get(
            "word_precision_collect_compressed_memory_critical_headroom"
        ),
        "word_precision_collect_compressed_memory_critical_headroom_delta": _round_delta(
            current_budget.get("word_precision_collect_compressed_memory_critical_headroom"),
            accepted_budget.get("word_precision_collect_compressed_memory_critical_headroom"),
        ),
        "word_precision_collect_pressure_reasons": [
            str(item).strip()
            for item in list(accepted_budget.get("word_precision_collect_pressure_reasons") or [])
            if str(item).strip()
        ],
        "current_word_precision_collect_pressure_reasons": [
            str(item).strip()
            for item in list(current_budget.get("word_precision_collect_pressure_reasons") or [])
            if str(item).strip()
        ],
        "word_precision_collect_pressure_reason_added": [
            reason
            for reason in [
                str(item).strip()
                for item in list(current_budget.get("word_precision_collect_pressure_reasons") or [])
                if str(item).strip()
            ]
            if reason
            not in {
                str(item).strip()
                for item in list(accepted_budget.get("word_precision_collect_pressure_reasons") or [])
                if str(item).strip()
            }
        ],
        "word_precision_collect_pressure_reason_removed": [
            reason
            for reason in [
                str(item).strip()
                for item in list(accepted_budget.get("word_precision_collect_pressure_reasons") or [])
                if str(item).strip()
            ]
            if reason
            not in {
                str(item).strip()
                for item in list(current_budget.get("word_precision_collect_pressure_reasons") or [])
                if str(item).strip()
            }
        ],
        "word_precision_collect_pressure_reason_stage": str(
            accepted_budget.get("word_precision_collect_pressure_reason_stage") or ""
        ).strip(),
        "current_word_precision_collect_pressure_reason_stage": str(
            current_budget.get("word_precision_collect_pressure_reason_stage") or ""
        ).strip(),
        "word_precision_collect_pressure_stage_reason_mismatch": bool(
            accepted_budget.get("word_precision_collect_pressure_stage_reason_mismatch")
        ),
        "current_word_precision_collect_pressure_stage_reason_mismatch": bool(
            current_budget.get("word_precision_collect_pressure_stage_reason_mismatch")
        ),
        "word_precision_collect_pressure_stage_reason_mismatch_kind": str(
            accepted_budget.get("word_precision_collect_pressure_stage_reason_mismatch_kind") or ""
        ).strip(),
        "current_word_precision_collect_pressure_stage_reason_mismatch_kind": str(
            current_budget.get("word_precision_collect_pressure_stage_reason_mismatch_kind") or ""
        ).strip(),
        "word_precision_submission_delta_rows": submission_delta_rows,
        "word_precision_submission_index_changed_count": submission_changed_count,
        "word_precision_submission_order_proven": bool(submission_changed_count),
        "word_precision_total_clip_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_total_clip_duration_sec"),
            accepted_budget.get("word_precision_total_clip_duration_sec"),
        ),
        "word_precision_non_applied_clip_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_non_applied_clip_duration_sec"),
            accepted_budget.get("word_precision_non_applied_clip_duration_sec"),
        ),
        "word_precision_max_clip_duration_sec_delta": _round_delta(
            current_budget.get("word_precision_max_clip_duration_sec"),
            accepted_budget.get("word_precision_max_clip_duration_sec"),
        ),
        "major_wallclock_gap_ms_delta": _round_delta(
            current_budget.get("major_wallclock_gap_ms"),
            accepted_budget.get("major_wallclock_gap_ms"),
        ),
        "major_runtime_phase_ms_deltas": {
            key: _round_delta(
                dict(current_budget.get("major_runtime_ms_by_phase") or {}).get(key),
                dict(accepted_budget.get("major_runtime_ms_by_phase") or {}).get(key),
            )
            for key in sorted(
                set(dict(accepted_budget.get("major_runtime_ms_by_phase") or {}))
                | set(dict(current_budget.get("major_runtime_ms_by_phase") or {}))
            )
        },
        "selective_runtime_phase_ms_deltas": {
            key: _round_delta(
                dict(current_budget.get("selective_runtime_ms_by_phase") or {}).get(key),
                dict(accepted_budget.get("selective_runtime_ms_by_phase") or {}).get(key),
            )
            for key in sorted(
                set(dict(accepted_budget.get("selective_runtime_ms_by_phase") or {}))
                | set(dict(current_budget.get("selective_runtime_ms_by_phase") or {}))
            )
        },
        "word_precision_runtime_phase_ms_deltas": {
            key: _round_delta(
                dict(current_budget.get("word_precision_runtime_ms_by_phase") or {}).get(key),
                dict(accepted_budget.get("word_precision_runtime_ms_by_phase") or {}).get(key),
            )
            for key in sorted(
                set(dict(accepted_budget.get("word_precision_runtime_ms_by_phase") or {}))
                | set(dict(current_budget.get("word_precision_runtime_ms_by_phase") or {}))
            )
        },
        "trim_recent_overlap_decision_deltas": {
            key: _round_delta(current_trim.get(key), accepted_trim.get(key))
            for key in trim_keys
        },
        "stage_segment_count_deltas": {
            key: _round_delta(current_stage_counts.get(key), accepted_stage_counts.get(key))
            for key in stage_keys
        },
        "final_cleanup_step_change_deltas": {
            key: _round_delta(current_cleanup_changes.get(key), accepted_cleanup_changes.get(key))
            for key in cleanup_keys
        },
        "runtime_policy_snapshot_changed_keys": sorted(
            key
            for key in (
                set(dict(accepted_budget.get("runtime_policy_snapshot") or {}))
                | set(dict(current_budget.get("runtime_policy_snapshot") or {}))
            )
            if (dict(accepted_budget.get("runtime_policy_snapshot") or {})).get(key)
            != (dict(current_budget.get("runtime_policy_snapshot") or {})).get(key)
        ),
        "runtime_policy_snapshot": {
            "accepted": dict(accepted_budget.get("runtime_policy_snapshot") or {}),
            "current": dict(current_budget.get("runtime_policy_snapshot") or {}),
        },
    }
    primary_collect_shape_static = (
        int(accepted_budget.get("primary_collect_submitted_chunk_count") or 0)
        == int(current_budget.get("primary_collect_submitted_chunk_count") or 0)
        and abs(float(runtime_budget_delta.get("primary_collect_submitted_total_duration_sec_delta") or 0.0))
        <= 0.001
    )
    primary_collect_route_plan_static = (
        primary_collect_shape_static
        and str(runtime_budget_delta.get("primary_collect_active_backend") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_active_backend") or "").strip()
        and str(runtime_budget_delta.get("primary_collect_active_model") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_active_model") or "").strip()
        and str(runtime_budget_delta.get("primary_collect_active_reason") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_active_reason") or "").strip()
        and int(runtime_budget_delta.get("primary_collect_challenger_count") or 0)
        == int(runtime_budget_delta.get("current_primary_collect_challenger_count") or 0)
        and str(runtime_budget_delta.get("primary_collect_vad_challenger_provider") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_vad_challenger_provider") or "").strip()
    )
    primary_collect_state_static = (
        primary_collect_route_plan_static
        and str(runtime_budget_delta.get("primary_collect_pressure_stage") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_pressure_stage") or "").strip()
        and str(runtime_budget_delta.get("primary_collect_worker_source") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_worker_source") or "").strip()
        and bool(runtime_budget_delta.get("primary_collect_reuse_enabled"))
        == bool(runtime_budget_delta.get("current_primary_collect_reuse_enabled"))
        and str(runtime_budget_delta.get("primary_collect_pressure_stage_source") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_pressure_stage_source") or "").strip()
        and str(runtime_budget_delta.get("primary_collect_pressure_stage_trigger_reason") or "").strip()
        == str(runtime_budget_delta.get("current_primary_collect_pressure_stage_trigger_reason") or "").strip()
    )
    primary_collect_completion_latency_dominates = (
        primary_collect_state_static
        and abs(float(runtime_budget_delta.get("primary_collect_max_completed_chunk_elapsed_ms_delta") or 0.0))
        >= 1000.0
        and abs(float(runtime_budget_delta.get("primary_collect_max_completed_chunk_elapsed_ms_delta") or 0.0))
        > max(
            2000.0,
            abs(float(runtime_budget_delta.get("word_precision_runtime_total_ms_delta") or 0.0)),
        )
    )
    runtime_budget_delta["primary_collect_shape_static"] = primary_collect_shape_static
    runtime_budget_delta["primary_collect_route_plan_static"] = primary_collect_route_plan_static
    runtime_budget_delta["primary_collect_state_static"] = primary_collect_state_static
    runtime_budget_delta["primary_collect_completion_latency_dominates"] = (
        primary_collect_completion_latency_dominates
    )
    hot_owner_hints = _hot_owner_hints_from_runtime_budget_delta(runtime_budget_delta)
    payload = {
        "ok": True,
        "accepted_target": accepted_target,
        "accepted": {
            "json": str(accepted_json),
            "winner": accepted_winner,
        },
        "current": {
            "json": str(current_json),
            "winner": current_winner,
        },
        "comparison": _pairwise_delta_payload(accepted_target, accepted_winner, "current", current_winner),
        "runtime_budget_delta": {
            **runtime_budget_delta,
            "hot_owner_hints": hot_owner_hints,
        },
        "hot_owner_hints": hot_owner_hints,
        "primary_collect_shape_static": primary_collect_shape_static,
        "primary_collect_route_plan_static": primary_collect_route_plan_static,
        "primary_collect_state_static": primary_collect_state_static,
        "primary_collect_completion_latency_dominates": primary_collect_completion_latency_dominates,
        "owner_file_shortlist": _owner_file_shortlist_from_hints(hot_owner_hints),
        "accepted_runtime_stage_budget": accepted_budget,
        "current_runtime_stage_budget": current_budget,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_next_owner_plan(args: argparse.Namespace) -> int:
    try:
        target_label, json_path = _resolve_plan_source(args)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    summary_payload = _artifact_summary_payload(json_path)
    payload = {
        "artifact_json": str(json_path),
        **_next_owner_plan_payload(target_label, summary_payload),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _pairwise_delta_payload(
    baseline_label: str,
    baseline_winner: dict[str, Any],
    candidate_label: str,
    candidate_winner: dict[str, Any],
) -> dict[str, Any]:
    return {
        "baseline_label": baseline_label,
        "candidate_label": candidate_label,
        "deltas": {
            "elapsed_sec_delta": _round_delta(candidate_winner.get("elapsed_sec"), baseline_winner.get("elapsed_sec")),
            "quality_score_delta": _round_delta(candidate_winner.get("quality_score"), baseline_winner.get("quality_score")),
            "timing_priority_quality_score_delta": _round_delta(
                candidate_winner.get("timing_priority_quality_score"),
                baseline_winner.get("timing_priority_quality_score"),
            ),
            "timing_mae_sec_delta": _round_delta(candidate_winner.get("timing_mae_sec"), baseline_winner.get("timing_mae_sec")),
            "word_precision_count_delta": _round_delta(
                candidate_winner.get("word_precision_count"),
                baseline_winner.get("word_precision_count"),
            ),
            "stt2_selected_count_delta": _round_delta(
                candidate_winner.get("stt2_selected_count"),
                baseline_winner.get("stt2_selected_count"),
            ),
            "recheck_applied_count_delta": _round_delta(
                candidate_winner.get("recheck_applied_count"),
                baseline_winner.get("recheck_applied_count"),
            ),
            "stt2_coverage_ratio_delta": _round_delta(
                candidate_winner.get("stt2_coverage_ratio"),
                baseline_winner.get("stt2_coverage_ratio"),
            ),
        },
    }


def _run_accepted_standings(args: argparse.Namespace) -> int:
    baseline = _artifact_summary_payload(Path(str(args.baseline_json)).expanduser())
    case1 = _artifact_summary_payload(Path(str(args.case1_json)).expanduser())
    case2 = _artifact_summary_payload(Path(str(args.case2_json)).expanduser())
    baseline_winner = dict(baseline.get("winner") or {})
    case1_winner = dict(case1.get("winner") or {})
    case2_winner = dict(case2.get("winner") or {})
    payload = {
        "ok": True,
        "accepted_artifacts": {
            "baseline": {"json": str(args.baseline_json), "winner": baseline_winner},
            "case1": {"json": str(args.case1_json), "winner": case1_winner},
            "case2": {"json": str(args.case2_json), "winner": case2_winner},
        },
        "standings": {
            "overall_quality_timing_winner": "case2",
            "speed_winner": "case1",
        },
        "comparisons": {
            "case1_vs_baseline": _pairwise_delta_payload("baseline", baseline_winner, "case1", case1_winner),
            "case2_vs_baseline": _pairwise_delta_payload("baseline", baseline_winner, "case2", case2_winner),
            "case2_vs_case1": _pairwise_delta_payload("case1", case1_winner, "case2", case2_winner),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _round_delta(candidate_value: Any, baseline_value: Any) -> float | None:
    if candidate_value is None or baseline_value is None:
        return None
    try:
        return round(float(candidate_value) - float(baseline_value), 6)
    except Exception:
        return None


def _best_run(runs: list[dict[str, Any]], score_key: str, prefer_lower_elapsed: bool) -> dict[str, Any] | None:
    ranked: list[dict[str, Any]] = []
    for run in runs:
        winner = dict(run.get("winner") or {})
        if not winner:
            continue
        ranked.append(
            {
                "preset": run.get("preset"),
                "artifact_json": run.get("artifact_json"),
                "winner": winner,
            }
        )
    if not ranked:
        return None
    if score_key == "elapsed_sec":
        ranked.sort(
            key=lambda item: (
                float((item.get("winner") or {}).get("elapsed_sec") or float("inf")),
                -float((item.get("winner") or {}).get("timing_priority_quality_score") or -1.0),
            )
        )
        return ranked[0]
    ranked.sort(
        key=lambda item: (
            -float((item.get("winner") or {}).get(score_key) or -1.0),
            float((item.get("winner") or {}).get("elapsed_sec") or float("inf")) if prefer_lower_elapsed else 0.0,
        )
    )
    return ranked[0]


def _best_attempt_from_runs(runs: list[dict[str, Any]], score_key: str) -> dict[str, Any] | None:
    ranked: list[dict[str, Any]] = []
    for run in runs:
        winner = dict(run.get("winner") or {})
        if not winner:
            continue
        ranked.append(run)
    if not ranked:
        return None
    if score_key == "elapsed_sec":
        ranked.sort(key=lambda item: float((item.get("winner") or {}).get("elapsed_sec") or float("inf")))
        return ranked[0]
    ranked.sort(
        key=lambda item: (
            -float((item.get("winner") or {}).get(score_key) or -1.0),
            float((item.get("winner") or {}).get("elapsed_sec") or float("inf")),
        )
    )
    return ranked[0]


def _best_preset_summary(per_preset_runs: list[dict[str, Any]], metric_key: str, speed_metric: bool = False) -> dict[str, Any] | None:
    ranked: list[dict[str, Any]] = []
    for summary in per_preset_runs:
        aggregate = dict(summary.get("aggregate") or {})
        metric = dict(aggregate.get(metric_key) or {})
        if metric.get("mean") is None:
            continue
        ranked.append(summary)
    if not ranked:
        return None
    if speed_metric:
        ranked.sort(
            key=lambda item: (
                float((((item.get("aggregate") or {}).get("elapsed_sec") or {}).get("mean") or float("inf"))),
                -float((((item.get("aggregate") or {}).get("timing_priority_quality_score") or {}).get("mean") or -1.0)),
            )
        )
        return ranked[0]
    ranked.sort(
        key=lambda item: (
            -float((((item.get("aggregate") or {}).get(metric_key) or {}).get("mean") or -1.0)),
            float((((item.get("aggregate") or {}).get("elapsed_sec") or {}).get("mean") or float("inf"))),
        )
    )
    return ranked[0]


def _run_artifact_summary(args: argparse.Namespace) -> int:
    json_path = Path(str(args.json)).expanduser()
    payload = _artifact_summary_payload(json_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _run_probe(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT))
    from core.audio.apple_speech_native import apple_speech_support

    result = apple_speech_support({"stt_apple_speech_locale": str(args.locale)}, locale=str(args.locale))
    print(
        json.dumps(
            {
                "ok": bool(result.available),
                "locale": result.locale,
                "available": result.available,
                "detector_available": result.detector_available,
                "reason": result.reason,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    args = _parser().parse_args()
    if args.command == "benchmark":
        return _run_benchmark(args)
    if args.command == "benchmark-preset":
        return _run_benchmark_preset(args)
    if args.command == "repeat-preset":
        return _run_repeat_preset(args)
    if args.command == "matrix-preset":
        return _run_matrix_preset(args)
    if args.command == "matrix-repeat":
        return _run_matrix_repeat(args)
    if args.command == "artifact-summary":
        return _run_artifact_summary(args)
    if args.command == "compare-artifacts":
        return _run_compare_artifacts(args)
    if args.command == "compare-current-vs-accepted":
        return _run_compare_current_vs_accepted(args)
    if args.command == "next-owner-plan":
        return _run_next_owner_plan(args)
    if args.command == "accepted-standings":
        return _run_accepted_standings(args)
    if args.command == "probe-apple":
        return _run_probe(args)
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
