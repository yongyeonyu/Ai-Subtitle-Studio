#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.performance import hardware_profile  # noqa: E402
from tools.benchmark_subtitle_pipeline_variants import (  # noqa: E402
    AudioProfile,
    Variant,
    _base_benchmark_settings,
    _bind_processor_settings,
    _copy_chunk_dir,
    _load_vad,
    _mode_profile_method,
    _rank_rows,
    _run_variant,
    _write_markdown,
    benchmark_audio_profiles,
    clip_reference,
    parse_srt,
)


DEFAULT_MEDIA = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처.MP4")
DEFAULT_REFERENCE = Path("/Users/u_mo_c/Downloads/티니핑/티니핑_유스어드벤처_완성.srt")
DEFAULT_SHORT_SEC = 180.0
DEFAULT_LONG_SEC = 660.0
MODEL_CATALOG = [
    "whisperkit-persistent:large-v3-v20240930_626MB",
    "whisperkit-persistent:large-v3-v20240930_turbo_632MB",
    "mlx-community/whisper-large-v3-mlx",
    "mlx-community/whisper-large-v3-turbo",
    "youngouk/whisper-medium-komixv2-mlx",
    "mlx-community/whisper-medium-mlx",
    "mlx-community/whisper-large-v2-mlx",
    "mlx-community/distil-whisper-large-v3",
]
MODEL_LABELS = {
    "whisperkit-persistent:large-v3-v20240930_626MB": "WhisperKit Large V3",
    "whisperkit-persistent:large-v3-v20240930_turbo_632MB": "WhisperKit Large V3 Turbo",
    "mlx-community/whisper-large-v3-mlx": "MLX Whisper Large V3",
    "mlx-community/whisper-large-v3-turbo": "MLX Whisper Large V3 Turbo",
    "youngouk/whisper-medium-komixv2-mlx": "KomixV2 MLX",
    "mlx-community/whisper-medium-mlx": "MLX Whisper Medium",
    "mlx-community/whisper-large-v2-mlx": "MLX Whisper Large V2",
    "mlx-community/distil-whisper-large-v3": "MLX Distil Whisper Large V3",
}
REMOVED_WHISPER_MODELS = {
    "whisperkit-persistent:large-v3",
    "coreml:large-v3-v20240930_626MB",
    "whisper-medium-komixv2",
    "seastar105/whisper-medium-komixv2",
    "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
    "ghost613/faster-whisper-large-v3-turbo-korean",
    "Systran/faster-whisper-large-v3",
    "faster-whisper-large-v3",
    "whisper.cpp:large-v3-turbo",
    "whisper_cpp:large-v3-turbo",
    "whisper-cpp:large-v3-turbo",
    "mlx-community/whisper-medium.en-mlx",
    "mlx-community/whisper-small-mlx",
    "mlx-community/whisper-small.en-mlx",
    "mlx-community/whisper-base-mlx",
    "mlx-community/whisper-base.en-mlx",
    "mlx-community/whisper-tiny-mlx",
    "mlx-community/whisper-tiny.en-mlx",
    "medium.en",
    "small",
    "small.en",
    "base",
    "base.en",
    "tiny",
    "tiny.en",
    "large-v3",
    "large-v3-turbo",
    "turbo",
    "large-v2",
    "large-v1",
    "large",
    "medium",
    "distil-large-v3",
    "distil-large-v2",
    "distil-medium.en",
    "distil-small.en",
}


@dataclass(frozen=True)
class BenchmarkSeed:
    mode: str
    primary_model: str
    secondary_model: str
    method: str
    run_llm: bool
    audio_profile: str
    audio_profile_description: str
    settings: dict[str, Any]
    objective_reason: str


def _seed_to_payload(seed: BenchmarkSeed) -> dict[str, Any]:
    return asdict(seed)


def _seed_from_payload(payload: dict[str, Any]) -> BenchmarkSeed:
    item = dict(payload or {})
    return BenchmarkSeed(
        mode=str(item.get("mode") or "fast"),
        primary_model=str(item.get("primary_model") or ""),
        secondary_model=str(item.get("secondary_model") or ""),
        method=str(item.get("method") or "stt1_only"),
        run_llm=bool(item.get("run_llm")),
        audio_profile=str(item.get("audio_profile") or "phase1"),
        audio_profile_description=str(item.get("audio_profile_description") or "phase1 seed"),
        settings=dict(item.get("settings") or {}),
        objective_reason=str(item.get("objective_reason") or ""),
    )


def _log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[tiniping-bench {stamp}] {message}", flush=True)


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _filter_available_whisper_models(models: Iterable[str]) -> list[str]:
    removed = {str(model).lower() for model in REMOVED_WHISPER_MODELS}
    filtered: list[str] = []
    for model in models:
        value = str(model or "").strip()
        if not value:
            continue
        if value in REMOVED_WHISPER_MODELS or value.lower() in removed:
            continue
        if value not in filtered:
            filtered.append(value)
    return filtered


