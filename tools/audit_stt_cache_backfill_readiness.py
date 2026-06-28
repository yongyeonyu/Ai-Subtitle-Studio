#!/usr/bin/env python3
"""Audit whether STT collect caches have enough evidence for default promotion."""

from __future__ import annotations

import argparse
import glob
import json
import shlex
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime.config import DEFAULT_ADV_SETTINGS
from tools.summarize_stage_variance import load_runs


FAMILY_RULES = {
    "stt_primary_collect_cache": {
        "default_keys": ("stt_primary_collect_cache_enabled",),
        "cache_keys": ("stt_primary",),
    },
    "stt_recheck_word_collect_cache": {
        "default_keys": ("stt_recheck_collect_cache_enabled",),
        "cache_keys": ("stt2_recheck", "word_precision"),
    },
    "combined_collect_cache": {
        "default_keys": ("stt_primary_collect_cache_enabled", "stt_recheck_collect_cache_enabled"),
        "cache_keys": ("stt_primary", "stt2_recheck", "word_precision"),
    },
}

DEFAULT_REPRESENTATIVE_MEDIA = "<REPRESENTATIVE_MEDIA>"
DEFAULT_REPRESENTATIVE_REFERENCE_SRT = "<REPRESENTATIVE_REFERENCE_SRT>"
DEFAULT_BACKFILL_OUTPUT_DIR = "output/manual_verification/latest/stt_collect_cache_real_backfill"
DEFAULT_BENCHMARK_GLOB = ".codex_work/benchmarks/subtitle_pipeline_variants/*/benchmark_results.json"


