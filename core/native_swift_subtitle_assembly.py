from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


QUALITY_BASELINE_VARIANTS = ("mode_fast", "mode_auto", "mode_high")
PREFERRED_SOURCE_VARIANTS = (
    "mode_high_full_core_overlap",
    "mode_high_piecewise_drift",
    "mode_high",
    "mode_auto",
    "mode_fast",
)
ASSEMBLED_VARIANT_NAME = "mode_swift_assembled"


def _variant_name(row: dict[str, Any]) -> str:
    return str(row.get("name") or "").strip()


def _quality_score(row: dict[str, Any] | None) -> float:
    try:
        quality = dict((row or {}).get("quality") or {})
        return float(quality.get("quality_score", (row or {}).get("quality_score", 0.0)) or 0.0)
    except Exception:
        return 0.0


def _fallback_subtitle_assembly_plan(available_variants: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    names = {_variant_name(row) for row in list(available_variants or []) if _variant_name(row)}
    source_variant = next((name for name in PREFERRED_SOURCE_VARIANTS if name in names), "mode_high")
    return {
        "schema": "ai_subtitle_studio.subtitle_assembly.plan.v1",
        "candidate_variant": ASSEMBLED_VARIANT_NAME,
        "source_variant": source_variant,
        "fallback_variant": "mode_high",
        "assembly_owner": "python_fallback",
        "stages": [
            {"id": "media_audio_prepare", "role": "extract_and_chunk_audio", "quality_sensitive": False},
            {"id": "stt_primary", "role": "primary_stt_ane_gpu", "quality_sensitive": True},
            {"id": "stt_secondary_recheck", "role": "selective_stt2_rescue", "quality_sensitive": True},
            {"id": "word_timing_precision", "role": "selected_word_timing_refine", "quality_sensitive": True},
            {"id": "subtitle_policy", "role": "split_merge_context_policy", "quality_sensitive": True},
            {"id": "final_anchor_guard", "role": "preserve_selected_stt_text_and_timing", "quality_sensitive": True},
            {"id": "benchmark_quality_gate", "role": "candidate_score_must_not_drop_below_fast_auto_high", "quality_sensitive": True},
        ],
        "settings_overrides": {
            "native_subtitle_assembly_enabled": True,
            "native_subtitle_assembly_source_variant": source_variant,
            "native_subtitle_assembly_quality_floor": "best_fast_auto_high",
            "native_resource_allocator_worker_plan_enabled": True,
            "runtime_hardware_acceleration_enabled": True,
            "stt_backend_policy": "native",
            "whisperkit_native_auto_enabled": True,
            "stt_accelerator_distribution": "gpu+npu+cpu",
            "audio_torch_gpu_enabled": True,
            "ffmpeg_videotoolbox_decode_enabled": True,
            "scan_cut_pioneer_pipe_hwaccel_enabled": True,
            "lora_gpu_acceleration_enabled": True,
            "subtitle_final_stt_anchor_guard_enabled": True,
            "subtitle_final_stt_anchor_guard_insert_missing_enabled": True,
            "subtitle_llm_prev_next_context_enabled": True,
            "subtitle_llm_context_candidate_limit": 5,
            "subtitle_llm_context_min_current_similarity": 0.86,
            "subtitle_llm_context_neighbor_reject_margin": 0.06,
            "subtitle_output_selector_enabled": True,
            "stt_word_timestamps_precision_max_segments": 48,
            "stt_word_timestamps_precision_min_similarity": 0.36,
            "stt_word_timestamps_precision_max_timing_shift_sec": 0.28,
        },
        "quality_floor": {
            "baseline_variants": list(QUALITY_BASELINE_VARIANTS),
            "metric": "quality_score",
            "comparison": "candidate_must_be_at_least_best_baseline",
            "minimum_delta": 0.0,
        },
        "promotion_rule": {
            "requires_benchmark": True,
            "candidate_variant": ASSEMBLED_VARIANT_NAME,
            "baseline_variants": list(QUALITY_BASELINE_VARIANTS),
            "failure_action": "keep_existing_fast_auto_high_paths",
        },
    }


def plan_subtitle_assembly_via_swift(
    available_variants: list[dict[str, Any]] | None = None,
    *,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "candidate_variant": ASSEMBLED_VARIANT_NAME,
        "quality_baseline_variants": list(QUALITY_BASELINE_VARIANTS),
        "available_variants": list(available_variants or []),
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_assembly_plan",
        payload,
        settings=settings,
        context={"bridge": "native_swift_subtitle_assembly"},
    )
    if isinstance(native, dict) and native.get("candidate_variant"):
        return native
    return _fallback_subtitle_assembly_plan(available_variants)


def evaluate_subtitle_assembly_quality_gate_via_swift(
    rows: list[dict[str, Any]],
    *,
    candidate_variant: str = ASSEMBLED_VARIANT_NAME,
    baseline_variants: tuple[str, ...] = QUALITY_BASELINE_VARIANTS,
) -> dict[str, Any]:
    payload = {
        "candidate_variant": str(candidate_variant or ASSEMBLED_VARIANT_NAME),
        "baseline_variants": list(baseline_variants or QUALITY_BASELINE_VARIANTS),
        "ranked_results": list(rows or []),
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_assembly_quality_gate",
        payload,
        context={"bridge": "native_swift_subtitle_assembly_quality_gate"},
    )
    if isinstance(native, dict) and native.get("schema"):
        return native
    return evaluate_subtitle_assembly_quality_gate(rows, candidate_variant=candidate_variant, baseline_variants=baseline_variants)


def evaluate_subtitle_assembly_quality_gate(
    rows: list[dict[str, Any]],
    *,
    candidate_variant: str = ASSEMBLED_VARIANT_NAME,
    baseline_variants: tuple[str, ...] = QUALITY_BASELINE_VARIANTS,
) -> dict[str, Any]:
    by_name = {_variant_name(row): dict(row) for row in list(rows or []) if _variant_name(row)}
    candidate_name = str(candidate_variant or ASSEMBLED_VARIANT_NAME)
    candidate = by_name.get(candidate_name)
    if candidate is None:
        return {
            "schema": "ai_subtitle_studio.subtitle_assembly.quality_gate.v1",
            "passed": False,
            "reason": "missing_candidate",
            "candidate_variant": candidate_name,
            "baseline_variants": list(baseline_variants),
        }
    baselines = [by_name[name] for name in baseline_variants if name in by_name]
    if not baselines:
        return {
            "schema": "ai_subtitle_studio.subtitle_assembly.quality_gate.v1",
            "passed": False,
            "reason": "missing_baseline",
            "candidate_variant": candidate_name,
            "baseline_variants": list(baseline_variants),
        }
    best = max(baselines, key=_quality_score)
    delta = _quality_score(candidate) - _quality_score(best)
    return {
        "schema": "ai_subtitle_studio.subtitle_assembly.quality_gate.v1",
        "passed": delta >= 0.0,
        "reason": "candidate_not_below_best_fast_auto_high" if delta >= 0.0 else "quality_score_below_best_fast_auto_high",
        "candidate_variant": candidate_name,
        "baseline_variant": _variant_name(best),
        "candidate_quality_score": round(_quality_score(candidate), 3),
        "baseline_quality_score": round(_quality_score(best), 3),
        "quality_delta": round(delta, 3),
        "baseline_variants": list(baseline_variants),
    }


__all__ = [
    "ASSEMBLED_VARIANT_NAME",
    "QUALITY_BASELINE_VARIANTS",
    "evaluate_subtitle_assembly_quality_gate",
    "evaluate_subtitle_assembly_quality_gate_via_swift",
    "plan_subtitle_assembly_via_swift",
]