def _discover_whisper_models() -> list[str]:
    models = list(MODEL_CATALOG)
    hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    if os.path.isdir(hf_cache_dir):
        for folder_name in sorted(os.listdir(hf_cache_dir)):
            if not folder_name.startswith("models--") or "whisper" not in folder_name.lower():
                continue
            repo_name = folder_name.replace("models--", "", 1).replace("--", "/", 1)
            models.append(repo_name)
    return _filter_available_whisper_models(models)


def _model_label(model: str) -> str:
    value = str(model or "").strip()
    return MODEL_LABELS.get(value, value)


def _normalized_mode(mode: str) -> str:
    key = str(mode or "").strip().lower()
    if key in {"auto", "balanced"}:
        return "auto"
    if key in {"high", "precise"}:
        return "high"
    return "fast"


def _mode_preset_key(mode: str) -> str:
    normalized = _normalized_mode(mode)
    return {"fast": "fast", "auto": "balanced", "high": "precise"}[normalized]


def _mode_base_settings(base_settings: dict[str, Any], mode: str) -> dict[str, Any]:
    normalized = _normalized_mode(mode)
    settings = dict(base_settings)
    settings["_ignore_saved_quality_preset_once"] = True
    settings["subtitle_mode"] = normalized
    settings["mode"] = normalized
    settings["user_facing_mode"] = normalized
    settings["simple_operation_mode"] = normalized
    settings["stt_quality_preset"] = _mode_preset_key(normalized)
    if normalized == "high":
        llm_model = str(settings.get("selected_model") or "").strip()
        if not llm_model or "사용 안함" in llm_model:
            settings["selected_model"] = "exaone3.5:2.4b"
            settings["selected_llm_provider"] = "ollama"
            settings["subtitle_llm_user_selected"] = True
    from core.mode_policy import apply_mode_runtime_settings

    out = apply_mode_runtime_settings(settings)
    out.update(
        {
            "benchmark_runtime_profile": "tiniping-mode-search",
            "stt_backend_policy": "legacy",
            "runtime_npu_acceleration_enabled": False,
            "apple_m_pipeline_parallel_enabled": False,
            "stt_npu_prefer_enabled": False,
            "whisperkit_native_auto_enabled": False,
            "stt_primary_fast_native_enabled": False,
            "stt_primary_fast_native_model": "",
            "reuse_preprocessed_audio_cache": False,
            "vad_detection_cache_enabled": False,
            "autopilot_stage_cache_enabled": False,
        }
    )
    return out


def _apply_method_overrides(settings: dict[str, Any], method: str) -> dict[str, Any]:
    out = dict(settings)
    if method == "stt1_only":
        out.update(
            {
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
            }
        )
        return out
    if method == "stt1_word_precision":
        out.update(
            {
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": True,
            }
        )
        return out
    if method == "selective_ensemble":
        out.update(
            {
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }
        )
        return out
    if method == "parallel_ensemble":
        out.update(
            {
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": True,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_mode": "off",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
            }
        )
        return out
    if method == "proposed_lora_deep_gate":
        out.update(
            {
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": True,
                "stt_word_timestamps_mode": "selective",
                "stt_word_timestamps_default_enabled": False,
                "stt_word_timestamps_precision_enabled": True,
            }
        )
        return out
    raise RuntimeError(f"unsupported method: {method}")


def _set_pair(settings: dict[str, Any], primary_model: str, secondary_model: str) -> dict[str, Any]:
    out = dict(settings)
    out["selected_whisper_model"] = str(primary_model or "").strip()
    out["selected_whisper_model_secondary"] = str(secondary_model or "").strip()
    return out


def _seed_name(seed: BenchmarkSeed) -> str:
    mode = _normalized_mode(seed.mode)
    return (
        f"{mode}__{seed.audio_profile}__"
        f"{Path(seed.primary_model).name.replace(':', '_')}__"
        f"{Path(seed.secondary_model).name.replace(':', '_')}__"
        f"{seed.method}"
    )


