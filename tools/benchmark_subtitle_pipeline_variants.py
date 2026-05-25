#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio.media_processor import VideoProcessor  # noqa: E402
from core.audio.npu_acceleration import prefer_npu_whisper_model  # noqa: E402
from core.audio.stt_backend_router import select_stt_backend  # noqa: E402
from core.audio.stt_candidate_scorer import annotate_stt_candidates, average_stt_score  # noqa: E402
from core.engine import subtitle_engine  # noqa: E402
from core.mode_policy import apply_mode_runtime_settings  # noqa: E402
from core.native_swift_subtitle_assembly import (  # noqa: E402
    ASSEMBLED_VARIANT_NAME,
    QUALITY_BASELINE_VARIANTS,
    evaluate_subtitle_assembly_quality_gate,
    plan_subtitle_assembly_via_swift,
)
from core.native_swift_subtitle_global_canvas import summarize_global_canvas_via_swift  # noqa: E402
from core.native_swift_subtitle_resource import plan_subtitle_resource_via_swift  # noqa: E402
from core.native_swift_subtitle_segments import summarize_segments_via_swift  # noqa: E402
from core.native_swift_subtitle_stt_segments import summarize_stt_segments_via_swift  # noqa: E402
from core.native_swift_subtitle_timing import score_timing_metrics_via_swift  # noqa: E402
from core.native_subtitle_global_canvas import global_canvas_summary as cpp_global_canvas_summary  # noqa: E402
from core.native_subtitle_segments import segment_summary as cpp_segment_summary  # noqa: E402
from core.native_subtitle_stt_segments import stt_segments_summary as cpp_stt_segments_summary  # noqa: E402
from core.native_subtitle_timing import timing_metrics as cpp_timing_metrics  # noqa: E402
from core.performance import hardware_profile  # noqa: E402
from core.pipeline.pipeline_helpers import PipelineHelpersMixin  # noqa: E402
from core.runtime import config  # noqa: E402
from core.runtime.multi_process import (  # noqa: E402
    APPLE_M_FULL_CORE_THROUGHPUT_PROFILE,
    apply_apple_m_subtitle_pipeline_plan,
)
from core.speaker_profile_settings import automatic_speaker_ceiling, speaker_diarization_auto_enabled  # noqa: E402
from tools.subtitle_benchmark_artifacts import (  # noqa: E402
    _chunk_extraction_signature,
    _chunk_wav_count,
    _collect_transcribe,
    _copy_chunk_dir,
    _load_cached_raw_segments,
    _load_vad,
    _slim_segments_for_artifact,
    _variant_chunk_settings,
)
from tools import subtitle_benchmark_scoring as _benchmark_scoring  # noqa: E402
from tools.subtitle_benchmark_readability import score_readability  # noqa: E402
from tools.subtitle_benchmark_scoring import (  # noqa: E402
    _best_ref_for,
    _compact_text,
    _overlap,
    clip_reference,
    parse_srt,
    srt_time_to_sec,
)
from tools.subtitle_benchmark_settings import (  # noqa: E402
    AudioProfile,
    Variant,
    _base_benchmark_settings,
    _llm_red_yellow_gate_overrides,
    _netflix_style_timing_overrides,
    _stt_swap_overrides,
    _strong_lora_merge_overrides,
    _timing_overrides,
    _with_subtitle_llm,
    _word_timestamp_overrides,
)


DEFAULT_FIXTURE_DIR = ROOT / "test video"
DEFAULT_MEDIA = DEFAULT_FIXTURE_DIR / "X5_시승기_후반.MP4"
DEFAULT_REFERENCE = DEFAULT_FIXTURE_DIR / "X5_시스응기_후반.srt"
if not DEFAULT_REFERENCE.exists():
    DEFAULT_REFERENCE = DEFAULT_FIXTURE_DIR / "X5_시승기_후반.srt"


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


def _infer_benchmark_llm_provider(model: str, fallback: str = "ollama") -> str:
    label = str(model or "").strip().lower()
    if not label:
        return str(fallback or "ollama").strip() or "ollama"
    if "codex" in label or "openai" in label or label.startswith("gpt-"):
        return "openai"
    return str(fallback or "ollama").strip() or "ollama"


def _mode_profile_settings(
    base_settings: dict[str, Any],
    mode: str,
    *,
    llm_model: str = "",
) -> dict[str, Any]:
    settings = dict(base_settings)
    settings["_ignore_saved_quality_preset_once"] = True
    settings["subtitle_mode"] = mode
    settings["mode"] = mode
    settings["user_facing_mode"] = mode
    if mode == "high" and str(llm_model or "").strip():
        settings["selected_model"] = str(llm_model).strip()
        settings["selected_llm_provider"] = _infer_benchmark_llm_provider(
            settings["selected_model"],
            str(settings.get("selected_llm_provider") or "ollama"),
        )
        settings["subtitle_llm_user_selected"] = True
    return apply_mode_runtime_settings(settings)


def _mode_profile_method(settings: dict[str, Any]) -> str:
    if bool(settings.get("stt_ensemble_enabled")):
        if bool(settings.get("stt_ensemble_parallel_enabled")):
            return "parallel_ensemble"
        if bool(settings.get("stt_ensemble_selective_enabled")) or bool(settings.get("stt_selective_secondary_recheck_enabled")):
            return "selective_ensemble"
    if bool(settings.get("stt_word_timestamps_precision_enabled")) or bool(settings.get("stt_word_timestamp_precision_pass")):
        return "stt1_word_precision"
    return "stt1_only"


