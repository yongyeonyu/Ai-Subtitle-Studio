# Version: 03.14.19
# Phase: PHASE2
from __future__ import annotations

from copy import deepcopy

from core.runtime import config
from core.mode_manager import MODE_MANAGED_ROUTE_KEYS, USER_SELECTABLE_MODEL_KEYS


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
USER_SELECTED_ROUTE_KEYS = USER_SELECTABLE_MODEL_KEYS
BENCHMARK_RUNTIME_ROUTE_KEYS = set(USER_SELECTABLE_MODEL_KEYS)
STT_QUALITY_SAVED_SETTING_KEYS = set(USER_SELECTABLE_MODEL_KEYS)
VAD_MODE_AUTOMATION_NOTE = (
    "VAD는 Fast/Auto/High 모드별 벤치 고정값으로 자동 적용됩니다. "
    "티니핑 0~3분 전체 조합 탐색과 0~11분 최종 검증 결과를 기준으로 잠갔습니다."
)

TINIPING_BENCHMARK_REFERENCE = "Tiniping 0~3분 sweep + 0~11분 final"
TINIPING_FAST_PRIMARY_MODEL = "youngouk/whisper-medium-komixv2-mlx"
TINIPING_SUBTITLE_LLM_MODEL = "exaone3.5:7.8b"
AUTO_WINDOWED_STT_REFERENCE = "3분 windowed STT + overlap hysteresis"
HIGH_WINDOWED_STT_REFERENCE = "120초 windowed STT + 8초 overlap / 4초 hysteresis"


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


def _windowed_stt_mapping(
    *,
    window_sec: float = 180.0,
    overlap_sec: float,
    hysteresis_sec: float,
    max_boundary_shift_sec: float,
) -> dict:
    return {
        "stt_windowed_finalize_enabled": True,
        "stt_window_sec": float(window_sec),
        "stt_window_overlap_sec": float(overlap_sec),
        "stt_window_hysteresis_sec": float(hysteresis_sec),
        "stt_window_max_boundary_shift_sec": float(max_boundary_shift_sec),
    }


def _ffmpeg_silero_relaxed_audio_mapping() -> dict:
    return {
        "selected_audio_ai": "none",
        "use_basic_filter": True,
        "ff_hp": 90,
        "ff_lp": 5200,
        "ff_nf": -18,
        "ff_dynaudnorm_m": 10.0,
        "ff_dynaudnorm_p": 0.97,
        "ff_treble_boost": 1.0,
        "ffmpeg_filter_threads": 8,
        "none_hp": 90,
        "none_lp": 3200,
        "none_nf": -32,
        "none_target": -14,
    }


