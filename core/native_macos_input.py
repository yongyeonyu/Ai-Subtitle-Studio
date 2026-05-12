from __future__ import annotations

import threading
import time
from typing import Any

from core.native_swift_subtitle import request_native_core_task
from core.runtime.config import IS_MAC

_SNAPSHOT_CACHE: dict[str, Any] | None = None
_SNAPSHOT_CACHE_AT = 0.0
_SNAPSHOT_LOCK = threading.Lock()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def clear_native_input_activity_cache() -> None:
    global _SNAPSHOT_CACHE, _SNAPSHOT_CACHE_AT
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE = None
        _SNAPSHOT_CACHE_AT = 0.0


def native_input_activity_snapshot(
    *,
    recent_threshold_sec: float = 0.25,
    max_age_sec: float = 0.05,
) -> dict[str, Any] | None:
    """Return a Swift-native macOS keyboard/mouse activity snapshot."""
    global _SNAPSHOT_CACHE, _SNAPSHOT_CACHE_AT
    if not IS_MAC:
        return None
    now = time.monotonic()
    with _SNAPSHOT_LOCK:
        if _SNAPSHOT_CACHE is not None and (now - _SNAPSHOT_CACHE_AT) <= max(0.0, float(max_age_sec)):
            return dict(_SNAPSHOT_CACHE)
    payload = request_native_core_task(
        "input_activity_snapshot",
        {"recent_threshold_sec": max(0.02, float(recent_threshold_sec))},
    )
    if not isinstance(payload, dict) or payload.get("error"):
        return None
    if str(payload.get("source") or "") != "swift_cgevent_source":
        return None
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE = dict(payload)
        _SNAPSHOT_CACHE_AT = time.monotonic()
    return dict(payload)


def recent_native_user_input_detected(*, threshold_sec: float = 0.25) -> tuple[bool, dict[str, Any]]:
    snapshot = native_input_activity_snapshot(recent_threshold_sec=threshold_sec, max_age_sec=0.02)
    if not isinstance(snapshot, dict):
        return False, {}
    if not bool(snapshot.get("ok", False)):
        return False, snapshot
    if bool(snapshot.get("recent", False)):
        return True, snapshot
    age_sec = _safe_float(snapshot.get("age_sec"), default=9999.0)
    return age_sec <= max(0.0, float(threshold_sec)), snapshot


__all__ = [
    "clear_native_input_activity_cache",
    "native_input_activity_snapshot",
    "recent_native_user_input_detected",
]
