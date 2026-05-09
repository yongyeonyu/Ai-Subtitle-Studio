# Version: 03.14.19
# Phase: PHASE2
from __future__ import annotations

from copy import deepcopy

from core.runtime import config


STT_QUALITY_PRESET_ORDER = ("fast", "balanced", "precise", "stt")
STT_QUALITY_PRESET_LABELS = {
    "fast": "Fast",
    "balanced": "Auto",
    "precise": "High",
    "stt": "STT",
}
STT_QUALITY_USER_PRESET_KEY = "stt_quality_user_presets"
BENCHMARK_RUNTIME_ROUTE_KEYS = {
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "selected_model",
    "selected_llm_provider",
    "subtitle_llm_user_selected",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
}
STT_QUALITY_SAVED_SETTING_KEYS = {
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "stt_ensemble_enabled",
    "stt_ensemble_llm_judge_enabled",
    "stt_candidate_scoring_enabled",
    "selected_model",
    "selected_llm_provider",
    "subtitle_llm_user_selected",
    "scan_cut_boundary_level",
    "cut_boundary_level",
    "scan_cut_level",
    "cut_boundary_detection_enabled",
    "scan_cut_enabled",
    "scan_cut_auto_enabled",
    "cut_boundary_enabled",
    "scan_cut_boundary_label",
    "scan_cut_grid_mask",
    "ff_chunk",
    "whisper_chunk_overlap_sec",
    "stt_parallel_level",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
    "w_beam_size",
    "w_patience",
    "w_length_penalty",
    "w_dm_no_speech",
    "w_dm_logprob",
    "w_dm_comp",
    "w_dm_temp_max",
    "w_df_no_speech",
    "w_df_logprob",
    "w_df_comp",
    "w_df_temp_max",
    "w_none_no_speech",
    "w_none_logprob",
    "w_none_comp",
    "w_none_temp_max",
    "stt_mode_enabled",
    "stt_mode_text_input_provider",
    "stt_mode_vad_models",
    "stt_mode_vad_ensemble_enabled",
    "stt_mode_lora_resegment_enabled",
    "stt_mode_rolling_window_size",
    "stt_mode_allow_os_dictation",
    "stt_mode_allow_desktop_mic_optional",
    "stt_mode_require_whisper",
    "stt_mode_use_whisper_for_dictation",
    "stt_mode_use_llm",
    "stt_lora_bundle_auto_export_enabled",
    "stt_lora_bundle_size_tier",
    "stt_lora_style_learning_enabled",
    "stt_lora_protected_terms",
}


def _quality_model() -> str:
    return getattr(config, "WHISPERKIT_QUALITY_MODEL", "whisperkit-persistent:large-v3")


def _fast_model() -> str:
    return getattr(config, "WHISPERKIT_FAST_MODEL", "whisperkit-persistent:large-v3-turbo")


def _secondary_model() -> str:
    return (
        "youngouk/ghost613-turbo-korean-4bit-mlx"
    )


def _decoder_settings(
    no_speech: float,
    logprob: float,
    compression: float,
    temp_max: float,
    beam_size: int,
    patience: float,
) -> dict:
    out = {
        "w_beam_size": beam_size,
        "w_patience": patience,
        "w_length_penalty": 1.0,
    }
    for prefix in ("dm", "df", "none"):
        out[f"w_{prefix}_no_speech"] = no_speech
        out[f"w_{prefix}_logprob"] = logprob
        out[f"w_{prefix}_comp"] = compression
        out[f"w_{prefix}_temp_max"] = temp_max
    return out


def _pipeline_mapping(ff_chunk: int, overlap_sec: float, parallel_level: int) -> dict:
    return {
        "ff_chunk": ff_chunk,
        "whisper_chunk_overlap_sec": overlap_sec,
        "stt_parallel_level": parallel_level,
    }


def _roughcut_llm_mapping(model_name: str) -> dict:
    enabled = bool(model_name and "사용 안함" not in model_name)
    return {
        "roughcut_llm_enabled": enabled,
        "roughcut_llm_use_override": enabled,
        "roughcut_llm_provider": "ollama" if enabled else "none",
        "roughcut_llm_model": model_name if enabled else "사용 안함",
    }


def _cut_boundary_mapping(level: str) -> dict:
    level = str(level or "medium").strip().lower()
    if level == "high":
        level = "medium"
    enabled = level != "off"
    labels = {
        "off": "미사용",
        "low": "중간 - 3초 간격",
        "medium": "높음 - 2초 간격",
    }
    masks = {
        "off": "off",
        "low": "cross4",
        "medium": "cross5",
    }
    return {
        "scan_cut_boundary_level": level,
        "cut_boundary_level": level,
        "scan_cut_level": level,
        "cut_boundary_detection_enabled": enabled,
        "scan_cut_enabled": enabled,
        "scan_cut_auto_enabled": enabled,
        "cut_boundary_enabled": enabled,
        "scan_cut_boundary_label": labels.get(level, labels["medium"]),
        "scan_cut_grid_mask": masks.get(level, "cross5"),
    }


