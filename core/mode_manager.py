"""Central user-facing Mode ownership.

Fast/Auto/High/STT are the only user-facing processing modes.  The mode owns
all algorithm choices such as audio filtering, VAD, STT2 ensemble, LoRA, Deep,
cut-boundary, and LLM runtime gates.  Users may persist only model identities
for STT1, STT2, subtitle LLM, and roughcut LLM as per-mode defaults.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MODE_MANAGER_SCHEMA = "ai_subtitle_studio.mode_manager.v1"

MODE_ORDER = ("fast", "auto", "high", "stt")
MODE_LABELS = {
    "fast": "Fast",
    "auto": "Auto",
    "high": "High",
    "stt": "STT 모드",
}
MODE_TO_STT_QUALITY = {
    "fast": "fast",
    "auto": "balanced",
    "high": "precise",
    "stt": "stt",
}
STT_QUALITY_TO_MODE = {
    "fast": "fast",
    "balanced": "auto",
    "precise": "high",
    "stt": "stt",
}

MODE_SCOPE_QUALITY_KEYS = (
    "stt_quality_preset",
    "auto_start_mode",
    "icloud_stt_quality_preset",
    "nas_stt_quality_preset",
    "multiclip_stt_quality_preset",
)

USER_SELECTABLE_MODEL_KEYS = (
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "selected_model",
    "selected_llm_provider",
    "subtitle_llm_user_selected",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
)

MODE_MANAGED_ROUTE_KEYS = (
    "selected_audio_ai",
    "audio_preset",
    "selected_vad",
    "vad_threshold",
    "ten_vad_threshold",
    "stt_ensemble_enabled",
    "stt_ensemble_llm_judge_enabled",
    "stt_ensemble_user_selected",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
)


def normalize_mode(value: Any, *, default: str = "auto") -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "fast": "fast",
        "speed": "fast",
        "quick": "fast",
        "빠름": "fast",
        "빠른": "fast",
        "빠른 인식": "fast",
        "빠른인식": "fast",
        "auto": "auto",
        "automatic": "auto",
        "autopilot": "auto",
        "default": "auto",
        "normal": "auto",
        "balanced": "auto",
        "balance": "auto",
        "보통": "auto",
        "균형": "auto",
        "자동": "auto",
        "high": "high",
        "precise": "high",
        "quality": "high",
        "accuracy": "high",
        "정밀": "high",
        "정확도 우선": "high",
        "정밀 인식": "high",
        "정밀인식": "high",
        "높음": "high",
        "stt": "stt",
        "stt mode": "stt",
        "stt 모드": "stt",
        "수동 stt": "stt",
        "수동": "stt",
        "받아쓰기": "stt",
    }
    if not text:
        return normalize_mode(default, default="auto") if default != "" else "auto"
    return aliases.get(text, normalize_mode(default, default="auto") if text not in MODE_ORDER else text)


def mode_to_stt_quality(mode: Any) -> str:
    return MODE_TO_STT_QUALITY[normalize_mode(mode)]


def stt_quality_to_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in STT_QUALITY_TO_MODE:
        return STT_QUALITY_TO_MODE[text]
    return normalize_mode(text)


def mode_label(mode: Any) -> str:
    return MODE_LABELS[normalize_mode(mode)]


def mode_items() -> list[tuple[str, str]]:
    return [(key, MODE_LABELS[key]) for key in MODE_ORDER]


def selected_mode_from_settings(settings: dict[str, Any] | None) -> str:
    data = dict(settings or {})
    for key in ("subtitle_mode", "mode", "user_facing_mode"):
        value = data.get(key)
        if str(value or "").strip():
            return normalize_mode(value)
    legacy_mode = str(data.get("simple_operation_mode") or "").strip()
    quality_value = data.get("stt_quality_preset") or data.get("auto_start_mode")
    quality_mode = stt_quality_to_mode(quality_value) if str(quality_value or "").strip() else ""
    if legacy_mode:
        normalized = normalize_mode(legacy_mode)
        if normalized == "auto" and quality_mode in {"fast", "high"}:
            return quality_mode
        return normalized
    return stt_quality_to_mode(data.get("stt_quality_preset") or data.get("auto_start_mode") or "balanced")


def mode_model_snapshot(settings: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(settings or {})
    snapshot = {
        key: deepcopy(data[key])
        for key in USER_SELECTABLE_MODEL_KEYS
        if key in data and data.get(key) not in (None, "")
    }
    model = str(snapshot.get("selected_model") or "").strip()
    provider = str(snapshot.get("selected_llm_provider") or "").strip().lower()
    if "selected_model" in snapshot:
        snapshot["subtitle_llm_user_selected"] = bool(model and "사용 안함" not in model and provider != "none")
    return snapshot


def apply_mode_scope_quality(settings: dict[str, Any] | None, mode: Any) -> dict[str, Any]:
    out = dict(settings or {})
    selected = normalize_mode(mode)
    quality = mode_to_stt_quality(selected)
    out["simple_operation_mode"] = selected
    out["subtitle_mode"] = selected
    for key in MODE_SCOPE_QUALITY_KEYS:
        out[key] = quality
    out["mode_manager_policy"] = {
        "schema": MODE_MANAGER_SCHEMA,
        "mode": selected,
        "label": mode_label(selected),
        "quality_preset": quality,
        "synced_scopes": list(MODE_SCOPE_QUALITY_KEYS),
        "user_selectable_model_keys": list(USER_SELECTABLE_MODEL_KEYS),
        "mode_managed_route_keys": list(MODE_MANAGED_ROUTE_KEYS),
    }
    return out


def strip_mode_managed_user_routes(settings: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(settings or {})
    for key in MODE_MANAGED_ROUTE_KEYS:
        if key not in USER_SELECTABLE_MODEL_KEYS:
            out.pop(key, None)
    return out


__all__ = [
    "MODE_LABELS",
    "MODE_MANAGER_SCHEMA",
    "MODE_MANAGED_ROUTE_KEYS",
    "MODE_ORDER",
    "MODE_SCOPE_QUALITY_KEYS",
    "MODE_TO_STT_QUALITY",
    "STT_QUALITY_TO_MODE",
    "USER_SELECTABLE_MODEL_KEYS",
    "apply_mode_scope_quality",
    "mode_items",
    "mode_label",
    "mode_model_snapshot",
    "mode_to_stt_quality",
    "normalize_mode",
    "selected_mode_from_settings",
    "stt_quality_to_mode",
    "strip_mode_managed_user_routes",
]