def _native_resource_summary_for_variant(settings: dict[str, Any], *, run_llm: bool) -> dict[str, Any]:
    active_labels = ["pipeline", "stt", "subtitle_optimize"]
    if run_llm:
        active_labels.append("subtitle_llm")
    resource_plan = plan_subtitle_resource_via_swift(settings=settings, active_labels=active_labels)
    if not isinstance(resource_plan, dict):
        return {}
    summary = dict(resource_plan.get("accelerator_summary") or {})
    if not summary:
        return {}
    return {
        "backend": str(resource_plan.get("backend") or "swift"),
        "pressure_stage": str(resource_plan.get("pressure_stage") or "normal"),
        "gpu_task_count": int(summary.get("gpu_task_count", 0) or 0),
        "ane_task_count": int(summary.get("ane_task_count", 0) or 0),
        "metal_task_count": int(summary.get("metal_task_count", 0) or 0),
        "gpu_lanes_total": int(summary.get("gpu_lanes_total", 0) or 0),
        "ane_lanes_total": int(summary.get("ane_lanes_total", 0) or 0),
        "max_gpu_lanes": int(summary.get("max_gpu_lanes", 0) or 0),
        "max_ane_lanes": int(summary.get("max_ane_lanes", 0) or 0),
        "gpu_lane_capacity": int(summary.get("gpu_lane_capacity", 0) or 0),
        "ane_model_lane_capacity": int(summary.get("ane_model_lane_capacity", 0) or 0),
        "gpu_lane_peak_ratio": round(float(summary.get("gpu_lane_peak_ratio", 0.0) or 0.0), 6),
        "ane_model_lane_peak_ratio": round(float(summary.get("ane_model_lane_peak_ratio", 0.0) or 0.0), 6),
        "full_gpu_lane_task_count": int(summary.get("full_gpu_lane_task_count", 0) or 0),
        "full_ane_model_lane_task_count": int(summary.get("full_ane_model_lane_task_count", 0) or 0),
        "gpu_lane_peak_saturated": bool(summary.get("gpu_lane_peak_saturated", False)),
        "ane_model_lane_peak_saturated": bool(summary.get("ane_model_lane_peak_saturated", False)),
        "gpu_tasks": list(summary.get("gpu_tasks") or []),
        "ane_tasks": list(summary.get("ane_tasks") or []),
        "metal_tasks": list(summary.get("metal_tasks") or []),
        "cpp_parity": bool(summary.get("cpp_parity", False)),
        "metal_claims_ane": bool(summary.get("metal_claims_ane", False)),
    }


def _native_segments_summary_for_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_segments_via_swift(rows) or cpp_segment_summary(rows)
    if not isinstance(summary, dict):
        return {}
    return {
        "backend": str(summary.get("backend") or summary.get("native_backend") or "native"),
        "segment_count": int(summary.get("segment_count", 0) or 0),
        "invalid_duration_count": int(summary.get("invalid_duration_count", 0) or 0),
        "non_monotonic_count": int(summary.get("non_monotonic_count", 0) or 0),
        "overlap_count": int(summary.get("overlap_count", 0) or 0),
        "empty_text_count": int(summary.get("empty_text_count", 0) or 0),
        "total_duration": round(float(summary.get("total_duration", 0.0) or 0.0), 6),
        "first_start": round(float(summary.get("first_start", 0.0) or 0.0), 6),
        "last_end": round(float(summary.get("last_end", 0.0) or 0.0), 6),
        "max_gap": round(float(summary.get("max_gap", 0.0) or 0.0), 6),
        "max_gap_index": int(summary.get("max_gap_index", -1)),
        "max_overlap": round(float(summary.get("max_overlap", 0.0) or 0.0), 6),
        "max_overlap_index": int(summary.get("max_overlap_index", -1)),
        "max_chars": int(summary.get("max_chars", 0) or 0),
        "avg_chars": round(float(summary.get("avg_chars", 0.0) or 0.0), 6),
        "stable_for_save_reopen": bool(summary.get("stable_for_save_reopen", False)),
        "segment_feed_signature": str(summary.get("segment_feed_signature") or ""),
    }


def _native_stt_segments_summary_for_variant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_stt_segments_via_swift(rows) or cpp_stt_segments_summary(rows)
    if not isinstance(summary, dict):
        return {}
    return {
        "backend": str(summary.get("backend") or summary.get("native_backend") or "native"),
        "segment_count": int(summary.get("segment_count", 0) or 0),
        "stt1_selected_count": int(summary.get("stt1_selected_count", 0) or 0),
        "stt2_selected_count": int(summary.get("stt2_selected_count", 0) or 0),
        "recheck_applied_count": int(summary.get("recheck_applied_count", 0) or 0),
        "word_precision_count": int(summary.get("word_precision_count", 0) or 0),
        "secondary_hint_count": int(summary.get("secondary_hint_count", 0) or 0),
        "unknown_source_count": int(summary.get("unknown_source_count", 0) or 0),
        "invalid_duration_count": int(summary.get("invalid_duration_count", 0) or 0),
        "non_monotonic_count": int(summary.get("non_monotonic_count", 0) or 0),
        "overlap_count": int(summary.get("overlap_count", 0) or 0),
        "source_switch_count": int(summary.get("source_switch_count", 0) or 0),
        "total_duration": round(float(summary.get("total_duration", 0.0) or 0.0), 6),
        "stt1_duration": round(float(summary.get("stt1_duration", 0.0) or 0.0), 6),
        "stt2_duration": round(float(summary.get("stt2_duration", 0.0) or 0.0), 6),
        "stt2_coverage_ratio": round(float(summary.get("stt2_coverage_ratio", 0.0) or 0.0), 6),
        "stt2_first_start": round(float(summary.get("stt2_first_start", 0.0) or 0.0), 6),
        "stt2_last_end": round(float(summary.get("stt2_last_end", 0.0) or 0.0), 6),
        "longest_stt2_run_sec": round(float(summary.get("longest_stt2_run_sec", 0.0) or 0.0), 6),
        "longest_stt2_run_start": round(float(summary.get("longest_stt2_run_start", 0.0) or 0.0), 6),
        "longest_stt2_run_end": round(float(summary.get("longest_stt2_run_end", 0.0) or 0.0), 6),
        "longest_stt2_run_count": int(summary.get("longest_stt2_run_count", 0) or 0),
        "stt2_active": bool(summary.get("stt2_active", False)),
        "selective_recheck_active": bool(summary.get("selective_recheck_active", False)),
        "stable_for_timeline_feed": bool(summary.get("stable_for_timeline_feed", False)),
        "timeline_feed_signature": str(summary.get("timeline_feed_signature") or ""),
    }


