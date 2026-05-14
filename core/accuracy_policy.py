# Version: 03.14.17
# Phase: PHASE2
"""Accuracy-first runtime policy for subtitle generation."""

from __future__ import annotations

from copy import deepcopy

from core.audio.stt_quality_presets import apply_stt_quality_preset, normalize_stt_quality_key
from core.autopilot_policy import apply_autopilot_runtime_policy, autopilot_runtime_defaults
from core.mode_policy import apply_mode_runtime_settings


ACCURACY_FIRST_DEFAULTS = {
    "accuracy_first_mode": True,
    "auto_start_mode": "balanced",
    "stt_quality_preset": "balanced",
    "selected_model": "사용 안함 (Whisper 단독 진행)",
    "selected_llm_provider": "none",
    "stt_ensemble_enabled": False,
    "stt_ensemble_llm_judge_enabled": False,
    "stt_ensemble_llm_judge_require_risk": True,
    "stt_ensemble_llm_judge_local_only": True,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 80,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "vad_post_stt_align_enabled": True,
    "vad_post_stt_max_shift_sec": 0.7,
    "vad_post_stt_edge_pad_sec": 0.04,
    "audio_chunk_routing_enabled": False,
    "audio_chunk_route_vad_enabled": False,
    "audio_chunk_route_max_workers": 2,
    "audio_chunk_profile_sec": 30.0,
    "whisper_chunk_overlap_sec": 3.0,
    "chunk_time_limit": 180,
    "review_auto_correct_apply_threshold": 94,
    "review_auto_correct_min_improvement": 8,
    "review_recheck_buffer_sec": 1.5,
    "review_vad_before_stt_enabled": True,
    "review_vad_strict_mode": True,
    "review_vad_speech_pad_sec": 0.35,
    "review_vad_min_silence_sec": 0.8,
}

ACCURACY_RUNTIME_DEFAULTS = {
    "accuracy_first_mode": True,
    "auto_start_mode": "balanced",
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 80,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "audio_chunk_routing_enabled": False,
    "audio_chunk_route_vad_enabled": False,
    "audio_chunk_route_max_workers": 2,
    "audio_chunk_profile_sec": 30.0,
    "review_auto_correct_apply_threshold": 94,
    "review_auto_correct_min_improvement": 8,
    "review_recheck_buffer_sec": 1.5,
    "review_vad_before_stt_enabled": True,
    "review_vad_strict_mode": True,
}

AUTO_SPEED_SAFE_RUNTIME_OVERRIDES = {
    # Auto mode must stay responsive. Precise mode can still opt into the
    # heavier ensemble/review path explicitly. Do not override
    # stt_quality_preset/auto_start_mode here: those are user-facing quality
    # selections, while AutoPilot only owns the internal execution caps.
    "selected_model": "사용 안함 (Whisper 단독 진행)",
    "selected_llm_provider": "none",
    "stt_ensemble_enabled": False,
    "stt_ensemble_llm_judge_enabled": False,
    "stt_ensemble_llm_judge_require_risk": True,
    "stt_ensemble_llm_judge_local_only": True,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_max_segments": 80,
    "whisper_chunk_overlap_sec": 1.5,
    "chunk_time_limit": 240,
    "subtitle_bundle_target_sec": 240,
    "subtitle_bundle_min_sec": 120,
    "subtitle_bundle_max_sec": 420,
    "segment_lora_retrieval_limit": 8,
    "segment_lora_retrieval_per_kind": 2,
    "editor_truth_runtime_pattern_limit": 80,
    "stt_lattice_artifact_candidate_limit": 16,
    "stt_lattice_artifact_word_limit": 64,
    "llm_verifier_max_chunks": 4,
    "accuracy_graph_persist_enabled": False,
    "deep_policy_event_logging_enabled": False,
    "deep_policy_event_max_rows_per_run": 128,
    "deep_quality_event_logging_enabled": False,
    "subtitle_decision_explanation_logging_enabled": False,
    "background_prefetch_lora_enabled": False,
    "background_prefetch_candidates_enabled": False,
    "background_prefetch_segment_limit": 4,
    "runtime_quality_self_review_enabled": False,
    "hardcase_training_queue_max_items_per_run": 48,
    "roughcut_llm_enabled": False,
    "roughcut_llm_use_override": False,
    "roughcut_llm_provider": "none",
    "roughcut_llm_model": "사용 안함",
    **autopilot_runtime_defaults(),
}
LIGHTWEIGHT_RUNTIME_CAP_OVERRIDES = {
    key: value
    for key, value in AUTO_SPEED_SAFE_RUNTIME_OVERRIDES.items()
    if key not in {"auto_start_mode", "stt_quality_preset"}
}

