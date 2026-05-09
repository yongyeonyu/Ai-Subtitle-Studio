#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.audio.npu_acceleration import prefer_npu_whisper_model  # noqa: E402
from core.audio.stt_backend_router import select_stt_backend  # noqa: E402
from core.audio.stt_candidate_scorer import annotate_stt_candidates, average_stt_score  # noqa: E402
from core.engine import subtitle_engine  # noqa: E402
from core.native_text_similarity import character_error_rate, similarity_ratio  # noqa: E402
from core.performance import hardware_profile  # noqa: E402
from core.runtime import config  # noqa: E402
from core.settings_profiles import materialize_user_settings  # noqa: E402


DEFAULT_FIXTURE_DIR = ROOT / "test video"
DEFAULT_MEDIA = DEFAULT_FIXTURE_DIR / "X5_시승기_후반.MP4"
DEFAULT_REFERENCE = DEFAULT_FIXTURE_DIR / "X5_시스응기_후반.srt"
if not DEFAULT_REFERENCE.exists():
    DEFAULT_REFERENCE = DEFAULT_FIXTURE_DIR / "X5_시승기_후반.srt"


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


def benchmark_variants(base_settings: dict[str, Any]) -> list[Variant]:
    subtitle_llm = str(base_settings.get("selected_model") or "사용 안함 (benchmark)").strip()
    if not subtitle_llm:
        subtitle_llm = "사용 안함 (benchmark)"
    return [
        Variant(
            name="stt_original_parallel_full_no_llm",
            phase="stt_swap",
            description="원래 STT1/STT2 배치로 전체 병렬 앙상블을 실행합니다.",
            method="parallel_ensemble",
            run_llm=False,
            overrides={
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": True,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_word_timestamp_precision_pass": False,
            },
        ),
        Variant(
            name="stt_swapped_parallel_full_no_llm",
            phase="stt_swap",
            description="STT1=KomixV2 MLX, STT2=large-v3 MLX로 바꿔 전체 병렬 앙상블을 실행합니다.",
            method="parallel_ensemble",
            run_llm=False,
            overrides={
                **_stt_swap_overrides(base_settings),
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": True,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_word_timestamp_precision_pass": False,
            },
        ),
        Variant(
            name="stt_original_selective_no_llm",
            phase="stt_swap",
            description="원래 STT1/STT2 배치로 STT1 전체 뒤 저점 구간만 STT2 rescue를 실행합니다.",
            method="selective_ensemble",
            run_llm=False,
            overrides={
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="stt_swapped_selective_no_llm",
            phase="stt_swap",
            description="STT1=KomixV2 MLX, STT2=large-v3 MLX로 바꿔 저점 rescue를 실행합니다.",
            method="selective_ensemble",
            run_llm=False,
            overrides={
                **_stt_swap_overrides(base_settings),
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="phase1_stt1_only_lora_deep",
            phase="phase1_order",
            description="STT1 전체 실행 뒤 LoRA/Deep만 적용합니다. STT2/LLM 비용이 없는 기준선입니다.",
            method="stt1_only",
            run_llm=False,
            overrides={
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="phase1_parallel_full_stt1_stt2",
            phase="phase1_order",
            description="기존 병렬 STT1/STT2 전체 앙상블 뒤 LoRA/Deep만 적용합니다.",
            method="parallel_ensemble",
            run_llm=False,
            overrides={
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": True,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_word_timestamp_precision_pass": False,
            },
        ),
        Variant(
            name="phase1_serial_selective_stt2",
            phase="phase1_order",
            description="STT1 전체 실행 뒤 저점 구간만 STT2로 재실행하고 LoRA/Deep만 적용합니다.",
            method="selective_ensemble",
            run_llm=False,
            overrides={
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="phase2_serial_lora_deep_gate_then_stt2",
            phase="phase2_quality_speed",
            description="제안 순서: STT1 → LoRA/Deep 게이트 → 저점만 STT2 → 저점/문맥만 LLM → VAD/컷 타이밍.",
            method="proposed_lora_deep_gate",
            run_llm=True,
            overrides={
                "selected_model": subtitle_llm,
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="phase2_serial_selective_llm_gate",
            phase="phase2_quality_speed",
            description="현재 선택 앙상블 순서에 LLM confidence gate를 적용합니다.",
            method="selective_ensemble",
            run_llm=True,
            overrides={
                "selected_model": subtitle_llm,
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="phase3_stt1_lora_deep_llm",
            phase="phase3_quality_llm",
            description="STT1 large-v3 전체 실행 뒤 LoRA/Deep/LLM까지 모두 적용합니다.",
            method="stt1_only",
            run_llm=True,
            overrides={
                "selected_model": subtitle_llm,
                "stt_ensemble_enabled": False,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="phase3_parallel_full_llm",
            phase="phase3_quality_llm",
            description="STT1/STT2 전체 병렬 앙상블 뒤 LoRA/Deep/LLM까지 모두 적용합니다.",
            method="parallel_ensemble",
            run_llm=True,
            overrides={
                "selected_model": subtitle_llm,
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": True,
                "stt_ensemble_selective_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
                "stt_low_score_recheck_enabled": False,
                "stt_word_timestamps_precision_enabled": False,
                "stt_word_timestamp_precision_pass": False,
            },
        ),
        Variant(
            name="phase3_selective_stt2_llm",
            phase="phase3_quality_llm",
            description="STT1 large-v3 뒤 저점 구간만 STT2로 확인하고 LoRA/Deep/LLM까지 모두 적용합니다.",
            method="selective_ensemble",
            run_llm=True,
            overrides={
                "selected_model": subtitle_llm,
                "stt_ensemble_enabled": True,
                "stt_ensemble_parallel_enabled": False,
                "stt_ensemble_selective_enabled": True,
                "stt_selective_secondary_recheck_enabled": True,
            },
        ),
        Variant(
            name="split_lora_baseline_cached",
            phase="split_merge",
            description="고정 STT 결과에 현재 LoRA/Deep 분할·병합 기준을 적용합니다.",
            method="cached_raw",
            run_llm=False,
            overrides={},
        ),
        Variant(
            name="split_lora_strong_cached",
            phase="split_merge",
            description="LoRA 병합 강하게: 1~2초 이내 짧은 자막을 주변 문맥과 적극 병합합니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_strong_lora_merge_overrides(),
        ),
        Variant(
            name="split_deep_first_lora_off_cached",
            phase="split_merge",
            description="Deep 진단 먼저 보는 대조군: LoRA micro merge를 끄고 최종 분할만 적용합니다.",
            method="cached_raw",
            run_llm=False,
            overrides={"subtitle_lora_micro_merge_enabled": False},
        ),
        Variant(
            name="split_netflix_style_cached",
            phase="split_merge",
            description="Netflix 스타일: 긴 무음만 끊고, 표시 타이밍은 살짝 앞당기는 보수적 병합 기준입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_netflix_style_timing_overrides(),
        ),
        Variant(
            name="word_ts_off_stt1",
            phase="word_timestamp",
            description="단어 타임태그 없이 STT1과 LoRA/Deep만 실행합니다.",
            method="stt1_only",
            run_llm=False,
            overrides={
                **_word_timestamp_overrides("off"),
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="word_ts_low_score_stt1",
            phase="word_timestamp",
            description="STT1 뒤 저점/검토 후보만 단어 타임태그 정밀 패스로 재인식합니다.",
            method="stt1_word_precision",
            run_llm=False,
            overrides={
                **_word_timestamp_overrides("low_score"),
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="word_ts_vad_boundary_stt1",
            phase="word_timestamp",
            description="VAD 위험/경계 후보 중심으로 단어 타임태그 정밀 패스를 제한합니다.",
            method="stt1_word_precision",
            run_llm=False,
            overrides={
                **_word_timestamp_overrides("vad_boundary"),
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="word_ts_all_stt1",
            phase="word_timestamp",
            description="전체 STT1 패스에서 단어 타임태그를 켜는 품질 상한 대조군입니다.",
            method="stt1_only",
            run_llm=False,
            overrides={
                **_word_timestamp_overrides("all"),
                "stt_ensemble_enabled": False,
                "stt_selective_secondary_recheck_enabled": False,
            },
        ),
        Variant(
            name="llm_none_cached",
            phase="llm_position",
            description="LLM 없이 LoRA/Deep만 적용하는 고정 STT 기준선입니다.",
            method="cached_raw",
            run_llm=False,
            overrides={},
        ),
        Variant(
            name="llm_red_yellow_context_cached",
            phase="llm_position",
            description="LoRA/Deep 확정 뒤 red/yellow/저신뢰 후보만 앞뒤 문맥과 함께 LLM에 보냅니다.",
            method="cached_raw",
            run_llm=True,
            overrides=_llm_red_yellow_gate_overrides(base_settings),
        ),
        Variant(
            name="llm_macro_forced_cached",
            phase="llm_position",
            description="10~15문장 macro chunk LLM을 강제로 켜서 품질 상한을 봅니다.",
            method="cached_raw",
            run_llm=True,
            overrides=_with_subtitle_llm(
                base_settings,
                {
                    "llm_confidence_gate_enabled": False,
                    "subtitle_llm_macro_chunk_enabled": True,
                    "subtitle_llm_macro_chunk_min_rows": 10,
                    "subtitle_llm_macro_chunk_max_rows": 15,
                },
            ),
        ),
        Variant(
            name="llm_macro_after_strong_lora_cached",
            phase="llm_position",
            description="강한 LoRA 병합 뒤 macro chunk LLM을 적용합니다.",
            method="cached_raw",
            run_llm=True,
            overrides={
                **_strong_lora_merge_overrides(),
                **_with_subtitle_llm(
                    base_settings,
                    {
                        "llm_confidence_gate_enabled": False,
                        "subtitle_llm_macro_chunk_enabled": True,
                        "subtitle_llm_macro_chunk_min_rows": 10,
                        "subtitle_llm_macro_chunk_max_rows": 15,
                    },
                ),
            },
        ),
        Variant(
            name="timing_vad_only_edge004_cached",
            phase="timing",
            description="VAD post-align만 사용하고 edge pad 0.04초를 적용합니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=True, confirmed_cut=False, provisional_cut=False, edge_pad=0.04),
        ),
        Variant(
            name="timing_cut_only_edge008_cached",
            phase="timing",
            description="컷 경계 guard만 켜고 VAD post-align을 끈 대조군입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=False, confirmed_cut=True, provisional_cut=False, edge_pad=0.08),
        ),
        Variant(
            name="timing_cut_vad_edge004_cached",
            phase="timing",
            description="정식 컷 경계 + VAD post-align + edge pad 0.04초입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=True, confirmed_cut=True, provisional_cut=False, edge_pad=0.04),
        ),
        Variant(
            name="timing_cut_vad_edge008_cached",
            phase="timing",
            description="정식 컷 경계 + VAD post-align + edge pad 0.08초입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=True, confirmed_cut=True, provisional_cut=False, edge_pad=0.08),
        ),
        Variant(
            name="timing_cut_vad_edge012_cached",
            phase="timing",
            description="정식 컷 경계 + VAD post-align + edge pad 0.12초입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=True, confirmed_cut=True, provisional_cut=False, edge_pad=0.12),
        ),
        Variant(
            name="timing_cut_provisional_vad_edge008_cached",
            phase="timing",
            description="임시+정식 컷 경계 + VAD post-align + edge pad 0.08초입니다.",
            method="cached_raw",
            run_llm=False,
            overrides=_timing_overrides(vad=True, confirmed_cut=True, provisional_cut=True, edge_pad=0.08),
        ),
    ]


def benchmark_audio_profiles(base_settings: dict[str, Any]) -> list[AudioProfile]:
    """Audio/VAD rescue profiles for low-confidence STT benchmarking.

    These profiles intentionally force fresh audio/VAD analysis so the benchmark
    measures the filter/VAD choice instead of reusing the previous chunk cache.
    """
    fresh = {
        "reuse_preprocessed_audio_cache": False,
        "vad_detection_cache_enabled": False,
        "autopilot_stage_cache_enabled": False,
        "vad_post_stt_align_enabled": True,
        "review_vad_before_stt_enabled": True,
    }
    baseline_audio = {
        "selected_audio_ai": base_settings.get("selected_audio_ai", "none"),
        "selected_vad": base_settings.get("selected_vad", "silero"),
        "ff_hp": base_settings.get("ff_hp", 150),
        "ff_lp": base_settings.get("ff_lp", 4600),
        "ff_nf": base_settings.get("ff_nf", -25),
        "vad_threshold": base_settings.get("vad_threshold", 0.5),
        "ten_vad_threshold": base_settings.get("ten_vad_threshold", 0.5),
        "review_vad_speech_pad_sec": base_settings.get("review_vad_speech_pad_sec", 0.35),
        "review_vad_min_silence_sec": base_settings.get("review_vad_min_silence_sec", 0.8),
    }
    return [
        AudioProfile(
            name="audio_baseline_fresh",
            description="현재 사용자 오디오/VAD 설정을 캐시 없이 다시 실행합니다.",
            overrides={**fresh, **baseline_audio},
        ),
        AudioProfile(
            name="ffmpeg_ten_vad_balanced",
            description="FFmpeg 네이티브 필터 + TEN VAD 균형형. 잡음은 누르고 타이밍은 보수적으로 봅니다.",
            overrides={
                **fresh,
                "vad_backend_policy": "legacy",
                "selected_audio_ai": "none",
                "selected_vad": "ten_vad",
                "use_basic_filter": True,
                "ff_hp": 120,
                "ff_lp": 4600,
                "ff_nf": -24,
                "ff_dynaudnorm_m": 12.0,
                "ff_treble_boost": 1.5,
                "ten_vad_threshold": 0.46,
                "vad_threshold": 0.46,
                "review_vad_speech_pad_sec": 0.28,
                "review_vad_min_silence_sec": 0.65,
            },
        ),
        AudioProfile(
            name="ffmpeg_silero_relaxed",
            description="FFmpeg 네이티브 필터 + Silero relaxed. 낮은 점수/짧은 발화를 더 잘 줍는 후보입니다.",
            overrides={
                **fresh,
                "vad_backend_policy": "legacy",
                "selected_audio_ai": "none",
                "selected_vad": "silero",
                "use_basic_filter": True,
                "ff_hp": 90,
                "ff_lp": 5200,
                "ff_nf": -18,
                "ff_dynaudnorm_m": 10.0,
                "ff_treble_boost": 1.0,
                "vad_threshold": 0.36,
                "vad_min_speech": 0.14,
                "vad_min_silence": 0.45,
                "vad_speech_pad": 0.28,
                "review_vad_speech_pad_sec": 0.32,
                "review_vad_min_silence_sec": 0.45,
            },
        ),
        AudioProfile(
            name="clearvoice_ten_vad_noisy",
            description="ClearVoice/네이티브 음성강화 + TEN VAD. 실외/노이즈 영상의 STT rescue 후보입니다.",
            overrides={
                **fresh,
                "vad_backend_policy": "legacy",
                "selected_audio_ai": "clearvoice",
                "selected_vad": "ten_vad",
                "use_basic_filter": True,
                "ff_hp": 150,
                "ff_lp": 4600,
                "ff_nf": -30,
                "ff_dynaudnorm_m": 18.0,
                "ff_treble_boost": 2.8,
                "ten_vad_threshold": 0.50,
                "vad_threshold": 0.50,
                "review_vad_speech_pad_sec": 0.35,
                "review_vad_min_silence_sec": 0.75,
            },
        ),
        AudioProfile(
            name="deepfilter_silero_quality",
            description="DeepFilter + Silero 품질형. 음성 분리 품질을 우선하는 후보입니다.",
            overrides={
                **fresh,
                "vad_backend_policy": "legacy",
                "selected_audio_ai": "deepfilter",
                "selected_vad": "silero",
                "use_basic_filter": True,
                "df_hp": 90,
                "df_eq_g": 5,
                "df_comp_th": -30,
                "df_vol": 3.0,
                "ff_hp": 100,
                "ff_lp": 4200,
                "ff_nf": -22,
                "vad_threshold": 0.42,
                "vad_min_speech": 0.18,
                "vad_min_silence": 0.7,
                "vad_speech_pad": 0.22,
                "review_vad_speech_pad_sec": 0.28,
                "review_vad_min_silence_sec": 0.65,
            },
        ),
        AudioProfile(
            name="rnnoise_silero_fast",
            description="RNNoise + Silero 빠른 rescue 후보. 속도 대비 품질을 확인합니다.",
            overrides={
                **fresh,
                "vad_backend_policy": "legacy",
                "selected_audio_ai": "rnnoise",
                "selected_vad": "silero",
                "use_basic_filter": True,
                "ff_hp": 130,
                "ff_lp": 4300,
                "ff_nf": -24,
                "vad_threshold": 0.40,
                "vad_min_speech": 0.16,
                "vad_min_silence": 0.55,
                "vad_speech_pad": 0.25,
                "review_vad_speech_pad_sec": 0.30,
                "review_vad_min_silence_sec": 0.55,
            },
        ),
    ]


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    rows: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), "")
        if not time_line:
            continue
        try:
            left, right = [part.strip() for part in time_line.split("-->", 1)]
            start = srt_time_to_sec(left)
            end = srt_time_to_sec(right)
        except Exception:
            continue
        idx = lines.index(time_line)
        body = "\n".join(lines[idx + 1 :]).strip()
        if body:
            rows.append({"start": start, "end": end, "text": body})
    return rows


def srt_time_to_sec(value: str) -> float:
    raw = str(value or "").strip().replace(",", ".")
    hms = raw.split(":")
    if len(hms) != 3:
        raise ValueError(f"bad srt time: {value}")
    hour = float(hms[0])
    minute = float(hms[1])
    sec = float(hms[2])
    return hour * 3600.0 + minute * 60.0 + sec


def clip_reference(rows: list[dict[str, Any]], start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start) or start)
        if end <= start_sec or start >= end_sec:
            continue
        out.append(
            {
                **row,
                "start": max(0.0, start - start_sec),
                "end": max(0.0, min(end, end_sec) - start_sec),
            }
        )
    return out


def _compact_text(value: Any) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or ""), flags=re.UNICODE).lower()


def _joined_text(rows: Iterable[dict[str, Any]]) -> str:
    return " ".join(str(row.get("text", "") or "").replace("\n", " ").strip() for row in rows if str(row.get("text", "") or "").strip())


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    start = max(float(left.get("start", 0.0) or 0.0), float(right.get("start", 0.0) or 0.0))
    end = min(float(left.get("end", start) or start), float(right.get("end", start) or start))
    return max(0.0, end - start)


def _best_ref_for(hyp: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    best_row = None
    best_score = -1.0
    hyp_mid = (float(hyp.get("start", 0.0) or 0.0) + float(hyp.get("end", 0.0) or 0.0)) / 2.0
    for ref in refs:
        overlap = _overlap(hyp, ref)
        ref_mid = (float(ref.get("start", 0.0) or 0.0) + float(ref.get("end", 0.0) or 0.0)) / 2.0
        proximity = max(0.0, 1.0 - abs(hyp_mid - ref_mid) / 4.0)
        score = overlap * 2.0 + proximity
        if score > best_score:
            best_score = score
            best_row = ref
    return best_row


def score_against_reference(hypothesis: list[dict[str, Any]], reference: list[dict[str, Any]]) -> dict[str, Any]:
    hyp = [dict(row) for row in hypothesis if str(row.get("text", "") or "").strip()]
    ref = [dict(row) for row in reference if str(row.get("text", "") or "").strip()]
    ref_compact = _compact_text(_joined_text(ref))
    hyp_compact = _compact_text(_joined_text(hyp))
    cer = character_error_rate(ref_compact, hyp_compact) if ref_compact else 1.0
    text_similarity = similarity_ratio(ref_compact, hyp_compact) if ref_compact or hyp_compact else 1.0
    text_score = max(0.0, min(100.0, (1.0 - min(1.0, cer)) * 72.0 + text_similarity * 28.0))

    timing_errors: list[float] = []
    overlap_scores: list[float] = []
    local_text_scores: list[float] = []
    for row in hyp:
        ref_row = _best_ref_for(row, ref)
        if not ref_row:
            continue
        start_err = abs(float(row.get("start", 0.0) or 0.0) - float(ref_row.get("start", 0.0) or 0.0))
        end_err = abs(float(row.get("end", 0.0) or 0.0) - float(ref_row.get("end", 0.0) or 0.0))
        timing_errors.append((start_err + end_err) / 2.0)
        span = max(
            float(row.get("end", 0.0) or 0.0) - float(row.get("start", 0.0) or 0.0),
            float(ref_row.get("end", 0.0) or 0.0) - float(ref_row.get("start", 0.0) or 0.0),
            0.001,
        )
        overlap_scores.append(min(1.0, _overlap(row, ref_row) / span))
        local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
    avg_timing_error = sum(timing_errors) / max(1, len(timing_errors))
    timing_score = max(0.0, min(100.0, 100.0 - avg_timing_error * 26.0))
    overlap_score = (sum(overlap_scores) / max(1, len(overlap_scores))) * 100.0 if overlap_scores else 0.0
    local_text_score = (sum(local_text_scores) / max(1, len(local_text_scores))) * 100.0 if local_text_scores else 0.0
    count_score = max(0.0, 100.0 - abs(len(hyp) - len(ref)) / max(1, len(ref)) * 100.0)
    quality_score = text_score * 0.52 + timing_score * 0.22 + overlap_score * 0.12 + local_text_score * 0.08 + count_score * 0.06
    return {
        "reference_segments": len(ref),
        "hypothesis_segments": len(hyp),
        "cer": round(float(cer), 6),
        "global_text_similarity": round(float(text_similarity), 6),
        "text_score": round(text_score, 3),
        "timing_mae_sec": round(avg_timing_error, 4),
        "timing_score": round(timing_score, 3),
        "overlap_score": round(overlap_score, 3),
        "local_text_score": round(local_text_score, 3),
        "count_score": round(count_score, 3),
        "quality_score": round(quality_score, 3),
    }


def _copy_chunk_dir(source: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)
    return target


def _bind_processor_settings(processor: VideoProcessor, settings: dict[str, Any]) -> None:
    """Keep benchmark variants from being re-routed by app-wide runtime autotune."""
    frozen = dict(settings)
    processor._fast_mode_overrides = frozen
    processor._load_all_settings = lambda: dict(frozen)  # type: ignore[method-assign]


@contextlib.contextmanager
def patched_subtitle_settings(settings: dict[str, Any], model: str):
    with (
        patch("core.engine.subtitle_engine._get_user_settings", return_value=dict(settings)),
        patch("core.engine.subtitle_engine.get_selected_llm", return_value=str(model or "")),
    ):
        yield


def _collect_transcribe(generator) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for chunk_rows, _idx, _total in generator:
        for row in chunk_rows or []:
            if isinstance(row, dict) and str(row.get("text", "") or "").strip():
                rows.append(dict(row))
    rows.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)))
    return rows


def _slim_segments_for_artifact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        words = item.pop("words", None)
        if words:
            item["word_count"] = len(words)
        slim.append(item)
    return slim


def _chunk_wav_count(chunk_dir: Path) -> int:
    try:
        return len([path for path in chunk_dir.iterdir() if path.is_file() and path.suffix.lower() == ".wav"])
    except Exception:
        return 0


def _load_vad(chunk_dir: Path) -> list[dict[str, Any]]:
    path = chunk_dir / "vad_strict.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [dict(row) for row in data if isinstance(row, dict)]
    except Exception:
        return []


def _load_cached_raw_segments(settings: dict[str, Any]) -> list[dict[str, Any]]:
    path_text = str(settings.get("_benchmark_cached_raw_segments_path") or "").strip()
    if not path_text:
        raise RuntimeError("cached_raw variant requires --cached-raw-segments")
    path = Path(path_text).expanduser()
    if not path.exists():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("segments") or data.get("rows") or data.get("raw_segments") or []
    rows = [dict(row) for row in data if isinstance(row, dict) and str(row.get("text", "") or "").strip()]
    rows.sort(key=lambda row: (float(row.get("start", 0.0) or 0.0), float(row.get("end", 0.0) or 0.0)))
    return rows


def _primary_model(settings: dict[str, Any]) -> str:
    requested = str(settings.get("selected_whisper_model") or getattr(config, "WHISPER_MODEL", "") or "").strip()
    routed = prefer_npu_whisper_model(requested, settings, purpose="stt", log_label="Bench-STT1")
    return str(routed or requested)


def _run_postprocess(rows: list[dict[str, Any]], vad: list[dict[str, Any]], settings: dict[str, Any], *, run_llm: bool) -> list[dict[str, Any]]:
    model = str(settings.get("selected_model") or "").strip()
    if not run_llm:
        model = "사용 안함 (benchmark no-llm)"
        settings = {**settings, "selected_model": model}
    with patched_subtitle_settings(settings, model):
        return subtitle_engine.optimize_segments([dict(row) for row in rows], vad_segments=vad)


def _avg_cps(rows: list[dict[str, Any]]) -> float:
    chars = 0
    duration = 0.0
    for row in rows:
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        chars += len(re.sub(r"\s+", "", text))
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start) or start)
        duration += max(0.0, end - start)
    return chars / duration if duration > 0.0 else 0.0


def _run_variant(
    variant: Variant,
    *,
    chunk_source: Path,
    work_dir: Path,
    base_settings: dict[str, Any],
    reference: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = {**base_settings, **variant.overrides}
    chunk_dir = _copy_chunk_dir(chunk_source, work_dir / variant.name / "chunks")
    vad = _load_vad(chunk_dir)
    processor = VideoProcessor()
    _bind_processor_settings(processor, settings)
    started = time.perf_counter()
    error = ""
    raw_rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    try:
        if variant.method == "cached_raw":
            raw_rows = _load_cached_raw_segments(settings)
            raw_rows = annotate_stt_candidates(raw_rows, source="cached", vad_segments=vad, settings=settings)
            final_rows = _run_postprocess(raw_rows, vad, settings, run_llm=variant.run_llm)
        elif variant.method == "stt1_only":
            raw_rows = _collect_transcribe(
                processor.transcribe(
                    str(chunk_dir),
                    target_end_sec=float(base_settings.get("_benchmark_span_sec", 180.0)),
                    model_override=_primary_model(settings),
                    cleanup_chunk_dir=False,
                    log_label="Bench-STT1",
                )
            )
            raw_rows = annotate_stt_candidates(raw_rows, source="STT1", vad_segments=vad, settings=settings)
            final_rows = _run_postprocess(raw_rows, vad, settings, run_llm=variant.run_llm)
        elif variant.method == "stt1_word_precision":
            raw_rows = _collect_transcribe(
                processor.transcribe(
                    str(chunk_dir),
                    target_end_sec=float(base_settings.get("_benchmark_span_sec", 180.0)),
                    model_override=_primary_model(settings),
                    cleanup_chunk_dir=False,
                    log_label="Bench-STT1",
                )
            )
            scored = annotate_stt_candidates(raw_rows, source="STT1", vad_segments=vad, settings=settings)
            lora_deep_rows = _run_postprocess(scored, vad, settings, run_llm=False)
            _bind_processor_settings(processor, settings)
            precision_rows = processor._recheck_word_timestamps_for_precision(
                str(chunk_dir),
                lora_deep_rows,
                settings,
                vad,
                _primary_model(settings),
            )
            raw_rows = precision_rows
            final_rows = _run_postprocess(precision_rows, vad, settings, run_llm=variant.run_llm)
        elif variant.method in {"parallel_ensemble", "selective_ensemble"}:
            raw_rows = _collect_transcribe(
                processor.transcribe_ensemble(
                    str(chunk_dir),
                    target_end_sec=float(base_settings.get("_benchmark_span_sec", 180.0)),
                    cleanup_chunk_dir=False,
                )
            )
            final_rows = _run_postprocess(raw_rows, vad, settings, run_llm=variant.run_llm)
        elif variant.method == "proposed_lora_deep_gate":
            raw_rows = _collect_transcribe(
                processor.transcribe(
                    str(chunk_dir),
                    target_end_sec=float(base_settings.get("_benchmark_span_sec", 180.0)),
                    model_override=_primary_model(settings),
                    cleanup_chunk_dir=False,
                    log_label="Bench-STT1",
                )
            )
            scored = annotate_stt_candidates(raw_rows, source="STT1", vad_segments=vad, settings=settings)
            lora_deep_rows = _run_postprocess(scored, vad, settings, run_llm=False)
            _bind_processor_settings(processor, settings)
            rechecked = processor._recheck_primary_low_score_with_secondary(
                str(chunk_dir),
                lora_deep_rows,
                settings,
                vad,
                _primary_model(settings),
            )
            rechecked = processor._recheck_word_timestamps_for_precision(
                str(chunk_dir),
                rechecked,
                settings,
                vad,
                _primary_model(settings),
            )
            raw_rows = rechecked
            final_rows = _run_postprocess(rechecked, vad, settings, run_llm=variant.run_llm)
        else:
            raise RuntimeError(f"unsupported variant method: {variant.method}")
    except Exception as exc:
        error = str(exc)
    finally:
        processor.release_runtime_models()
    elapsed = time.perf_counter() - started
    score = score_against_reference(final_rows, reference) if final_rows else {}
    if score:
        score["avg_cps"] = round(_avg_cps(final_rows), 3)
        score["segment_count_delta"] = int(len(final_rows) - len(reference))
    avg_stt_score = average_stt_score(raw_rows) if raw_rows else 0.0
    row = {
        "name": variant.name,
        "phase": variant.phase,
        "description": variant.description,
        "method": variant.method,
        "run_llm": variant.run_llm,
        "elapsed_sec": round(elapsed, 3),
        "raw_segments": len(raw_rows),
        "final_segments": len(final_rows),
        "avg_stt_score": round(float(avg_stt_score), 3),
        "error": error,
        "quality": score,
        "settings": {
            key: settings.get(key)
            for key in (
                "selected_whisper_model",
                "selected_whisper_model_secondary",
                "selected_model",
                "stt_ensemble_enabled",
                "stt_ensemble_parallel_enabled",
                "stt_ensemble_selective_enabled",
                "stt_selective_secondary_recheck_enabled",
                "stt_low_score_recheck_threshold",
                "stt_word_timestamps_mode",
                "stt_word_timestamps_default_enabled",
                "stt_word_timestamps_precision_enabled",
                "subtitle_lora_micro_merge_enabled",
                "sub_gap_break_sec",
                "word_timing_gap_break_sec",
                "continuous_threshold",
                "vad_post_stt_align_enabled",
                "vad_post_stt_edge_pad_sec",
                "subtitle_cut_boundary_guard_enabled",
                "subtitle_bundle_use_confirmed_cuts",
                "subtitle_bundle_use_provisional_cuts",
                "subtitle_llm_macro_chunk_enabled",
            )
        },
    }
    (work_dir / variant.name).mkdir(parents=True, exist_ok=True)
    (work_dir / variant.name / "output_segments.json").write_text(
        json.dumps(_slim_segments_for_artifact(final_rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (work_dir / variant.name / "raw_segments.json").write_text(
        json.dumps(_slim_segments_for_artifact(raw_rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return row


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fastest = min((float(row.get("elapsed_sec", 0.0) or 0.0) for row in rows if not row.get("error")), default=0.0)
    ranked = []
    for row in rows:
        item = dict(row)
        quality = float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)
        elapsed = float(row.get("elapsed_sec", 0.0) or 0.0)
        speed_score = 0.0 if elapsed <= 0.0 or fastest <= 0.0 else min(100.0, fastest / elapsed * 100.0)
        item["speed_score"] = round(speed_score, 3)
        item["quality_speed_score"] = round(quality * 0.82 + speed_score * 0.18, 3)
        ranked.append(item)
    ranked.sort(key=lambda row: (float(row.get("quality_speed_score", 0.0) or 0.0), float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)), reverse=True)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def _write_markdown(payload: dict[str, Any], output_path: Path) -> None:
    rows = payload.get("ranked_results") or []
    lines = [
        "# Subtitle Pipeline Variant Benchmark",
        "",
        f"- Media: `{payload.get('media')}`",
        f"- Reference: `{payload.get('reference_srt')}`",
        f"- Span: {payload.get('start_sec')}s ~ {payload.get('end_sec')}s",
        f"- Created: {payload.get('created_at')}",
        "",
        "| Rank | Variant | Phase | Time(s) | Quality | Speed | Q+Speed | Segs | ΔSegs | Avg CPS | CER | Timing MAE | Error |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        q = dict(row.get("quality") or {})
        lines.append(
            "| {rank} | `{name}` | {phase} | {elapsed:.3f} | {quality:.3f} | {speed:.3f} | {combo:.3f} | {segs} | {delta} | {cps:.3f} | {cer:.4f} | {timing:.3f} | {error} |".format(
                rank=row.get("rank", ""),
                name=row.get("name", ""),
                phase=row.get("phase", ""),
                elapsed=float(row.get("elapsed_sec", 0.0) or 0.0),
                quality=float(q.get("quality_score", 0.0) or 0.0),
                speed=float(row.get("speed_score", 0.0) or 0.0),
                combo=float(row.get("quality_speed_score", 0.0) or 0.0),
                segs=row.get("final_segments", 0),
                delta=int(q.get("segment_count_delta", 0) or 0),
                cps=float(q.get("avg_cps", 0.0) or 0.0),
                cer=float(q.get("cer", 0.0) or 0.0),
                timing=float(q.get("timing_mae_sec", 0.0) or 0.0),
                error=str(row.get("error") or "").replace("|", "/")[:90],
            )
        )
    lines.append("")
    if rows:
        best = rows[0]
        lines.append(
            f"Recommended current winner: `{best.get('name')}` with quality-speed score {best.get('quality_speed_score')}."
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark subtitle pipeline order/gating variants on a real 3-minute fixture.")
    parser.add_argument("--media", default=str(DEFAULT_MEDIA), help="Benchmark media path.")
    parser.add_argument("--reference-srt", default=str(DEFAULT_REFERENCE), help="Reference SRT path.")
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--duration-sec", type=float, default=180.0)
    parser.add_argument(
        "--stt-profile",
        choices=["current", "mlx-turbo", "mlx-large-v3"],
        default="current",
        help="Use current app STT routes, MLX turbo, or MLX large-v3 for STT1.",
    )
    parser.add_argument("--variants", nargs="*", default=[], help="Optional variant names to run.")
    parser.add_argument("--llm-model", default="", help="Override subtitle LLM model for LLM variants.")
    parser.add_argument(
        "--cached-raw-segments",
        default="",
        help="Reuse an existing raw_segments.json for cached post-processing variants.",
    )
    parser.add_argument(
        "--audio-profiles",
        nargs="*",
        default=[],
        help="Optional fresh audio/VAD profiles to benchmark. Use 'all' for every profile.",
    )
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()

    media = Path(args.media).expanduser()
    reference_srt = Path(args.reference_srt).expanduser()
    if not media.exists():
        raise FileNotFoundError(media)
    if not reference_srt.exists():
        raise FileNotFoundError(reference_srt)

    start_sec = max(0.0, float(args.start_sec))
    end_sec = start_sec + max(1.0, float(args.duration_sec))
    created = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = ROOT / ".codex_work" / "benchmarks" / "subtitle_pipeline_variants" / created
    work_dir.mkdir(parents=True, exist_ok=True)

    base_settings = _base_benchmark_settings(args.stt_profile)
    base_settings["_benchmark_span_sec"] = float(args.duration_sec)
    if str(args.llm_model or "").strip():
        base_settings["selected_model"] = str(args.llm_model).strip()
    if str(args.cached_raw_segments or "").strip():
        base_settings["_benchmark_cached_raw_segments_path"] = str(Path(args.cached_raw_segments).expanduser())
    variants = benchmark_variants(base_settings)
    if args.variants:
        wanted = set(args.variants)
        variants = [variant for variant in variants if variant.name in wanted]
        missing_variants = sorted(wanted - {variant.name for variant in variants})
        if missing_variants:
            raise RuntimeError(f"unknown variants: {', '.join(missing_variants)}")
    if not variants:
        raise RuntimeError("no variants selected")

    reference_rows = clip_reference(parse_srt(reference_srt), start_sec, end_sec)
    requested_audio_profiles = [str(item or "").strip() for item in args.audio_profiles if str(item or "").strip()]
    audio_profiles = benchmark_audio_profiles(base_settings)
    selected_audio_profiles: list[AudioProfile] = []
    if requested_audio_profiles:
        if any(item.lower() == "all" for item in requested_audio_profiles):
            selected_audio_profiles = audio_profiles
        else:
            by_name = {profile.name: profile for profile in audio_profiles}
            selected_audio_profiles = [by_name[name] for name in requested_audio_profiles if name in by_name]
            missing = [name for name in requested_audio_profiles if name not in by_name]
            if missing:
                raise RuntimeError(f"unknown audio profiles: {', '.join(missing)}")

    results = []
    audio_extracts: list[dict[str, Any]] = []
    if selected_audio_profiles:
        for profile in selected_audio_profiles:
            profile_settings = {**base_settings, **profile.overrides, "_benchmark_audio_profile": profile.name}
            extractor = VideoProcessor()
            _bind_processor_settings(extractor, profile_settings)
            extract_started = time.perf_counter()
            chunk_dir_text, _vad_segments = extractor.extract_audio(
                str(media),
                target_start_sec=start_sec,
                target_end_sec=end_sec,
                is_single_segment=False,
            )
            extract_elapsed = time.perf_counter() - extract_started
            extractor.release_runtime_models()
            chunk_source = Path(chunk_dir_text)
            if not chunk_source.exists():
                raise RuntimeError(f"audio chunk extraction failed for {profile.name}: {chunk_source}")
            vad_count = len(_load_vad(chunk_source))
            audio_extracts.append(
                {
                    "profile": profile.name,
                    "description": profile.description,
                    "elapsed_sec": round(extract_elapsed, 3),
                    "audio_chunk_dir": str(chunk_source),
                    "chunk_wavs": _chunk_wav_count(chunk_source),
                    "vad_segments": vad_count,
                    "settings": {
                        key: profile_settings.get(key)
                        for key in (
                            "selected_audio_ai",
                            "selected_vad",
                            "ff_hp",
                            "ff_lp",
                            "ff_nf",
                            "vad_threshold",
                            "ten_vad_threshold",
                            "review_vad_speech_pad_sec",
                            "review_vad_min_silence_sec",
                        )
                    },
                }
            )
            profile_work_dir = work_dir / profile.name
            profile_work_dir.mkdir(parents=True, exist_ok=True)
            for variant in variants:
                profiled_variant = Variant(
                    name=f"{profile.name}__{variant.name}",
                    phase=variant.phase,
                    description=f"{profile.description} / {variant.description}",
                    method=variant.method,
                    overrides=dict(variant.overrides),
                    run_llm=variant.run_llm,
                )
                row = _run_variant(
                    profiled_variant,
                    chunk_source=chunk_source,
                    work_dir=profile_work_dir,
                    base_settings=profile_settings,
                    reference=reference_rows,
                )
                row["audio_profile"] = profile.name
                row["audio_profile_description"] = profile.description
                row["audio_extract_elapsed_sec"] = round(extract_elapsed, 3)
                row["audio_chunk_wavs"] = _chunk_wav_count(chunk_source)
                row["audio_vad_segments"] = vad_count
                results.append(row)
    else:
        extractor = VideoProcessor()
        _bind_processor_settings(extractor, base_settings)
        extract_started = time.perf_counter()
        chunk_dir_text, _vad_segments = extractor.extract_audio(
            str(media),
            target_start_sec=start_sec,
            target_end_sec=end_sec,
            is_single_segment=False,
        )
        extract_elapsed = time.perf_counter() - extract_started
        extractor.release_runtime_models()
        chunk_source = Path(chunk_dir_text)
        if not chunk_source.exists():
            raise RuntimeError(f"audio chunk extraction failed: {chunk_source}")
        audio_extracts.append(
            {
                "profile": "default",
                "elapsed_sec": round(extract_elapsed, 3),
                "audio_chunk_dir": str(chunk_source),
                "chunk_wavs": _chunk_wav_count(chunk_source),
                "vad_segments": len(_load_vad(chunk_source)),
            }
        )

        for variant in variants:
            results.append(
                _run_variant(
                    variant,
                    chunk_source=chunk_source,
                    work_dir=work_dir,
                    base_settings=base_settings,
                    reference=reference_rows,
                )
            )
    ranked = _rank_rows(results)
    payload = {
        "schema": "ai_subtitle_studio.subtitle_pipeline_variant_benchmark.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "media": str(media),
        "reference_srt": str(reference_srt),
        "fixture_dir": str(DEFAULT_FIXTURE_DIR),
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": float(args.duration_sec),
        "stt_profile": args.stt_profile,
        "audio_extracts": audio_extracts,
        "reference_segments": len(reference_rows),
        "hardware": hardware_profile(),
        "stt_routes": {
            "primary": asdict(select_stt_backend(base_settings.get("selected_whisper_model"), base_settings)),
            "secondary": asdict(select_stt_backend(base_settings.get("selected_whisper_model_secondary"), base_settings)),
        },
        "results": results,
        "ranked_results": ranked,
    }
    json_path = work_dir / "benchmark_results.json"
    md_path = work_dir / "benchmark_results.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(payload, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "ranked_results": ranked}, ensure_ascii=False, indent=2))

    if not args.keep_artifacts:
        for path in work_dir.glob("**/chunks"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
