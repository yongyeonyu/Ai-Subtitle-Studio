from __future__ import annotations

from pathlib import Path
from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_RUNTIME_CACHE")


def prune_runtime_disk_caches_via_swift(
    paths: list[str | Path],
    *,
    target_total_bytes: int,
) -> dict[str, Any] | None:
    if not _enabled() or not paths:
        return None

    decoded = request_native_core_task(
        "runtime_disk_cache_prune",
        {
            "paths": [str(Path(path)) for path in paths],
            "target_total_bytes": max(0, int(target_total_bytes or 0)),
        },
    )
    if not isinstance(decoded, dict) or not decoded.get("used_native"):
        return None

    required = ("removed_files", "removed_bytes", "remaining_bytes", "target_total_bytes")
    if any(key not in decoded for key in required):
        return None

    return {
        "removed_files": max(0, int(decoded.get("removed_files", 0) or 0)),
        "removed_bytes": max(0, int(decoded.get("removed_bytes", 0) or 0)),
        "remaining_bytes": max(0, int(decoded.get("remaining_bytes", 0) or 0)),
        "target_total_bytes": max(0, int(decoded.get("target_total_bytes", 0) or 0)),
        "used_native": True,
    }


__all__ = ["prune_runtime_disk_caches_via_swift"]