def _adaptive_audio_profiles(base_settings: dict[str, Any]) -> list[AudioProfile]:
    fresh = {
        "reuse_preprocessed_audio_cache": False,
        "vad_detection_cache_enabled": False,
        "autopilot_stage_cache_enabled": False,
        "review_vad_before_stt_enabled": True,
        "vad_post_stt_align_enabled": True,
    }
    return [
        AudioProfile(
            name="adaptive_voice_change_balanced",
            description="음성 변화 구간마다 오디오/VAD를 가변 적용하는 균형형 경로입니다.",
            overrides={
                **fresh,
                "selected_audio_ai": "none",
                "selected_vad": "ten_vad",
                "use_basic_filter": True,
                "audio_chunk_routing_enabled": True,
                "audio_chunk_route_vad_enabled": True,
                "audio_chunk_profile_sec": 18.0,
                "scan_cut_audio_gain_enabled": True,
                "cut_boundary_detection_enabled": True,
                "cut_boundary_enabled": True,
                "scan_cut_enabled": True,
                "scan_cut_auto_enabled": True,
                "vad_threshold": 0.46,
                "ten_vad_threshold": 0.46,
                "review_vad_speech_pad_sec": 0.28,
                "review_vad_min_silence_sec": 0.65,
            },
        ),
        AudioProfile(
            name="adaptive_voice_change_quality",
            description="음성 변화 구간마다 quality 우선 오디오/VAD를 가변 적용합니다.",
            overrides={
                **fresh,
                "selected_audio_ai": "deepfilter",
                "selected_vad": "silero",
                "use_basic_filter": True,
                "audio_chunk_routing_enabled": True,
                "audio_chunk_route_vad_enabled": True,
                "audio_chunk_profile_sec": 14.0,
                "scan_cut_audio_gain_enabled": True,
                "cut_boundary_detection_enabled": True,
                "cut_boundary_enabled": True,
                "scan_cut_enabled": True,
                "scan_cut_auto_enabled": True,
                "vad_threshold": 0.40,
                "review_vad_speech_pad_sec": 0.28,
                "review_vad_min_silence_sec": 0.60,
            },
        ),
        AudioProfile(
            name="adaptive_voice_change_fast",
            description="음성 변화 구간만 빠르게 재조정하는 가벼운 가변 오디오/VAD 경로입니다.",
            overrides={
                **fresh,
                "selected_audio_ai": "rnnoise",
                "selected_vad": "silero",
                "use_basic_filter": True,
                "audio_chunk_routing_enabled": True,
                "audio_chunk_route_vad_enabled": True,
                "audio_chunk_profile_sec": 22.0,
                "scan_cut_audio_gain_enabled": False,
                "cut_boundary_detection_enabled": False,
                "cut_boundary_enabled": False,
                "scan_cut_enabled": False,
                "scan_cut_auto_enabled": False,
                "vad_threshold": 0.40,
                "review_vad_speech_pad_sec": 0.30,
                "review_vad_min_silence_sec": 0.55,
            },
        ),
    ]


def _run_extract(
    *,
    media: Path,
    settings: dict[str, Any],
    start_sec: float,
    end_sec: float,
    work_dir: Path,
    name: str,
) -> tuple[Path, dict[str, Any]]:
    extractor = VideoProcessor()
    _bind_processor_settings(extractor, settings)
    started = time.perf_counter()
    try:
        chunk_dir_text, _vad_segments = extractor.extract_audio(
            str(media),
            target_start_sec=float(start_sec),
            target_end_sec=float(end_sec),
            is_single_segment=False,
        )
    finally:
        extractor.release_runtime_models()
    elapsed = time.perf_counter() - started
    chunk_source = Path(chunk_dir_text)
    if not chunk_source.exists():
        raise RuntimeError(f"audio chunk extraction failed: {chunk_source}")
    copied = _copy_chunk_dir(chunk_source, work_dir / "_seed_chunks" / name)
    return copied, {
        "name": name,
        "elapsed_sec": round(elapsed, 3),
        "chunk_dir": str(copied),
        "vad_segments": len(_load_vad(copied)),
    }


def _row_quality(row: dict[str, Any]) -> float:
    return float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)


def _row_speed(row: dict[str, Any]) -> float:
    return float(row.get("speed_score", 0.0) or 0.0)


def _row_timing(row: dict[str, Any]) -> float:
    return float(dict(row.get("quality") or {}).get("timing_score", 0.0) or 0.0)


def _row_local_text(row: dict[str, Any]) -> float:
    return float(dict(row.get("quality") or {}).get("local_text_score", 0.0) or 0.0)


