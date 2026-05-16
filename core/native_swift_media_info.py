from __future__ import annotations

from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_MEDIA_INFO")


def normalize_probe_json_via_swift(probe_json: str) -> dict[str, Any] | None:
    if not _enabled():
        return None
    decoded = request_native_core_task(
        "media_probe_normalize_json",
        {"probe_json": str(probe_json or "")},
    )
    if not isinstance(decoded, dict):
        return None
    result = decoded.get("result")
    return dict(result) if isinstance(result, dict) else None


__all__ = ["normalize_probe_json_via_swift"]