def _native_global_canvas_summary_for_variant(
    rows: list[dict[str, Any]],
    *,
    duration: float = 0.0,
    bin_count: int = 120,
) -> dict[str, Any]:
    max_end = 0.0
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        try:
            max_end = max(max_end, float(row.get("end", 0.0) or 0.0))
        except Exception:
            continue
    canvas_duration = max(float(duration or 0.0), max_end)
    summary = summarize_global_canvas_via_swift(
        rows,
        duration=canvas_duration,
        bin_count=bin_count,
    ) or cpp_global_canvas_summary(rows, duration=canvas_duration, bin_count=bin_count)
    if not isinstance(summary, dict):
        return {}
    return {
        "backend": str(summary.get("backend") or summary.get("native_backend") or "native"),
        "segment_count": int(summary.get("segment_count", 0) or 0),
        "valid_segment_count": int(summary.get("valid_segment_count", 0) or 0),
        "invalid_duration_count": int(summary.get("invalid_duration_count", 0) or 0),
        "non_monotonic_count": int(summary.get("non_monotonic_count", 0) or 0),
        "duration": round(float(summary.get("duration", 0.0) or 0.0), 6),
        "bin_count": int(summary.get("bin_count", 0) or 0),
        "occupied_bin_count": int(summary.get("occupied_bin_count", 0) or 0),
        "empty_bin_count": int(summary.get("empty_bin_count", 0) or 0),
        "dense_bin_count": int(summary.get("dense_bin_count", 0) or 0),
        "max_bin_active": int(summary.get("max_bin_active", 0) or 0),
        "max_active_bin_index": int(summary.get("max_active_bin_index", -1)),
        "avg_bin_active": round(float(summary.get("avg_bin_active", 0.0) or 0.0), 6),
        "coverage_duration": round(float(summary.get("coverage_duration", 0.0) or 0.0), 6),
        "coverage_ratio": round(float(summary.get("coverage_ratio", 0.0) or 0.0), 6),
        "longest_empty_span_sec": round(float(summary.get("longest_empty_span_sec", 0.0) or 0.0), 6),
        "longest_empty_start_sec": round(float(summary.get("longest_empty_start_sec", 0.0) or 0.0), 6),
        "longest_empty_end_sec": round(float(summary.get("longest_empty_end_sec", 0.0) or 0.0), 6),
        "max_active_segments": int(summary.get("max_active_segments", 0) or 0),
        "stable_for_global_canvas": bool(summary.get("stable_for_global_canvas", False)),
    }


def _high_full_core_throughput_settings(mode_settings: dict[str, Any]) -> dict[str, Any]:
    settings = dict(mode_settings)
    settings.update(
        {
            "benchmark_runtime_profile": APPLE_M_FULL_CORE_THROUGHPUT_PROFILE,
            "apple_m_full_core_aggressive_enabled": True,
            "apple_m_aggressive_full_parallel_stt_enabled": False,
            "apple_m_pipeline_respect_manual_worker_settings": False,
            "stt_window_ensemble_enabled": True,
            "stt_window_parallel_enabled": True,
            "stt_window_parallel_aggressive_enabled": True,
            "stt_window_sec": 180.0,
            "stt_quarter_parallel_count": 4,
            "stt_quarter_parallel_max_workers": 4,
            "stt_ensemble_parallel_enabled": False,
            "stt_ensemble_selective_enabled": True,
            "stt_selective_secondary_recheck_enabled": True,
        }
    )
    return apply_apple_m_subtitle_pipeline_plan(settings)


def _append_swift_assembled_variant(variants: list[Variant], base_settings: dict[str, Any]) -> None:
    if any(variant.name == ASSEMBLED_VARIANT_NAME for variant in variants):
        return
    available = [
        {
            "name": variant.name,
            "phase": variant.phase,
            "method": variant.method,
        }
        for variant in variants
    ]
    plan = plan_subtitle_assembly_via_swift(available, settings=base_settings)
    by_name = {variant.name: variant for variant in variants}
    source_name = str(plan.get("source_variant") or "").strip()
    source = by_name.get(source_name) or by_name.get("mode_high") or variants[-1]
    settings_overrides = dict(plan.get("settings_overrides") or {})
    assembled_overrides = dict(source.overrides)
    assembled_overrides.update(settings_overrides)
    assembled_overrides["native_subtitle_assembly_plan"] = plan
    assembled_overrides["native_subtitle_assembly_candidate_variant"] = ASSEMBLED_VARIANT_NAME
    variants.append(
        Variant(
            name=ASSEMBLED_VARIANT_NAME,
            phase="mode_profile",
            description="Swift assembly planner가 분리된 자막 생성 단계를 재조립하고 Fast/Auto/High 최고점 품질 하한을 적용합니다.",
            method=source.method,
            overrides=assembled_overrides,
            run_llm=source.run_llm,
        )
    )


