# Version: 03.14.17
# Phase: PHASE2
"""
ui/settings_common.py
settings 다이얼로그 공통 상수, 유틸 함수, 공유 데이터
모든 settings_*.py 파일이 이 모듈을 import합니다.
"""
import os
import json

from PyQt6.QtWidgets import (
    QHBoxLayout, QPushButton
)
from core.runtime import config
from ui.settings.qml_panel import create_qml_action_bar
from ui.style import line_icon, settings_button_style

DATASET_DIR = config.DATASET_DIR

# ── OS별 Whisper 모델 목록 ──
MAC_WHISPER_MODELS = [
    "mlx-community/whisper-large-v3-mlx",
    "mlx-community/whisper-large-v3-turbo",
    "youngouk/ghost613-turbo-korean-4bit-mlx",
    "whisper-medium-komixv2",
    "youngouk/whisper-medium-komixv2-mlx",
    "whisperkit-persistent:large-v3",
    "whisper.cpp:large-v3-turbo",
    "seastar105/whisper-medium-komixv2",
    "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
    "mlx-community/whisper-large-v2-mlx",
    "mlx-community/whisper-medium-mlx",
    "mlx-community/distil-whisper-large-v3",
]

WINDOWS_WHISPER_MODELS = [
    "large-v3",
    "large-v3-turbo",
    "turbo",
    "ghost613/faster-whisper-large-v3-turbo-korean",
    "whisper-medium-komixv2",
    "whisper.cpp:large-v3-turbo",
    "seastar105/whisper-medium-komixv2",
    "o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2",
    "large-v2",
    "large-v1",
    "large",
    "medium",
    "distil-large-v3",
    "distil-large-v2",
    "distil-medium.en",
    "distil-small.en",
]

REMOVED_WHISPER_MODELS = {
    "coreml:large-v3-v20240930_626MB",
    "mlx-community/whisper-medium.en-mlx",
    "mlx-community/whisper-small-mlx",
    "mlx-community/whisper-small.en-mlx",
    "mlx-community/whisper-base-mlx",
    "mlx-community/whisper-base.en-mlx",
    "mlx-community/whisper-tiny-mlx",
    "mlx-community/whisper-tiny.en-mlx",
    "medium.en",
    "small",
    "small.en",
    "base",
    "base.en",
    "tiny",
    "tiny.en",
}


def filter_available_whisper_models(models):
    return [model for model in models if model not in REMOVED_WHISPER_MODELS]


DEFAULT_WHISPER_MODELS = filter_available_whisper_models(
    MAC_WHISPER_MODELS if config.IS_MAC else WINDOWS_WHISPER_MODELS
)

