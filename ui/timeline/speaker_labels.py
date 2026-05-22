# Version: 03.02.04
# Phase: PHASE2
"""
Speaker label helpers for timeline rendering.
"""
from core.settings import load_settings
from core.speaker_profile_settings import (
    materialize_automatic_speaker_settings,
    normalize_speaker_id,
)


_SPEAKER_KEYS = (
    "spk1_id",
    "spk1_name",
    "spk1_color",
    "spk2_id",
    "spk2_name",
    "spk2_color",
    "spk2_voice_disabled",
    "spk2_voice_file",
    "spk3_id",
    "spk3_name",
    "spk3_color",
    "spk3_voice_disabled",
    "spk3_voice_file",
    "spk1_voice_disabled",
    "spk1_voice_file",
    "spk2_enabled",
    "spk3_enabled",
    "speaker_diarization_auto_enabled",
)


def current_speaker_settings(owner_settings: dict | None = None) -> dict:
    merged = dict(owner_settings or {})
    try:
        saved = load_settings()
    except Exception:
        saved = {}
    for key in _SPEAKER_KEYS:
        value = saved.get(key)
        if value not in (None, ""):
            merged[key] = value
    return materialize_automatic_speaker_settings(merged)


def speaker_name_for_id(settings: dict, raw, fallback_index: int = 1) -> str:
    spk = normalize_speaker_id(raw)
    mapping = {
        str(settings.get("spk1_id", "00")): str(settings.get("spk1_name", "") or "화자 1"),
        str(settings.get("spk2_id", "01")): str(settings.get("spk2_name", "") or "화자 2"),
        str(settings.get("spk3_id", "02")): str(settings.get("spk3_name", "") or "화자 3"),
    }
    if spk in mapping:
        return mapping[spk]
    return str(settings.get(f"spk{fallback_index}_name", "") or f"화자 {fallback_index}")


def speaker_color_for_id(settings: dict, raw, fallback_index: int = 1) -> str:
    spk = normalize_speaker_id(raw)
    mapping = {
        str(settings.get("spk1_id", "00")): str(settings.get("spk1_color", "#579DFF")),
        str(settings.get("spk2_id", "01")): str(settings.get("spk2_color", "#75C76B")),
        str(settings.get("spk3_id", "02")): str(settings.get("spk3_color", "#FF9F2F")),
    }
    if spk in mapping:
        return mapping[spk]
    return str(settings.get(f"spk{fallback_index}_color", "") or "#8E8E93")


def _speaker_ids_for_segment(segment: dict) -> list[str]:
    raw_values = list(segment.get("speaker_list", []) or [])
    primary = segment.get("speaker", segment.get("spk_id", segment.get("spk", None)))
    secondary = segment.get("speaker2", None)
    if primary not in (None, "") and not raw_values:
        raw_values.append(primary)
    elif primary not in (None, ""):
        raw_values.insert(0, primary)
    if secondary not in (None, ""):
        raw_values.append(secondary)

    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        spk = normalize_speaker_id(raw)
        if not spk or spk in seen:
            continue
        seen.add(spk)
        out.append(spk)
        if len(out) >= 2:
            break
    return out


def speaker_rows_for_segment(settings: dict, segment: dict) -> list[dict[str, str]]:
    ids = _speaker_ids_for_segment(segment)
    if ids:
        return [
            {
                "id": spk,
                "name": speaker_name_for_id(settings, spk, idx + 1),
                "color": speaker_color_for_id(settings, spk, idx + 1),
            }
            for idx, spk in enumerate(ids)
        ]

    explicit = str(segment.get("speaker_name", "") or "").strip()
    if explicit and explicit != "홍길동":
        return [{"id": "", "name": explicit, "color": speaker_color_for_id(settings, settings.get("spk1_id", "00"), 1)}]

    spk1 = str(settings.get("spk1_id", "00"))
    return [{"id": spk1, "name": speaker_name_for_id(settings, spk1, 1), "color": speaker_color_for_id(settings, spk1, 1)}]


def speaker_labels_for_segment(settings: dict, segment: dict) -> list[str]:
    return [row["name"] for row in speaker_rows_for_segment(settings, segment)]


def speaker_label_for_segment(settings: dict, segment: dict) -> str:
    return " / ".join(speaker_labels_for_segment(settings, segment))
