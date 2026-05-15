from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import Any

from core.native_json import dumps_json_bytes, json_default, loads_json_output
from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import KOREAN_FALSE_VALUES, env_bool as _env_bool, setting_bool as _setting_bool

_SNAPSHOT_CACHE: dict[str, Any] | None = None
_SNAPSHOT_CACHE_AT = 0.0
_SNAPSHOT_LOCK = threading.Lock()
_ALLOCATOR_LOCK = threading.Lock()
_ALLOCATOR_FUNCS: tuple[Any, Any] | None = None

def _enabled(settings: dict[str, Any] | None) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_NATIVE_MEMORY")
    if env is not None:
        return env
    return _setting_bool(
        (settings or {}).get("macos_native_memory_snapshot_enabled"),
        True,
        false_values=KOREAN_FALSE_VALUES,
        false_only_strings=True,
        empty_is_default=False,
    )


def clear_native_memory_snapshot_cache() -> None:
    global _SNAPSHOT_CACHE, _SNAPSHOT_CACHE_AT
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE = None
        _SNAPSHOT_CACHE_AT = 0.0


def native_memory_snapshot(
    settings: dict[str, Any] | None = None,
    *,
    max_age_sec: float = 1.0,
    timeout: float = 1.5,
) -> dict[str, Any] | None:
    global _SNAPSHOT_CACHE, _SNAPSHOT_CACHE_AT
    if not _enabled(settings):
        return None
    now = time.time()
    with _SNAPSHOT_LOCK:
        if _SNAPSHOT_CACHE is not None and (now - _SNAPSHOT_CACHE_AT) <= max(0.0, float(max_age_sec)):
            return dict(_SNAPSHOT_CACHE)

    cli = find_native_cli_path()
    if cli is None:
        return None
    payload = {
        "pid": os.getpid(),
        "settings": settings or {},
    }
    try:
        proc = subprocess.run(
            [str(cli), "native-memory-snapshot-json"],
            input=dumps_json_bytes(payload, compact=True, default=json_default),
            check=True,
            capture_output=True,
            timeout=max(0.25, float(timeout)),
        )
        decoded = loads_json_output(proc.stdout, default={})
    except Exception:
        return None
    if not isinstance(decoded, dict) or decoded.get("error"):
        return None
    if not decoded.get("memory_bytes") or "available_memory_bytes" not in decoded:
        return None
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE = dict(decoded)
        _SNAPSHOT_CACHE_AT = time.time()
    return dict(decoded)


def native_allocator_pressure_relief(
    settings: dict[str, Any] | None = None,
    *,
    stage: str = "warning",
    goal_bytes: int | None = None,
) -> dict[str, Any]:
    """Ask macOS malloc zones to release cached pages back to the OS.

    This is intentionally conservative: it never touches Python objects, only
    libSystem's allocator caches. It is most useful after STT/VAD/LLM stages
    release large temporary arrays but before macOS notices the pressure by
    itself.
    """
    settings = dict(settings or {})
    if not _setting_bool(
        settings.get("macos_allocator_pressure_relief_enabled"),
        True,
        false_values=KOREAN_FALSE_VALUES,
        false_only_strings=True,
        empty_is_default=False,
    ):
        return {"ok": False, "reason": "disabled", "released_bytes": 0}
    if not IS_MAC:
        return {"ok": False, "reason": "not_macos", "released_bytes": 0}
    try:
        import ctypes
    except Exception as exc:
        return {"ok": False, "reason": f"ctypes_unavailable:{exc}", "released_bytes": 0}

    stage_text = str(stage or "warning").strip().lower()
    if goal_bytes is None:
        default_mb = 256 if stage_text == "critical" else 64
        key = (
            "macos_allocator_pressure_relief_critical_mb"
            if stage_text == "critical"
            else "macos_allocator_pressure_relief_warning_mb"
        )
        goal_bytes = int(float(settings.get(key, default_mb) or default_mb) * 1024 * 1024)
    goal_bytes = max(1, int(goal_bytes or 1))

    global _ALLOCATOR_FUNCS
    with _ALLOCATOR_LOCK:
        try:
            if _ALLOCATOR_FUNCS is None:
                lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
                malloc_default_zone = lib.malloc_default_zone
                malloc_default_zone.argtypes = []
                malloc_default_zone.restype = ctypes.c_void_p
                pressure_relief = lib.malloc_zone_pressure_relief
                pressure_relief.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
                pressure_relief.restype = ctypes.c_size_t
                _ALLOCATOR_FUNCS = (malloc_default_zone, pressure_relief)
            malloc_default_zone, pressure_relief = _ALLOCATOR_FUNCS
            zone = malloc_default_zone()
            if not zone:
                return {"ok": False, "reason": "missing_default_zone", "released_bytes": 0}
            released = int(pressure_relief(zone, goal_bytes) or 0)
        except Exception as exc:
            return {"ok": False, "reason": f"native_allocator_failed:{exc}", "released_bytes": 0}
    return {
        "ok": True,
        "stage": stage_text,
        "goal_bytes": goal_bytes,
        "released_bytes": max(0, released),
    }


__all__ = [
    "clear_native_memory_snapshot_cache",
    "native_allocator_pressure_relief",
    "native_memory_snapshot",
]
