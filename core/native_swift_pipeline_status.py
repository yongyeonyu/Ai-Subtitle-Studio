from __future__ import annotations

import os
from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import env_bool, positive_int


def _enabled(status_text: object) -> bool:
    blob = str(status_text or "")
    if not blob.strip() or not IS_MAC:
        return False

    env = env_bool("AI_SUBTITLE_STUDIO_SWIFT_PIPELINE_STATUS")
    if env is False:
        return False
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_PIPELINE_STATUS"):
        return False
    if env is True:
        return True

    min_chars = positive_int(os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_PIPELINE_STATUS_MIN_CHARS"), 180)
    min_lines = positive_int(os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_PIPELINE_STATUS_MIN_LINES"), 3)
    line_count = blob.count("\n") + 1
    return len(blob) >= min_chars or line_count >= min_lines or "<br" in blob.casefold()


def summarize_pipeline_status_via_swift(
    status_text: object,
    *,
    stt_ensemble_enabled: bool = False,
) -> dict[str, Any] | None:
    if not _enabled(status_text):
        return None

    decoded = request_native_core_task(
        "pipeline_status_summary",
        {
            "status_text": str(status_text or ""),
            "stt_ensemble_enabled": bool(stt_ensemble_enabled),
        },
    )
    if not isinstance(decoded, dict):
        return None

    latest_keys = decoded.get("keys")
    all_keys = decoded.get("all_keys")
    if not isinstance(latest_keys, list) or not isinstance(all_keys, list):
        return None

    return {
        "keys": [str(key) for key in latest_keys if str(key or "").strip()],
        "all_keys": [str(key) for key in all_keys if str(key or "").strip()],
        "label": str(decoded.get("label", "") or ""),
        "active": bool(decoded.get("active", bool(latest_keys))),
    }


__all__ = ["summarize_pipeline_status_via_swift"]