def benchmark_mode_profiles(base_settings: dict[str, Any], *, llm_model: str = "") -> list[Variant]:
    labels = {
        "fast": "Fast 모드 실제 설정(STT1 + LoRA 중심)으로 실행합니다.",
        "auto": "Auto 모드 실제 설정(selective word precision + Deep)으로 실행합니다.",
        "high": "High 모드 실제 설정(selective word precision + Deep + mode LLM)으로 실행합니다.",
    }
    variants: list[Variant] = []
    for mode in ("fast", "auto", "high"):
        mode_settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
        model_label = str(mode_settings.get("selected_model") or "").strip()
        run_llm = mode == "high" and bool(model_label and "사용 안함" not in model_label)
        variants.append(
            Variant(
                name=f"mode_{mode}",
                phase="mode_profile",
                description=labels[mode],
                method=_mode_profile_method(mode_settings),
                overrides=mode_settings,
                run_llm=run_llm,
            )
        )
        if mode == "auto":
            split_settings = dict(mode_settings)
            split_settings.update(
                {
                    "audio_chunk_route_split_enabled": True,
                    "audio_chunk_route_max_span_sec": 120.0,
                    "audio_chunk_route_split_confidence_threshold": 0.78,
                    "audio_chunk_route_split_candidate_gap_max": 0.07,
                    "audio_chunk_route_split_preview_divergence_min": 0.08,
                }
            )
            variants.append(
                Variant(
                    name="mode_auto_adaptive_split",
                    phase="mode_profile",
                    description="Auto 모드에 route disagreement 기반 selective adaptive split v2를 추가합니다.",
                    method=_mode_profile_method(split_settings),
                    overrides=split_settings,
                    run_llm=False,
                )
            )
            drift_settings = dict(mode_settings)
            drift_settings.update(
                {
                    "subtitle_timing_piecewise_drift_enabled": True,
                    "subtitle_timing_piecewise_drift_trigger_sec": 0.05,
                    "subtitle_timing_piecewise_drift_max_shift_sec": 0.10,
                    "subtitle_timing_piecewise_drift_min_run_segments": 3,
                    "subtitle_timing_piecewise_drift_anchor_spread_sec": 0.08,
                }
            )
            variants.append(
                Variant(
                    name="mode_auto_piecewise_drift",
                    phase="mode_profile",
                    description="Auto 모드에 연속 구간 piecewise drift timing 보정을 추가합니다.",
                    method=_mode_profile_method(drift_settings),
                    overrides=drift_settings,
                    run_llm=False,
                )
            )
            split_drift_settings = dict(split_settings)
            split_drift_settings.update(
                {
                    "subtitle_timing_piecewise_drift_enabled": True,
                    "subtitle_timing_piecewise_drift_trigger_sec": 0.05,
                    "subtitle_timing_piecewise_drift_max_shift_sec": 0.10,
                    "subtitle_timing_piecewise_drift_min_run_segments": 3,
                    "subtitle_timing_piecewise_drift_anchor_spread_sec": 0.08,
                }
            )
            variants.append(
                Variant(
                    name="mode_auto_adaptive_split_drift",
                    phase="mode_profile",
                    description="Auto 모드에 selective split v2와 piecewise drift 보정을 함께 적용합니다.",
                    method=_mode_profile_method(split_drift_settings),
                    overrides=split_drift_settings,
                    run_llm=False,
                )
            )
        if mode == "high":
            high_full_core_settings = _high_full_core_throughput_settings(mode_settings)
            variants.append(
                Variant(
                    name="mode_high_full_core_overlap",
                    phase="mode_profile",
                    description="High 품질 경로를 유지하면서 3분 STT 창, 컷 경계, 네이티브/LLM worker를 full-core opt-in으로 겹쳐 실행합니다.",
                    method=_mode_profile_method(high_full_core_settings),
                    overrides=high_full_core_settings,
                    run_llm=run_llm,
                )
            )
            high_drift_settings = dict(mode_settings)
            high_drift_settings.update(
                {
                    "subtitle_timing_piecewise_drift_enabled": True,
                    "subtitle_timing_piecewise_drift_trigger_sec": 0.05,
                    "subtitle_timing_piecewise_drift_max_shift_sec": 0.10,
                    "subtitle_timing_piecewise_drift_min_run_segments": 3,
                    "subtitle_timing_piecewise_drift_anchor_spread_sec": 0.08,
                }
            )
            variants.append(
                Variant(
                    name="mode_high_piecewise_drift",
                    phase="mode_profile",
                    description="High 모드에 연속 구간 piecewise drift timing 보정을 추가합니다.",
                    method=_mode_profile_method(high_drift_settings),
                    overrides=high_drift_settings,
                    run_llm=run_llm,
                )
            )
    _append_swift_assembled_variant(variants, base_settings)
    return variants


def _deep_ablation_overrides(*, enabled: bool) -> dict[str, Any]:
    value = bool(enabled)
    return {
        "deep_subtitle_policy_enabled": value,
        "deep_segment_setting_policy_enabled": value,
        "deep_stt_candidate_selector_enabled": value,
        "deep_timing_adjustment_enabled": value,
        "subtitle_output_selector_enabled": value,
    }


