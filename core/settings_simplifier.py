from __future__ import annotations

from typing import Any


SIMPLE_OPERATION_MODE_SCHEMA = "ai_subtitle_studio.simple_operation_mode.v1"
SIMPLE_OPERATION_MODE_ORDER = ("auto", "fast", "balanced", "precise")

SIMPLE_OPERATION_MODES: dict[str, dict[str, Any]] = {
    "auto": {
        "label": "자동",
        "summary": "영상 진단, LoRA, 딥러닝 정책이 작업량과 정확도 균형을 자동으로 고릅니다.",
        "settings": {
            "accuracy_first_mode": True,
            "auto_start_mode": "precise",
            "stt_quality_preset": "precise",
            "subtitle_bundle_target_sec": 180,
            "subtitle_bundle_min_sec": 90,
            "subtitle_bundle_max_sec": 300,
            "scan_cut_level": "medium",
            "cut_boundary_level": "medium",
            "scan_cut_boundary_level": "medium",
        },
    },
    "fast": {
        "label": "빠름",
        "summary": "확실한 구간은 빠르게 확정하고 애매한 구간만 정밀 패스로 보냅니다.",
        "settings": {
            "accuracy_first_mode": True,
            "auto_start_mode": "fast",
            "stt_quality_preset": "fast",
            "subtitle_bundle_target_sec": 240,
            "subtitle_bundle_min_sec": 120,
            "subtitle_bundle_max_sec": 420,
            "scan_cut_level": "low",
            "cut_boundary_level": "low",
            "scan_cut_boundary_level": "low",
        },
    },
    "balanced": {
        "label": "균형",
        "summary": "대부분의 영상에 맞는 기본값입니다. 속도와 정확도를 같이 봅니다.",
        "settings": {
            "accuracy_first_mode": True,
            "auto_start_mode": "balanced",
            "stt_quality_preset": "balanced",
            "subtitle_bundle_target_sec": 180,
            "subtitle_bundle_min_sec": 90,
            "subtitle_bundle_max_sec": 300,
            "scan_cut_level": "medium",
            "cut_boundary_level": "medium",
            "scan_cut_boundary_level": "medium",
        },
    },
    "precise": {
        "label": "정밀",
        "summary": "LoRA/딥러닝 검증과 후보 경쟁을 최대한 활용해 정확도를 우선합니다.",
        "settings": {
            "accuracy_first_mode": True,
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
    "llm_confidence_gate_enabled": True,
    "llm_minimize_enabled": True,
    "llm_candidate_policy_enabled": True,
    "linebreak_lora_policy_enabled": True,
    "llm_verifier_enabled": True,
    "uncertainty_first_enabled": True,
}


def normalize_simple_operation_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower()
    if mode in {"자동", "auto", "autopilot", "default"}:
        return "auto"
    if mode in {"빠름", "fast", "speed"}:
        return "fast"
    if mode in {"균형", "balance", "balanced"}:
        return "balanced"
    if mode in {"정밀", "precise", "accuracy", "high"}:
        return "precise"
    return "auto"


def simple_operation_mode_items() -> list[tuple[str, str, str]]:
    return [
        (mode, str(SIMPLE_OPERATION_MODES[mode]["label"]), str(SIMPLE_OPERATION_MODES[mode]["summary"]))
        for mode in SIMPLE_OPERATION_MODE_ORDER
    ]


def simple_operation_mode_summary(mode: Any) -> str:
    normalized = normalize_simple_operation_mode(mode)
    return str(SIMPLE_OPERATION_MODES[normalized]["summary"])


def apply_simple_operation_mode(settings: dict[str, Any] | None, mode: Any = None) -> dict[str, Any]:
    out = dict(settings or {})
    selected_mode = normalize_simple_operation_mode(mode if mode is not None else out.get("simple_operation_mode", "auto"))
    out["simple_operation_mode"] = selected_mode
    out.update(_ALWAYS_AUTOMATED_SETTINGS)
    out.update(dict(SIMPLE_OPERATION_MODES[selected_mode]["settings"]))
    target = int(float(out.get("subtitle_bundle_target_sec", 180) or 180))
    out["chunk_time_limit"] = target
    out["roughcut_llm_prompt"] = ""
    out["editor_roughcut_draft_prompt"] = ""
    out["user_prompt"] = ""
    out["llm_prompt"] = ""
    out["simple_operation_mode_policy"] = {
        "schema": SIMPLE_OPERATION_MODE_SCHEMA,
        "mode": selected_mode,
        "label": SIMPLE_OPERATION_MODES[selected_mode]["label"],
        "summary": SIMPLE_OPERATION_MODES[selected_mode]["summary"],
        "automated_settings": sorted(_ALWAYS_AUTOMATED_SETTINGS),
    }
    return out


__all__ = [
    "SIMPLE_OPERATION_MODE_ORDER",
    "SIMPLE_OPERATION_MODE_SCHEMA",
    "SIMPLE_OPERATION_MODES",
    "apply_simple_operation_mode",
    "normalize_simple_operation_mode",
    "simple_operation_mode_items",
    "simple_operation_mode_summary",
]
