# Version: 03.14.17
# Phase: PHASE2
"""Accuracy-first runtime policy for subtitle generation."""

from __future__ import annotations

from copy import deepcopy

from core.audio.stt_quality_presets import apply_stt_quality_preset, normalize_stt_quality_key


ACCURACY_FIRST_DEFAULTS = {
    "accuracy_first_mode": True,
    "auto_start_mode": "precise",
    "stt_quality_preset": "precise",
    "stt_ensemble_enabled": True,
    "stt_ensemble_llm_judge_enabled": True,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 240,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "vad_post_stt_align_enabled": True,
    "vad_post_stt_max_shift_sec": 0.7,
    "vad_post_stt_edge_pad_sec": 0.04,
    "audio_chunk_routing_enabled": True,
    "audio_chunk_route_vad_enabled": True,
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
    "auto_start_mode": "precise",
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 240,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "audio_chunk_routing_enabled": True,
    "audio_chunk_route_vad_enabled": True,
    "audio_chunk_profile_sec": 30.0,
    "review_auto_correct_apply_threshold": 94,
    "review_auto_correct_min_improvement": 8,
    "review_recheck_buffer_sec": 1.5,
    "review_vad_before_stt_enabled": True,
    "review_vad_strict_mode": True,
}

PRESERVE_EXPLICIT_KEYS = {
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
    "roughcut_llm_prompt",
    "roughcut_llm_threads",
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
        out.get("auto_start_mode") or out.get("stt_quality_preset") or "precise"
    )
    if "stt_quality_preset" not in out or not str(out.get("stt_quality_preset") or "").strip():
        out["stt_quality_preset"] = "precise"
    return out


def apply_accuracy_first_runtime_settings(settings: dict | None) -> dict:
    out = apply_accuracy_first_defaults(settings)
    if not bool(out.get("accuracy_first_mode", True)):
        return out

    explicit_values = {
        key: deepcopy(out[key])
        for key in PRESERVE_EXPLICIT_KEYS
        if key in out
    }

    preset_key = normalize_stt_quality_key(out.get("stt_quality_preset") or "precise")
    out = apply_stt_quality_preset(out, preset_key)

    out.update(explicit_values)

    for key, value in ACCURACY_RUNTIME_DEFAULTS.items():
        out.setdefault(key, deepcopy(value))
    return out
