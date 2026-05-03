# Version: 03.14.00
# Phase: PHASE1-B
"""
core/audio/audio_presets.py
Audio/STT preset loader and applier.
"""
from __future__ import annotations

import json
import os
from copy import deepcopy

from core.runtime import config


PRESET_PATH = os.path.join(config.DATASET_DIR, "audio_presets.json")

from core.audio.audio_preset_data import (
    CURATED_AUDIO_PRESET_SPECS,
    DEFAULT_AUDIO_APPLY_DATA,
    DEFAULT_AUDIO_PRESETS,
)


def ensure_audio_presets_file() -> None:
    if os.path.exists(PRESET_PATH):
        return
    os.makedirs(os.path.dirname(PRESET_PATH), exist_ok=True)
    with open(PRESET_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_AUDIO_PRESETS, f, ensure_ascii=False, indent=2)


def load_audio_presets() -> dict[str, dict]:
    ensure_audio_presets_file()
    try:
        with open(PRESET_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged = deepcopy(DEFAULT_AUDIO_PRESETS)
            for name, preset in data.items():
                if isinstance(preset, dict):
                    merged[name] = preset
            return _inject_curated_audio_presets(merged)
    except Exception:
        pass
    return _inject_curated_audio_presets(deepcopy(DEFAULT_AUDIO_PRESETS))


def apply_audio_preset(settings: dict, preset_name: str) -> dict:
    presets = load_audio_presets()
    preset = presets.get(preset_name)
    if not preset:
        return settings
    out = dict(settings)
    for key, value in dict(preset.get("settings", {}) or {}).items():
        out[key] = value
    for key, value in dict(preset.get("stack", {}) or {}).items():
        out[key] = deepcopy(value)
    out["audio_preset"] = preset_name
    return out


def apply_default_audio_preset(settings: dict) -> dict:
    out = dict(settings)
    for key, value in DEFAULT_AUDIO_APPLY_DATA.items():
        out[key] = deepcopy(value)
    out["audio_preset"] = ""
    return out


def uses_default_audio_preset(settings: dict | None) -> bool:
    data = dict(settings or {})
    if str(data.get("audio_preset", "") or "").strip():
        return False
    for key, value in DEFAULT_AUDIO_APPLY_DATA.items():
        if data.get(key) != value:
            return False
    return True


def resolve_audio_preset_combo_data(settings: dict | None) -> str:
    data = dict(settings or {})
    preset_name = str(data.get("audio_preset", "") or "").strip()
    if preset_name:
        return preset_name
    if uses_default_audio_preset(data):
        return "__default__"
    return ""


def curated_audio_preset_names() -> list[str]:
    return list(CURATED_AUDIO_PRESET_SPECS.keys())


def _first_preset(base_presets: dict[str, dict], names: list[str]) -> dict | None:
    for name in names:
        preset = base_presets.get(name)
        if isinstance(preset, dict):
            return preset
    return None


def _inject_curated_audio_presets(base_presets: dict[str, dict]) -> dict[str, dict]:
    merged = deepcopy(base_presets or {})
    for name, spec in CURATED_AUDIO_PRESET_SPECS.items():
        candidates = [str(spec.get("base") or "")]
        candidates.extend(list(spec.get("fallbacks") or []))
        source = _first_preset(merged, candidates)
        if not isinstance(source, dict):
            continue
        row = deepcopy(source)
        row["description"] = str(spec.get("description") or row.get("description") or name)
        settings = dict(row.get("settings") or {})
        settings.update(deepcopy(spec.get("overrides") or {}))
        row["settings"] = settings
        if spec.get("stack"):
            row["stack"] = deepcopy(spec.get("stack") or {})
        merged[name] = row
    return merged
