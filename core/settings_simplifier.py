from __future__ import annotations

from typing import Any

from core.autopilot_policy import apply_autopilot_runtime_policy, autopilot_runtime_defaults
from core.audio.stt_quality_presets import USER_SELECTED_ROUTE_KEYS
from core.mode_policy import (
    MODE_LABELS,
    MODE_ORDER,
    apply_mode_runtime_settings,
    mode_label,
    mode_to_stt_quality,
    normalize_mode,
)


SIMPLE_OPERATION_MODE_SCHEMA = "ai_subtitle_studio.simple_operation_mode.v1"
SIMPLE_OPERATION_MODE_ORDER = MODE_ORDER
USER_VISIBLE_OPERATION_MODE_ORDER = MODE_ORDER
AUTOPILOT_AUTO_MANAGED_KEYS = tuple(autopilot_runtime_defaults().keys())

SIMPLE_OPERATION_MODES: dict[str, dict[str, Any]] = {
    "fast": {
        "label": MODE_LABELS["fast"],
        "summary": "Fast mode uses the lightest safe subtitle path and blocks obvious hallucinations.",
        "settings": {
            "accuracy_first_mode": True,
            "subtitle_mode": "fast",
            "auto_start_mode": "fast",
            "stt_quality_preset": "fast",
            "subtitle_bundle_target_sec": 240,
            "subtitle_bundle_min_sec": 120,
            "subtitle_bundle_max_sec": 420,
            "scan_cut_level": "off",
            "cut_boundary_level": "off",
            "scan_cut_boundary_level": "off",
        },
    },
    "auto": {
        "label": MODE_LABELS["auto"],
        "summary": "Auto mode starts light and escalates only uncertain sections.",
        "settings": {
            "accuracy_first_mode": True,
            "subtitle_mode": "auto",
            "auto_start_mode": "balanced",
            "stt_quality_preset": "balanced",
            "selected_model": "사용 안함 (Whisper 단독 진행)",
            "selected_llm_provider": "none",
            "subtitle_bundle_target_sec": 240,
            "subtitle_bundle_min_sec": 120,
            "subtitle_bundle_max_sec": 420,
            "scan_cut_level": "low",
            "cut_boundary_level": "low",
            "scan_cut_boundary_level": "low",
            "stt_low_score_recheck_max_segments": 80,
            "segment_lora_retrieval_limit": 8,
            "segment_lora_retrieval_per_kind": 2,
            "editor_truth_runtime_pattern_limit": 80,
            "stt_lattice_artifact_candidate_limit": 16,
            "stt_lattice_artifact_word_limit": 64,
            "llm_verifier_max_chunks": 4,
            "accuracy_graph_persist_enabled": False,
            "deep_policy_event_logging_enabled": False,
            "deep_quality_event_logging_enabled": False,
            "subtitle_decision_explanation_logging_enabled": False,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "background_prefetch_segment_limit": 4,
            "runtime_scheduler_ramp_up_enabled": True,
            "runtime_scheduler_ramp_initial_sec": 45.0,
            "runtime_scheduler_ramp_step_sec": 60.0,
            "runtime_quality_self_review_enabled": False,
            "hardcase_training_queue_max_items_per_run": 48,
            "roughcut_llm_enabled": False,
            "roughcut_llm_use_override": False,
            "roughcut_llm_provider": "none",
            "roughcut_llm_model": "사용 안함",
            **autopilot_runtime_defaults(),
        },
    },
    "high": {
        "label": MODE_LABELS["high"],
        "summary": "High mode turns on the full accuracy stack and may take much longer.",
        "settings": {
            "accuracy_first_mode": True,
            "subtitle_mode": "high",
            "auto_start_mode": "precise",
            "stt_quality_preset": "precise",
            "subtitle_bundle_target_sec": 150,
            "subtitle_bundle_min_sec": 75,
            "subtitle_bundle_max_sec": 240,
            "scan_cut_level": "medium",
            "cut_boundary_level": "medium",
            "scan_cut_boundary_level": "medium",
        },
    },
    "stt": {
        "label": MODE_LABELS["stt"],
        "summary": "STT mode creates VAD work segments for human typing or OS dictation, then resegments with LoRA/Deep/rules.",
        "settings": {
            "accuracy_first_mode": True,
            "subtitle_mode": "stt",
            "auto_start_mode": "stt",
            "stt_quality_preset": "stt",
            "stt_mode_enabled": True,
            "stt_mode_text_input_provider": "manual",
            "stt_mode_allow_os_dictation": True,
            "stt_mode_allow_desktop_mic_optional": True,
            "stt_mode_require_whisper": False,
            "stt_mode_use_whisper_for_dictation": False,
            "stt_mode_use_llm": False,
            "stt_mode_vad_models": ["silero", "ten_vad"],
            "stt_mode_vad_ensemble_enabled": True,
            "stt_mode_lora_resegment_enabled": True,
            "stt_mode_rolling_window_size": 2,
            "stt_mode_project_compat_enabled": True,
            "selected_model": "사용 안함 (STT 모드)",
            "selected_llm_provider": "none",
            "roughcut_llm_enabled": False,
            "roughcut_llm_use_override": False,
            "roughcut_llm_provider": "none",
            "roughcut_llm_model": "사용 안함",
        },
    },
}

