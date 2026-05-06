from __future__ import annotations

from pathlib import Path
from typing import Any

from core.personalization.lora_retrieval_config import RUNTIME_SETTING_KEYS as _RUNTIME_SETTING_KEYS
from core.personalization.lora_runtime_policy import (
    LORA_POLICY_OFF,
    lora_policy_label_for_quality,
    lora_policy_mode_for_quality,
    lora_quality_key_from_settings,
    lora_runtime_setting_keys_for_quality,
    lora_uses_full_stt_ensemble,
    lora_uses_stt1_only,
)
from core.personalization.lora_store_common import read_json
from core.personalization.lora_storage import (
    load_best_settings,
    load_learned_rules,
    personalization_path_lookup_keys,
    store_paths,
)
from core.personalization.lora_vector_retriever import retrieve_lora_context, runtime_settings_from_retrieved_items
from core.runtime import config
from core.settings import load_settings


def _runtime_quality_key(base_settings: dict[str, Any] | None = None) -> str:
    if isinstance(base_settings, dict) and (
        str(base_settings.get("stt_quality_preset") or "").strip()
        or str(base_settings.get("auto_start_mode") or "").strip()
    ):
        return lora_quality_key_from_settings(base_settings)
    try:
        return lora_quality_key_from_settings(load_settings())
    except Exception:
        return "precise"


def _finalize_policy_override(override: dict[str, Any], quality_key: str) -> dict[str, Any]:
    allowed_keys = lora_runtime_setting_keys_for_quality(quality_key, _RUNTIME_SETTING_KEYS)
    filtered = {
        key: value
        for key, value in dict(override or {}).items()
        if key in allowed_keys and value not in (None, "")
    }
    if lora_uses_stt1_only(quality_key):
        filtered["stt_ensemble_enabled"] = False
    elif lora_uses_full_stt_ensemble(quality_key):
        filtered["stt_ensemble_enabled"] = True
        filtered["stt_quality_preset"] = "precise"
    return filtered


def _runtime_model_exists(model_value: Any) -> bool:
    text = str(model_value or "").strip()
    if not text:
        return False
    if text.lower().startswith("coreml:"):
        return True
    return Path(text).expanduser().exists()


def _stt1_whisper_adapter_override(
    retrieved_items: list[dict[str, Any]],
    *,
    store_dir: str | None = None,
) -> dict[str, Any]:
    try:
        manifest = read_json(store_paths(store_dir)["stt1_whisper_adapter_runtime_manifest"], {})
    except Exception:
        return {}
    if not isinstance(manifest, dict) or not bool(manifest.get("runtime_ready")):
        return {}

    dataset_stats = dict(manifest.get("dataset_stats") or {})
    activation_policy = dict(manifest.get("activation_policy") or {})
    usable_rows = int(dataset_stats.get("usable_training_rows", 0) or 0)
    min_rows = int(activation_policy.get("minimum_truth_rows", 24) or 24)
    if usable_rows < min_rows:
        return {}

    support_score = max(
        float(item.get("retrieval_score", 0.0) or 0.0)
        for item in list(retrieved_items or [])
        if isinstance(item, dict)
    ) if retrieved_items else 0.0
    min_support = float(activation_policy.get("minimum_retrieval_score", 28.0) or 28.0)
    allow_global_fallback = bool(activation_policy.get("allow_global_fallback", True))
    if support_score < min_support and not allow_global_fallback:
        return {}

    candidate_key = "mac" if bool(config.IS_MAC) else "windows"
    runtime_candidates = dict(manifest.get("runtime_candidates") or {})
    candidate = dict(runtime_candidates.get(candidate_key) or {})
    if not bool(candidate.get("ready")):
        candidate = dict(runtime_candidates.get("portable") or {})
    model_value = str(candidate.get("selected_whisper_model") or "").strip()
    if not _runtime_model_exists(model_value):
        return {}
    return {"selected_whisper_model": model_value}


def personalization_settings_override_for_media(
    media_path: str = "",
    *,
    media_id: str = "",
    store_dir: str | None = None,
    base_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality_key = _runtime_quality_key(base_settings)
    if lora_policy_mode_for_quality(quality_key) == LORA_POLICY_OFF:
        return _finalize_policy_override({}, quality_key)

    best_settings = load_best_settings(store_dir)
    override: dict[str, Any] = dict(best_settings.get("global_recommended_defaults") or {})
    media_key = str(media_id or "").strip()
    path_keys = personalization_path_lookup_keys(media_path)
    exact_match = False
    retrieved_items: list[dict[str, Any]] = []

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
            settings={"stt_quality_preset": quality_key},
            store_dir=store_dir,
            limit=12,
            per_kind=4,
            kinds=("setting_trials", "best_settings", "audio_preset_lora", "multimodal_lora_context"),
            rebuild_if_stale=False,
        )
        retrieved_items = list(retrieved.get("items") or [])
        retrieved_override = runtime_settings_from_retrieved_items(retrieved_items, min_score=28.0)
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

    try:
        adapter_override = _stt1_whisper_adapter_override(retrieved_items, store_dir=store_dir)
        if exact_match:
            for key, value in adapter_override.items():
                override.setdefault(key, value)
        else:
            override.update(adapter_override)
    except Exception:
        pass

    return _finalize_policy_override(override, quality_key)


def merged_runtime_override(
    base_override: dict[str, Any] | None,
    media_path: str = "",
    *,
    media_id: str = "",
    store_dir: str | None = None,
) -> dict[str, Any]:
    merged = dict(base_override or {})
    merged.update(
        personalization_settings_override_for_media(
            media_path,
            media_id=media_id,
            store_dir=store_dir,
            base_settings=merged,
        )
    )
    return merged


__all__ = [
    "lora_policy_label_for_quality",
    "merged_runtime_override",
    "personalization_settings_override_for_media",
]
