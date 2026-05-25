#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.runtime import config
from core.settings_profiles import materialize_user_settings


@dataclass(frozen=True)
class Variant:
    name: str
    phase: str
    description: str
    method: str
    overrides: dict[str, Any]
    run_llm: bool


@dataclass(frozen=True)
class AudioProfile:
    name: str
    description: str
    overrides: dict[str, Any]


def _read_user_settings() -> dict[str, Any]:
    settings = materialize_user_settings({})
    settings_path = Path(config.DATASET_DIR) / "user_settings.json"
    if settings_path.exists():
        try:
            loaded = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update(loaded)
        except Exception:
            pass
    return settings


def _base_benchmark_settings(stt_profile: str = "current") -> dict[str, Any]:
    settings = _read_user_settings()
    settings.update(
        {
            "benchmark_runtime_profile": "subtitle-pipeline-variants",
            "apple_m_pipeline_respect_manual_worker_settings": True,
            "audio_preset_auto_tune": {},
            "stt_candidate_scoring_enabled": True,
            "stt_low_score_recheck_enabled": True,
            "stt_low_score_recheck_threshold": max(58.0, float(settings.get("stt_low_score_recheck_threshold", 58.0) or 58.0)),
            "stt_low_score_recheck_max_segments": min(48, int(settings.get("stt_low_score_recheck_max_segments", 48) or 48)),
            "stt_low_score_recheck_max_audio_sec": min(150.0, float(settings.get("stt_low_score_recheck_max_audio_sec", 150.0) or 150.0)),
            "stt_selective_recheck_min_segment_retention_ratio": 0.9,
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamp_precision_pass": False,
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamps_precision_max_segments": min(16, int(settings.get("stt_word_timestamps_precision_max_segments", 16) or 16)),
            "stt_word_timestamps_precision_max_audio_sec": min(70.0, float(settings.get("stt_word_timestamps_precision_max_audio_sec", 70.0) or 70.0)),
            "subtitle_output_selector_enabled": True,
            "runtime_quality_self_review_enabled": True,
            "subtitle_context_consistency_enabled": True,
            "subtitle_auto_review_enabled": True,
            "llm_confidence_gate_enabled": True,
            "llm_confidence_gate_strong_signal_score": 88.0,
            "llm_confidence_gate_strong_max_compact_ratio": 1.85,
            "llm_confidence_gate_strong_max_duration_ratio": 1.65,
            "subtitle_llm_macro_chunk_enabled": True,
            "subtitle_llm_macro_chunk_min_rows": 10,
            "subtitle_llm_macro_chunk_max_rows": 15,
            "direct_ffmpeg_chunk_extract": True,
            "direct_ffmpeg_chunk_batch_extract": True,
            "wav_pcm_fast_chunk_extract": True,
        }
    )
    stt_profile_key = str(stt_profile or "").strip().lower()
    if stt_profile_key in {"mlx-turbo", "mlx-large-v3"}:
        secondary = str(settings.get("selected_whisper_model_secondary") or "").strip()
        if not secondary or secondary == str(getattr(config, "MLX_FALLBACK_MODEL", "")):
            secondary = "youngouk/whisper-medium-komixv2-mlx"
        primary = (
            "mlx-community/whisper-large-v3-mlx"
            if stt_profile_key == "mlx-large-v3"
            else getattr(config, "MLX_FALLBACK_MODEL", "mlx-community/whisper-large-v3-turbo")
        )
        settings.update(
            {
                "runtime_npu_acceleration_enabled": False,
                "apple_m_pipeline_parallel_enabled": False,
                "stt_npu_prefer_enabled": False,
                "stt_backend_policy": "auto",
                "whisperkit_native_auto_enabled": False,
                "selected_whisper_model": primary,
                "selected_whisper_model_secondary": secondary,
                "stt_primary_fast_native_enabled": False,
                "stt_primary_fast_native_model": "",
            }
        )
    return settings