def _expand_inputs(inputs: list[str], globs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in inputs:
        paths.append(Path(value))
    for pattern in globs:
        paths.extend(Path(item) for item in glob.glob(pattern))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        if path.exists():
            unique.append(path)
    return unique


def _path_exists(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return Path(text).exists()


def _is_generated_media(value: Any) -> bool:
    text = str(value or "").lower()
    if not text:
        return False
    return any(marker in text for marker in ("synthetic", "generated", "/output/", "output/manual_verification"))


def _is_real_media(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _is_generated_media(text):
        return False
    return Path(text).is_absolute()


def _strict_final_pass(run: dict[str, Any]) -> bool:
    gates = dict(run.get("final_gates") or {})
    return (
        gates.get("invalid_duration_count") == 0
        and gates.get("non_monotonic_count") == 0
        and gates.get("overlap_count") == 0
        and (gates.get("global_canvas_max_active_segments") or 0) <= 1
        and gates.get("last_end_within_duration_bound") is not False
    )


def _cache_hit_without_provider(run: dict[str, Any], cache_keys: tuple[str, ...]) -> bool:
    cache = dict(run.get("cache") or {})
    for key in cache_keys:
        data = dict(cache.get(key) or {})
        if data.get("hit") is not True:
            return False
        if data.get("provider_called") is not False:
            return False
    return True


def _cache_write_with_provider(run: dict[str, Any], cache_keys: tuple[str, ...]) -> bool:
    cache = dict(run.get("cache") or {})
    for key in cache_keys:
        data = dict(cache.get(key) or {})
        if data.get("write") is not True:
            return False
        if data.get("provider_called") is not True:
            return False
    return True


def _run_ref(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("run_id"),
        "path": run.get("path"),
        "media": run.get("media"),
        "reference_srt": run.get("reference_srt"),
        "elapsed_sec": run.get("elapsed_sec"),
        "quality_score": run.get("quality_score"),
        "raw_segments": run.get("raw_segments"),
        "final_segments": run.get("final_segments"),
        "reference_segments": run.get("reference_segments"),
        "strict_final_pass": _strict_final_pass(run),
        "last_end_within_duration_bound": (run.get("final_gates") or {}).get("last_end_within_duration_bound"),
        "media_exists_now": _path_exists(run.get("media")),
        "reference_srt_exists_now": _path_exists(run.get("reference_srt")),
    }


def _quote(value: str | Path) -> str:
    return shlex.quote(str(value))


def _benchmark_command(
    *,
    media: str,
    reference_srt: str,
    primary_cache_path: str,
    recheck_cache_path: str,
    macro_cache_path: str,
) -> str:
    settings = [
        ("stt_primary_collect_cache_enabled", "true"),
        ("stt_primary_collect_cache_path", primary_cache_path),
        ("stt_recheck_collect_cache_enabled", "true"),
        ("stt_recheck_collect_cache_path", recheck_cache_path),
        ("subtitle_llm_macro_response_cache_enabled", "true"),
        ("subtitle_llm_macro_response_cache_path", macro_cache_path),
    ]
    setting_args = " ".join(
        f"--setting {_quote(f'{key}={value}')}" for key, value in settings
    )
    return (
        "QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/benchmark_subtitle_pipeline_variants.py "
        f"--suite modes --variants mode_high --media {_quote(media)} "
        f"--reference-srt {_quote(reference_srt)} --start-sec 0 --duration-sec 180 "
        f"--keep-artifacts {setting_args}"
    )


def build_next_run_plan(
    *,
    representative_media: str = DEFAULT_REPRESENTATIVE_MEDIA,
    representative_reference_srt: str = DEFAULT_REPRESENTATIVE_REFERENCE_SRT,
    output_dir: str = DEFAULT_BACKFILL_OUTPUT_DIR,
    benchmark_glob: str = DEFAULT_BENCHMARK_GLOB,
) -> dict[str, Any]:
    cache_dir = f"{output_dir}/collect_cache"
    primary_cache_path = f"{cache_dir}/stt_primary_collect.json"
    recheck_cache_path = f"{cache_dir}/stt_recheck_collect.json"
    macro_cache_path = f"{cache_dir}/macro_response.json"
    benchmark_command = _benchmark_command(
        media=representative_media,
        reference_srt=representative_reference_srt,
        primary_cache_path=primary_cache_path,
        recheck_cache_path=recheck_cache_path,
        macro_cache_path=macro_cache_path,
    )
    return {
        "representative_media": representative_media,
        "representative_reference_srt": representative_reference_srt,
        "start_sec": 0,
        "duration_sec": 180,
        "same_cache_paths_required": True,
        "cache_paths": {
            "stt_primary_collect": primary_cache_path,
            "stt_recheck_collect": recheck_cache_path,
            "macro_response": macro_cache_path,
        },
        "commands": {
            "preflight": (
                "QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py "
                f"--media {_quote(representative_media)} "
                f"--reference-srt {_quote(representative_reference_srt)} "
                f"--start-sec 0 --duration-sec 180 --output-dir {_quote(f'{output_dir}/preflight')}"
            ),
            "cache_write": benchmark_command,
            "cache_hit": benchmark_command,
            "accept_write": (
                "QT_QPA_PLATFORM=offscreen ./venv/bin/python "
                "tools/evaluate_reference_benchmark_acceptance.py "
                ".codex_work/benchmarks/subtitle_pipeline_variants/<write_run>/benchmark_results.json "
                f"--output-dir {_quote(f'{output_dir}/acceptance_write')}"
            ),
            "accept_hit": (
                "QT_QPA_PLATFORM=offscreen ./venv/bin/python "
                "tools/evaluate_reference_benchmark_acceptance.py "
                ".codex_work/benchmarks/subtitle_pipeline_variants/<hit_run>/benchmark_results.json "
                f"--output-dir {_quote(f'{output_dir}/acceptance_hit')}"
            ),
            "readiness_refresh": (
                "QT_QPA_PLATFORM=offscreen ./venv/bin/python "
                "tools/audit_stt_cache_backfill_readiness.py "
                f"--glob {_quote(benchmark_glob)} --output-dir {_quote(output_dir)} "
                f"--representative-media {_quote(representative_media)} "
                f"--representative-reference-srt {_quote(representative_reference_srt)}"
            ),
        },
        "forbidden_substitutes": [
            "generated_or_local_fixture",
            "X5_or_project_reference_fixture",
            "fallback_cached_audio_without_matching_srt",
            "preflight_only_without_reference_scored_benchmark",
            "real_media_cache_write_without_matching_cache_hit_replay",
            "profiler_or_cprofile_elapsed_as_speed_truth",
        ],
        "owner_review_gate": [
            "current_real_inputs_available=true",
            "strict real-media cache write run exists for each collect-cache family",
            "strict real-media cache hit replay exists for each collect-cache family",
            "accepted=true from evaluate_reference_benchmark_acceptance.py on write and hit runs",
            "final invalid/non-monotonic/overlap remains 0/0/0",
            "global canvas max active remains <=1",
            "collect-cache defaults remain false until explicit owner review",
        ],
    }


def build_readiness(
    runs: list[dict[str, Any]],
    *,
    defaults: dict[str, Any] | None = None,
    representative_media: str = DEFAULT_REPRESENTATIVE_MEDIA,
    representative_reference_srt: str = DEFAULT_REPRESENTATIVE_REFERENCE_SRT,
    output_dir: str = DEFAULT_BACKFILL_OUTPUT_DIR,
    benchmark_glob: str = DEFAULT_BENCHMARK_GLOB,
) -> dict[str, Any]:
    defaults = dict(DEFAULT_ADV_SETTINGS if defaults is None else defaults)
    real_runs = [run for run in runs if _is_real_media(run.get("media"))]
    generated_runs = [run for run in runs if not _is_real_media(run.get("media"))]
    current_real_inputs_available = any(
        _path_exists(run.get("media")) and _path_exists(run.get("reference_srt")) for run in real_runs
    )
    default_settings = {
        "stt_primary_collect_cache_enabled": bool(defaults.get("stt_primary_collect_cache_enabled", False)),
        "stt_recheck_collect_cache_enabled": bool(defaults.get("stt_recheck_collect_cache_enabled", False)),
    }
    families: dict[str, Any] = {}
    for family, rule in FAMILY_RULES.items():
        cache_keys = tuple(rule["cache_keys"])
        default_keys = tuple(rule["default_keys"])
        default_violations = [key for key in default_keys if bool(default_settings.get(key, False))]
        strict_real_hit = [
            _run_ref(run)
            for run in real_runs
            if _strict_final_pass(run) and _cache_hit_without_provider(run, cache_keys)
        ]
        strict_generated_hit = [
            _run_ref(run)
            for run in generated_runs
            if _strict_final_pass(run) and _cache_hit_without_provider(run, cache_keys)
        ]
        failed_hit = [
            _run_ref(run)
            for run in runs
            if not _strict_final_pass(run) and _cache_hit_without_provider(run, cache_keys)
        ]
        strict_real_write = [
            _run_ref(run)
            for run in real_runs
            if _strict_final_pass(run) and _cache_write_with_provider(run, cache_keys)
        ]
        blockers: list[str] = []
        if default_violations:
            blockers.append("collect_cache_default_enabled")
        if not current_real_inputs_available:
            blockers.append("representative_real_media_currently_unavailable")
        if not strict_real_write:
            blockers.append("missing_strict_real_media_cache_write_run")
        if not strict_real_hit:
            blockers.append("missing_strict_real_media_cache_hit_replay")
        if failed_hit and not strict_generated_hit:
            blockers.append("cache_hit_runs_fail_strict_final_gate")
        status = "hold_default_off"
        if default_violations:
            status = "blocked_default_enabled"
        elif strict_real_write and strict_real_hit:
            status = "real_backfill_present_owner_review_required"
        elif strict_real_hit:
            status = "hold_real_media_cache_write_required"
        elif strict_generated_hit:
            status = "hold_real_media_backfill_required"
        elif failed_hit:
            status = "hold_refresh_strict_generated_cache_hit_then_real_backfill"
        families[family] = {
            "status": status,
            "default_keys": {key: default_settings.get(key) for key in default_keys},
            "blockers": blockers,
            "strict_real_cache_hit_runs": strict_real_hit,
            "strict_generated_cache_hit_runs": strict_generated_hit,
            "strict_real_cache_write_runs": strict_real_write,
            "failed_cache_hit_runs": failed_hit,
        }
    return {
        "schema": "ai_subtitle_studio.stt_cache_backfill_readiness.v1",
        "note": "Analysis-only audit. It does not change runtime behavior or approve collect-cache defaults.",
        "run_count": len(runs),
        "real_media_run_count": len(real_runs),
        "generated_or_local_run_count": len(generated_runs),
        "current_real_inputs_available": current_real_inputs_available,
        "default_settings": default_settings,
        "families": families,
        "production_default_recommendation": "hold_default_off",
        "next_required_evidence": (
            "Run representative real-media first-180s backfill with cache write and cache-hit replay, "
            "then require strict final gates before any owner review of collect-cache defaults."
        ),
        "next_run_plan": build_next_run_plan(
            representative_media=representative_media,
            representative_reference_srt=representative_reference_srt,
            output_dir=output_dir,
            benchmark_glob=benchmark_glob,
        ),
    }


def _markdown_table(rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    sep = ["---"] * len(header)
    output = ["| " + " | ".join(str(item) for item in header) + " |", "| " + " | ".join(sep) + " |"]
    for row in rows[1:]:
        output.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(output)


def render_markdown(readiness: dict[str, Any]) -> str:
    family_rows: list[list[Any]] = [[
        "family",
        "status",
        "default_keys",
        "strict_real_hits",
        "strict_generated_hits",
        "failed_hits",
        "blockers",
    ]]
    for family, data in dict(readiness.get("families") or {}).items():
        family_rows.append([
            family,
            data.get("status"),
            data.get("default_keys"),
            len(data.get("strict_real_cache_hit_runs") or []),
            len(data.get("strict_generated_cache_hit_runs") or []),
            len(data.get("failed_cache_hit_runs") or []),
            ", ".join(data.get("blockers") or []),
        ])
    lines = [
        "# STT Cache Backfill Readiness Audit",
        "",
        "## Scope",
        "",
        "- Analysis-only audit from existing benchmark artifacts.",
        "- No runtime behavior, STT/STT2 policy, word precision policy, cache default, subtitle timing, save/load, render/export, or UI changed.",
        "- Collect-cache default promotion remains blocked without representative real-media backfill.",
        "",
        "## Summary",
        "",
        f"- Run count: `{readiness.get('run_count')}`",
        f"- Real-media run count: `{readiness.get('real_media_run_count')}`",
        f"- Generated/local run count: `{readiness.get('generated_or_local_run_count')}`",
        f"- Current real inputs available: `{readiness.get('current_real_inputs_available')}`",
        f"- Default settings: `{readiness.get('default_settings')}`",
        f"- Production default recommendation: `{readiness.get('production_default_recommendation')}`",
        f"- Next required evidence: {readiness.get('next_required_evidence')}",
        "",
        "## Families",
        "",
        _markdown_table(family_rows),
        "",
        "## Interpretation Guard",
        "",
        "- Do not enable `stt_recheck_collect_cache_enabled` or `stt_primary_collect_cache_enabled` by default from generated/local evidence.",
        "- Cache-hit replay must still pass strict final gates: invalid `0`, non-monotonic `0`, overlap `0`, global max-active `<=1`, and duration-bound pass.",
        "- Real-media write evidence without a matching cache-hit replay is not enough for default promotion.",
        "",
    ]
    next_run_plan = dict(readiness.get("next_run_plan") or {})
    if next_run_plan:
        commands = dict(next_run_plan.get("commands") or {})
        lines.extend([
            "## Next Real-Media Backfill Plan",
            "",
            f"- Representative media: `{next_run_plan.get('representative_media')}`",
            f"- Representative reference SRT: `{next_run_plan.get('representative_reference_srt')}`",
            f"- Start/duration: `{next_run_plan.get('start_sec')}` / `{next_run_plan.get('duration_sec')}` seconds",
            f"- Same cache paths required for write and hit: `{next_run_plan.get('same_cache_paths_required')}`",
            f"- Cache paths: `{next_run_plan.get('cache_paths')}`",
            "",
            "Run these only after the representative media and matching SRT are mounted:",
            "",
        ])
        for label in ("preflight", "cache_write", "cache_hit", "accept_write", "accept_hit", "readiness_refresh"):
            command = str(commands.get(label) or "").strip()
            if not command:
                continue
            lines.extend([f"### {label}", "", "```bash", command, "```", ""])
        lines.extend([
            "## Forbidden Substitutes",
            "",
        ])
        lines.extend(f"- `{item}`" for item in list(next_run_plan.get("forbidden_substitutes") or []))
        lines.extend([
            "",
            "## Owner Review Gate",
            "",
        ])
        lines.extend(f"- {item}" for item in list(next_run_plan.get("owner_review_gate") or []))
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], help="benchmark_results.json path")
    parser.add_argument("--glob", action="append", default=[], help="glob for benchmark_results.json files")
    parser.add_argument("--output-dir", required=True, help="directory for readiness JSON and Markdown")
    parser.add_argument("--representative-media", default=DEFAULT_REPRESENTATIVE_MEDIA)
    parser.add_argument("--representative-reference-srt", default=DEFAULT_REPRESENTATIVE_REFERENCE_SRT)
    args = parser.parse_args(argv)

    paths = _expand_inputs(args.input, args.glob)
    if not paths:
        parser.error("at least one existing --input or --glob match is required")
    output_dir = Path(args.output_dir)
    readiness = build_readiness(
        load_runs(paths),
        representative_media=args.representative_media,
        representative_reference_srt=args.representative_reference_srt,
        output_dir=str(output_dir),
        benchmark_glob=args.glob[-1] if args.glob else DEFAULT_BENCHMARK_GLOB,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "stt_cache_backfill_readiness.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "stt_cache_backfill_readiness.md").write_text(render_markdown(readiness), encoding="utf-8")
    print(output_dir / "stt_cache_backfill_readiness.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
