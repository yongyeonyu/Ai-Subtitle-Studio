from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from core.performance import hardware_profile  # noqa: E402
from tools.benchmark_tiniping_mode_search import (
    BenchmarkSeed,
    _adaptive_audio_profiles,
    _apply_method_overrides,
    _json_dump,
    _log,
    _mode_base_settings,
    _normalized_mode,
    _objective_rank,
    _row_quality,
    _row_speed,
    _row_with_effective_settings,
    _run_extract,
    _seed_from_payload,
    _seed_to_payload,
    _set_pair,
    _variant_row,
)


def _primary_scan(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    models: list[str],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    results_by_mode: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        mode_settings = _mode_base_settings(base_settings, mode)
        extract_name = f"phase1_primary_{mode}"
        chunk_source, extract_meta = _run_extract(
            media=media,
            settings=mode_settings,
            start_sec=start_sec,
            end_sec=end_sec,
            work_dir=run_dir,
            name=extract_name,
        )
        method = "stt1_only" if mode == "fast" else "stt1_word_precision"
        for primary_model in models:
            settings = _set_pair(mode_settings, primary_model, primary_model)
            settings = _apply_method_overrides(settings, method)
            row = _variant_row(
                name=f"{mode}__primary__{Path(primary_model).name.replace(':', '_')}",
                phase="phase1_primary",
                description=f"{mode} primary model scan",
                method=method,
                settings=settings,
                run_llm=bool(
                    mode == "high"
                    and str(settings.get("selected_model") or "").strip()
                    and "사용 안함" not in str(settings.get("selected_model") or "")
                ),
                chunk_source=chunk_source,
                work_dir=run_dir / "phase1_primary" / mode,
                reference=reference,
                span_sec=span_sec,
            )
            row["mode"] = mode
            row["scan_kind"] = "primary"
            row["primary_model"] = primary_model
            row["secondary_model"] = primary_model
            row["audio_profile"] = "mode_default"
            row["audio_profile_description"] = "모드 기본 오디오/VAD"
            row["audio_extract_elapsed_sec"] = extract_meta["elapsed_sec"]
            results_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase1 primary {mode}: {len(results_by_mode[mode])} candidates")
    return results_by_mode


def _pair_scan(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    models: list[str],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    results_by_mode: dict[str, list[dict[str, Any]]] = {"auto": [], "high": []}
    for mode in ("auto", "high"):
        mode_settings = _mode_base_settings(base_settings, mode)
        method = "selective_ensemble"
        chunk_source, extract_meta = _run_extract(
            media=media,
            settings=mode_settings,
            start_sec=start_sec,
            end_sec=end_sec,
            work_dir=run_dir,
            name=f"phase1_pairs_{mode}",
        )
        for primary_model in models:
            for secondary_model in models:
                settings = _set_pair(mode_settings, primary_model, secondary_model)
                settings = _apply_method_overrides(settings, method)
                row = _variant_row(
                    name=(
                        f"{mode}__pair__{Path(primary_model).name.replace(':', '_')}"
                        f"__{Path(secondary_model).name.replace(':', '_')}"
                    ),
                    phase="phase1_pairs",
                    description=f"{mode} STT1/STT2 pair scan",
                    method=method,
                    settings=settings,
                    run_llm=bool(
                        mode == "high"
                        and str(settings.get("selected_model") or "").strip()
                        and "사용 안함" not in str(settings.get("selected_model") or "")
                    ),
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase1_pairs" / mode,
                    reference=reference,
                    span_sec=span_sec,
                )
                row["mode"] = mode
                row["scan_kind"] = "pair"
                row["primary_model"] = primary_model
                row["secondary_model"] = secondary_model
                row["audio_profile"] = "mode_default"
                row["audio_profile_description"] = "모드 기본 오디오/VAD"
                row["audio_extract_elapsed_sec"] = extract_meta["elapsed_sec"]
                results_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase1 pairs {mode}: {len(results_by_mode[mode])} candidates")
    return results_by_mode


def _collect_phase1_seeds(
    primary_rows: dict[str, list[dict[str, Any]]],
    pair_rows: dict[str, list[dict[str, Any]]],
) -> dict[str, list[BenchmarkSeed]]:
    out: dict[str, list[BenchmarkSeed]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        if mode == "fast":
            ranked = _objective_rank(primary_rows.get(mode, []), mode, 3)
        else:
            ranked = _objective_rank(pair_rows.get(mode, []), mode, 3)
        for row in ranked:
            settings = dict(row.get("effective_settings") or row.get("settings") or {})
            out[mode].append(
                BenchmarkSeed(
                    mode=mode,
                    primary_model=str(row.get("primary_model") or settings.get("selected_whisper_model") or ""),
                    secondary_model=str(row.get("secondary_model") or settings.get("selected_whisper_model_secondary") or ""),
                    method=str(row.get("method") or ""),
                    run_llm=bool(row.get("run_llm")),
                    audio_profile=str(row.get("audio_profile") or "mode_default"),
                    audio_profile_description=str(row.get("audio_profile_description") or "모드 기본 오디오/VAD"),
                    settings=settings,
                    objective_reason=str(row.get("mode_objective_reason") or ""),
                )
            )
    return out


def _audio_scan(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    seeds_by_mode: dict[str, list[BenchmarkSeed]],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        profiles = _adaptive_audio_profiles(base_settings)
        seeds = list(seeds_by_mode.get(mode) or [])
        for seed in seeds:
            seed_settings = dict(seed.settings or _mode_base_settings(base_settings, mode))
            for profile in profiles:
                settings = {**seed_settings, **profile.overrides}
                chunk_source, extract_meta = _run_extract(
                    media=media,
                    settings=settings,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    work_dir=run_dir,
                    name=f"phase2_{mode}_{profile.name}_{Path(seed.primary_model).name}",
                )
                row = _variant_row(
                    name=f"{mode}__audio__{profile.name}__{Path(seed.primary_model).name.replace(':', '_')}",
                    phase="phase2_audio",
                    description=f"{mode} audio/VAD scan",
                    method=seed.method,
                    settings=settings,
                    run_llm=seed.run_llm,
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase2_audio" / mode / profile.name,
                    reference=reference,
                    span_sec=span_sec,
                )
                row["mode"] = mode
                row["primary_model"] = seed.primary_model
                row["secondary_model"] = seed.secondary_model
                row["audio_profile"] = profile.name
                row["audio_profile_description"] = profile.description
                row["audio_extract_elapsed_sec"] = extract_meta["elapsed_sec"]
                rows_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase2 audio {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _collect_audio_seeds(audio_rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[BenchmarkSeed]]:
    out: dict[str, list[BenchmarkSeed]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        ranked = _objective_rank(audio_rows.get(mode, []), mode, 3)
        for row in ranked:
            out[mode].append(_seed_from_payload(row))
    return out


def _method_scan(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    seeds_by_mode: dict[str, list[BenchmarkSeed]],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    methods_by_mode = {
        "fast": ("stt1_only", "selective_ensemble"),
        "auto": ("stt1_word_precision", "selective_ensemble", "parallel_ensemble"),
        "high": ("selective_ensemble", "parallel_ensemble", "proposed_lora_deep_gate"),
    }
    for mode in ("fast", "auto", "high"):
        seeds = list(seeds_by_mode.get(mode) or [])
        for seed in seeds:
            base_seed_settings = dict(seed.settings or _mode_base_settings(base_settings, mode))
            for method in methods_by_mode[mode]:
                settings = _apply_method_overrides(base_seed_settings, method)
                chunk_source, _extract_meta = _run_extract(
                    media=media,
                    settings=settings,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    work_dir=run_dir,
                    name=f"phase3_{mode}_{method}_{Path(seed.primary_model).name}",
                )
                row = _variant_row(
                    name=f"{mode}__method__{method}__{Path(seed.primary_model).name.replace(':', '_')}",
                    phase="phase3_method",
                    description=f"{mode} method scan",
                    method=method,
                    settings=settings,
                    run_llm=seed.run_llm,
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase3_method" / mode / method,
                    reference=reference,
                    span_sec=span_sec,
                )
                row["mode"] = mode
                row["primary_model"] = seed.primary_model
                row["secondary_model"] = seed.secondary_model
                row["audio_profile"] = seed.audio_profile
                row["audio_profile_description"] = seed.audio_profile_description
                rows_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase3 method {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _cached_postprocess_scan(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    method_rows: dict[str, list[dict[str, Any]]],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        ranked = _objective_rank(method_rows.get(mode, []), mode, 3)
        for row in ranked:
            settings = dict(row.get("effective_settings") or row.get("settings") or _mode_base_settings(base_settings, mode))
            cached_raw = row.get("raw_segments_artifact")
            if not cached_raw:
                continue
            settings["_benchmark_cached_raw_segments_path"] = str(cached_raw)
            chunk_source, _extract_meta = _run_extract(
                media=media,
                settings=settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase4_{mode}_{Path(str(row.get('name') or 'row')).name}",
            )
            cached_row = _variant_row(
                name=f"{mode}__cached__{Path(str(row.get('name') or 'row')).name}",
                phase="phase4_cached",
                description=f"{mode} cached postprocess scan",
                method=str(row.get("method") or ""),
                settings=settings,
                run_llm=bool(row.get("run_llm")),
                chunk_source=chunk_source,
                work_dir=run_dir / "phase4_cached" / mode,
                reference=reference,
                span_sec=span_sec,
            )
            cached_row["mode"] = mode
            cached_row["primary_model"] = row.get("primary_model")
            cached_row["secondary_model"] = row.get("secondary_model")
            cached_row["audio_profile"] = row.get("audio_profile")
            cached_row["audio_profile_description"] = row.get("audio_profile_description")
            rows_by_mode[mode].append(_row_with_effective_settings(cached_row, settings))
        _log(f"phase4 cached {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _finalists_from_cached(rows_by_mode: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {
        mode: _objective_rank(rows_by_mode.get(mode, []), mode, 3)
        for mode in ("fast", "auto", "high")
    }


def _long_run_validation(
    *,
    media: Path,
    reference: list[dict[str, Any]],
    finalists: dict[str, list[dict[str, Any]]],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    span_sec: float,
) -> dict[str, list[dict[str, Any]]]:
    rows_by_mode: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    for mode in ("fast", "auto", "high"):
        rows = list(finalists.get(mode) or [])
        for row in rows:
            settings = dict(row.get("effective_settings") or row.get("settings") or _mode_base_settings(base_settings, mode))
            chunk_source, extract_meta = _run_extract(
                media=media,
                settings=settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase5_{mode}_{Path(str(row.get('name') or 'row')).name}",
            )
            long_row = _variant_row(
                name=f"phase5_long_{mode}_{Path(str(row.get('name') or 'row')).name}",
                phase="phase5_long",
                description=f"{mode} long-run validation",
                method=str(row.get("method") or ""),
                settings=settings,
                run_llm=bool(row.get("run_llm")),
                chunk_source=chunk_source,
                work_dir=run_dir / "phase5_long" / mode,
                reference=reference,
                span_sec=span_sec,
            )
            long_row["mode"] = mode
            long_row["primary_model"] = str(row.get("primary_model") or "")
            long_row["secondary_model"] = str(row.get("secondary_model") or "")
            long_row["audio_profile"] = row.get("audio_profile")
            long_row["audio_profile_description"] = row.get("audio_profile_description")
            long_row["audio_extract_elapsed_sec"] = extract_meta["elapsed_sec"]
            rows_by_mode[mode].append(_row_with_effective_settings(long_row, settings))
        _log(f"phase5 long {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _winner_rows(long_rows: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    winners: dict[str, dict[str, Any]] = {}
    for mode, rows in long_rows.items():
        picked = _objective_rank(rows, mode, 1)
        winners[mode] = dict(picked[0]) if picked else {}
    return winners


def _mode_ui_tag(mode: str) -> str:
    return {"fast": "Fast", "auto": "Auto", "high": "High"}[_normalized_mode(mode)]


def _winner_summary(winner: dict[str, Any]) -> dict[str, Any]:
    settings = dict(winner.get("effective_settings") or {})
    quality = dict(winner.get("quality") or {})
    readability = dict(winner.get("readability") or {})
    return {
        "primary_model": str(winner.get("primary_model") or settings.get("selected_whisper_model") or ""),
        "secondary_model": str(winner.get("secondary_model") or settings.get("selected_whisper_model_secondary") or ""),
        "method": str(winner.get("method") or ""),
        "audio_profile": str(winner.get("audio_profile") or ""),
        "quality_score": float(quality.get("quality_score", 0.0) or 0.0),
        "timing_score": float(quality.get("timing_score", 0.0) or 0.0),
        "local_text_score": float(quality.get("local_text_score", 0.0) or 0.0),
        "readability_score": float(readability.get("readability_score", 0.0) or 0.0),
        "speed_score": float(winner.get("speed_score", 0.0) or 0.0),
        "elapsed_sec": float(winner.get("elapsed_sec", 0.0) or 0.0),
        "settings": settings,
    }


def _recommendations_payload(
    *,
    media: Path,
    reference_srt: Path,
    short_rows: dict[str, list[dict[str, Any]]],
    long_rows: dict[str, list[dict[str, Any]]],
    winners: dict[str, dict[str, Any]],
    models: list[str],
    run_dir: Path,
) -> dict[str, Any]:
    return {
        "schema": "ai_subtitle_studio.tiniping_mode_search.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media": str(media),
        "reference_srt": str(reference_srt),
        "run_dir": str(run_dir),
        "hardware": hardware_profile(),
        "models_tested": models,
        "short_phase_top3": {
            mode: [
                {
                    "name": row.get("name"),
                    "primary_model": row.get("primary_model"),
                    "secondary_model": row.get("secondary_model"),
                    "method": row.get("method"),
                    "audio_profile": row.get("audio_profile"),
                    "quality_score": _row_quality(row),
                    "speed_score": _row_speed(row),
                    "elapsed_sec": float(row.get("elapsed_sec", 0.0) or 0.0),
                }
                for row in rows[:3]
            ]
            for mode, rows in short_rows.items()
        },
        "long_phase_top3": {
            mode: [
                {
                    "name": row.get("name"),
                    "primary_model": row.get("primary_model"),
                    "secondary_model": row.get("secondary_model"),
                    "method": row.get("method"),
                    "audio_profile": row.get("audio_profile"),
                    "quality_score": _row_quality(row),
                    "speed_score": _row_speed(row),
                    "elapsed_sec": float(row.get("elapsed_sec", 0.0) or 0.0),
                }
                for row in rows[:3]
            ]
            for mode, rows in long_rows.items()
        },
        "winners": {mode: _winner_summary(winner) for mode, winner in winners.items()},
    }


def _write_manual_summary(*, summary_path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Tiniping Mode Benchmark Summary",
        "",
        f"- Media: `{payload['media']}`",
        f"- Reference: `{payload['reference_srt']}`",
        f"- Run dir: `{payload['run_dir']}`",
        "",
        "## Final winners",
        "",
        "| Mode | STT1 | STT2 | Method | Audio/VAD | Quality | Speed | Time(s) |",
        "|---|---|---|---|---|---:|---:|---:|",
    ]
    for mode in ("fast", "auto", "high"):
        winner = dict(payload.get("winners", {}).get(mode) or {})
        lines.append(
            "| {mode} | `{stt1}` | `{stt2}` | `{method}` | `{audio}` | {quality:.3f} | {speed:.3f} | {elapsed:.3f} |".format(
                mode=_mode_ui_tag(mode),
                stt1=winner.get("primary_model", ""),
                stt2=winner.get("secondary_model", ""),
                method=winner.get("method", ""),
                audio=winner.get("audio_profile", ""),
                quality=float(winner.get("quality_score", 0.0) or 0.0),
                speed=float(winner.get("speed_score", 0.0) or 0.0),
                elapsed=float(winner.get("elapsed_sec", 0.0) or 0.0),
            )
        )
    lines.extend(["", "## UI recommendation tags", ""])
    model_tags: dict[str, list[str]] = {}
    for mode, winner in dict(payload.get("winners") or {}).items():
        tag = _mode_ui_tag(mode)
        stt1 = str(winner.get("primary_model") or "")
        stt2 = str(winner.get("secondary_model") or "")
        for model in (stt1, stt2):
            if not model:
                continue
            model_tags.setdefault(model, [])
            if tag not in model_tags[model]:
                model_tags[model].append(tag)
    for model, tags in sorted(model_tags.items()):
        lines.append(f"- `{model}` -> [{' / '.join(tags)}]")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