_ALWAYS_AUTOMATED_SETTINGS = {
    "settings_simplified_ui_enabled": True,
    "subtitle_bundle_autopilot_enabled": True,
    "subtitle_bundle_lora_enabled": True,
    "subtitle_bundle_use_confirmed_cuts": True,
    "subtitle_bundle_use_provisional_cuts": True,
    "subtitle_target_line_count_auto_enabled": True,
    "roughcut_llm_rows_auto_enabled": True,
    "roughcut_llm_rows_lora_enabled": True,
    "roughcut_llm_threads_auto_enabled": True,
    "llm_threads_auto_enabled": True,
    "llm_workers_auto_enabled": True,
    "runtime_scheduler_auto_enabled": True,
    "stt_workers_auto_enabled": True,
    "cut_pioneer_workers_auto_enabled": True,
    "cut_follower_workers_auto_enabled": True,
    "lora_workers_auto_enabled": True,
    "background_prefetch_enabled": True,
    "editor_lora_runtime_enabled": True,
    "deep_runtime_adaptation_enabled": True,
    "deep_segment_setting_policy_enabled": True,
    "deep_subtitle_policy_enabled": True,
    "deep_stt_candidate_selector_enabled": True,
    "deep_timing_adjustment_enabled": True,
    "subtitle_timing_fusion_enabled": True,
    "subtitle_cut_boundary_guard_enabled": True,
    "subtitle_common_split_guard_enabled": True,
    "llm_confidence_gate_enabled": True,
    "llm_minimize_enabled": True,
    "llm_candidate_policy_enabled": True,
    "linebreak_lora_policy_enabled": True,
    "llm_verifier_enabled": True,
    "uncertainty_first_enabled": True,
}


def normalize_simple_operation_mode(value: Any) -> str:
    return normalize_mode(value)


def simple_operation_mode_items(*, include_advanced: bool = False) -> list[tuple[str, str, str]]:
    order = SIMPLE_OPERATION_MODE_ORDER if include_advanced else USER_VISIBLE_OPERATION_MODE_ORDER
    return [
        (mode, str(SIMPLE_OPERATION_MODES[mode]["label"]), str(SIMPLE_OPERATION_MODES[mode]["summary"]))
        for mode in order
    ]


def simple_operation_mode_summary(mode: Any) -> str:
    normalized = normalize_simple_operation_mode(mode)
    return str(SIMPLE_OPERATION_MODES[normalized]["summary"])


def apply_simple_operation_mode(settings: dict[str, Any] | None, mode: Any = None) -> dict[str, Any]:
    out = dict(settings or {})
    user_routes = {
        key: out[key]
        for key in USER_SELECTED_ROUTE_KEYS
        if key in out and out.get(key) not in (None, "")
    }
    selected_mode = normalize_simple_operation_mode(mode if mode is not None else out.get("simple_operation_mode", "auto"))
    out["simple_operation_mode"] = selected_mode
    out["subtitle_mode"] = selected_mode
    out.update(_ALWAYS_AUTOMATED_SETTINGS)
    out.update(dict(SIMPLE_OPERATION_MODES[selected_mode]["settings"]))
    if selected_mode != "stt":
        out.update(user_routes)
    quality_preset = mode_to_stt_quality(selected_mode)
    out["stt_quality_preset"] = quality_preset
    out["auto_start_mode"] = quality_preset
    target = int(float(out.get("subtitle_bundle_target_sec", 180) or 180))
    out["chunk_time_limit"] = target
    out["roughcut_llm_prompt"] = ""
    out["editor_roughcut_draft_prompt"] = ""
    out["user_prompt"] = ""
    out["llm_prompt"] = ""
    out["simple_operation_mode_policy"] = {
        "schema": SIMPLE_OPERATION_MODE_SCHEMA,
        "mode": selected_mode,
        "label": mode_label(selected_mode),
        "summary": SIMPLE_OPERATION_MODES[selected_mode]["summary"],
        "user_visible_modes": list(USER_VISIBLE_OPERATION_MODE_ORDER),
        "automated_settings": sorted(set(_ALWAYS_AUTOMATED_SETTINGS) | set(AUTOPILOT_AUTO_MANAGED_KEYS)),
    }
    out = apply_autopilot_runtime_policy(out)
    return apply_mode_runtime_settings(out)


__all__ = [
    "SIMPLE_OPERATION_MODE_ORDER",
    "USER_VISIBLE_OPERATION_MODE_ORDER",
    "SIMPLE_OPERATION_MODE_SCHEMA",
    "SIMPLE_OPERATION_MODES",
    "apply_simple_operation_mode",
    "normalize_simple_operation_mode",
    "simple_operation_mode_items",
    "simple_operation_mode_summary",
]
