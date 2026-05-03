# Version: 03.14.00
# Phase: PHASE2
"""Project persistence helpers for captured AI model settings."""

from datetime import datetime
from typing import Optional

MODEL_SETTINGS_SCHEMA_VERSION = "ai_model_settings.v1"
MODEL_SETTING_KEYS = (
    "cut_boundary_detection_enabled",
    "scan_cut_enabled",
    "selected_audio_ai",
    "selected_vad",
    "vad_pre_split_enabled",
    "vad_post_stt_align_enabled",
    "vad_post_stt_max_shift_sec",
    "vad_post_stt_edge_pad_sec",
    "selected_whisper_model",
    "stt_ensemble_enabled",
    "selected_whisper_model_secondary",
    "stt_ensemble_llm_judge_enabled",
    "selected_llm_provider",
    "selected_model",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
    "roughcut_llm_api_key_mode",
    "roughcut_llm_temperature",
    "roughcut_llm_max_context_rows",
    "roughcut_llm_chunk_rows",
    "roughcut_llm_lookahead_rows",
    "roughcut_llm_threads",
)


def build_model_settings_snapshot(settings: Optional[dict]) -> dict:
    source = dict(settings or {})
    selected = {key: source[key] for key in MODEL_SETTING_KEYS if key in source}
    selected.setdefault("preprocess_engine", "FFMPEG")
    stt2_enabled = bool(selected.get("stt_ensemble_enabled", False))
    roughcut_inherits = (
        bool(selected.get("roughcut_llm_enabled", False))
        and not bool(selected.get("roughcut_llm_use_override", False))
    )
    return {
        "schema": MODEL_SETTINGS_SCHEMA_VERSION,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "settings": selected,
        "models": {
            "preprocess": "FFMPEG",
            "audio": selected.get("selected_audio_ai", ""),
            "vad": selected.get("selected_vad", ""),
            "stt1": selected.get("selected_whisper_model", ""),
            "stt2_enabled": stt2_enabled,
            "stt2": selected.get("selected_whisper_model_secondary", "") if stt2_enabled else "",
            "subtitle_llm_provider": selected.get("selected_llm_provider", "ollama"),
            "subtitle_llm": selected.get("selected_model", ""),
            "roughcut_llm_provider": (
                "inherit" if roughcut_inherits else selected.get("roughcut_llm_provider", "")
            ),
            "roughcut_llm": (
                selected.get("selected_model", "")
                if roughcut_inherits
                else selected.get("roughcut_llm_model", "")
            ),
        },
    }


def extract_model_settings(project: dict | None) -> dict:
    if not isinstance(project, dict):
        return {}
    raw = project.get("model_settings")
    if isinstance(raw, dict):
        settings = raw.get("settings")
        if isinstance(settings, dict):
            return {key: settings[key] for key in MODEL_SETTING_KEYS if key in settings}
    legacy = project.get("user_settings")
    if isinstance(legacy, dict):
        return {key: legacy[key] for key in MODEL_SETTING_KEYS if key in legacy}
    return {}


def merge_project_model_settings(base_settings: Optional[dict], project: dict | None) -> dict:
    merged = dict(base_settings or {})
    merged.update(extract_model_settings(project))
    return merged
