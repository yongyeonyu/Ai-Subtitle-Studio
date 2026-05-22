from __future__ import annotations

import os
import threading
import time
from typing import Any

from core.native_json import dumps_json_text, json_default
from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import KOREAN_FALSE_VALUES, env_bool as _env_bool, setting_bool as _setting_bool

_CACHE_LOCK = threading.Lock()
_CACHE_KEY = ""
_CACHE_AT = 0.0
_CACHE_VALUE: dict[str, Any] | None = None


def _resource_priority_for_task(task: str) -> int:
    key = str(task or "").strip().lower()
    priorities = {
        "ui": 120,
        "timeline": 115,
        "cut_boundary": 110,
        "cut_pioneer": 110,
        "cut_follower": 105,
        "stt": 100,
        "stt1": 100,
        "stt_window": 96,
        "stt_precision": 96,
        "stt2": 90,
        "subtitle": 80,
        "subtitle_llm": 80,
        "roughcut": 45,
        "roughcut_llm": 45,
        "background": 10,
    }
    return int(priorities.get(key, 50))


def _request_with_priority(item: dict[str, Any]) -> dict[str, Any]:
    request = dict(item or {})
    if "priority" not in request:
        request["priority"] = _resource_priority_for_task(str(request.get("task") or "worker"))
    return request


def _enabled(settings: dict[str, Any] | None = None) -> bool:
    if not IS_MAC:
        return False
    env = _env_bool("AI_SUBTITLE_STUDIO_NATIVE_RESOURCE_ALLOCATOR")
    if env is not None:
        return env
    data = dict(settings or {})
    if not _setting_bool(
        data.get("macos_native_resource_allocator_enabled"),
        True,
        false_values=KOREAN_FALSE_VALUES,
        false_only_strings=True,
        empty_is_default=False,
    ):
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_RESOURCE_ALLOCATOR")


def clear_native_resource_allocation_cache() -> None:
    global _CACHE_AT, _CACHE_KEY, _CACHE_VALUE
    with _CACHE_LOCK:
        _CACHE_AT = 0.0
        _CACHE_KEY = ""
        _CACHE_VALUE = None


def native_resource_allocation(
    settings: dict[str, Any] | None = None,
    *,
    active_labels: list[str] | tuple[str, ...] | None = None,
    requests: list[dict[str, Any]] | None = None,
    memory: dict[str, Any] | None = None,
    topology: dict[str, Any] | None = None,
    previous_allocation: dict[str, Any] | None = None,
    max_age_sec: float = 0.2,
) -> dict[str, Any] | None:
    """Return a Swift-native live resource allocation plan.

    The Swift side owns the cheap Apple-core and memory budgeting decision. This
    wrapper keeps only a tiny sub-second cache so frequent UI/resource polling
    does not spawn extra work.
    """
    global _CACHE_AT, _CACHE_KEY, _CACHE_VALUE
    data = dict(settings or {})
    if not _enabled(data):
        return None
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "settings": data,
        "active_labels": [str(label or "").strip().lower() for label in list(active_labels or []) if str(label or "").strip()],
    }
    if requests:
        payload["requests"] = [_request_with_priority(item) for item in requests if isinstance(item, dict)]
    if memory:
        payload["memory"] = dict(memory)
    if topology:
        payload["topology"] = dict(topology)
    if previous_allocation:
        payload["previous_allocation"] = dict(previous_allocation)

    try:
        cache_key = dumps_json_text(payload, compact=True, default=json_default)
    except Exception:
        cache_key = str(sorted(payload.keys()))
    now = time.time()
    with _CACHE_LOCK:
        if _CACHE_VALUE is not None and cache_key == _CACHE_KEY and (now - _CACHE_AT) <= max(0.0, float(max_age_sec)):
            return dict(_CACHE_VALUE)

    decoded = request_native_core_task("native_resource_allocation", payload)
    if not isinstance(decoded, dict) or not decoded.get("ok"):
        return None
    with _CACHE_LOCK:
        _CACHE_KEY = cache_key
        _CACHE_AT = time.time()
        _CACHE_VALUE = dict(decoded)
    return dict(decoded)


def native_task_allocation(
    task: str,
    *,
    settings: dict[str, Any] | None = None,
    workload: int = 1,
    requested_workers: int | None = None,
    minimum: int = 1,
    maximum: int | None = None,
    active_labels: list[str] | tuple[str, ...] | None = None,
    previous_allocation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    request = {
        "task": str(task or "worker"),
        "workload": max(0, int(workload or 0)),
        "minimum": max(0, int(minimum or 0)),
    }
    if requested_workers is not None:
        request["requested_workers"] = max(0, int(requested_workers or 0))
    if maximum is not None:
        request["maximum"] = max(0, int(maximum or 0))
    request = _request_with_priority(request)
    plan = native_resource_allocation(
        settings,
        active_labels=active_labels,
        requests=[request],
        previous_allocation=previous_allocation,
    )
    allocations = dict((plan or {}).get("allocations") or {})
    item = allocations.get(str(task or "worker").strip().lower())
    return dict(item) if isinstance(item, dict) else None


__all__ = [
    "clear_native_resource_allocation_cache",
    "native_resource_allocation",
    "native_task_allocation",
]
