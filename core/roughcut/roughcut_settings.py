# Version: 03.01.28
# Phase: PHASE2
from __future__ import annotations

from typing import Any

import config


def default_roughcut_settings() -> dict[str, Any]:
    """Return PAGE 3-B roughcut defaults without mutating global settings."""
    return dict(getattr(config, "DEFAULT_ROUGHCUT_SETTINGS", {}) or {})


def merge_roughcut_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = default_roughcut_settings()
    if isinstance(settings, dict):
        merged.update({key: value for key, value in settings.items() if key in merged})
    return merged


def roughcut_llm_enabled(settings: dict[str, Any] | None = None) -> bool:
    return bool(merge_roughcut_settings(settings).get("roughcut_llm_enabled", False))


__all__ = ["default_roughcut_settings", "merge_roughcut_settings", "roughcut_llm_enabled"]