def benchmark_mode_lora_deep_profiles(base_settings: dict[str, Any], *, llm_model: str = "") -> list[Variant]:
    labels = {
        "fast": "Fast 모드에서 LoRA/Deep 위치를 비교합니다.",
        "auto": "Auto 모드에서 LoRA/Deep 위치를 비교합니다.",
        "high": "High 모드에서 LoRA/Deep 위치를 비교합니다.",
    }
    variants: list[Variant] = []
    for mode in ("fast", "auto", "high"):
        base_mode_settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
        model_label = str(base_mode_settings.get("selected_model") or "").strip()
        run_llm = mode == "high" and bool(model_label and "사용 안함" not in model_label)
        definitions: list[tuple[str, str, dict[str, Any]]] = [
            (
                f"mode_{mode}_baseline",
                "현재 모드 기본 LoRA/Deep 배치를 그대로 사용합니다.",
                {},
            ),
            (
                f"mode_{mode}_lora_off",
                "LoRA micro-merge를 꺼서 STT 원형과 Deep만 남깁니다.",
                {"subtitle_lora_micro_merge_enabled": False},
            ),
        ]
        if mode == "fast":
            definitions.extend(
                [
                    (
                        "mode_fast_deep_on",
                        "Fast 모드에 Deep/출력선택만 추가해서 STT1 + LoRA + Deep을 비교합니다.",
                        _deep_ablation_overrides(enabled=True),
                    ),
                    (
                        "mode_fast_lora_off_deep_on",
                        "Fast 모드에서 LoRA를 끄고 Deep만 추가한 대조군입니다.",
                        {
                            "subtitle_lora_micro_merge_enabled": False,
                            **_deep_ablation_overrides(enabled=True),
                        },
                    ),
                ]
            )
        else:
            definitions.extend(
                [
                    (
                        f"mode_{mode}_deep_off",
                        "Deep/출력선택을 꺼서 LoRA만 남긴 대조군입니다.",
                        _deep_ablation_overrides(enabled=False),
                    ),
                    (
                        f"mode_{mode}_lora_deep_off",
                        "LoRA와 Deep/출력선택을 모두 꺼서 STT timing 원형을 봅니다.",
                        {
                            "subtitle_lora_micro_merge_enabled": False,
                            **_deep_ablation_overrides(enabled=False),
                        },
                    ),
                ]
            )
        for name, description, extra_overrides in definitions:
            mode_settings = dict(base_mode_settings)
            mode_settings.update(extra_overrides)
            variants.append(
                Variant(
                    name=name,
                    phase="mode_lora_deep",
                    description=f"{labels[mode]} {description}",
                    method=_mode_profile_method(mode_settings),
                    overrides=mode_settings,
                    run_llm=run_llm,
                )
            )
    return variants


def benchmark_mode_lora_selective_profiles(base_settings: dict[str, Any], *, llm_model: str = "") -> list[Variant]:
    labels = {
        "fast": "Fast 모드에서 LoRA full/selective를 현재 기본값과 비교합니다.",
        "auto": "Auto 모드에서 LoRA full/selective를 현재 기본값과 비교합니다.",
        "high": "High 모드에서 LoRA full/selective를 현재 기본값과 비교합니다.",
    }
    variants: list[Variant] = []
    for mode in ("fast", "auto", "high"):
        base_mode_settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
        model_label = str(base_mode_settings.get("selected_model") or "").strip()
        run_llm = mode == "high" and bool(model_label and "사용 안함" not in model_label)
        definitions: list[tuple[str, str, dict[str, Any]]] = [
            (
                f"mode_{mode}_baseline",
                "현재 모드 기본 설정을 그대로 사용합니다.",
                {},
            ),
            (
                f"mode_{mode}_lora_full",
                "LoRA micro-merge를 전체 세그먼트에 다시 켭니다.",
                {
                    "subtitle_lora_micro_merge_enabled": True,
                    "subtitle_lora_micro_merge_mode": "full",
                },
            ),
            (
                f"mode_{mode}_lora_selective",
                "LoRA micro-merge를 low readability 구간에만 선택 적용합니다.",
                {
                    "subtitle_lora_micro_merge_enabled": True,
                    "subtitle_lora_micro_merge_mode": "readability_selective",
                },
            ),
        ]
        for name, description, extra_overrides in definitions:
            mode_settings = dict(base_mode_settings)
            mode_settings.update(extra_overrides)
            variants.append(
                Variant(
                    name=name,
                    phase="mode_lora_selective",
                    description=f"{labels[mode]} {description}",
                    method=_mode_profile_method(mode_settings),
                    overrides=mode_settings,
                    run_llm=run_llm,
                )
            )
    return variants


def benchmark_mode_lora_packaging_profiles(base_settings: dict[str, Any], *, llm_model: str = "") -> list[Variant]:
    labels = {
        "fast": "Fast 모드에서 timing-0 LoRA packaging만 현재 기본값과 비교합니다.",
        "auto": "Auto 모드에서 timing-0 LoRA packaging만 현재 기본값과 비교합니다.",
        "high": "High 모드에서 timing-0 LoRA packaging만 현재 기본값과 비교합니다.",
    }
    variants: list[Variant] = []
    for mode in ("fast", "auto", "high"):
        base_mode_settings = _mode_profile_settings(base_settings, mode, llm_model=llm_model)
        model_label = str(base_mode_settings.get("selected_model") or "").strip()
        run_llm = mode == "high" and bool(model_label and "사용 안함" not in model_label)
        definitions: list[tuple[str, str, dict[str, Any]]] = [
            (
                f"mode_{mode}_baseline",
                "현재 모드 기본 설정을 그대로 사용합니다.",
                {},
            ),
            (
                f"mode_{mode}_packaging_full",
                "LoRA micro-merge는 끄고, 후단 줄바꿈/카드 포장만 전체 세그먼트에 적용합니다.",
                {
                    "subtitle_lora_micro_merge_enabled": False,
                    "subtitle_lora_packaging_enabled": True,
                    "subtitle_lora_packaging_mode": "full",
                },
            ),
            (
                f"mode_{mode}_packaging_selective",
                "LoRA micro-merge는 끄고, 후단 줄바꿈/카드 포장만 low readability 구간에 선택 적용합니다.",
                {
                    "subtitle_lora_micro_merge_enabled": False,
                    "subtitle_lora_packaging_enabled": True,
                    "subtitle_lora_packaging_mode": "readability_selective",
                },
            ),
        ]
        for name, description, extra_overrides in definitions:
            mode_settings = dict(base_mode_settings)
            mode_settings.update(extra_overrides)
            variants.append(
                Variant(
                    name=name,
                    phase="mode_lora_packaging",
                    description=f"{labels[mode]} {description}",
                    method=_mode_profile_method(mode_settings),
                    overrides=mode_settings,
                    run_llm=run_llm,
                )
            )
    return variants


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


