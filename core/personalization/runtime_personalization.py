from __future__ import annotations

from typing import Any

from core.personalization.lora_retrieval_config import RUNTIME_SETTING_KEYS as _RUNTIME_SETTING_KEYS
from core.personalization.lora_storage import (
    load_best_settings,
    load_learned_rules,
    personalization_path_lookup_keys,
)
from core.personalization.lora_vector_retriever import retrieve_lora_context, runtime_settings_from_retrieved_items


def personalization_settings_override_for_media(
    media_path: str = "",
    *,
    media_id: str = "",
    store_dir: str | None = None,
) -> dict[str, Any]:
    best_settings = load_best_settings(store_dir)
    override: dict[str, Any] = dict(best_settings.get("global_recommended_defaults") or {})
    media_key = str(media_id or "").strip()
    path_keys = personalization_path_lookup_keys(media_path)
    exact_match = False

    if media_key and media_key in dict(best_settings.get("by_media_id") or {}):
        payload = dict((best_settings.get("by_media_id") or {}).get(media_key) or {})
        override.update(dict(payload.get("config") or {}))
        exact_match = True

    if path_keys:
        by_path = dict(best_settings.get("by_media_path") or {})
        matched_payload = None
        for path_key in path_keys:
            if path_key in by_path:
                matched_payload = dict(by_path.get(path_key) or {})
                break
        if matched_payload is None:
            for payload in dict(best_settings.get("by_media_id") or {}).values():
                payload = dict(payload or {})
                stored_keys = personalization_path_lookup_keys(payload.get("media_path") or "")
                if any(path_key in stored_keys for path_key in path_keys):
                    matched_payload = payload
                    break
        if matched_payload is not None:
            override.update(dict(matched_payload.get("config") or {}))
            exact_match = True

    try:
        retrieved = retrieve_lora_context(
            f"{media_key} {media_path}",
            media_path=media_path,
            media_id=media_key,
            store_dir=store_dir,
            limit=12,
            per_kind=4,
            kinds=("setting_trials", "best_settings", "audio_preset_lora", "multimodal_lora_context"),
        )
        retrieved_override = runtime_settings_from_retrieved_items(list(retrieved.get("items") or []), min_score=28.0)
        if exact_match:
            for key, value in retrieved_override.items():
                override.setdefault(key, value)
        else:
            override.update(retrieved_override)
    except Exception:
        pass

    try:
        learned_split = load_learned_rules("split", store_dir)
        summary = dict((learned_split.get("metadata") or {}).get("summary") or {})
        if "split_length_threshold" not in override and summary.get("char_count_p50"):
            override["split_length_threshold"] = max(12, min(24, int(round(float(summary["char_count_p50"])))))
        if "sub_max_cps" not in override and summary.get("cps_p90"):
            override["sub_max_cps"] = max(10, min(18, int(round(float(summary["cps_p90"])))))
    except Exception:
        pass

    return {key: value for key, value in override.items() if key in _RUNTIME_SETTING_KEYS and value not in (None, "")}


def merged_runtime_override(
    base_override: dict[str, Any] | None,
    media_path: str = "",
    *,
    media_id: str = "",
    store_dir: str | None = None,
) -> dict[str, Any]:
    merged = dict(base_override or {})
    merged.update(personalization_settings_override_for_media(media_path, media_id=media_id, store_dir=store_dir))
    return merged


__all__ = [
    "merged_runtime_override",
    "personalization_settings_override_for_media",
]