PRESERVE_EXPLICIT_KEYS = {
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
    "roughcut_llm_prompt",
    "roughcut_llm_threads_auto_enabled",
    "roughcut_llm_threads",
    "roughcut_llm_threads_resource_max",
    "roughcut_llm_rows_auto_enabled",
    "roughcut_llm_rows_lora_enabled",
    "roughcut_llm_rows_lora_blend",
    "roughcut_llm_rows_exploration_rate",
    "roughcut_llm_max_context_rows",
    "roughcut_llm_chunk_rows",
    "roughcut_llm_lookahead_rows",
    "roughcut_llm_context_min_rows",
    "roughcut_llm_context_max_rows",
    "roughcut_llm_chunk_min_rows",
    "roughcut_llm_chunk_max_rows",
    "roughcut_llm_lookahead_min_rows",
    "roughcut_llm_lookahead_max_rows",
    "selected_roughcut_llm_model",
    "selected_roughcut_llm_provider",
}


def accuracy_first_defaults() -> dict:
    return deepcopy(ACCURACY_FIRST_DEFAULTS)


def apply_accuracy_first_defaults(settings: dict | None) -> dict:
    out = dict(settings or {})
    for key, value in ACCURACY_FIRST_DEFAULTS.items():
        out.setdefault(key, deepcopy(value))
    out["auto_start_mode"] = normalize_stt_quality_key(
        out.get("auto_start_mode") or out.get("stt_quality_preset") or "balanced"
    )
    if "stt_quality_preset" not in out or not str(out.get("stt_quality_preset") or "").strip():
        out["stt_quality_preset"] = "balanced"
    return out


def _apply_apple_m_runtime_plan(settings: dict) -> dict:
    try:
        from core.runtime.multi_process import apply_apple_m_subtitle_pipeline_plan

        return apply_apple_m_subtitle_pipeline_plan(settings)
    except Exception:
        return settings


def apply_accuracy_first_runtime_settings(settings: dict | None) -> dict:
    out = apply_accuracy_first_defaults(settings)
    if not bool(out.get("accuracy_first_mode", True)):
        return _apply_apple_m_runtime_plan(out)

    explicit_values = {
        key: deepcopy(out[key])
        for key in PRESERVE_EXPLICIT_KEYS
        if key in out
    }

    preset_key = normalize_stt_quality_key(out.get("stt_quality_preset") or "balanced")
    auto_start_key = normalize_stt_quality_key(out.get("auto_start_mode") or preset_key)
    out = apply_stt_quality_preset(out, preset_key)

    out.update(explicit_values)

    for key, value in ACCURACY_RUNTIME_DEFAULTS.items():
        out.setdefault(key, deepcopy(value))
    simple_mode = str(out.get("simple_operation_mode") or "").strip().lower()
    preset_key = normalize_stt_quality_key(out.get("stt_quality_preset") or "balanced")
    if preset_key != "precise":
        if simple_mode in {"auto", "자동", "autopilot", "default"}:
            out.update(deepcopy(AUTO_SPEED_SAFE_RUNTIME_OVERRIDES))
        elif simple_mode not in {"precise", "정밀", "accuracy", "high"}:
            out.update(deepcopy(LIGHTWEIGHT_RUNTIME_CAP_OVERRIDES))
        out["stt_quality_preset"] = preset_key
        out["auto_start_mode"] = auto_start_key
        out["_speed_safe_auto_profile"] = "03.21.auto_speed_safe.v1"
    out = apply_autopilot_runtime_policy(out)
    out = apply_mode_runtime_settings(out)
    return _apply_apple_m_runtime_plan(out)
