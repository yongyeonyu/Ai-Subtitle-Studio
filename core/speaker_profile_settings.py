from __future__ import annotations

import glob
import os
from typing import Any

from core.runtime import config


DEFAULT_SPEAKER_IDS = {
    1: "00",
    2: "01",
    3: "02",
}

DEFAULT_SPEAKER_COLORS = {
    1: "#FFFFFF",
    2: "#FFD60A",
    3: "#00FFFF",
}


def normalize_speaker_id(raw: Any) -> str:
    speaker = str(raw or "").strip()
    if speaker.startswith("SPEAKER_"):
        speaker = speaker.replace("SPEAKER_", "", 1)
    return speaker or "00"


def _bool_value(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    return bool(value)


def speaker_diarization_auto_enabled(settings: dict[str, Any] | None = None) -> bool:
    return _bool_value((settings or {}).get("speaker_diarization_auto_enabled", True), True)


def _default_speaker_name(idx: int) -> str:
    return f"화자 {idx}"


def _speaker_name_variants(idx: int) -> set[str]:
    return {
        "",
        _default_speaker_name(idx),
        f"화자{idx}",
    }


def _voice_dir(voice_dir: str | None = None) -> str:
    return str(voice_dir or config.VOICE_DATA_DIR)


def speaker_voice_files(idx: int, *, voice_dir: str | None = None) -> list[str]:
    pattern = os.path.join(_voice_dir(voice_dir), f"spk{int(idx)}_*.wav")
    return sorted(glob.glob(pattern))


def speaker_slot_record(
    settings: dict[str, Any] | None,
    idx: int,
    *,
    voice_dir: str | None = None,
) -> dict[str, Any]:
    data = dict(settings or {})
    index = int(idx)
    default_id = DEFAULT_SPEAKER_IDS.get(index, f"{index - 1:02d}")
    default_color = DEFAULT_SPEAKER_COLORS.get(index, "#FFFFFF")
    name = str(data.get(f"spk{index}_name", "") or _default_speaker_name(index)).strip()
    speaker_id = normalize_speaker_id(data.get(f"spk{index}_id", default_id))
    color = str(data.get(f"spk{index}_color", default_color) or default_color).strip() or default_color
    voice_disabled = _bool_value(data.get(f"spk{index}_voice_disabled", False), False)
    files = speaker_voice_files(index, voice_dir=voice_dir)
    file_basenames = [os.path.basename(path) for path in files]
    configured_voice = str(data.get(f"spk{index}_voice_file", "") or "").strip()
    primary_file = None
    if configured_voice:
        candidate = os.path.join(_voice_dir(voice_dir), configured_voice)
        if os.path.exists(candidate):
            primary_file = candidate
    if primary_file is None and files:
        primary_file = files[0]

    legacy_enabled = True if index == 1 else _bool_value(data.get(f"spk{index}_enabled", False), False)
    renamed = name not in _speaker_name_variants(index)
    customized = (
        renamed
        or speaker_id != default_id
        or str(color).lower() != str(default_color).lower()
    )
    visible = index == 1 or legacy_enabled or customized or bool(files)
    trained = bool(files) and not voice_disabled

    return {
        "index": index,
        "id": speaker_id,
        "name": name or _default_speaker_name(index),
        "color": color,
        "voice_disabled": voice_disabled,
        "voice_files": file_basenames,
        "primary_voice_file": os.path.basename(primary_file) if primary_file else "",
        "primary_voice_path": primary_file or "",
        "has_voice_files": bool(files),
        "legacy_enabled": legacy_enabled,
        "visible": visible,
        "trained": trained,
    }


def speaker_slot_records(
    settings: dict[str, Any] | None = None,
    *,
    voice_dir: str | None = None,
) -> list[dict[str, Any]]:
    return [
        speaker_slot_record(settings, idx, voice_dir=voice_dir)
        for idx in (1, 2, 3)
    ]


def visible_speaker_slots(
    settings: dict[str, Any] | None = None,
    *,
    voice_dir: str | None = None,
) -> list[dict[str, Any]]:
    return [row for row in speaker_slot_records(settings, voice_dir=voice_dir) if row.get("visible")]


def trained_speaker_profiles(
    settings: dict[str, Any] | None = None,
    *,
    voice_dir: str | None = None,
) -> list[dict[str, Any]]:
    return [row for row in speaker_slot_records(settings, voice_dir=voice_dir) if row.get("trained")]


def automatic_speaker_ceiling(
    settings: dict[str, Any] | None = None,
    *,
    voice_dir: str | None = None,
) -> int:
    if not speaker_diarization_auto_enabled(settings):
        return max(1, min(3, int((settings or {}).get("max_speakers", 1) or 1)))
    ceiling = 2
    for row in speaker_slot_records(settings, voice_dir=voice_dir):
        if row.get("index", 1) <= 1:
            continue
        if row.get("visible") or row.get("trained"):
            ceiling = max(ceiling, int(row.get("index", 1) or 1))
    return max(1, min(3, ceiling))


def materialize_automatic_speaker_settings(
    settings: dict[str, Any] | None = None,
    *,
    voice_dir: str | None = None,
) -> dict[str, Any]:
    out = dict(settings or {})
    out["speaker_diarization_auto_enabled"] = True
    out["min_speakers"] = 1
    out["max_speakers"] = 1

    for row in speaker_slot_records(out, voice_dir=voice_dir):
        idx = int(row.get("index", 1) or 1)
        out[f"spk{idx}_id"] = row.get("id", DEFAULT_SPEAKER_IDS.get(idx, "00"))
        out[f"spk{idx}_name"] = row.get("name", _default_speaker_name(idx))
        out[f"spk{idx}_color"] = row.get("color", DEFAULT_SPEAKER_COLORS.get(idx, "#FFFFFF"))
        out[f"spk{idx}_enabled"] = bool(row.get("visible")) if idx > 1 else True
        primary_file = str(row.get("primary_voice_file", "") or "").strip()
        if primary_file:
            out[f"spk{idx}_voice_file"] = primary_file
        else:
            out.pop(f"spk{idx}_voice_file", None)
    return out


__all__ = [
    "DEFAULT_SPEAKER_COLORS",
    "DEFAULT_SPEAKER_IDS",
    "automatic_speaker_ceiling",
    "materialize_automatic_speaker_settings",
    "normalize_speaker_id",
    "speaker_diarization_auto_enabled",
    "speaker_slot_record",
    "speaker_slot_records",
    "speaker_voice_files",
    "trained_speaker_profiles",
    "visible_speaker_slots",
]
