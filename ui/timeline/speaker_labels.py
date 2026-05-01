# Version: 03.02.04
# Phase: PHASE2
"""
Speaker label helpers for timeline rendering.
"""
from core.settings import load_settings


_SPEAKER_KEYS = (
    "spk1_id",
    "spk1_name",
    "spk1_color",
    "spk2_id",
    "spk2_name",
    "spk2_color",
    "spk3_id",
    "spk3_name",
    "spk3_color",
    "spk2_enabled",
    "spk3_enabled",
    "min_speakers",
    "max_speakers",
)


def normalize_speaker_id(raw) -> str:
    spk = str(raw or "").strip()
    if spk.startswith("SPEAKER_"):
        spk = spk.replace("SPEAKER_", "", 1)
    return spk


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
    return merged


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


def speaker_labels_for_segment(settings: dict, segment: dict) -> list[str]:
    spk_list = list(segment.get("speaker_list", []) or [])
    if len(spk_list) > 1:
        return [
            speaker_name_for_id(settings, spk, idx + 1)
            for idx, spk in enumerate(spk_list)
        ]

    raw = segment.get("speaker", segment.get("spk_id", None))
    if raw not in (None, ""):
        return [speaker_name_for_id(settings, raw, 1)]

    explicit = str(segment.get("speaker_name", "") or "").strip()
    if explicit and explicit != "홍길동":
        return [explicit]

    return [speaker_name_for_id(settings, settings.get("spk1_id", "00"), 1)]


def speaker_label_for_segment(settings: dict, segment: dict) -> str:
    return " / ".join(speaker_labels_for_segment(settings, segment))
