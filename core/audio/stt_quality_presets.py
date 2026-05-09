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
STT_ENSEMBLE_USER_SELECTED_KEY = "stt_ensemble_user_selected"
USER_SELECTED_STT_MODEL_KEYS = (
    "selected_whisper_model",
    "selected_whisper_model_secondary",
)
USER_SELECTED_ROUTE_KEYS = (
    "selected_audio_ai",
    "audio_preset",
    "selected_vad",
    "selected_whisper_model",
    "selected_whisper_model_secondary",
    "selected_model",
    "selected_llm_provider",
    "subtitle_llm_user_selected",
    "roughcut_llm_enabled",
    "roughcut_llm_use_override",
    "roughcut_llm_provider",
    "roughcut_llm_model",
    "selected_roughcut_llm_provider",
    "selected_roughcut_llm_model",
)
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
    "stt_ensemble_user_selected",
    "stt_ensemble_enabled",
    "stt_ensemble_llm_judge_enabled",
    "stt_ensemble_selective_enabled",
    "stt_ensemble_parallel_enabled",
    "stt_selective_secondary_recheck_enabled",
    "stt_candidate_scoring_enabled",
    "stt_low_score_recheck_enabled",
    "stt_low_score_recheck_threshold",
    "stt_low_score_recheck_padding_sec",
    "stt_low_score_recheck_max_segments",
    "stt_low_score_recheck_max_audio_sec",
    "stt_word_timestamps_mode",
    "stt_word_timestamps_default_enabled",
    "stt_word_timestamps_precision_enabled",
    "stt_word_timestamps_precision_threshold",
    "stt_word_timestamps_precision_max_segments",
    "stt_word_timestamps_precision_max_audio_sec",
    "stt_word_timestamps_precision_keep_text",
    "stt_word_timestamps_precision_min_similarity",
    "stt_word_timestamps_precision_max_timing_shift_sec",
    "stt_word_timestamps_precision_min_duration_ratio",
    "stt_word_timestamps_precision_max_duration_ratio",
    "vad_post_stt_align_enabled",
    "vad_post_stt_edge_pad_sec",
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
    # BENCH LOCK 2026-05-09 (X5_시승기_후반.MP4 1-minute SRT reference):
    # ghost613 4-bit MLX was fastest but produced repetition/large omissions
    # (WER 0.8496, compact CER 0.7401). Keep MLX large-v3 turbo as STT2.
    return getattr(config, "MLX_FALLBACK_MODEL", "mlx-community/whisper-large-v3-turbo")


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


def _stt_single_pass_mapping(
    *,
    word_mode: str,
    word_precision: bool,
    word_max_segments: int,
    word_max_audio_sec: float,
    word_threshold: float = 72.0,
) -> dict:
    return {
        "stt_ensemble_enabled": False,
        "stt_ensemble_llm_judge_enabled": False,
        "stt_ensemble_selective_enabled": False,
        "stt_ensemble_parallel_enabled": False,
        "stt_selective_secondary_recheck_enabled": False,
        "stt_low_score_recheck_enabled": False,
        "stt_word_timestamps_mode": word_mode,
        "stt_word_timestamps_default_enabled": False,
        "stt_word_timestamps_precision_enabled": bool(word_precision),
        "stt_word_timestamps_precision_threshold": float(word_threshold),
        "stt_word_timestamps_precision_max_segments": int(word_max_segments),
        "stt_word_timestamps_precision_max_audio_sec": float(word_max_audio_sec),
        "stt_word_timestamps_precision_keep_text": True,
        "stt_word_timestamps_precision_min_similarity": 0.18,
        "stt_word_timestamps_precision_max_timing_shift_sec": 0.55,
        "stt_word_timestamps_precision_min_duration_ratio": 0.45,
        "stt_word_timestamps_precision_max_duration_ratio": 1.8,
        "vad_post_stt_align_enabled": True,
        "vad_post_stt_edge_pad_sec": 0.04,
    }