def score_against_reference(hypothesis: list[dict[str, Any]], reference: list[dict[str, Any]]) -> dict[str, Any]:
    return _benchmark_scoring.score_against_reference(
        hypothesis,
        reference,
        swift_timing_backend=score_timing_metrics_via_swift,
        cpp_timing_backend=cpp_timing_metrics,
    )


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
        optimized = subtitle_engine.optimize_segments([dict(row) for row in rows], vad_segments=vad)
    return _apply_benchmark_speaker_postprocess(optimized, settings)


class _BenchmarkSpeakerRuntime(PipelineHelpersMixin):
    def __init__(self, settings: dict[str, Any]) -> None:
        ceiling = max(1, automatic_speaker_ceiling(settings))
        self.min_speakers = 1
        self.max_speakers = 1
        self._effective_min_speakers = 1
        self._effective_max_speakers = ceiling
        self._speaker_auto_enabled = speaker_diarization_auto_enabled(settings)
        self._speaker_map: list[dict[str, Any]] = []


def _apply_benchmark_speaker_postprocess(rows: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = _BenchmarkSpeakerRuntime(settings)
    if not runtime._speaker_auto_processing_enabled():
        return [dict(row) for row in list(rows or []) if isinstance(row, dict)]
    return runtime._apply_runtime_speaker_diarization([dict(row) for row in list(rows or []) if isinstance(row, dict)])


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


def _row_quality_score(row: dict[str, Any]) -> float:
    try:
        return float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)
    except Exception:
        return 0.0


def _preserve_candidate_attempt_artifact(work_dir: Path, variant_name: str, filename: str) -> None:
    path = work_dir / variant_name / filename
    if not path.exists():
        return
    attempt_path = work_dir / variant_name / f"candidate_attempt_{filename}"
    if not attempt_path.exists():
        shutil.copy2(path, attempt_path)


def _copy_variant_artifact(work_dir: Path, source_name: str, target_name: str, filename: str) -> None:
    source = work_dir / source_name / filename
    target = work_dir / target_name / filename
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    _preserve_candidate_attempt_artifact(work_dir, target_name, filename)
    shutil.copy2(source, target)


def _enforce_swift_assembly_quality_floor(rows: list[dict[str, Any]], work_dir: Path) -> list[dict[str, Any]]:
    by_name = {str(row.get("name") or ""): dict(row) for row in rows}
    candidate = by_name.get(ASSEMBLED_VARIANT_NAME)
    if not candidate:
        return rows
    baselines = [by_name[name] for name in QUALITY_BASELINE_VARIANTS if name in by_name and not by_name[name].get("error")]
    if not baselines:
        return rows
    best = max(baselines, key=_row_quality_score)
    gate = evaluate_subtitle_assembly_quality_gate(rows)
    if bool(gate.get("passed")) or _row_quality_score(candidate) >= _row_quality_score(best):
        return rows

    repaired = dict(best)
    repaired.update(
        {
            "name": ASSEMBLED_VARIANT_NAME,
            "phase": candidate.get("phase", repaired.get("phase")),
            "description": candidate.get("description", repaired.get("description")),
            "method": candidate.get("method", repaired.get("method")),
            "run_llm": candidate.get("run_llm", repaired.get("run_llm")),
            "elapsed_sec": candidate.get("elapsed_sec", repaired.get("elapsed_sec")),
            "native_subtitle_assembly_quality_floor_applied": True,
            "native_subtitle_assembly_selected_result_variant": best.get("name"),
            "native_subtitle_assembly_quality_floor_gate": gate,
            "candidate_attempt_quality": candidate.get("quality"),
            "candidate_attempt_readability": candidate.get("readability"),
            "candidate_attempt_final_segments": candidate.get("final_segments"),
        }
    )
    repaired_settings = dict(candidate.get("settings") or {})
    repaired_settings["native_subtitle_assembly_selected_result_variant"] = best.get("name")
    repaired_settings["native_subtitle_assembly_quality_floor_applied"] = True
    repaired["settings"] = repaired_settings

    for filename in ("output_segments.json", "raw_segments.json"):
        _copy_variant_artifact(work_dir, str(best.get("name") or ""), ASSEMBLED_VARIANT_NAME, filename)

    return [repaired if str(row.get("name") or "") == ASSEMBLED_VARIANT_NAME else row for row in rows]


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
    readability = score_readability(final_rows, settings) if final_rows else {}
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
        "readability": readability,
        "settings": {
            key: settings.get(key)
            for key in (
                "subtitle_mode",
                "simple_operation_mode",
                "stt_quality_preset",
                "selected_whisper_model",
                "selected_whisper_model_secondary",
                "selected_model",
                "selected_llm_provider",
                "stt_ensemble_enabled",
                "stt_ensemble_parallel_enabled",
                "stt_ensemble_selective_enabled",
                "stt_selective_secondary_recheck_enabled",
                "stt_low_score_recheck_threshold",
                "stt_word_timestamps_mode",
                "stt_word_timestamps_default_enabled",
                "stt_word_timestamps_precision_enabled",
                "stt_word_timestamps_precision_min_similarity",
                "stt_word_timestamps_precision_max_timing_shift_sec",
                "subtitle_lora_micro_merge_enabled",
                "subtitle_lora_packaging_enabled",
                "subtitle_lora_packaging_mode",
                "sub_gap_break_sec",
                "word_timing_gap_break_sec",
                "continuous_threshold",
                "gap_push_rate",
                "gap_pull_rate",
                "single_subtitle_end",
                "vad_post_stt_align_enabled",
                "vad_post_stt_edge_pad_sec",
                "subtitle_cut_boundary_guard_enabled",
                "subtitle_bundle_use_confirmed_cuts",
                "subtitle_bundle_use_provisional_cuts",
                "subtitle_llm_macro_chunk_enabled",
                "subtitle_llm_context_boundary_refine_enabled",
                "subtitle_llm_context_word_correction_enabled",
                "subtitle_llm_context_max_pairs",
                "subtitle_llm_context_require_risk_signal",
                "deep_subtitle_policy_enabled",
                "deep_timing_adjustment_enabled",
                "subtitle_timing_anchor_max_start_lag_sec",
                "subtitle_timing_anchor_max_end_lead_sec",
                "subtitle_timing_anchor_max_end_lag_sec",
            )
        },
    }
    resource_summary = _native_resource_summary_for_variant(settings, run_llm=variant.run_llm)
    if resource_summary:
        row["native_resource_summary"] = resource_summary
    stt_segments_summary = _native_stt_segments_summary_for_variant(raw_rows)
    if stt_segments_summary:
        row["native_stt_segments_summary"] = stt_segments_summary
    segments_summary = _native_segments_summary_for_variant(final_rows)
    if segments_summary:
        row["native_segments_summary"] = segments_summary
    global_canvas_summary = _native_global_canvas_summary_for_variant(
        final_rows,
        duration=float(base_settings.get("_benchmark_span_sec", 180.0) or 180.0),
    )
    if global_canvas_summary:
        row["native_global_canvas_summary"] = global_canvas_summary
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


