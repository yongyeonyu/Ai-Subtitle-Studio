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
if __name__ == "__main__":
    sys.modules.setdefault("tools.benchmark_tiniping_mode_search", sys.modules[__name__])

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
from tools.subtitle_regression_pack import (  # noqa: E402
    DEFAULT_REGRESSION_PACK_DIR,
    REGRESSION_FIXTURE_KEYS,
    _build_regression_pack,
    _parse_regression_fixtures,
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


def _row_with_effective_settings(row: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["effective_settings"] = dict(settings)
    return out


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


def _selected_modes(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return ["fast", "auto", "high"]
    if isinstance(raw, str):
        parts = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        parts = [str(item or "").strip() for item in raw if str(item or "").strip()]
    chosen: list[str] = []
    for item in parts:
        normalized = _normalized_mode(item)
        if normalized not in chosen:
            chosen.append(normalized)
    return chosen or ["fast", "auto", "high"]


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
    profiles = [
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
    if _normalized_mode(
        base_settings.get("mode")
        or base_settings.get("subtitle_mode")
        or base_settings.get("user_facing_mode")
        or base_settings.get("simple_operation_mode")
        or base_settings.get("stt_quality_preset")
        or "fast"
    ) == "high":
        profiles.append(
            AudioProfile(
                name="adaptive_voice_change_high_detail",
                description="High 전용: 선발대 음성/장면 경계를 더 촘촘히 보고 구간별 오디오/VAD를 세밀하게 바꿉니다.",
                overrides={
                    **fresh,
                    "selected_audio_ai": "deepfilter",
                    "selected_vad": "silero",
                    "use_basic_filter": True,
                    "audio_chunk_routing_enabled": True,
                    "audio_chunk_route_vad_enabled": True,
                    "audio_chunk_profile_sec": 10.0,
                    "scan_cut_audio_gain_enabled": True,
                    "scan_cut_audio_gain_window_sec": 0.60,
                    "scan_cut_audio_gain_threshold_db": 7.5,
                    "scan_cut_audio_gain_context_windows": 4,
                    "scan_cut_audio_gain_min_gap_sec": 0.16,
                    "scan_cut_ffmpeg_scene_prepass_enabled": True,
                    "scan_cut_ffmpeg_scene_replace_opencv_enabled": False,
                    "scan_cut_ffmpeg_scene_threshold": 0.28,
                    "scan_cut_ffmpeg_scene_timeout_sec": 18.0,
                    "scan_cut_ffmpeg_scene_max_candidates": 420,
                    "scan_cut_pioneer_worker_overlap_steps": 2,
                    "scan_cut_pioneer_packet_bucket_sec": 0.16,
                    "scan_cut_pioneer_packet_min_gap_sec": 0.14,
                    "scan_cut_pioneer_packet_scout_raw_candidates": 280,
                    "scan_cut_pioneer_packet_delta_threshold": 1.18,
                    "scan_cut_pioneer_packet_mad_multiplier": 2.4,
                    "scan_cut_pioneer_min_gap_sec": 0.32,
                    "vad_threshold": 0.38,
                    "review_vad_speech_pad_sec": 0.24,
                    "review_vad_min_silence_sec": 0.52,
                },
            )
        )
    return profiles


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


def _cleanup_chunks(run_dir: Path) -> None:
    for path in run_dir.glob("**/chunks"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


def _prepare_phase1(
    *,
    args: argparse.Namespace,
    media: Path,
    short_reference: list[dict[str, Any]],
    models: list[str],
    run_dir: Path,
    base_settings: dict[str, Any],
    start_sec: float,
    short_end: float,
    short_sec: float,
    selected_modes: list[str],
    primary_scan: Any,
    pair_scan: Any,
    collect_phase1_seeds: Any,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, list[BenchmarkSeed]]]:
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
        return primary_rows, pair_rows, phase1_seeds
    primary_rows = primary_scan(
        media=media,
        reference=short_reference,
        models=models,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=short_end,
        span_sec=short_sec,
        modes=selected_modes,
    )
    pair_rows = pair_scan(
        media=media,
        reference=short_reference,
        models=models,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        end_sec=short_end,
        span_sec=short_sec,
        modes=selected_modes,
    )
    _json_dump(run_dir / "phase1_primary.json", primary_rows)
    _json_dump(run_dir / "phase1_pairs.json", pair_rows)
    phase1_seeds = collect_phase1_seeds(primary_rows, pair_rows, selected_modes)
    return primary_rows, pair_rows, phase1_seeds


def _finalize_mode_search(
    *,
    args: argparse.Namespace,
    run_dir: Path,
    media: Path,
    reference_srt: Path,
    start_sec: float,
    long_end: float,
    long_sec: float,
    long_rows: dict[str, list[dict[str, Any]]],
    selected_modes: list[str],
    summary_path: Path,
    recommendations: dict[str, Any],
    pack_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    final_flat_rows = [row for rows in long_rows.values() for row in rows]
    final_ranked = []
    for mode in selected_modes:
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
    return {
        "run_dir": str(run_dir),
        "summary_md": str(summary_path),
        "recommendations_json": str(run_dir / "tiniping_recommendations.json"),
        "regression_pack_json": str(Path(args.regression_pack_dir).expanduser() / "subtitle_regression_pack.json")
        if pack_payload
        else "",
        "winners": recommendations["winners"],
    }


def _run_search(args: argparse.Namespace) -> dict[str, Any]:
    from tools.tiniping_mode_search_phases import (
        _audio_scan,
        _cached_postprocess_scan,
        _collect_audio_seeds,
        _collect_phase1_seeds,
        _finalists_from_cached,
        _long_run_validation,
        _method_scan,
        _pair_scan,
        _primary_scan,
        _recommendations_payload,
        _winner_rows,
        _write_manual_summary,
    )

    media = Path(args.media).expanduser()
    reference_srt = Path(args.reference_srt).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    if not reference_srt.exists():
        raise FileNotFoundError(reference_srt)

    short_sec = max(30.0, float(args.short_sec))
    long_sec = max(short_sec, float(args.long_sec))
    start_sec = max(0.0, float(args.start_sec))
    selected_modes = _selected_modes(args.modes)
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

    primary_rows, pair_rows, phase1_seeds = _prepare_phase1(
        args=args,
        media=media,
        short_reference=short_reference,
        models=models,
        run_dir=run_dir,
        base_settings=base_settings,
        start_sec=start_sec,
        short_end=short_end,
        short_sec=short_sec,
        selected_modes=selected_modes,
        primary_scan=_primary_scan,
        pair_scan=_pair_scan,
        collect_phase1_seeds=_collect_phase1_seeds,
    )
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
        modes=selected_modes,
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
        modes=selected_modes,
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
        modes=selected_modes,
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
        modes=selected_modes,
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
        modes=selected_modes,
    )
    _json_dump(run_dir / "tiniping_recommendations.json", recommendations)

    summary_path = ROOT / "output" / "manual_verification" / "latest" / "tiniping_benchmark_summary.md"
    _write_manual_summary(summary_path=summary_path, payload=recommendations)
    pack_payload = None
    if args.build_regression_pack:
        pack_payload = _build_regression_pack(
            source_run_dir=run_dir,
            tiniping_summary_md=summary_path,
            fixtures=_parse_regression_fixtures(args.regression_pack_fixtures),
            pack_dir=Path(args.regression_pack_dir).expanduser(),
            x5_duration_sec=max(30.0, float(args.x5_duration_sec)),
            full_verify_mode=str(args.regression_pack_full_mode or "high").strip().lower(),
        )
    return _finalize_mode_search(
        args=args,
        run_dir=run_dir,
        media=media,
        reference_srt=reference_srt,
        start_sec=start_sec,
        long_end=long_end,
        long_sec=long_sec,
        long_rows=long_rows,
        selected_modes=selected_modes,
        summary_path=summary_path,
        recommendations=recommendations,
        pack_payload=pack_payload,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Tiered Fast/Auto/High Tiniping benchmark and recommendation builder.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA))
    parser.add_argument("--reference-srt", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--short-sec", type=float, default=DEFAULT_SHORT_SEC)
    parser.add_argument("--long-sec", type=float, default=DEFAULT_LONG_SEC)
    parser.add_argument("--manual-seeds-json", default="", help="Skip phase1 exhaustive STT scan and resume from a manual seed JSON.")
    parser.add_argument("--build-regression-pack", action="store_true")
    parser.add_argument("--regression-pack-dir", default=str(DEFAULT_REGRESSION_PACK_DIR))
    parser.add_argument(
        "--regression-pack-fixtures",
        default=",".join(REGRESSION_FIXTURE_KEYS),
        help="Comma-separated fixtures: x5, macau, tinyping_short, tinyping_full",
    )
    parser.add_argument("--x5-duration-sec", type=float, default=180.0)
    parser.add_argument("--regression-pack-full-mode", default="high", choices=["fast", "auto", "high", "stt"])
    parser.add_argument("--keep-artifacts", action="store_true")
    parser.add_argument(
        "--modes",
        default="fast,auto,high",
        help="Comma-separated modes to benchmark: fast, auto, high",
    )
    result = _run_search(parser.parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