def _high_llm_gate_mapping() -> dict:
    return {
        "subtitle_llm_macro_chunk_enabled": True,
        "subtitle_llm_macro_chunk_min_rows": 10,
        "subtitle_llm_macro_chunk_max_rows": 15,
        "subtitle_llm_macro_chunk_use_cut_boundaries": True,
        "llm_confidence_gate_enabled": True,
        "llm_confidence_gate_min_lora_score": 88.0,
        "llm_confidence_gate_max_compact_ratio": 1.37,
        "llm_confidence_gate_strong_signal_score": 92.0,
        "llm_confidence_gate_strong_max_compact_ratio": 1.28,
        "llm_confidence_gate_strong_max_duration_ratio": 1.35,
        "llm_candidate_policy_enabled": True,
        "llm_minimize_enabled": True,
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
            "description": "벤치 검증 Fast: STT1 단일 + LoRA, word timestamp/LLM/STT2 생략",
            "settings": {
                "selected_whisper_model": quality_model,
                "selected_whisper_model_secondary": secondary_model,
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "stt_candidate_scoring_enabled": True,
                **_pipeline_mapping(30, 0.5, 4),
                **_cut_boundary_mapping("off"),
                **_stt_single_pass_mapping(
                    word_mode="off",
                    word_precision=False,
                    word_max_segments=0,
                    word_max_audio_sec=0.0,
                ),
                **_decoder_settings(0.86, -1.0, 1.6, 0.0, 3, 1.0),
            },
        },
        "balanced": {
            "label": STT_QUALITY_PRESET_LABELS["balanced"],
            "description": "일반 자막 생성용 기본 조합",
            "settings": {
                "selected_whisper_model": quality_model,
                "selected_model": "exaone3.5:2.4b",
                "stt_candidate_scoring_enabled": True,
                **_pipeline_mapping(25, 1.5, 3),
                **_cut_boundary_mapping("low"),
                **_stt_single_pass_mapping(
                    word_mode="selective",
                    word_precision=True,
                    word_max_segments=16,
                    word_max_audio_sec=70.0,
                ),
                **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            },
        },
        "precise": {
            "label": STT_QUALITY_PRESET_LABELS["precise"],
            "description": "벤치 검증 High: STT1 + 낮은 점수 word timestamp + LoRA/Deep + red/yellow LLM",
            "settings": {
                "selected_whisper_model": quality_model,
                "selected_model": "exaone3.5:2.4b",
                "stt_candidate_scoring_enabled": True,
                "selected_whisper_model_secondary": secondary_model,
                **_pipeline_mapping(35, 3.0, 2),
                **_cut_boundary_mapping("medium"),
                **_roughcut_llm_mapping("exaone3.5:7.8b"),
                **_stt_single_pass_mapping(
                    word_mode="selective",
                    word_precision=True,
                    word_max_segments=32,
                    word_max_audio_sec=100.0,
                ),
                **_high_llm_gate_mapping(),
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


def _user_selected_route_snapshot(settings: dict | None) -> dict:
    data = dict(settings or {})
    snapshot = {
        key: deepcopy(data[key])
        for key in USER_SELECTED_ROUTE_KEYS
        if key in data and data.get(key) not in (None, "")
    }
    user_selected_stt2 = bool(data.get(STT_ENSEMBLE_USER_SELECTED_KEY))
    legacy_enabled_stt2 = bool(data.get("stt_ensemble_enabled")) and bool(
        str(data.get("selected_whisper_model_secondary") or "").strip()
    )
    if user_selected_stt2 or legacy_enabled_stt2:
        snapshot[STT_ENSEMBLE_USER_SELECTED_KEY] = bool(user_selected_stt2 or legacy_enabled_stt2)
        if "stt_ensemble_enabled" in data:
            snapshot["stt_ensemble_enabled"] = bool(data.get("stt_ensemble_enabled"))
    return snapshot


def apply_stt_quality_preset(
    settings: dict,
    preset_key: str,
    *,
    use_saved_user_preset: bool = True,
    preserve_user_routes: bool = False,
) -> dict:
    presets = load_stt_quality_presets()
    key = normalize_stt_quality_key(preset_key)
    preset = presets[key]
    user_route_snapshot = _user_selected_route_snapshot(settings) if preserve_user_routes else {}
    incoming_user_stt_models = {
        model_key: deepcopy(settings[model_key])
        for model_key in USER_SELECTED_STT_MODEL_KEYS
        if str(settings.get(model_key, "") or "").strip()
    }
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
    user_preset_applied = False
    if use_saved_user_preset and isinstance(user_preset, dict):
        user_settings = user_preset.get("settings", {})
        if isinstance(user_settings, dict):
            out.update(deepcopy(user_settings))
            user_preset_applied = True
    if user_route_snapshot:
        out.update(user_route_snapshot)
    if incoming_user_stt_models and not user_preset_applied:
        # Mode presets control processing policy. STT1/STT2 model identity is
        # a direct user choice and should not be replaced by mode defaults.
        out.update(incoming_user_stt_models)
    if benchmark_routes:
        out.update(benchmark_routes)
    out["stt_quality_preset"] = key
    return out


def apply_recommended_stt_quality_defaults(settings: dict | None, preset_key: str) -> dict:
    """Apply benchmark-locked mode defaults while preserving user-selected routes."""
    return apply_stt_quality_preset(
        dict(settings or {}),
        preset_key,
        use_saved_user_preset=False,
        preserve_user_routes=True,
    )


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
