# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/settings_common.py
settings 다이얼로그 공통 상수, 유틸 함수, 공유 데이터
모든 settings_*.py 파일이 이 모듈을 import합니다.
"""
import os
import json

from core.data_manager import load_settings, save_settings, save_default_settings
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QSpinBox, QPushButton, QSlider, QFrame,
    QToolTip, QTabWidget, QWidget, QTextEdit, QCheckBox, QMessageBox, QLineEdit
)
from PyQt6.QtGui import QCursor
from PyQt6.QtCore import Qt, QTimer
import requests
import config

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset")

# ── OS별 Whisper 모델 목록 ──
if config.IS_MAC:
    DEFAULT_WHISPER_MODELS = [
        "mlx-community/whisper-large-v3-mlx",
        "mlx-community/whisper-large-v3-turbo",
        "mlx-community/whisper-medium-mlx",
        "mlx-community/whisper-small-mlx",
        "mlx-community/whisper-base-mlx"
    ]
else:
    DEFAULT_WHISPER_MODELS = [
        "large-v3",
        "large-v3-turbo",
        "medium",
        "small",
        "base",
        "tiny"
    ]

DEFAULT_ADV_SETTINGS = {
    # Silero
    "vad_threshold": 0.5,
    "vad_min_speech": 0.25,
    "vad_min_silence": 2.0,
    "vad_speech_pad": 0.1,
    "vad_window_size": 512,

    # Demucs
    "dm_vol": 3.5,
    "dm_shifts": 2,
    "dm_overlap": 0.25,
    "dm_segments": 45,
    "w_dm_no_speech": 0.6,
    "w_dm_logprob": -1.5,
    "w_dm_comp": 2.4,
    "w_dm_temp_max": 0.6,

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
    "gap_pull_rate": 0.3,
    "gap_push_rate": 0.7,
    "single_subtitle_end": 0.2,
    "split_length_threshold": 10,
    "sub_min_duration": 0.2,
    "sub_max_cps": 12,
    "sub_dedup_window": 0.5,
    "sub_gap_break_sec": 1.5
}

CUSTOM_DEFAULTS_FILE = os.path.join(DATASET_DIR, "custom_defaults.json")
try:
    if os.path.exists(CUSTOM_DEFAULTS_FILE):
        with open(CUSTOM_DEFAULTS_FILE, "r", encoding="utf-8") as f:
            DEFAULT_ADV_SETTINGS.update(json.load(f))
except Exception:
    pass


def _fetch_models():
    settings = load_settings()

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

    for fallback_name in [
        (settings.get("selected_model", "") or "").strip(),
        (getattr(config, "OLLAMA_MODEL", "") or "").strip(),
    ]:
        if fallback_name and fallback_name not in merged and not fallback_name.startswith("Gemini "):
            merged[fallback_name] = {
                "name": fallback_name,
                "size": 0,
                "details": {
                    "family": "Local",
                    "parameter_size": "Unknown",
                    "format": "ollama",
                },
            }

    return sorted(merged.values(), key=lambda x: x["name"].lower())

def _create_bottom_buttons(dialog, accept_callback, reset_callback=None,
                           save_callback=None, save_def_callback=None):
    btn_layout = QHBoxLayout()

    if reset_callback:
        btn_reset = QPushButton("🔄 전체 초기화")
        btn_reset.setStyleSheet("background-color: #555555; color: #FFFFFF; padding: 6px 16px; font-weight: bold; border-radius: 4px;")
        btn_reset.clicked.connect(reset_callback)
        btn_layout.addWidget(btn_reset)

    if save_callback:
        btn_save = QPushButton("💾 저장")
        btn_save.setStyleSheet("background-color: #4fc3f7; color: #000000; padding: 6px 16px; font-weight: bold; border-radius: 4px;")
        btn_save.clicked.connect(save_callback)
        btn_layout.addWidget(btn_save)

    if save_def_callback:
        btn_def = QPushButton("⭐ 기본값으로 저장")
        btn_def.setStyleSheet("background-color: #FFA726; color: #000000; padding: 6px 16px; font-weight: bold; border-radius: 4px;")
        btn_def.clicked.connect(save_def_callback)
        btn_layout.addWidget(btn_def)

    btn_layout.addStretch()

    btn_cancel = QPushButton("취소")
    btn_ok     = QPushButton("확인")
    btn_cancel.setStyleSheet("background-color: #444444; color: #FFFFFF; padding: 6px 16px; font-weight: bold; border-radius: 4px;")
    btn_ok.setStyleSheet    ("background-color: #4AFF80; color: #000000; padding: 6px 16px; font-weight: bold; border-radius: 4px;")

    btn_cancel.clicked.connect(dialog.reject)
    btn_ok.clicked.connect(accept_callback)
    btn_layout.addWidget(btn_cancel)
    btn_layout.addWidget(btn_ok)
    return btn_layout