DEFAULT_ADV_SETTINGS = {
    # Silero
    "vad_threshold": 0.5,
    "vad_min_speech": 0.25,
    "vad_min_silence": 2.0,
    "vad_speech_pad": 0.1,
    "vad_window_size": 512,

    # DeepFilter
    "df_hp": 100,
    "df_eq_g": 8,
    "df_comp_th": -28,
    "df_vol": 3.5,
    "df_atten_lim": 100,
    "w_df_no_speech": 0.4,
    "w_df_logprob": -2.5,
    "w_df_comp": 2.4,
    "w_df_temp_max": 0.8,

    # None / Whisper General
    "none_hp": 80,
    "none_comp_th": -28,
    "none_vol": 4.0,
    "w_none_no_speech": 0.85,
    "w_none_logprob": -1.0,
    "w_none_comp": 1.6,
    "w_none_temp_max": 0.4,
    "w_beam_size": 5,
    "w_patience": 1.0,
    "w_length_penalty": 1.0,

    # System
    "io_workers": 6,
    "llm_threads": 4,

    # FFmpeg
    "ff_threads": 0,
    "ff_ac": 1,
    "ff_ar": 16000,
    "ff_hp": 200,
    "ff_lp": 3000,
    "ff_nf": -25,
    "ff_chunk": 30,
    "ff_dynaudnorm_m": 10.0,
    "ff_dynaudnorm_p": 0.95,
    "ff_treble_boost": 0.0,

    "user_prompt": "",

    "continuous_threshold": 2.0,
    "gap_push_rate": 0.7,
    "single_subtitle_end": 0.2,
    "split_length_threshold": 10,
    "sub_min_duration": 0.2,
    "sub_max_duration": 6.0,
    "subtitle_common_split_guard_enabled": True,
    "subtitle_common_split_target_chars": 16,
    "subtitle_common_split_hard_max_chars": 24,
    "subtitle_common_split_hard_max_duration_sec": 5.5,
    "sub_max_cps": 12,
    "sub_dedup_window": 0.5,
    "sub_gap_break_sec": 1.5,

    # Accuracy-first subtitle generation defaults.
    "accuracy_first_mode": True,
    "settings_simplified_ui_enabled": True,
    "simple_operation_mode": "auto",
    "auto_start_mode": "balanced",
    "stt_quality_preset": "balanced",
    "stt_ensemble_enabled": False,
    "stt_candidate_scoring_enabled": True,
    "stt_low_score_recheck_enabled": True,
    "stt_low_score_recheck_threshold": 60,
    "stt_low_score_recheck_padding_sec": 0.8,
    "stt_low_score_recheck_max_segments": 80,
    "selected_whisper_model_secondary": (
        "youngouk/ghost613-turbo-korean-4bit-mlx"
        if config.IS_MAC else
        "ghost613/faster-whisper-large-v3-turbo-korean"
    ),
    "stt_ensemble_llm_judge_enabled": False,
    "vad_post_stt_align_enabled": True,
    "vad_post_stt_max_shift_sec": 0.7,
    "vad_post_stt_edge_pad_sec": 0.04,
    "subtitle_quality_enabled": False,
    "subtitle_quality_auto_check_after_generate": True,
    "subtitle_quality_auto_correct_enabled": True,
    "editor_lora_runtime_enabled": True,
    "audio_chunk_routing_enabled": True,
    "audio_chunk_route_vad_enabled": True,
    "audio_chunk_profile_sec": 30.0,
    "whisper_chunk_overlap_sec": 3.0,
    "chunk_time_limit": 180,
    "vad_pre_split_enabled": False,
    "review_vad_before_stt_enabled": True,
    "review_vad_strict_mode": True,
    "review_vad_speech_pad_sec": 0.35,
    "review_vad_min_silence_sec": 0.8,
    "review_min_segment_score_to_keep": 55,
    "review_auto_correct_apply_threshold": 94,
    "review_auto_correct_min_improvement": 8,
    "review_recheck_buffer_sec": 1.5,
    "review_auto_correct_require_user_confirm": False,
    "correction_memory_enabled": True,
    "wrong_answer_memory_enabled": True,
    "score_weight_asr_metadata": 0.25,
    "score_weight_vad_alignment": 0.20,
    "score_weight_word_timestamp": 0.15,
    "score_weight_timing": 0.10,
    "score_weight_repetition": 0.10,
    "score_weight_context": 0.10,
    "score_weight_memory": 0.05,
    "score_weight_hallucination_penalty": 0.30,
    "runtime_scheduler_auto_enabled": True,
    "scheduler_reduce_on_battery": True,
    "scheduler_reduce_on_user_input": True,
    "runtime_scheduler_reserve_cores": 0,
    "runtime_npu_acceleration_enabled": True,
    "stt_npu_prefer_enabled": True,
    "live_stt_npu_prefer_enabled": True,
    "editor_rendering_gpu_enabled": True,
    "editor_rendering_gpu_scope": "all",
    "editor_rendering_opengl_widgets_enabled": True,
    "editor_rendering_scenegraph_enabled": True,
    "editor_rendering_force_qt_opengl": False,
    "editor_rendering_qt_backend": "auto",
    "stt_workers_auto_enabled": True,
    "cut_pioneer_workers_auto_enabled": True,
    "cut_follower_workers_auto_enabled": True,
    "lora_workers_auto_enabled": True,
    "cut_boundary_cache_enabled": True,
    "scan_cut_compare_max_width": 1920,
    "scan_cut_compare_max_height": 1080,
    "vad_detection_cache_enabled": True,
}

