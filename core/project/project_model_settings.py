# Version: 03.14.00
# Phase: PHASE2
"""Project persistence helpers for captured AI model settings."""

from datetime import datetime
from typing import Any, Optional

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
    "stt_ensemble_llm_judge_require_risk",
    "stt_ensemble_llm_judge_local_only",
    "stt_ensemble_llm_judge_low_score_threshold",
    "stt_ensemble_llm_judge_min_score_delta",
    "stt_ensemble_llm_judge_max_similarity",
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
    "roughcut_llm_rows_auto_enabled",
    "roughcut_llm_rows_lora_enabled",
    "roughcut_llm_rows_lora_blend",
    "roughcut_llm_rows_exploration_rate",
    "roughcut_llm_context_min_rows",
    "roughcut_llm_context_max_rows",
    "roughcut_llm_chunk_min_rows",
    "roughcut_llm_chunk_max_rows",
    "roughcut_llm_lookahead_min_rows",
    "roughcut_llm_lookahead_max_rows",
    "roughcut_llm_threads_auto_enabled",
    "roughcut_llm_threads",
    "roughcut_llm_threads_resource_max",
)
_MODEL_SETTING_ALLOWED_KEYS = frozenset((*MODEL_SETTING_KEYS, "preprocess_engine"))


def _selected_model_settings(source: dict[str, Any] | None) -> dict[str, Any]:
    data = source if isinstance(source, dict) else {}
    if _looks_like_selected_model_settings(data):
        selected = dict(data)
    else:
        selected = {key: data[key] for key in MODEL_SETTING_KEYS if key in data}
    selected.setdefault("preprocess_engine", "FFMPEG")
    return selected


def _looks_like_selected_model_settings(source: dict[str, Any] | None) -> bool:
    return isinstance(source, dict) and set(source).issubset(_MODEL_SETTING_ALLOWED_KEYS)


def _project_settings_source(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict):
        return None
    settings = _stored_model_settings(project)
    if settings is not None:
        return settings
    legacy = project.get("user_settings")
    return legacy if isinstance(legacy, dict) else None


def _stored_model_settings(project: dict[str, Any] | None) -> dict[str, Any] | None:
    snapshot = _stored_model_settings_snapshot(project)
    if snapshot is None:
        return None
    settings = snapshot.get("settings")
    return settings if isinstance(settings, dict) else None


def _stored_model_settings_snapshot(project: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(project, dict):
        return None
    stored = project.get("model_settings")
    return stored if isinstance(stored, dict) else None


def _model_summary(selected: dict[str, Any]) -> dict[str, Any]:
    stt2_enabled = bool(selected.get("stt_ensemble_enabled", False))
    roughcut_inherits = (
        bool(selected.get("roughcut_llm_enabled", False))
        and not bool(selected.get("roughcut_llm_use_override", False))
    )
    subtitle_model = selected.get("selected_model", "")
    return {
        "preprocess": "FFMPEG",
        "audio": selected.get("selected_audio_ai", ""),
        "vad": selected.get("selected_vad", ""),
        "stt1": selected.get("selected_whisper_model", ""),
        "stt2_enabled": stt2_enabled,
        "stt2": selected.get("selected_whisper_model_secondary", "") if stt2_enabled else "",
        "subtitle_llm_provider": selected.get("selected_llm_provider", "ollama"),
        "subtitle_llm": subtitle_model,
        "roughcut_llm_provider": "inherit" if roughcut_inherits else selected.get("roughcut_llm_provider", ""),
        "roughcut_llm": subtitle_model if roughcut_inherits else selected.get("roughcut_llm_model", ""),
    }


def _model_settings_bundle(source: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = _selected_model_settings(source)
    return selected, _model_summary(selected)


def _model_settings_snapshot_payload(selected: dict[str, Any], models: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": MODEL_SETTINGS_SCHEMA_VERSION,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "settings": selected,
        "models": models,
    }


def build_model_settings_summary(settings: Optional[dict]) -> dict:
    return _model_summary(_selected_model_settings(settings))


def build_model_settings_snapshot(settings: Optional[dict]) -> dict:
    selected = _selected_model_settings(settings)
    return _model_settings_snapshot_payload(selected, _model_summary(selected))


def _project_model_settings_views(
    project: dict[str, Any] | None,
    *,
    include_models: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    stored = _stored_model_settings_snapshot(project)
    if stored is not None:
        raw_settings = stored.get("settings")
        if isinstance(raw_settings, dict):
            selected = raw_settings if _looks_like_selected_model_settings(raw_settings) else _selected_model_settings(raw_settings)
        else:
            selected = {}
        models: dict[str, Any] = {}
        if include_models:
            raw_models = stored.get("models")
            models = raw_models if isinstance(raw_models, dict) and raw_models else (_model_summary(selected) if selected else {})
        return stored, selected, models

    source = _project_settings_source(project)
    if not isinstance(source, dict):
        return None, {}, {}
    selected = _selected_model_settings(source)
    if not include_models:
        return None, selected, {}
    return None, selected, _model_summary(selected)


def project_model_settings_snapshot(
    project: dict[str, Any] | None,
    *,
    build_if_missing: bool = False,
) -> dict[str, Any]:
    stored, selected, models = _project_model_settings_views(project)
    if stored is not None:
        return stored
    if not build_if_missing or not selected:
        return {}
    return _model_settings_snapshot_payload(selected, models)


def _project_model_settings_summary_view(
    project: dict[str, Any] | None,
    *,
    build_if_missing: bool = False,
) -> dict[str, Any]:
    stored, _selected, models = _project_model_settings_views(project)
    if stored is not None:
        return models
    if not build_if_missing:
        return {}
    return models


def _project_selected_model_settings_view(project: dict[str, Any] | None) -> dict[str, Any]:
    _stored, selected, _models = _project_model_settings_views(project, include_models=False)
    return selected


def _merge_selected_model_settings(
    base_settings: Optional[dict],
    selected: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(base_settings or {})
    if selected:
        merged.update(selected)
    return merged


def project_model_settings_summary(
    project: dict[str, Any] | None,
    *,
    build_if_missing: bool = False,
) -> dict[str, Any]:
    return dict(
        _project_model_settings_summary_view(
            project,
            build_if_missing=build_if_missing,
        )
    )


def restore_project_model_settings(
    base_settings: Optional[dict],
    project: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _stored, selected, _models = _project_model_settings_views(project, include_models=False)
    extracted = dict(selected)
    return extracted, _merge_selected_model_settings(base_settings, extracted)


def store_project_model_settings_snapshot(
    project: dict[str, Any] | None,
    settings: Optional[dict] = None,
    *,
    user_settings_provided: bool = True,
) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    if user_settings_provided:
        effective_settings = settings if isinstance(settings, dict) else {}
        project["user_settings"] = effective_settings
        snapshot = build_model_settings_snapshot(effective_settings)
        project["model_settings"] = snapshot
        return snapshot
    if "model_settings" not in project and isinstance(project.get("user_settings"), dict):
        snapshot = project_model_settings_snapshot(project, build_if_missing=True)
        project["model_settings"] = snapshot
        return snapshot
    return project_model_settings_snapshot(project)


def extract_model_settings(project: dict | None) -> dict:
    return dict(_project_selected_model_settings_view(project))


def merge_project_model_settings(base_settings: Optional[dict], project: dict | None) -> dict:
    return _merge_selected_model_settings(
        base_settings,
        _project_selected_model_settings_view(project),
    )