def _with_subtitle_llm(base_settings: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    subtitle_llm = str(base_settings.get("selected_model") or "사용 안함 (benchmark)").strip()
    if not subtitle_llm:
        subtitle_llm = "사용 안함 (benchmark)"
    return {"selected_model": subtitle_llm, **(overrides or {})}


def _stt_swap_overrides(base_settings: dict[str, Any]) -> dict[str, Any]:
    primary = str(base_settings.get("selected_whisper_model") or "").strip()
    secondary = str(base_settings.get("selected_whisper_model_secondary") or "").strip()
    return {
        "runtime_npu_acceleration_enabled": False,
        "apple_m_pipeline_parallel_enabled": False,
        "stt_npu_prefer_enabled": False,
        "whisperkit_native_auto_enabled": False,
        "stt_primary_fast_native_enabled": False,
        "stt_primary_fast_native_model": "",
        "selected_whisper_model": secondary or "youngouk/whisper-medium-komixv2-mlx",
        "selected_whisper_model_secondary": primary or "mlx-community/whisper-large-v3-mlx",
    }


def _strong_lora_merge_overrides() -> dict[str, Any]:
    return {
        "subtitle_lora_micro_merge_enabled": True,
        "split_length_threshold": 28,
        "sub_min_duration": 0.9,
        "sub_max_cps": 14,
        "subtitle_lora_micro_merge_min_duration": 2.0,
        "sub_gap_break_sec": 2.2,
        "subtitle_lora_micro_merge_gap_sec": 2.4,
        "word_timing_gap_break_sec": 1.4,
        "subtitle_lora_micro_merge_word_gap_sec": 1.6,
        "continuous_threshold": 3.4,
        "subtitle_lora_micro_merge_continuous_sec": 4.2,
    }


def _netflix_style_timing_overrides() -> dict[str, Any]:
    return {
        **_strong_lora_merge_overrides(),
        "continuous_threshold": 3.8,
        "gap_push_rate": 0.45,
        "gap_pull_rate": 0.55,
        "single_subtitle_end": 0.35,
        "sub_min_duration": 1.0,
        "sub_gap_break_sec": 2.6,
        "word_timing_gap_break_sec": 1.8,
        "sub_max_duration": 7.0,
        "vad_post_stt_align_enabled": True,
        "vad_post_stt_edge_pad_sec": 0.04,
    }


def _word_timestamp_overrides(mode: str) -> dict[str, Any]:
    if mode == "off":
        return {
            "stt_word_timestamps_mode": "off",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamp_precision_pass": False,
        }
    if mode == "all":
        return {
            "stt_word_timestamps_mode": "always",
            "stt_word_timestamps_default_enabled": True,
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamp_precision_pass": False,
        }
    if mode == "vad_boundary":
        return {
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": True,
            "stt_word_timestamp_precision_pass": False,
            "stt_word_timestamps_precision_threshold": 60.0,
            "stt_word_timestamps_precision_max_segments": 32,
            "stt_word_timestamps_precision_max_audio_sec": 100.0,
        }
    return {
        "stt_word_timestamps_mode": "selective",
        "stt_word_timestamps_default_enabled": False,
        "stt_word_timestamps_precision_enabled": True,
        "stt_word_timestamp_precision_pass": False,
        "stt_word_timestamps_precision_threshold": 72.0,
        "stt_word_timestamps_precision_max_segments": 32,
        "stt_word_timestamps_precision_max_audio_sec": 100.0,
    }


def _llm_red_yellow_gate_overrides(base_settings: dict[str, Any]) -> dict[str, Any]:
    return _with_subtitle_llm(
        base_settings,
        {
            "llm_confidence_gate_enabled": True,
            "llm_confidence_gate_min_lora_score": 88.0,
            "llm_confidence_gate_strong_signal_score": 92.0,
            "llm_confidence_gate_strong_max_compact_ratio": 1.28,
            "llm_confidence_gate_strong_max_duration_ratio": 1.35,
            "subtitle_llm_macro_chunk_enabled": True,
            "subtitle_llm_macro_chunk_min_rows": 10,
            "subtitle_llm_macro_chunk_max_rows": 15,
        },
    )


def _timing_overrides(*, vad: bool, confirmed_cut: bool, provisional_cut: bool, edge_pad: float) -> dict[str, Any]:
    return {
        "vad_post_stt_align_enabled": bool(vad),
        "vad_post_stt_edge_pad_sec": float(edge_pad),
        "subtitle_cut_boundary_guard_enabled": bool(confirmed_cut or provisional_cut),
        "subtitle_bundle_use_confirmed_cuts": bool(confirmed_cut),
        "subtitle_bundle_use_provisional_cuts": bool(provisional_cut),
    }