CUSTOM_DEFAULTS_FILE = os.path.join(DATASET_DIR, "custom_defaults.json")
try:
    if os.path.exists(CUSTOM_DEFAULTS_FILE):
        with open(CUSTOM_DEFAULTS_FILE, "r", encoding="utf-8") as f:
            DEFAULT_ADV_SETTINGS.update(json.load(f))
except Exception:
    pass


def _fetch_models():
    models = []
    try:
        from core.model_manager import get_local_llm_models
        models = get_local_llm_models()
    except Exception:
        models = []

    merged = {}
    for m in models:
        name = (m.get("name") or "").strip()
        if not name:
            continue
        merged[name] = {
            "name": name,
            "size": int(m.get("size", 0) or 0),
            "details": dict(m.get("details", {}) or {}),
        }

    # Ollama가 감지되지 않으면 로컬 모델은 표시하지 않습니다.
    # 단, 현재 선택값이 실제 감지 목록에 있으면 그대로 유지됩니다.
    return sorted(merged.values(), key=lambda x: x["name"].lower())

def _create_bottom_buttons(dialog, accept_callback, reset_callback=None,
                           save_callback=None, save_def_callback=None):
    btn_layout = QHBoxLayout()
    control_height = int(getattr(dialog, "_settings_control_height", 40) or 40)
    actions = []

    if reset_callback:
        actions.append({"id": "reset", "title": "전체 초기화", "kind": "secondary", "enabled": True})
    if save_callback:
        actions.append({"id": "save", "title": "저장", "kind": "primary", "enabled": True})
    if save_def_callback:
        actions.append({"id": "save_default", "title": "기본값 저장", "kind": "secondary", "enabled": True})
    actions.extend(
        [
            {"id": "cancel", "title": "취소", "kind": "secondary", "enabled": True},
            {"id": "ok", "title": "확인", "kind": "primary", "enabled": True},
        ]
    )

    qml_bar = create_qml_action_bar(dialog, actions=actions, scope="settings")
    if qml_bar is not None:
        callback_map = {
            "reset": reset_callback,
            "save": save_callback,
            "save_default": save_def_callback,
            "cancel": dialog.reject,
            "ok": accept_callback,
        }
        try:
            root = qml_bar.rootObject()
            if root is not None:
                root.actionTriggered.connect(lambda action_id: (callback_map.get(str(action_id)) or (lambda: None))())
        except Exception:
            qml_bar = None
    if qml_bar is not None:
        btn_layout.addWidget(qml_bar)
        return btn_layout

    if reset_callback:
        btn_reset = QPushButton("전체 초기화")
        btn_reset.setIcon(line_icon("refresh", "#A9B0B7", 18))
        btn_reset.setStyleSheet(settings_button_style("toolbar", min_width=96, min_height=control_height))
        btn_reset.clicked.connect(reset_callback)
        btn_layout.addWidget(btn_reset)

    if save_callback:
        btn_save = QPushButton("저장")
        btn_save.setIcon(line_icon("save", "#FFFFFF", 18))
        btn_save.setStyleSheet(settings_button_style("primary", min_width=96, min_height=control_height))
        btn_save.clicked.connect(save_callback)
        btn_layout.addWidget(btn_save)

    if save_def_callback:
        btn_def = QPushButton("기본값으로 저장")
        btn_def.setIcon(line_icon("save", "#A9B0B7", 18))
        btn_def.setStyleSheet(settings_button_style("toolbar", min_width=118, min_height=control_height))
        btn_def.clicked.connect(save_def_callback)
        btn_layout.addWidget(btn_def)

    btn_layout.addStretch()

    btn_cancel = QPushButton("취소")
    btn_ok     = QPushButton("확인")
    btn_cancel.setIcon(line_icon("cancel", "#A9B0B7", 18))
    btn_ok.setIcon(line_icon("check", "#FFFFFF", 18))
    btn_cancel.setStyleSheet(settings_button_style("toolbar", min_width=82, min_height=control_height))
    btn_ok.setStyleSheet(settings_button_style("primary", min_width=96, min_height=control_height))

    btn_cancel.clicked.connect(dialog.reject)
    btn_ok.clicked.connect(accept_callback)
    btn_layout.addWidget(btn_cancel)
    btn_layout.addWidget(btn_ok)
    return btn_layout