def _high_runtime_detail_mapping() -> dict:
    return {
        "audio_preset_auto_benchmark_locked": True,
        "audio_chunk_routing_benchmark_locked": False,
        "audio_chunk_routing_enabled": False,
        "audio_chunk_route_vad_enabled": False,
        "vad_backend_policy": "legacy",
        "audio_chunk_profile_sec": 24.0,
        "audio_chunk_route_profile_samples": 3,
        "audio_chunk_route_profile_window_sec": 8.0,
        "audio_chunk_route_candidate_limit": 3,
        "audio_chunk_route_preview_enabled": True,
        "audio_chunk_route_preview_min_confidence": 0.76,
        "audio_chunk_route_preview_gap_max": 0.08,
        "audio_chunk_route_hysteresis_enabled": True,
        "audio_chunk_route_hysteresis_margin": 0.05,
        "audio_chunk_route_profile_memory_enabled": True,
        "audio_chunk_route_profile_memory_margin": 0.04,
        "audio_chunk_route_profile_memory_min_confidence": 0.64,
        "audio_chunk_route_switch_confirmation_enabled": True,
        "audio_chunk_route_switch_confirmation_margin": 0.04,
        "audio_chunk_route_switch_confirmation_strong_margin": 0.11,
        "audio_chunk_route_switch_confirmation_min_streak": 2,
        "audio_chunk_route_precision_threshold": 0.74,
        "audio_chunk_route_secondary_recheck_threshold": 0.68,
        "audio_chunk_route_low_confidence_threshold": 0.58,
        "audio_chunk_route_max_workers": 2,
        "scan_cut_audio_gain_enabled": True,
        "cut_boundary_detection_enabled": True,
        "cut_boundary_enabled": True,
        "scan_cut_enabled": True,
        "scan_cut_auto_enabled": True,
        "ten_vad_threshold": 0.46,
        "review_vad_before_stt_enabled": True,
        "vad_post_stt_align_enabled": True,
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
        "stt_ensemble_llm_judge_require_risk": True,
        "stt_ensemble_llm_judge_local_only": True,
        "stt_ensemble_llm_judge_low_score_threshold": 78.0,
        "stt_ensemble_llm_judge_min_score_delta": 10.0,
        "stt_ensemble_llm_judge_max_similarity": 0.94,
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


def _mode_locked_vad_mapping(preset_key: str) -> dict:
    key = str(preset_key or "").strip().lower()
    if key not in {"fast", "balanced", "precise", "stt"}:
        key = {
            "auto": "balanced",
            "high": "precise",
            "빠름": "fast",
            "보통": "balanced",
            "높음": "precise",
        }.get(key, "balanced")
    # BENCH LOCK 2026-05-18:
    # - Fast    -> clearvoice_ten_vad_noisy
    # - Auto    -> ffmpeg_silero_relaxed + 3분 롤링 재시작
    # - High    -> ffmpeg_silero_relaxed + 120초 롤링 재시작
    #              adaptive chunk audio는 구현은 유지하되 covered-only 회귀가 있어
    #              기본 High 잠금값에서는 비활성화
    # Source:
    # - Auto: Tiniping 0~3m sweep + 0~11m final validation.
    # - High: 11~17분 무자막 공백 제외 full rerun.
    profiles = {
        "fast": {
            "selected_vad": "ten_vad",
            "vad_threshold": 0.50,
            "ten_vad_threshold": 0.50,
            "vad_min_speech": 0.16,
            "vad_min_silence": 0.55,
            "vad_speech_pad": 0.25,
            "vad_window_size": 512,
            "review_vad_speech_pad_sec": 0.35,
            "review_vad_min_silence_sec": 0.75,
            "vad_post_stt_align_enabled": True,
        },
        "balanced": {
            "selected_vad": "silero",
            "vad_threshold": 0.36,
            "vad_min_speech": 0.14,
            "vad_min_silence": 0.45,
            "vad_speech_pad": 0.28,
            "vad_window_size": 512,
            "review_vad_speech_pad_sec": 0.32,
            "review_vad_min_silence_sec": 0.45,
            "vad_post_stt_align_enabled": True,
        },
        "precise": {
            "selected_vad": "silero",
            "vad_threshold": 0.36,
            "vad_min_speech": 0.14,
            "vad_min_silence": 0.45,
            "vad_speech_pad": 0.28,
            "vad_window_size": 512,
            "review_vad_speech_pad_sec": 0.32,
            "review_vad_min_silence_sec": 0.45,
            "vad_post_stt_align_enabled": True,
        },
        "stt": {
            "selected_vad": "ten_vad",
            "vad_threshold": 0.46,
            "ten_vad_threshold": 0.46,
            "vad_min_speech": 0.20,
            "vad_min_silence": 0.65,
            "vad_speech_pad": 0.28,
            "vad_window_size": 512,
            "review_vad_speech_pad_sec": 0.28,
            "review_vad_min_silence_sec": 0.65,
            "vad_post_stt_align_enabled": True,
        },
    }
    return dict(profiles.get(key, profiles["balanced"]))


def mode_locked_vad_settings(preset_key: str) -> dict:
    return _mode_locked_vad_mapping(preset_key)


def _tiniping_benchmark_mode_models() -> dict[str, tuple[str, ...]]:
    quality_model = _quality_model()
    turbo_model = _fast_model()
    return {
        "fast": (TINIPING_FAST_PRIMARY_MODEL, quality_model),
        "balanced": (turbo_model, quality_model),
        "precise": (quality_model, turbo_model),
    }


def recommended_mode_tags_for_model(model: str) -> tuple[str, ...]:
    value = str(model or "").strip()
    if not value:
        return ()
    tags: list[str] = []
    for preset_key in ("fast", "balanced", "precise"):
        if value in _tiniping_benchmark_mode_models().get(preset_key, ()):
            tags.append(STT_QUALITY_PRESET_LABELS[preset_key])
    return tuple(tags)


def mode_benchmark_locked_settings(preset_key: str) -> dict:
    key = str(preset_key or "").strip().lower()
    if key not in {"fast", "balanced", "precise", "stt"}:
        key = {
            "auto": "balanced",
            "high": "precise",
            "빠름": "fast",
            "보통": "balanced",
            "높음": "precise",
        }.get(key, "balanced")
    quality_model = _quality_model()
    turbo_model = _fast_model()
    secondary_model = _secondary_model()
    profiles = {
        "fast": {
            "selected_whisper_model": TINIPING_FAST_PRIMARY_MODEL,
            "selected_whisper_model_secondary": quality_model,
            "selected_audio_ai": "clearvoice",
            "stt_candidate_scoring_enabled": True,
            **_mode_locked_vad_mapping("fast"),
            **_pipeline_mapping(180, 6.0, 4),
            **_windowed_stt_mapping(overlap_sec=6.0, hysteresis_sec=3.0, max_boundary_shift_sec=0.16),
            **_cut_boundary_mapping("off"),
            **_decoder_settings(0.86, -1.0, 1.6, 0.0, 3, 1.0),
            "stt_ensemble_enabled": True,
            "stt_ensemble_llm_judge_enabled": False,
            "stt_ensemble_llm_judge_require_risk": True,
            "stt_ensemble_llm_judge_local_only": True,
            "stt_ensemble_llm_judge_low_score_threshold": 78.0,
            "stt_ensemble_llm_judge_min_score_delta": 10.0,
            "stt_ensemble_llm_judge_max_similarity": 0.94,
            "stt_ensemble_selective_enabled": True,
            "stt_ensemble_parallel_enabled": False,
            "stt_selective_secondary_recheck_enabled": True,
            "stt_low_score_recheck_enabled": False,
            "stt_low_score_recheck_threshold": 54,
            "stt_low_score_recheck_padding_sec": 0.35,
            "stt_low_score_recheck_max_segments": 0,
            "stt_low_score_recheck_max_audio_sec": 0.0,
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamps_precision_threshold": 72.0,
            "stt_word_timestamps_precision_max_segments": 0,
            "stt_word_timestamps_precision_max_audio_sec": 0.0,
            "stt_word_timestamps_precision_keep_text": True,
            "stt_word_timestamps_precision_min_similarity": 0.18,
            "stt_word_timestamps_precision_max_timing_shift_sec": 0.55,
            "stt_word_timestamps_precision_min_duration_ratio": 0.45,
            "stt_word_timestamps_precision_max_duration_ratio": 1.8,
            "subtitle_lora_micro_merge_enabled": False,
            "subtitle_lora_packaging_enabled": False,
            "subtitle_lora_packaging_mode": "readability_selective",
            "subtitle_output_selector_enabled": False,
            "vad_post_stt_align_enabled": True,
            "vad_post_stt_edge_pad_sec": 0.04,
            "subtitle_timing_anchor_max_start_lag_sec": 0.06,
            "subtitle_timing_anchor_max_end_lead_sec": 0.06,
            "subtitle_timing_anchor_max_end_lag_sec": 0.12,
            "runtime_quality_self_review_enabled": False,
            "fast_hallucination_guard_enabled": True,
            "editor_lora_runtime_enabled": True,
            "lora_pattern_first_enabled": True,
            "lora_pattern_query_compact_enabled": True,
            "subtitle_lora_quality_buckets": ["high"],
            "subtitle_cut_boundary_guard_enabled": False,
            "subtitle_bundle_use_confirmed_cuts": False,
            "subtitle_bundle_use_provisional_cuts": False,
            "deep_subtitle_policy_enabled": False,
            "deep_segment_setting_policy_enabled": False,
            "deep_stt_candidate_selector_enabled": False,
            "deep_timing_adjustment_enabled": True,
            "runtime_scheduler_ramp_up_enabled": True,
            "runtime_scheduler_ramp_initial_sec": 90.0,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "audio_chunk_routing_enabled": False,
            "audio_chunk_route_vad_enabled": False,
            "audio_chunk_profile_sec": 24.0,
            "vad_dual_model_enabled": True,
            "speaker_diarization_auto_enabled": True,
            "ff_hp": 150,
            "ff_lp": 4600,
            "ff_nf": -30,
            "ff_dynaudnorm_m": 18.0,
            "ff_dynaudnorm_p": 0.97,
            "ff_treble_boost": 2.8,
            "ffmpeg_filter_threads": 8,
            "none_hp": 90,
            "none_lp": 3200,
            "none_nf": -32,
            "none_target": -14,
        },
        "balanced": {
            "selected_whisper_model": turbo_model,
            "selected_whisper_model_secondary": quality_model,
            "stt_candidate_scoring_enabled": True,
            **_ffmpeg_silero_relaxed_audio_mapping(),
            **_mode_locked_vad_mapping("balanced"),
            **_pipeline_mapping(180, 10.0, 3),
            **_windowed_stt_mapping(overlap_sec=10.0, hysteresis_sec=5.0, max_boundary_shift_sec=0.14),
            **_cut_boundary_mapping("low"),
            **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            "stt_ensemble_enabled": True,
            "stt_ensemble_llm_judge_enabled": False,
            "stt_ensemble_llm_judge_require_risk": True,
            "stt_ensemble_llm_judge_local_only": True,
            "stt_ensemble_llm_judge_low_score_threshold": 78.0,
            "stt_ensemble_llm_judge_min_score_delta": 10.0,
            "stt_ensemble_llm_judge_max_similarity": 0.94,
            "stt_ensemble_selective_enabled": True,
            "stt_ensemble_parallel_enabled": False,
            "stt_selective_secondary_recheck_enabled": True,
            "stt_low_score_recheck_enabled": False,
            "stt_low_score_recheck_max_segments": 0,
            "stt_low_score_recheck_max_audio_sec": 0.0,
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": False,
            "stt_word_timestamps_precision_threshold": 72.0,
            "stt_word_timestamps_precision_max_segments": 16,
            "stt_word_timestamps_precision_max_audio_sec": 70.0,
            "stt_word_timestamps_precision_keep_text": True,
            "stt_word_timestamps_precision_min_similarity": 0.30,
            "stt_word_timestamps_precision_max_timing_shift_sec": 0.35,
            "stt_word_timestamps_precision_min_duration_ratio": 0.45,
            "stt_word_timestamps_precision_max_duration_ratio": 1.8,
            "subtitle_lora_micro_merge_enabled": False,
            "subtitle_lora_packaging_enabled": True,
            "subtitle_lora_packaging_mode": "readability_selective",
            "subtitle_output_selector_enabled": True,
            "vad_post_stt_align_enabled": True,
            "vad_post_stt_edge_pad_sec": 0.04,
            "subtitle_timing_anchor_max_start_lag_sec": 0.08,
            "subtitle_timing_anchor_max_end_lead_sec": 0.08,
            "subtitle_timing_anchor_max_end_lag_sec": 0.14,
            "runtime_quality_self_review_enabled": True,
            "fast_hallucination_guard_enabled": True,
            "editor_lora_runtime_enabled": True,
            "lora_pattern_first_enabled": True,
            "lora_pattern_query_compact_enabled": True,
            "subtitle_lora_quality_buckets": ["high"],
            "subtitle_cut_boundary_guard_enabled": True,
            "subtitle_bundle_use_confirmed_cuts": True,
            "subtitle_bundle_use_provisional_cuts": False,
            "deep_subtitle_policy_enabled": True,
            "deep_segment_setting_policy_enabled": False,
            "deep_stt_candidate_selector_enabled": True,
            "deep_timing_adjustment_enabled": False,
            "runtime_scheduler_ramp_up_enabled": True,
            "runtime_scheduler_ramp_initial_sec": 45.0,
            "runtime_scheduler_ramp_step_sec": 60.0,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "audio_chunk_routing_enabled": True,
            "audio_chunk_route_vad_enabled": True,
            "audio_chunk_profile_sec": 30.0,
            "audio_chunk_route_profile_memory_enabled": True,
            "audio_chunk_route_profile_memory_margin": 0.04,
            "audio_chunk_route_profile_memory_min_confidence": 0.64,
            "audio_chunk_route_switch_confirmation_enabled": True,
            "audio_chunk_route_switch_confirmation_margin": 0.04,
            "audio_chunk_route_switch_confirmation_strong_margin": 0.11,
            "audio_chunk_route_switch_confirmation_min_streak": 2,
            "vad_dual_model_enabled": False,
            "speaker_diarization_auto_enabled": True,
        },
        "precise": {
            "selected_whisper_model": quality_model,
            "selected_whisper_model_secondary": turbo_model,
            "selected_model": TINIPING_SUBTITLE_LLM_MODEL,
            "selected_llm_provider": "ollama",
            "subtitle_llm_user_selected": True,
            "stt_candidate_scoring_enabled": True,
            **_ffmpeg_silero_relaxed_audio_mapping(),
            **_mode_locked_vad_mapping("precise"),
            **_high_runtime_detail_mapping(),
            **_pipeline_mapping(120, 8.0, 2),
            **_windowed_stt_mapping(
                window_sec=120.0,
                overlap_sec=8.0,
                hysteresis_sec=4.0,
                max_boundary_shift_sec=0.10,
            ),
            **_cut_boundary_mapping("medium"),
            **_roughcut_llm_mapping(TINIPING_SUBTITLE_LLM_MODEL),
            **_decoder_settings(0.42, -2.6, 2.4, 0.6, 8, 1.35),
            **_high_llm_gate_mapping(),
            "stt_ensemble_enabled": True,
            "stt_ensemble_llm_judge_enabled": True,
            "stt_ensemble_llm_judge_require_risk": True,
            "stt_ensemble_llm_judge_local_only": True,
            "stt_ensemble_llm_judge_low_score_threshold": 78.0,
            "stt_ensemble_llm_judge_min_score_delta": 10.0,
            "stt_ensemble_llm_judge_max_similarity": 0.94,
            "stt_ensemble_selective_enabled": True,
            "stt_ensemble_parallel_enabled": False,
            "stt_selective_secondary_recheck_enabled": True,
            "stt_low_score_recheck_enabled": True,
            "stt_low_score_recheck_threshold": 78,
            "stt_low_score_recheck_padding_sec": 0.45,
            "stt_low_score_recheck_max_segments": 24,
            "stt_low_score_recheck_max_audio_sec": 110.0,
            "stt_low_score_recheck_min_improvement": 2.0,
            "stt_word_timestamps_mode": "selective",
            "stt_word_timestamps_default_enabled": False,
            "stt_word_timestamps_precision_enabled": True,
            "stt_word_timestamps_precision_threshold": 72.0,
            "stt_word_timestamps_precision_max_segments": 48,
            "stt_word_timestamps_precision_max_audio_sec": 100.0,
            "stt_word_timestamps_precision_keep_text": True,
            "stt_word_timestamps_precision_min_similarity": 0.36,
            "stt_word_timestamps_precision_max_timing_shift_sec": 0.28,
            "stt_word_timestamps_precision_min_duration_ratio": 0.45,
            "stt_word_timestamps_precision_max_duration_ratio": 1.8,
            "subtitle_lora_micro_merge_enabled": False,
            "subtitle_lora_packaging_enabled": True,
            "subtitle_lora_packaging_mode": "readability_selective",
            "subtitle_output_selector_enabled": True,
            "vad_post_stt_align_enabled": True,
            "vad_post_stt_edge_pad_sec": 0.04,
            "subtitle_timing_anchor_max_start_lag_sec": 0.06,
            "subtitle_timing_anchor_max_end_lead_sec": 0.06,
            "subtitle_timing_anchor_max_end_lag_sec": 0.12,
            "runtime_quality_self_review_enabled": True,
            "fast_hallucination_guard_enabled": True,
            "editor_lora_runtime_enabled": True,
            "lora_pattern_first_enabled": True,
            "lora_pattern_query_compact_enabled": True,
            "subtitle_lora_quality_buckets": ["high"],
            "subtitle_cut_boundary_guard_enabled": True,
            "subtitle_bundle_use_confirmed_cuts": True,
            "subtitle_bundle_use_provisional_cuts": False,
            "deep_subtitle_policy_enabled": True,
            "deep_segment_setting_policy_enabled": False,
            "deep_stt_candidate_selector_enabled": True,
            "deep_timing_adjustment_enabled": True,
            "subtitle_llm_runtime_enabled": True,
            "subtitle_llm_macro_chunk_enabled": True,
            "subtitle_llm_context_boundary_refine_enabled": True,
            "subtitle_llm_context_word_correction_enabled": True,
            "subtitle_llm_context_max_pairs": 8,
            "subtitle_llm_context_require_risk_signal": True,
            "subtitle_llm_context_max_pair_gap_sec": 0.85,
            "subtitle_llm_context_min_pair_chars": 6,
            "subtitle_llm_context_max_pair_chars": 58,
            "subtitle_llm_context_allow_merge": True,
            "subtitle_llm_context_merge_max_chars": 32,
            "subtitle_llm_context_merge_micro_max_chars": 4,
            "subtitle_llm_context_merge_micro_max_duration_sec": 0.55,
            "subtitle_llm_context_max_word_corrections": 2,
            "subtitle_llm_context_timeout_sec": 45.0,
            "subtitle_llm_context_num_predict": 180,
            "subtitle_llm_mode_disabled": False,
            "runtime_scheduler_ramp_up_enabled": False,
            "background_prefetch_lora_enabled": False,
            "background_prefetch_candidates_enabled": False,
            "vad_dual_model_enabled": True,
            "speaker_diarization_auto_enabled": True,
            "ff_hp": 90,
            "ff_lp": 5200,
            "ff_nf": -18,
            "ff_dynaudnorm_m": 10.0,
            "ff_dynaudnorm_p": 0.97,
            "ff_treble_boost": 1.0,
            "ffmpeg_filter_threads": 8,
            "none_hp": 90,
            "none_lp": 3200,
            "none_nf": -32,
            "none_target": -14,
        },
        "stt": {
            "selected_whisper_model": quality_model,
            "selected_whisper_model_secondary": secondary_model,
            "selected_model": "사용 안함 (STT 모드)",
            "selected_llm_provider": "none",
            "subtitle_llm_user_selected": False,
            "selected_audio_ai": "none",
            "stt_ensemble_enabled": False,
            "stt_ensemble_llm_judge_enabled": False,
            "stt_ensemble_llm_judge_require_risk": True,
            "stt_ensemble_llm_judge_local_only": True,
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
            **_mode_locked_vad_mapping("stt"),
            **_pipeline_mapping(20, 0.0, 1),
            **_cut_boundary_mapping("low"),
            **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
        },
    }
    return deepcopy(profiles[key])


def load_stt_quality_presets() -> dict[str, dict]:
    return {
        "fast": {
            "label": STT_QUALITY_PRESET_LABELS["fast"],
            "description": f"{TINIPING_BENCHMARK_REFERENCE} 기준 Fast 우승 조합: Komix STT1 + WhisperKit 품질 STT2 selective rescue",
            "settings": mode_benchmark_locked_settings("fast"),
        },
        "balanced": {
            "label": STT_QUALITY_PRESET_LABELS["balanced"],
            "description": f"{TINIPING_BENCHMARK_REFERENCE} 기준 Auto 우승 조합: WhisperKit Turbo + ffmpeg/silero relaxed + {AUTO_WINDOWED_STT_REFERENCE}",
            "settings": mode_benchmark_locked_settings("balanced"),
        },
        "precise": {
            "label": STT_QUALITY_PRESET_LABELS["precise"],
            "description": "Tiniping 11~17분 무자막 공백 제외 full rerun 기준 High 우승 조합: "
            f"WhisperKit 품질 + ffmpeg/silero relaxed + {HIGH_WINDOWED_STT_REFERENCE} + selective STT2/word precision + LLM "
            "(adaptive chunk audio 엔진은 유지하지만 기본 High에는 아직 강제하지 않음)",
            "settings": mode_benchmark_locked_settings("precise"),
        },
        "stt": {
            "label": STT_QUALITY_PRESET_LABELS["stt"],
            "description": "수동/받아쓰기 STT 전용, VAD + STT LoRA 재분할",
            "settings": mode_benchmark_locked_settings("stt"),
        },
    }


def normalize_stt_quality_key(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if key in {"fast", "balanced", "precise", "stt"}:
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
    return snapshot


def _strip_mode_managed_routes(settings: dict | None) -> dict:
    out = dict(settings or {})
    for route_key in MODE_MANAGED_ROUTE_KEYS:
        if route_key not in USER_SELECTABLE_MODEL_KEYS:
            out.pop(route_key, None)
    return out


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
    out = _strip_mode_managed_routes(settings)
    out.update(deepcopy(preset.get("settings", {})))
    user_presets = dict(out.get(STT_QUALITY_USER_PRESET_KEY) or {})
    user_preset = user_presets.get(key)
    user_preset_applied = False
    if use_saved_user_preset and isinstance(user_preset, dict):
        user_settings = user_preset.get("settings", {})
        if isinstance(user_settings, dict):
            out.update(
                {
                    setting_key: deepcopy(user_settings[setting_key])
                    for setting_key in USER_SELECTABLE_MODEL_KEYS
                    if setting_key in user_settings and user_settings.get(setting_key) not in (None, "")
                }
            )
            user_preset_applied = True
    if user_route_snapshot:
        out.update(user_route_snapshot)
    if incoming_user_stt_models and not user_preset_applied:
        # Mode presets control processing policy. STT1/STT2 model identity is
        # a direct user choice and should not be replaced by mode defaults.
        out.update(incoming_user_stt_models)
    if benchmark_routes:
        out.update(benchmark_routes)
    out.pop(STT_ENSEMBLE_USER_SELECTED_KEY, None)
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
