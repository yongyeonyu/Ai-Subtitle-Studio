from __future__ import annotations

from pathlib import Path
from typing import Any

from core.personalization.lora_models import iso_now
from core.personalization.lora_store_common import read_json, write_json
from core.runtime import config
from core.settings_profiles import LORA_AUTO_MANAGED_SETTING_KEYS, materialize_user_settings


AUTOPILOT_METADATA_KEY = "_lora_user_settings_autopilot"


def _dataset_dir_for_store(store_dir: str | Path | None = None) -> Path:
    if store_dir is None:
        return Path(config.DATASET_DIR)
    root = Path(store_dir).expanduser()
    if root.name == "lora_personalization":
        return root.parent
    return root


def _settings_path_for_store(store_dir: str | Path | None = None) -> Path:
    return _dataset_dir_for_store(store_dir) / "user_settings.json"


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        return abs(_as_float(left, 0.0) - _as_float(right, 0.0)) < 0.0005
    return left == right


def _numeric_blend(current: Any, learned: Any, blend: float) -> Any:
    current_float = _as_float(current, _as_float(learned, 0.0))
    learned_float = _as_float(learned, current_float)
    merged = current_float + (learned_float - current_float) * max(0.0, min(1.0, blend))
    if isinstance(current, int) and not isinstance(current, bool):
        return int(round(merged))
    return round(merged, 3)


def _merge_setting_value(current: Any, learned: Any, *, score: float, settings: dict[str, Any]) -> tuple[bool, Any, str]:
    if learned in (None, ""):
        return False, current, "empty"
    categorical_min = _as_float(settings.get("lora_user_settings_auto_apply_categorical_min_score"), 92.0)
    blend = _as_float(settings.get("lora_user_settings_auto_apply_blend"), 0.35)
    if isinstance(current, bool) or isinstance(learned, bool):
        if score < categorical_min:
            return False, current, "low_categorical_score"
        return True, bool(learned), "direct"
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        return True, _numeric_blend(current, learned, blend), "blend"
    if isinstance(learned, (int, float)) and not isinstance(learned, bool):
        return True, _numeric_blend(current, learned, blend), "blend"
    if score < categorical_min:
        return False, current, "low_categorical_score"
    return True, learned, "direct"


def apply_lora_user_settings_autopilot(
    learned_config: dict[str, Any],
    *,
    score: float,
    media_id: str = "",
    media_path: str = "",
    subtitle_path: str = "",
    reason: str = "",
    source: str = "setting_optimizer",
    store_dir: str | Path | None = None,
    base_settings: dict[str, Any] | None = None,
    exploration_bundle_id: str = "",
) -> dict[str, Any]:
    settings_path = _settings_path_for_store(store_dir)
    dataset_dir = str(settings_path.parent)
    disk_settings = read_json(settings_path, {})
    if not isinstance(disk_settings, dict):
        disk_settings = {}
    seed_settings = dict(base_settings or {})
    seed_settings.update(disk_settings)
    current = materialize_user_settings(seed_settings, dataset_dir=dataset_dir)

    if not _as_bool(current.get("lora_user_settings_autopilot_enabled"), True):
        return {
            "status": "disabled",
            "settings_path": str(settings_path),
            "applied_keys": [],
            "score": round(float(score or 0.0), 2),
        }

    min_score = _as_float(current.get("lora_user_settings_auto_apply_min_score"), 88.0)
    score_value = round(float(score or 0.0), 2)
    if score_value < min_score:
        return {
            "status": "low_score",
            "settings_path": str(settings_path),
            "applied_keys": [],
            "score": score_value,
            "min_score": min_score,
        }

    next_settings = dict(current)
    applied: dict[str, dict[str, Any]] = {}
    skipped: dict[str, str] = {}
    for key, learned_value in dict(learned_config or {}).items():
        if key not in LORA_AUTO_MANAGED_SETTING_KEYS:
            continue
        should_apply, merged_value, mode = _merge_setting_value(
            next_settings.get(key),
            learned_value,
            score=score_value,
            settings=current,
        )
        if not should_apply:
            skipped[key] = mode
            continue
        if _same_value(next_settings.get(key), merged_value):
            continue
        previous = next_settings.get(key)
        next_settings[key] = merged_value
        applied[key] = {
            "previous": previous,
            "learned": learned_value,
            "stored": merged_value,
            "mode": mode,
        }

    metadata = {
        "enabled": True,
        "updated_at": iso_now(),
        "source": source,
        "media_id": str(media_id or ""),
        "media_path": str(media_path or ""),
        "subtitle_path": str(subtitle_path or ""),
        "score": score_value,
        "min_score": min_score,
        "reason": str(reason or ""),
        "exploration_bundle_id": str(exploration_bundle_id or ""),
        "applied_keys": applied,
        "skipped_keys": skipped,
    }
    next_settings[AUTOPILOT_METADATA_KEY] = metadata
    materialized = materialize_user_settings(next_settings, dataset_dir=dataset_dir)
    write_json(settings_path, materialized)
    return {
        "status": "applied" if applied else "metadata_only",
        "settings_path": str(settings_path),
        "applied_keys": sorted(applied),
        "score": score_value,
        "metadata": metadata,
    }


__all__ = [
    "AUTOPILOT_METADATA_KEY",
    "apply_lora_user_settings_autopilot",
]
