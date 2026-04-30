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


def load_stt_quality_presets() -> dict[str, dict]:
    return {
        "fast": {
            "label": "빠른 인식",
            "description": "속도 우선, Whisper 단독 진행",
            "settings": {
                "selected_whisper_model": _fast_model(),
                "selected_model": "사용 안함 (Whisper 단독 진행)",
                "ff_chunk": 30,
                "whisper_chunk_overlap_sec": 0.5,
                "stt_parallel_level": 4,
                **_decoder_settings(0.86, -1.0, 1.6, 0.0, 3, 1.0),
            },
        },
        "balanced": {
            "label": "균형",
            "description": "속도와 정확도 균형",
            "settings": {
                "selected_whisper_model": _quality_model(),
                "selected_model": "exaone3.5:2.4b",
                "ff_chunk": 25,
                "whisper_chunk_overlap_sec": 1.5,
                "stt_parallel_level": 3,
                **_decoder_settings(0.58, -1.8, 2.2, 0.4, 5, 1.1),
            },
        },
        "precise": {
            "label": "정밀 인식",
            "description": "정확도 우선, 더 긴 검토",
            "settings": {
                "selected_whisper_model": _quality_model(),
                "selected_model": "exaone3.5:7.8b",
                "ff_chunk": 20,
                "whisper_chunk_overlap_sec": 3.0,
                "stt_parallel_level": 2,
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
