# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Defaults and small helpers for UI-independent STT Mode logic."""
from __future__ import annotations

from typing import Any


DEFAULT_STT_MODE_SETTINGS: dict[str, Any] = {
    "stt_mode_min_work_segment_sec": 0.45,
    "stt_mode_target_work_segment_sec": 4.0,
    "stt_mode_max_work_segment_sec": 9.0,
    "stt_mode_merge_gap_sec": 0.35,
    "stt_mode_split_long_segments": True,
    "stt_mode_respect_cut_boundaries": True,
    "stt_mode_playback_preroll_sec": 0.25,
    "stt_mode_playback_postroll_sec": 0.35,
    "stt_mode_target_chars_per_line": 12,
    "stt_mode_max_lines": 2,
    "stt_mode_min_subtitle_duration_sec": 0.6,
    "stt_mode_max_subtitle_duration_sec": 5.5,
    "stt_mode_balance_by_text_length": True,
    "stt_mode_netflix_style_enabled": True,
    "stt_mode_text_input_provider": "manual",
    "stt_mode_empty_input_policy": "needs_review",
    "stt_mode_rolling_window_size": 2,
    "stt_learning_enabled": True,
    "stt_learning_save_audio_snippets": False,
    "stt_learning_save_text_pairs": True,
    "stt_learning_save_vad_features": True,
    "stt_learning_save_edit_events": True,
    "stt_lora_bundle_auto_export_enabled": True,
    "stt_lora_bundle_size_tier": "300MB",
    "stt_lora_style_learning_enabled": True,
    "stt_lora_protected_terms": [],
}


def stt_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(DEFAULT_STT_MODE_SETTINGS)
    if isinstance(settings, dict):
        merged.update(settings)
    return merged


def setting_float(settings: dict[str, Any] | None, key: str, default: float) -> float:
    try:
        return float(stt_settings(settings).get(key, default))
    except (TypeError, ValueError):
        return float(default)


def setting_int(settings: dict[str, Any] | None, key: str, default: int) -> int:
    try:
        return int(float(stt_settings(settings).get(key, default)))
    except (TypeError, ValueError):
        return int(default)


def setting_bool(settings: dict[str, Any] | None, key: str, default: bool) -> bool:
    value = stt_settings(settings).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(value)


__all__ = [
    "DEFAULT_STT_MODE_SETTINGS",
    "setting_bool",
    "setting_float",
    "setting_int",
    "stt_settings",
]
