from __future__ import annotations

from typing import Any

from core.audio.stt_quality_presets import normalize_stt_quality_key


LORA_POLICY_OFF = "off"
LORA_POLICY_STT1_MINIMAL = "stt1_minimal"
LORA_POLICY_FULL = "full"

STT1_MINIMAL_LORA_SETTING_KEYS = frozenset(
    {
        "selected_audio_ai",
        "selected_whisper_model",
        "continuous_threshold",
        "gap_push_rate",
        "single_subtitle_end",
        "split_length_threshold",
        "sub_min_duration",
        "sub_max_duration",
        "sub_max_cps",
        "sub_dedup_window",
        "sub_gap_break_sec",
    }
)


def lora_quality_key_from_settings(settings_or_key: dict[str, Any] | str | None, *, default: str = "precise") -> str:
    if isinstance(settings_or_key, dict):
        raw = settings_or_key.get("stt_quality_preset") or settings_or_key.get("auto_start_mode") or default
    else:
        raw = settings_or_key or default
    return normalize_stt_quality_key(str(raw or default))


def lora_policy_mode_for_quality(quality_key: str | None) -> str:
    key = normalize_stt_quality_key(quality_key or "precise")
    if key == "fast":
        return LORA_POLICY_OFF
    if key == "balanced":
        return LORA_POLICY_STT1_MINIMAL
    return LORA_POLICY_FULL


def lora_runtime_setting_keys_for_quality(quality_key: str | None, all_keys: set[str] | frozenset[str]) -> frozenset[str]:
    mode = lora_policy_mode_for_quality(quality_key)
    if mode == LORA_POLICY_OFF:
        return frozenset()
    if mode == LORA_POLICY_STT1_MINIMAL:
        return frozenset(key for key in STT1_MINIMAL_LORA_SETTING_KEYS if key in all_keys)
    return frozenset(all_keys)


def lora_policy_label_for_quality(quality_key: str | None) -> str:
    mode = lora_policy_mode_for_quality(quality_key)
    if mode == LORA_POLICY_OFF:
        return "LoRA 제외"
    if mode == LORA_POLICY_STT1_MINIMAL:
        return "STT1 핵심 LoRA"
    return "전체 LoRA"


def lora_uses_stt1_only(quality_key: str | None) -> bool:
    return normalize_stt_quality_key(quality_key or "precise") in {"fast", "balanced"}


def lora_uses_full_stt_ensemble(quality_key: str | None) -> bool:
    return normalize_stt_quality_key(quality_key or "precise") == "precise"


__all__ = [
    "LORA_POLICY_FULL",
    "LORA_POLICY_OFF",
    "LORA_POLICY_STT1_MINIMAL",
    "STT1_MINIMAL_LORA_SETTING_KEYS",
    "lora_policy_label_for_quality",
    "lora_policy_mode_for_quality",
    "lora_quality_key_from_settings",
    "lora_runtime_setting_keys_for_quality",
    "lora_uses_full_stt_ensemble",
    "lora_uses_stt1_only",
]