def load_stt_quality_presets() -> dict[str, dict]:
    quality_model = _quality_model()
    secondary_model = _secondary_model()
    return {
        "fast": {
            "label": STT_QUALITY_PRESET_LABELS["fast"],
            "description": "속도 우선, STT/LLM 경량 조합",
            "settings": {
                "selected_whisper_model": _fast_model(),
                "selected_whisper_model_secondary": secondary_model,
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": False,
                "stt_candidate_scoring_enabled": True,
                **_pipeline_mapping(30, 0.5, 4),
                **_cut_boundary_mapping("off"),
                **_decoder_settings(0.86, -1.0, 1.6, 0.0, 3, 1.0),
            },
        },
        "balanced": {
            "label": STT_QUALITY_PRESET_LABELS["balanced"],
            "description": "일반 자막 생성용 기본 조합",
            "settings": {
                "selected_whisper_model": _quality_model(),
                "selected_model": "exaone3.5:2.4b",
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": False,
                "stt_candidate_scoring_enabled": True,
                **_pipeline_mapping(25, 1.5, 3),
                **_cut_boundary_mapping("low"),
                **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            },
        },
        "precise": {
            "label": STT_QUALITY_PRESET_LABELS["precise"],
            "description": "정확도 우선, STT 앙상블/LLM 검수 강화",
            "settings": {
                "selected_whisper_model": quality_model,
                "selected_model": "gemma4:e4b",
                "stt_candidate_scoring_enabled": True,
                "selected_whisper_model_secondary": secondary_model,
                "stt_ensemble_enabled": True,
                "stt_ensemble_llm_judge_enabled": True,
                **_pipeline_mapping(35, 3.0, 2),
                **_cut_boundary_mapping("medium"),
                **_roughcut_llm_mapping("exaone3.5:7.8b"),
                **_decoder_settings(0.42, -2.6, 2.4, 0.6, 8, 1.35),
            },
        },
        "stt": {
            "label": STT_QUALITY_PRESET_LABELS["stt"],
            "description": "수동/받아쓰기 STT 전용, VAD + STT LoRA 재분할",
            "settings": {
                "selected_whisper_model": quality_model,
                "selected_whisper_model_secondary": secondary_model,
                "selected_model": "사용 안함 (STT 모드)",
                "selected_llm_provider": "none",
                "subtitle_llm_user_selected": False,
                "stt_ensemble_enabled": False,
                "stt_ensemble_llm_judge_enabled": False,
                "stt_candidate_scoring_enabled": True,
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
                "stt_lora_bundle_auto_export_enabled": True,
                "stt_lora_bundle_size_tier": "300MB",
                "stt_lora_style_learning_enabled": True,
                **_pipeline_mapping(20, 0.0, 1),
                **_cut_boundary_mapping("low"),
                **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            },
        },
    }


def normalize_stt_quality_key(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if key in load_stt_quality_presets():
        return key
    aliases = {
        "빠름": "fast",
        "빠른 인식": "fast",
        "빠른인식": "fast",
        "fast": "fast",
        "auto": "balanced",
        "자동": "balanced",
        "normal": "balanced",
        "보통": "balanced",
        "균형": "balanced",
        "balance": "balanced",
        "balanced": "balanced",
        "high": "precise",
        "높음": "precise",
        "정확도 우선": "precise",
        "quality": "precise",
        "정밀 인식": "precise",
        "정밀인식": "precise",
        "precise": "precise",
        "stt": "stt",
        "stt mode": "stt",
        "stt 모드": "stt",
        "받아쓰기": "stt",
        "수동": "stt",
    }
    return aliases.get(key, "balanced")


def apply_stt_quality_preset(settings: dict, preset_key: str) -> dict:
    presets = load_stt_quality_presets()
    key = normalize_stt_quality_key(preset_key)
    preset = presets[key]
    benchmark_profile = str(settings.get("benchmark_runtime_profile") or "").strip()
    benchmark_routes = {
        route_key: deepcopy(settings[route_key])
        for route_key in BENCHMARK_RUNTIME_ROUTE_KEYS
        if benchmark_profile and route_key in settings
    }
    out = dict(settings)
    out.update(deepcopy(preset.get("settings", {})))
    user_presets = dict(out.get(STT_QUALITY_USER_PRESET_KEY) or {})
    user_preset = user_presets.get(key)
    if isinstance(user_preset, dict):
        user_settings = user_preset.get("settings", {})
        if isinstance(user_settings, dict):
            out.update(deepcopy(user_settings))
    if benchmark_routes:
        out.update(benchmark_routes)
    out["stt_quality_preset"] = key
    return out


def stt_quality_label(value: str | None) -> str:
    key = normalize_stt_quality_key(value)
    return STT_QUALITY_PRESET_LABELS.get(key, STT_QUALITY_PRESET_LABELS["precise"])


def save_stt_quality_user_preset(settings: dict, preset_key: str) -> dict:
    key = normalize_stt_quality_key(preset_key)
    out = dict(settings or {})
    snapshot = {
        setting_key: deepcopy(out[setting_key])
        for setting_key in STT_QUALITY_SAVED_SETTING_KEYS
        if setting_key in out
    }
    user_presets = dict(out.get(STT_QUALITY_USER_PRESET_KEY) or {})
    user_presets[key] = {
        "label": stt_quality_label(key),
        "settings": snapshot,
    }
    out[STT_QUALITY_USER_PRESET_KEY] = user_presets
    out["stt_quality_preset"] = key
    return out
