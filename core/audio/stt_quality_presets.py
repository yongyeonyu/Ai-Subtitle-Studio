# Version: 03.01.22
# Phase: PHASE2
from __future__ import annotations

from copy import deepcopy

import config


def _quality_model() -> str:
    return "mlx-community/whisper-large-v3-mlx" if config.IS_MAC else "large-v3"


def _fast_model() -> str:
    return "mlx-community/whisper-large-v3-turbo" if config.IS_MAC else "large-v3-turbo"


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


def _pipeline_mapping(audio_preset: str, audio_ai: str, vad: str, ff_chunk: int, overlap_sec: float, parallel_level: int) -> dict:
    return {
        "audio_preset": audio_preset,
        "selected_audio_ai": audio_ai,
        "selected_vad": vad,
        "ff_chunk": ff_chunk,
        "whisper_chunk_overlap_sec": overlap_sec,
        "stt_parallel_level": parallel_level,
    }


def _cut_boundary_mapping(level: str) -> dict:
    level = str(level or "medium").strip().lower()
    if level == "high":
        level = "medium"
    enabled = level != "off"
    labels = {
        "off": "사용안함",
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
    return {
        "fast": {
            "label": "빠른 인식",
            "description": "속도 우선, 전처리/음성필터/VAD 최소화",
            "settings": {
                "selected_whisper_model": _fast_model(),
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                **_pipeline_mapping("실내-마이크무", "none", "none", 30, 0.5, 4),
                **_cut_boundary_mapping("off"),
                **_decoder_settings(0.86, -1.0, 1.6, 0.0, 3, 1.0),
            },
        },
        "balanced": {
            "label": "균형",
            "description": "일반 자막 생성용 기본 조합",
            "settings": {
                "selected_whisper_model": _quality_model(),
                "selected_model": "exaone3.5:2.4b",
                **_pipeline_mapping("실내-마이크유", "deepfilter", "silero", 25, 1.5, 3),
                **_cut_boundary_mapping("low"),
                **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            },
        },
        "precise": {
            "label": "정밀 인식",
            "description": "정확도 우선, 강한 전처리/음성필터/VAD 조합",
            "settings": {
                "selected_whisper_model": _quality_model(),
                "selected_model": "gemma4:e4b",
                **_pipeline_mapping("실외-마이크유", "clearvoice", "ten_vad", 20, 3.0, 2),
                **_cut_boundary_mapping("medium"),
                **_decoder_settings(0.42, -2.6, 2.4, 0.6, 8, 1.35),
            },
        },
    }


def normalize_stt_quality_key(value: str | None) -> str:
    key = str(value or "").strip().lower()
    if key in load_stt_quality_presets():
        return key
    aliases = {
        "빠른 인식": "fast",
        "빠른인식": "fast",
        "fast": "fast",
        "균형": "balanced",
        "balance": "balanced",
        "balanced": "balanced",
        "정밀 인식": "precise",
        "정밀인식": "precise",
        "precise": "precise",
    }
    return aliases.get(key, "balanced")


def apply_stt_quality_preset(settings: dict, preset_key: str) -> dict:
    presets = load_stt_quality_presets()
    key = normalize_stt_quality_key(preset_key)
    preset = presets[key]
    out = dict(settings)
    out.update(deepcopy(preset.get("settings", {})))
    out["stt_quality_preset"] = key
    return out