def _rank_rows(
    rows: list[dict[str, Any]],
    *,
    objective: str = "reference",
    ranking_policy: str = "speed_weighted",
) -> list[dict[str, Any]]:
    fastest = min((float(row.get("elapsed_sec", 0.0) or 0.0) for row in rows if not row.get("error")), default=0.0)
    objective_key = "readability" if str(objective or "").strip().lower() == "readability" else "quality"
    ranking_key = str(ranking_policy or "speed_weighted").strip().lower()
    ranked = []
    for row in rows:
        item = dict(row)
        quality = float(dict(row.get("quality") or {}).get("quality_score", 0.0) or 0.0)
        readability = float(dict(row.get("readability") or {}).get("readability_score", 0.0) or 0.0)
        elapsed = float(row.get("elapsed_sec", 0.0) or 0.0)
        speed_score = 0.0 if elapsed <= 0.0 or fastest <= 0.0 else min(100.0, fastest / elapsed * 100.0)
        item["speed_score"] = round(speed_score, 3)
        item["quality_speed_score"] = round(quality * 0.82 + speed_score * 0.18, 3)
        item["readability_speed_score"] = round(readability * 0.82 + speed_score * 0.18, 3)
        if objective_key == "readability":
            item["primary_score_name"] = "readability"
            item["primary_score"] = round(readability, 3)
            item["primary_speed_score"] = item["readability_speed_score"]
        else:
            item["primary_score_name"] = "quality"
            item["primary_score"] = round(quality, 3)
            item["primary_speed_score"] = item["quality_speed_score"]
        item["ranking_policy"] = ranking_key
        ranked.append(item)
    if ranking_key == "primary_first":
        ranked.sort(
            key=lambda row: (
                float(row.get("primary_score", 0.0) or 0.0),
                float(row.get("speed_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
    else:
        ranked.sort(
            key=lambda row: (
                float(row.get("primary_speed_score", 0.0) or 0.0),
                float(row.get("primary_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked


def _write_markdown(payload: dict[str, Any], output_path: Path) -> None:
    rows = payload.get("ranked_results") or []
    objective = str(payload.get("objective") or "reference")
    ranking_policy = str(payload.get("ranking_policy") or "speed_weighted")
    lines = [
        "# Subtitle Pipeline Variant Benchmark",
        "",
        f"- Media: `{payload.get('media')}`",
        f"- Reference: `{payload.get('reference_srt')}`",
        f"- Span: {payload.get('start_sec')}s ~ {payload.get('end_sec')}s",
        f"- Objective: `{objective}`",
        f"- Ranking policy: `{ranking_policy}`",
        f"- Created: {payload.get('created_at')}",
        "",
        "| Rank | Variant | Phase | Time(s) | Quality | Readability | Speed | Primary+Speed | Segs | ΔSegs | Avg CPS | Max Line | Orphans | CER | Timing MAE | Error |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        q = dict(row.get("quality") or {})
        readability = dict(row.get("readability") or {})
        lines.append(
            "| {rank} | `{name}` | {phase} | {elapsed:.3f} | {quality:.3f} | {readability_score:.3f} | {speed:.3f} | {combo:.3f} | {segs} | {delta} | {cps:.3f} | {max_line:.3f} | {orphans} | {cer:.4f} | {timing:.3f} | {error} |".format(
                rank=row.get("rank", ""),
                name=row.get("name", ""),
                phase=row.get("phase", ""),
                elapsed=float(row.get("elapsed_sec", 0.0) or 0.0),
                quality=float(q.get("quality_score", 0.0) or 0.0),
                readability_score=float(readability.get("readability_score", 0.0) or 0.0),
                speed=float(row.get("speed_score", 0.0) or 0.0),
                combo=float(row.get("primary_speed_score", 0.0) or 0.0),
                segs=row.get("final_segments", 0),
                delta=int(q.get("segment_count_delta", 0) or 0),
                cps=float(q.get("avg_cps", 0.0) or 0.0),
                max_line=float(readability.get("avg_max_line_chars", 0.0) or 0.0),
                orphans=int(readability.get("orphan_line_segments", 0) or 0),
                cer=float(q.get("cer", 0.0) or 0.0),
                timing=float(q.get("timing_mae_sec", 0.0) or 0.0),
                error=str(row.get("error") or "").replace("|", "/")[:90],
            )
        )
    lines.append("")
    if rows:
        best = rows[0]
        lines.append(
            f"Recommended current winner: `{best.get('name')}` with {best.get('primary_score_name')} score {best.get('primary_score')} (ranking policy `{ranking_policy}`)."
        )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark subtitle pipeline order/gating variants on a real 3-minute fixture.")
    parser.add_argument(
        "--suite",
        choices=["variants", "modes", "mode-lora-deep", "mode-lora-selective", "mode-lora-packaging"],
        default="variants",
        help="Run historical tuning variants, exact Fast/Auto/High mode profiles, or mode-specific LoRA ablations.",
    )
    parser.add_argument(
        "--objective",
        choices=["reference", "readability"],
        default="reference",
        help="Rank variants by reference quality or by display readability heuristics.",
    )
    parser.add_argument(
        "--ranking-policy",
        choices=["auto", "speed_weighted", "primary_first"],
        default="auto",
        help="Ranking rule. Auto uses quality/readability-first for mode suites and speed-weighted ranking elsewhere.",
    )
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
    if args.suite == "modes":
        variants = benchmark_mode_profiles(base_settings, llm_model=str(args.llm_model or "").strip())
    elif args.suite == "mode-lora-deep":
        variants = benchmark_mode_lora_deep_profiles(base_settings, llm_model=str(args.llm_model or "").strip())
    elif args.suite == "mode-lora-selective":
        variants = benchmark_mode_lora_selective_profiles(base_settings, llm_model=str(args.llm_model or "").strip())
    elif args.suite == "mode-lora-packaging":
        variants = benchmark_mode_lora_packaging_profiles(base_settings, llm_model=str(args.llm_model or "").strip())
    else:
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
    extraction_cache: dict[str, dict[str, Any]] = {}

    def _seed_chunks_for_settings(
        extraction_settings: dict[str, Any],
        *,
        seed_name: str,
        profile_name: str,
        profile_description: str = "",
    ) -> dict[str, Any]:
        signature = _chunk_extraction_signature(extraction_settings)
        cached = extraction_cache.get(signature)
        if cached:
            return cached
        extractor = VideoProcessor()
        _bind_processor_settings(extractor, extraction_settings)
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
            raise RuntimeError(f"audio chunk extraction failed for {seed_name}: {chunk_source}")
        seed_chunk_source = _copy_chunk_dir(chunk_source, work_dir / "_seed_chunks" / seed_name)
        cached = {
            "profile": profile_name,
            "description": profile_description,
            "elapsed_sec": round(extract_elapsed, 3),
            "chunk_source": seed_chunk_source,
            "chunk_wavs": _chunk_wav_count(seed_chunk_source),
            "vad_segments": len(_load_vad(seed_chunk_source)),
            "signature": signature,
            "settings": extraction_settings,
        }
        extraction_cache[signature] = cached
        audio_extracts.append(
            {
                "profile": profile_name,
                "description": profile_description,
                "elapsed_sec": cached["elapsed_sec"],
                "audio_chunk_dir": str(seed_chunk_source),
                "chunk_wavs": cached["chunk_wavs"],
                "vad_segments": cached["vad_segments"],
                "settings": {
                    key: extraction_settings.get(key)
                    for key in (
                        "subtitle_mode",
                        "stt_quality_preset",
                        "selected_audio_ai",
                        "selected_vad",
                        "audio_chunk_routing_enabled",
                        "audio_chunk_route_vad_enabled",
                        "audio_chunk_profile_sec",
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
        return cached

    if selected_audio_profiles:
        for profile in selected_audio_profiles:
            profile_settings = {**base_settings, **profile.overrides, "_benchmark_audio_profile": profile.name}
            profile_work_dir = work_dir / profile.name
            profile_work_dir.mkdir(parents=True, exist_ok=True)
            for variant in variants:
                extraction_settings = _variant_chunk_settings(profile_settings, variant.overrides)
                chunk_info = _seed_chunks_for_settings(
                    extraction_settings,
                    seed_name=f"{profile.name}__{variant.name}",
                    profile_name=profile.name,
                    profile_description=profile.description,
                )
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
                    chunk_source=Path(chunk_info["chunk_source"]),
                    work_dir=profile_work_dir,
                    base_settings=profile_settings,
                    reference=reference_rows,
                )
                row["audio_profile"] = profile.name
                row["audio_profile_description"] = profile.description
                row["audio_extract_elapsed_sec"] = float(chunk_info["elapsed_sec"])
                row["audio_chunk_wavs"] = int(chunk_info["chunk_wavs"])
                row["audio_vad_segments"] = int(chunk_info["vad_segments"])
                results.append(row)
    else:
        for variant in variants:
            extraction_settings = _variant_chunk_settings(base_settings, variant.overrides)
            chunk_info = _seed_chunks_for_settings(
                extraction_settings,
                seed_name=variant.name,
                profile_name="default",
            )
            results.append(
                _run_variant(
                    variant,
                    chunk_source=Path(chunk_info["chunk_source"]),
                    work_dir=work_dir,
                    base_settings=base_settings,
                    reference=reference_rows,
                )
            )
    ranking_policy = str(args.ranking_policy or "auto").strip().lower()
    if ranking_policy == "auto":
        ranking_policy = "primary_first" if str(args.suite or "").startswith("mode") or str(args.suite or "") == "modes" else "speed_weighted"
    results = _enforce_swift_assembly_quality_floor(results, work_dir)
    ranked = _rank_rows(results, objective=str(args.objective or "reference"), ranking_policy=ranking_policy)
    payload = {
        "schema": "ai_subtitle_studio.subtitle_pipeline_variant_benchmark.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "suite": args.suite,
        "objective": str(args.objective or "reference"),
        "ranking_policy": ranking_policy,
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