def _objective_rank(rows: list[dict[str, Any]], mode: str, top_n: int) -> list[dict[str, Any]]:
    clean_rows = [dict(row) for row in rows if not str(row.get("error") or "").strip()]
    ranked = _rank_rows(clean_rows, objective="reference", ranking_policy="speed_weighted")
    normalized = _normalized_mode(mode)
    scored: list[tuple[tuple[float, ...], dict[str, Any]]] = []
    for row in ranked:
        quality = _row_quality(row)
        speed = _row_speed(row)
        timing = _row_timing(row)
        local_text = _row_local_text(row)
        elapsed = float(row.get("elapsed_sec", 0.0) or 0.0)
        if normalized == "fast":
            in_band = 1.0 if 50.0 <= quality <= 80.0 else 0.0
            band_penalty = abs(65.0 - min(80.0, max(50.0, quality)))
            sort_key = (
                in_band,
                -elapsed,
                -speed,
                -quality,
                -local_text,
                -timing,
                -band_penalty,
            )
            reason = f"quality={quality:.1f}, speed={speed:.1f}, elapsed={elapsed:.1f}s"
        elif normalized == "auto":
            in_band = 1.0 if 70.0 <= quality <= 100.0 and 70.0 <= speed <= 100.0 else 0.0
            balance = 100.0 - abs(quality - speed)
            combined = balance * 0.55 + min(quality, speed) * 0.45
            sort_key = (
                in_band,
                combined,
                balance,
                min(quality, speed),
                quality,
                speed,
                -elapsed,
            )
            reason = f"quality={quality:.1f}, speed={speed:.1f}, balance={balance:.1f}"
        else:
            combined = quality * 0.72 + timing * 0.18 + local_text * 0.10
            sort_key = (
                combined,
                quality,
                timing,
                local_text,
                -elapsed,
            )
            reason = f"quality={quality:.1f}, timing={timing:.1f}, local={local_text:.1f}"
        row["mode_objective_reason"] = reason
        scored.append((sort_key, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _key, row in scored[:top_n]]


def _variant_row(
    *,
    name: str,
    phase: str,
    description: str,
    method: str,
    settings: dict[str, Any],
    run_llm: bool,
    chunk_source: Path,
    work_dir: Path,
    reference: list[dict[str, Any]],
    span_sec: float,
) -> dict[str, Any]:
    variant = Variant(
        name=name,
        phase=phase,
        description=description,
        method=method,
        overrides=dict(settings),
        run_llm=bool(run_llm),
    )
    base_settings = dict(settings)
    base_settings["_benchmark_span_sec"] = float(span_sec)
    return _run_variant(
        variant,
        chunk_source=chunk_source,
        work_dir=work_dir,
        base_settings=base_settings,
        reference=reference,
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
        if mode == "fast":
            method = "stt1_only"
        else:
            method = "stt1_word_precision"
        for primary_model in models:
            settings = _set_pair(mode_settings, primary_model, primary_model)
            settings = _apply_method_overrides(settings, method)
            row = _variant_row(
                name=f"{mode}__primary__{Path(primary_model).name.replace(':', '_')}",
                phase="phase1_primary",
                description=f"{mode} primary model scan",
                method=method,
                settings=settings,
                run_llm=bool(mode == "high" and str(settings.get("selected_model") or "").strip() and "사용 안함" not in str(settings.get("selected_model") or "")),
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
                    run_llm=bool(mode == "high" and str(settings.get("selected_model") or "").strip() and "사용 안함" not in str(settings.get("selected_model") or "")),
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
        _log(f"phase1 pair {mode}: {len(results_by_mode[mode])} candidates")
    return results_by_mode


def _seed_from_row(row: dict[str, Any]) -> BenchmarkSeed:
    settings = dict(row.get("effective_settings") or row.get("settings_snapshot") or row.get("settings") or {})
    return BenchmarkSeed(
        mode=str(row.get("mode") or "fast"),
        primary_model=str(row.get("primary_model") or settings.get("selected_whisper_model") or ""),
        secondary_model=str(row.get("secondary_model") or settings.get("selected_whisper_model_secondary") or ""),
        method=str(row.get("method") or ""),
        run_llm=bool(row.get("run_llm")),
        audio_profile=str(row.get("audio_profile") or "mode_default"),
        audio_profile_description=str(row.get("audio_profile_description") or "모드 기본 오디오/VAD"),
        settings=settings,
        objective_reason=str(row.get("mode_objective_reason") or ""),
    )


def _row_with_effective_settings(row: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["effective_settings"] = dict(settings)
    return item


def _collect_phase1_seeds(primary_rows: dict[str, list[dict[str, Any]]], pair_rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[BenchmarkSeed]]:
    seeds_by_mode: dict[str, list[BenchmarkSeed]] = {"fast": [], "auto": [], "high": []}
    fast_top = _objective_rank(primary_rows["fast"], "fast", 2)
    seeds_by_mode["fast"] = [_seed_from_row(row) for row in fast_top]
    auto_pool = list(primary_rows["auto"]) + list(pair_rows["auto"])
    auto_top = _objective_rank(auto_pool, "auto", 2)
    seeds_by_mode["auto"] = [_seed_from_row(row) for row in auto_top]
    high_pool = list(primary_rows["high"]) + list(pair_rows["high"])
    high_top = _objective_rank(high_pool, "high", 2)
    seeds_by_mode["high"] = [_seed_from_row(row) for row in high_top]
    return seeds_by_mode


def _audio_profile_catalog(base_settings: dict[str, Any]) -> list[AudioProfile]:
    profiles = benchmark_audio_profiles(base_settings)
    profiles.extend(_adaptive_audio_profiles(base_settings))
    deduped: list[AudioProfile] = []
    seen: set[str] = set()
    for profile in profiles:
        if profile.name in seen:
            continue
        seen.add(profile.name)
        deduped.append(profile)
    return deduped


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
    for mode, seeds in seeds_by_mode.items():
        mode_base = _mode_base_settings(base_settings, mode)
        profiles = _audio_profile_catalog(mode_base)
        extracts: dict[str, tuple[Path, dict[str, Any], AudioProfile]] = {}
        for profile in profiles:
            profile_settings = {**mode_base, **profile.overrides}
            chunk_source, extract_meta = _run_extract(
                media=media,
                settings=profile_settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase2_audio_{mode}_{profile.name}",
            )
            extracts[profile.name] = (chunk_source, extract_meta, profile)
        for seed in seeds:
            for profile_name, (chunk_source, extract_meta, profile) in extracts.items():
                settings = {**mode_base, **profile.overrides}
                settings = _set_pair(settings, seed.primary_model, seed.secondary_model)
                settings = _apply_method_overrides(settings, seed.method)
                row = _variant_row(
                    name=f"{_seed_name(seed)}__{profile_name}",
                    phase="phase2_audio",
                    description=f"{mode} audio sweep",
                    method=seed.method,
                    settings=settings,
                    run_llm=seed.run_llm,
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase2_audio" / mode / profile_name,
                    reference=reference,
                    span_sec=span_sec,
                )
                row["mode"] = mode
                row["primary_model"] = seed.primary_model
                row["secondary_model"] = seed.secondary_model
                row["audio_profile"] = profile_name
                row["audio_profile_description"] = profile.description
                row["audio_extract_elapsed_sec"] = extract_meta["elapsed_sec"]
                rows_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase2 audio {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _collect_audio_seeds(audio_rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[BenchmarkSeed]]:
    seeds_by_mode: dict[str, list[BenchmarkSeed]] = {"fast": [], "auto": [], "high": []}
    for mode, rows in audio_rows.items():
        seeds_by_mode[mode] = [_seed_from_row(row) for row in _objective_rank(rows, mode, 1)]
    return seeds_by_mode


def _method_candidates_for_mode(mode: str) -> list[str]:
    normalized = _normalized_mode(mode)
    if normalized == "fast":
        return ["stt1_only", "selective_ensemble"]
    if normalized == "auto":
        return ["stt1_word_precision", "selective_ensemble", "parallel_ensemble"]
    return ["stt1_word_precision", "selective_ensemble", "parallel_ensemble", "proposed_lora_deep_gate"]


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
    profile_lookup: dict[str, AudioProfile] = {}
    for mode in ("fast", "auto", "high"):
        mode_base = _mode_base_settings(base_settings, mode)
        for profile in _audio_profile_catalog(mode_base):
            profile_lookup[f"{mode}:{profile.name}"] = profile
    for mode, seeds in seeds_by_mode.items():
        mode_base = _mode_base_settings(base_settings, mode)
        for seed in seeds[:2]:
            profile = profile_lookup.get(f"{mode}:{seed.audio_profile}")
            profile_overrides = dict(profile.overrides if profile else {})
            extract_settings = {**mode_base, **profile_overrides}
            chunk_source, _extract_meta = _run_extract(
                media=media,
                settings=extract_settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase3_method_{_seed_name(seed)}",
            )
            for method in _method_candidates_for_mode(mode):
                settings = {**mode_base, **profile_overrides}
                settings = _set_pair(settings, seed.primary_model, seed.secondary_model)
                settings = _apply_method_overrides(settings, method)
                run_llm = bool(method == "proposed_lora_deep_gate" or seed.run_llm)
                row = _variant_row(
                    name=f"{_seed_name(seed)}__{method}",
                    phase="phase3_method",
                    description=f"{mode} method sweep",
                    method=method,
                    settings=settings,
                    run_llm=run_llm,
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase3_method" / mode,
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


def _cached_variant_definitions(mode: str) -> list[tuple[str, dict[str, Any]]]:
    normalized = _normalized_mode(mode)
    base_timing = {
        "vad_post_stt_align_enabled": True,
        "vad_post_stt_edge_pad_sec": 0.04,
        "subtitle_cut_boundary_guard_enabled": normalized != "fast",
        "subtitle_bundle_use_confirmed_cuts": normalized != "fast",
        "subtitle_bundle_use_provisional_cuts": False,
    }
    return [
        ("baseline_keep", {}),
        ("lora_off", {"editor_lora_runtime_enabled": False, "subtitle_lora_quality_buckets": [], "subtitle_lora_micro_merge_enabled": False, "subtitle_lora_packaging_enabled": False}),
        ("lora_high", {"editor_lora_runtime_enabled": True, "subtitle_lora_quality_buckets": ["high"]}),
        ("lora_high_medium", {"editor_lora_runtime_enabled": True, "subtitle_lora_quality_buckets": ["high", "medium"]}),
        ("lora_high_medium_low", {"editor_lora_runtime_enabled": True, "subtitle_lora_quality_buckets": ["high", "medium", "low"]}),
        ("deep_off", {"deep_subtitle_policy_enabled": False, "deep_segment_setting_policy_enabled": False, "deep_stt_candidate_selector_enabled": False, "deep_timing_adjustment_enabled": False, "subtitle_output_selector_enabled": False}),
        ("deep_selector_only", {"deep_subtitle_policy_enabled": True, "deep_segment_setting_policy_enabled": False, "deep_stt_candidate_selector_enabled": True, "deep_timing_adjustment_enabled": False, "subtitle_output_selector_enabled": True}),
        ("deep_timing_only", {"deep_subtitle_policy_enabled": False, "deep_segment_setting_policy_enabled": False, "deep_stt_candidate_selector_enabled": False, "deep_timing_adjustment_enabled": True, "subtitle_output_selector_enabled": False}),
        ("deep_full", {"deep_subtitle_policy_enabled": True, "deep_segment_setting_policy_enabled": True, "deep_stt_candidate_selector_enabled": True, "deep_timing_adjustment_enabled": True, "subtitle_output_selector_enabled": True}),
        ("packaging_off", {"subtitle_lora_packaging_enabled": False}),
        ("packaging_full", {"subtitle_lora_packaging_enabled": True, "subtitle_lora_packaging_mode": "full"}),
        ("packaging_selective", {"subtitle_lora_packaging_enabled": True, "subtitle_lora_packaging_mode": "readability_selective"}),
        ("timing_edge004", dict(base_timing)),
        ("timing_edge008", {**base_timing, "vad_post_stt_edge_pad_sec": 0.08, "subtitle_cut_boundary_guard_enabled": True, "subtitle_bundle_use_confirmed_cuts": True}),
        ("timing_edge012", {**base_timing, "vad_post_stt_edge_pad_sec": 0.12, "subtitle_cut_boundary_guard_enabled": True, "subtitle_bundle_use_confirmed_cuts": True}),
        ("timing_provisional008", {**base_timing, "vad_post_stt_edge_pad_sec": 0.08, "subtitle_cut_boundary_guard_enabled": True, "subtitle_bundle_use_confirmed_cuts": True, "subtitle_bundle_use_provisional_cuts": True}),
        (
            "blend_conservative",
            {
                "editor_lora_runtime_enabled": True,
                "subtitle_lora_quality_buckets": ["high"],
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": False,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": False,
                "subtitle_output_selector_enabled": True,
                "subtitle_lora_packaging_enabled": True,
                "subtitle_lora_packaging_mode": "readability_selective",
                **base_timing,
            },
        ),
        (
            "blend_balanced",
            {
                "editor_lora_runtime_enabled": True,
                "subtitle_lora_quality_buckets": ["high", "medium"],
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": True,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": True,
                "subtitle_output_selector_enabled": True,
                "subtitle_lora_packaging_enabled": True,
                "subtitle_lora_packaging_mode": "readability_selective",
                **base_timing,
            },
        ),
        (
            "blend_quality_max",
            {
                "editor_lora_runtime_enabled": True,
                "subtitle_lora_quality_buckets": ["high", "medium", "low"],
                "deep_subtitle_policy_enabled": True,
                "deep_segment_setting_policy_enabled": True,
                "deep_stt_candidate_selector_enabled": True,
                "deep_timing_adjustment_enabled": True,
                "subtitle_output_selector_enabled": True,
                "subtitle_lora_packaging_enabled": True,
                "subtitle_lora_packaging_mode": "full",
                "vad_post_stt_align_enabled": True,
                "vad_post_stt_edge_pad_sec": 0.08,
                "subtitle_cut_boundary_guard_enabled": True,
                "subtitle_bundle_use_confirmed_cuts": True,
                "subtitle_bundle_use_provisional_cuts": True,
            },
        ),
    ]


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
    for mode, rows in method_rows.items():
        shortlisted = _objective_rank(rows, mode, 1)
        for index, baseline_row in enumerate(shortlisted, start=1):
            baseline_settings = dict(baseline_row.get("effective_settings") or {})
            profile_name = str(baseline_row.get("audio_profile") or "mode_default")
            mode_base = _mode_base_settings(base_settings, mode)
            profile = next((item for item in _audio_profile_catalog(mode_base) if item.name == profile_name), None)
            extract_settings = {**mode_base, **(profile.overrides if profile else {})}
            chunk_source, _extract_meta = _run_extract(
                media=media,
                settings=extract_settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase4_cached_{mode}_{index}",
            )
            baseline_variant = _variant_row(
                name=f"{mode}__cached_seed_{index}",
                phase="phase4_cached_seed",
                description=f"{mode} cached seed baseline",
                method=str(baseline_row.get("method") or ""),
                settings=baseline_settings,
                run_llm=bool(baseline_row.get("run_llm")),
                chunk_source=chunk_source,
                work_dir=run_dir / "phase4_cached" / mode / f"seed_{index}",
                reference=reference,
                span_sec=span_sec,
            )
            raw_path = run_dir / "phase4_cached" / mode / f"seed_{index}" / f"{baseline_variant['name']}" / "raw_segments.json"
            if not raw_path.exists():
                raw_path = run_dir / "phase4_cached" / mode / f"seed_{index}" / "raw_segments.json"
            for name, overrides in _cached_variant_definitions(mode):
                settings = dict(baseline_settings)
                settings.update(overrides)
                settings["_benchmark_cached_raw_segments_path"] = str(raw_path)
                row = _variant_row(
                    name=f"{baseline_variant['name']}__{name}",
                    phase="phase4_cached_postprocess",
                    description=f"{mode} cached postprocess sweep",
                    method="cached_raw",
                    settings=settings,
                    run_llm=bool(baseline_row.get("run_llm")),
                    chunk_source=chunk_source,
                    work_dir=run_dir / "phase4_cached" / mode / f"seed_{index}",
                    reference=reference,
                    span_sec=span_sec,
                )
                row["mode"] = mode
                row["primary_model"] = str(baseline_row.get("primary_model") or "")
                row["secondary_model"] = str(baseline_row.get("secondary_model") or "")
                row["audio_profile"] = profile_name
                row["audio_profile_description"] = str(baseline_row.get("audio_profile_description") or "")
                rows_by_mode[mode].append(_row_with_effective_settings(row, settings))
        _log(f"phase4 cached {mode}: {len(rows_by_mode[mode])} candidates")
    return rows_by_mode


def _finalists_from_cached(rows_by_mode: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    finalists: dict[str, list[dict[str, Any]]] = {"fast": [], "auto": [], "high": []}
    for mode, rows in rows_by_mode.items():
        finalists[mode] = _objective_rank(rows, mode, 3)
    return finalists


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
    for mode, rows in finalists.items():
        mode_base = _mode_base_settings(base_settings, mode)
        profiles = {profile.name: profile for profile in _audio_profile_catalog(mode_base)}
        for row in rows:
            settings = dict(row.get("effective_settings") or {})
            profile_name = str(row.get("audio_profile") or "mode_default")
            profile = profiles.get(profile_name)
            extract_settings = {**mode_base, **(profile.overrides if profile else {})}
            chunk_source, extract_meta = _run_extract(
                media=media,
                settings=extract_settings,
                start_sec=start_sec,
                end_sec=end_sec,
                work_dir=run_dir,
                name=f"phase5_long_{mode}_{Path(str(row.get('name') or 'row')).name}",
            )
            long_row = _variant_row(
                name=f"long__{row.get('name')}",
                phase="phase5_long",
                description=f"{mode} 11-minute validation",
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
            long_row["audio_profile"] = profile_name
            long_row["audio_profile_description"] = str(row.get("audio_profile_description") or "")
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


def _mode_key_for_code(mode: str) -> str:
    return {"fast": "fast", "auto": "balanced", "high": "precise"}[_normalized_mode(mode)]


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


def _load_manual_seeds(path: Path) -> dict[str, list[BenchmarkSeed]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    source = payload.get("seeds") if isinstance(payload, dict) and isinstance(payload.get("seeds"), dict) else payload
    if not isinstance(source, dict):
        raise RuntimeError(f"manual seed json must be an object keyed by mode: {path}")
    seeds_by_mode: dict[str, list[BenchmarkSeed]] = {"fast": [], "auto": [], "high": []}
    for key, rows in source.items():
        mode = _normalized_mode(str(key or ""))
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                seeds_by_mode[mode].append(_seed_from_payload(row))
    return seeds_by_mode


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


def _write_manual_summary(
    *,
    summary_path: Path,
    payload: dict[str, Any],
) -> None:
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


def _cleanup_chunks(run_dir: Path) -> None:
    for path in run_dir.glob("**/chunks"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiered Fast/Auto/High Tiniping benchmark and recommendation builder.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    parser.add_argument("--reference-srt", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--short-sec", type=float, default=DEFAULT_SHORT_SEC)
    parser.add_argument("--long-sec", type=float, default=DEFAULT_LONG_SEC)
    parser.add_argument("--manual-seeds-json", default="", help="Skip phase1 exhaustive STT scan and resume from a manual seed JSON.")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()

    media = Path(args.media).expanduser()
    reference_srt = Path(args.reference_srt).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    if not reference_srt.exists():
        raise FileNotFoundError(reference_srt)

    short_sec = max(30.0, float(args.short_sec))
    long_sec = max(short_sec, float(args.long_sec))
    start_sec = max(0.0, float(args.start_sec))
    short_end = start_sec + short_sec
    long_end = start_sec + long_sec
    created = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / ".codex_work" / "benchmarks" / "tiniping_mode_search" / created
    run_dir.mkdir(parents=True, exist_ok=True)

    base_settings = _base_benchmark_settings("current")
    models = _discover_whisper_models()
    _json_dump(run_dir / "models_tested.json", {"models": models, "labels": {model: _model_label(model) for model in models}})
    _log(f"models discovered: {len(models)}")

    short_reference = clip_reference(parse_srt(reference_srt), start_sec, short_end)
    long_reference = clip_reference(parse_srt(reference_srt), start_sec, long_end)

    manual_seed_path = Path(str(args.manual_seeds_json or "").strip()).expanduser() if str(args.manual_seeds_json or "").strip() else None
    if manual_seed_path:
        if not manual_seed_path.exists():
            raise FileNotFoundError(manual_seed_path)
        primary_rows = {"fast": [], "auto": [], "high": []}
        pair_rows = {"auto": [], "high": []}
        phase1_seeds = _load_manual_seeds(manual_seed_path)
        _json_dump(run_dir / "phase1_manual_seeds_source.json", json.loads(manual_seed_path.read_text(encoding="utf-8")))
        _json_dump(run_dir / "phase1_primary.json", primary_rows)
        _json_dump(run_dir / "phase1_pairs.json", pair_rows)
        _log(f"manual seeds loaded: fast={len(phase1_seeds['fast'])}, auto={len(phase1_seeds['auto'])}, high={len(phase1_seeds['high'])}")
    else:
        primary_rows = _primary_scan(
            media=media,
            reference=short_reference,
            models=models,
            run_dir=run_dir,
            base_settings=base_settings,
            start_sec=start_sec,
            end_sec=short_end,
            span_sec=short_sec,
        )
        pair_rows = _pair_scan(
            media=media,
            reference=short_reference,
            models=models,
            run_dir=run_dir,
            base_settings=base_settings,
            start_sec=start_sec,
            end_sec=short_end,
            span_sec=short_sec,
        )
        _json_dump(run_dir / "phase1_primary.json", primary_rows)
        _json_dump(run_dir / "phase1_pairs.json", pair_rows)
        phase1_seeds = _collect_phase1_seeds(primary_rows, pair_rows)
    _json_dump(run_dir / "phase1_seeds.json", {mode: [_seed_to_payload(seed) for seed in seeds] for mode, seeds in phase1_seeds.items()})

    audio_rows = _audio_scan(
        media=media,
        reference=short_reference,
        seeds_by_mode=phase1_seeds,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=short_end,
        span_sec=short_sec,
    )
    _json_dump(run_dir / "phase2_audio.json", audio_rows)
    audio_seeds = _collect_audio_seeds(audio_rows)
    _json_dump(run_dir / "phase2_seeds.json", {mode: [asdict(seed) for seed in seeds] for mode, seeds in audio_seeds.items()})

    method_rows = _method_scan(
        media=media,
        reference=short_reference,
        seeds_by_mode=audio_seeds,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=short_end,
        span_sec=short_sec,
    )
    _json_dump(run_dir / "phase3_method.json", method_rows)

    cached_rows = _cached_postprocess_scan(
        media=media,
        reference=short_reference,
        method_rows=method_rows,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=short_end,
        span_sec=short_sec,
    )
    _json_dump(run_dir / "phase4_cached.json", cached_rows)
    short_top3 = _finalists_from_cached(cached_rows)
    _json_dump(run_dir / "short_top3.json", short_top3)

    long_rows = _long_run_validation(
        media=media,
        reference=long_reference,
        finalists=short_top3,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=long_end,
        span_sec=long_sec,
    )
    _json_dump(run_dir / "phase5_long.json", long_rows)
    long_top3 = {mode: _objective_rank(rows, mode, 3) for mode, rows in long_rows.items()}
    winners = _winner_rows(long_rows)
    recommendations = _recommendations_payload(
        media=media,
        reference_srt=reference_srt,
        short_rows=short_top3,
        long_rows=long_top3,
        winners=winners,
        models=models,
        run_dir=run_dir,
    )
    _json_dump(run_dir / "tiniping_recommendations.json", recommendations)

    summary_path = ROOT / "output" / "manual_verification" / "latest" / "tiniping_benchmark_summary.md"
    _write_manual_summary(summary_path=summary_path, payload=recommendations)

    # Write a benchmark-style markdown table for the final 11-minute rows.
    final_flat_rows = [row for rows in long_rows.values() for row in rows]
    final_ranked = []
    for mode in ("fast", "auto", "high"):
        final_ranked.extend(_objective_rank(long_rows[mode], mode, 3))
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media": str(media),
        "reference_srt": str(reference_srt),
        "start_sec": start_sec,
        "end_sec": long_end,
        "duration_sec": long_sec,
        "objective": "reference",
        "ranking_policy": "speed_weighted",
        "results": final_flat_rows,
        "ranked_results": final_ranked,
    }
    _write_markdown(payload, run_dir / "final_long_results.md")

    if not args.keep_artifacts:
        _cleanup_chunks(run_dir)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "summary_md": str(summary_path),
                "recommendations_json": str(run_dir / "tiniping_recommendations.json"),
                "winners": recommendations["winners"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
