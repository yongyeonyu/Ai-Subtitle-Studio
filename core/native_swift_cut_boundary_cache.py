from __future__ import annotations

import os
from typing import Any

from core.cut_boundary_api import CUT_BOUNDARY_ALGORITHM_ID, CUT_BOUNDARY_ALGORITHM_VERSION, CUT_BOUNDARY_API_VERSION
from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime import config
from core.runtime.config import IS_MAC


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CUT_CACHE")


def cut_boundary_cache_settings_payload_via_swift(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _enabled():
        return None
    decoded = request_native_core_task(
        "cut_boundary_cache_settings_payload",
        {"settings": dict(settings or {})},
    )
    if not isinstance(decoded, dict):
        return None
    payload = decoded.get("settings_payload")
    return dict(payload) if isinstance(payload, dict) else None


def cut_boundary_cache_plan_via_swift(
    *,
    file_entries: list[dict[str, Any]],
    settings: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not _enabled():
        return None
    cache_root = os.path.join(config.OUTPUT_DIR, "cut_boundary_cache")
    decoded = request_native_core_task(
        "cut_boundary_cache_plan",
        {
            "files": [dict(row) for row in list(file_entries or []) if isinstance(row, dict)],
            "settings": dict(settings or {}),
            "cache_root": cache_root,
            "version": 7,
            "cut_boundary_api_version": CUT_BOUNDARY_API_VERSION,
            "cut_boundary_algorithm_version": CUT_BOUNDARY_ALGORITHM_VERSION,
            "cut_boundary_algorithm_id": CUT_BOUNDARY_ALGORITHM_ID,
        },
    )
    return decoded if isinstance(decoded, dict) else None


__all__ = [
    "cut_boundary_cache_plan_via_swift",
    "cut_boundary_cache_settings_payload_via_swift",
]
