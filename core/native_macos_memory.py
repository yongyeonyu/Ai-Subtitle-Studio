from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any

from core.native_swift_subtitle import find_native_cli_path
from core.runtime.config import IS_MAC

_SNAPSHOT_CACHE: dict[str, Any] | None = None
_SNAPSHOT_CACHE_AT = 0.0
_SNAPSHOT_LOCK = threading.Lock()


def _setting_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() not in {"0", "false", "off", "no", "사용 안함", "끔"}
    return bool(value)


def _env_bool(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    text = value.strip().casefold()
    if text in {"1", "true", "on", "yes"}:
        return True
    if text in {"0", "false", "off", "no"}:
        return False
    return None


def _enabled(settings: dict[str, Any] | None) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_NATIVE_MEMORY")
    if env is not None:
        return env
    return _setting_bool((settings or {}).get("macos_native_memory_snapshot_enabled"), True)


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


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
            input=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default).encode("utf-8"),
            check=True,
            capture_output=True,
            timeout=max(0.25, float(timeout)),
        )
        decoded = json.loads(proc.stdout.decode("utf-8") or "{}")
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


__all__ = ["clear_native_memory_snapshot_cache", "native_memory_snapshot"]
