from __future__ import annotations

import os
import platform
import sys
from typing import Any

from core.runtime.logger import get_logger


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "enable"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "disable", "끄기", "끔"}
_ACCEL_LOGGED: set[tuple[str, str]] = set()


def _setting_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _torch_module():
    return sys.modules.get("torch")


def allow_mps_empty_cache() -> bool:
    value = os.environ.get("AI_SUBTITLE_STUDIO_ENABLE_MPS_EMPTY_CACHE")
    if value is None:
        return platform.system() != "Darwin"
    return _setting_bool(value, False)


def torch_gpu_acceleration_enabled(settings: dict[str, Any] | None = None) -> bool:
    loaded = dict(settings or {})
    if not _setting_bool(loaded.get("runtime_hardware_acceleration_enabled"), True):
        return False
    return _setting_bool(loaded.get("audio_torch_gpu_enabled"), True)


def torch_device_memory_snapshot(device_name: str, *, estimated_bytes: int = 0) -> dict[str, Any]:
    device = str(device_name or "cpu").strip().lower() or "cpu"
    snapshot = {
        "device": device,
        "available": device != "cpu",
        "allocated_bytes": 0,
        "driver_bytes": 0,
        "free_bytes": 0,
        "total_bytes": 0,
        "recommended_max_bytes": 0,
        "pressure_ratio": 0.0,
        "future_pressure_ratio": 0.0,
    }
    torch_mod = _torch_module()
    if torch_mod is None or device == "cpu":
        return snapshot
    try:
        if device == "mps":
            mps_mod = getattr(torch_mod, "mps", None)
            if mps_mod is None:
                snapshot["available"] = False
                return snapshot
            allocated = _safe_int(getattr(mps_mod, "current_allocated_memory", lambda: 0)())
            driver = _safe_int(getattr(mps_mod, "driver_allocated_memory", lambda: 0)())
            recommended = _safe_int(getattr(mps_mod, "recommended_max_memory", lambda: 0)())
            used = max(allocated, driver)
            snapshot.update(
                {
                    "allocated_bytes": allocated,
                    "driver_bytes": driver,
                    "recommended_max_bytes": recommended,
                    "pressure_ratio": round((used / float(recommended)) if recommended > 0 else 0.0, 4),
                    "future_pressure_ratio": round(
                        ((used + max(0, int(estimated_bytes or 0))) / float(recommended)) if recommended > 0 else 0.0,
                        4,
                    ),
                }
            )
            return snapshot
        if device == "cuda" and hasattr(torch_mod, "cuda") and torch_mod.cuda.is_available():
            free_bytes, total_bytes = getattr(torch_mod.cuda, "mem_get_info", lambda: (0, 0))()
            allocated = _safe_int(getattr(torch_mod.cuda, "memory_allocated", lambda: 0)())
            total = _safe_int(total_bytes)
            used = max(allocated, total - _safe_int(free_bytes))
            snapshot.update(
                {
                    "allocated_bytes": allocated,
                    "free_bytes": _safe_int(free_bytes),
                    "total_bytes": total,
                    "recommended_max_bytes": total,
                    "pressure_ratio": round((used / float(total)) if total > 0 else 0.0, 4),
                    "future_pressure_ratio": round(
                        ((used + max(0, int(estimated_bytes or 0))) / float(total)) if total > 0 else 0.0,
                        4,
                    ),
                }
            )
            return snapshot
    except Exception:
        pass
    return snapshot


def torch_execution_backends(
    settings: dict[str, Any] | None = None,
    *,
    task: str = "torch",
    estimated_bytes: int = 0,
) -> list[str]:
    del task
    if not torch_gpu_acceleration_enabled(settings):
        return ["cpu"]
    try:
        torch_mod = _torch_module()
        if torch_mod is None:
            return ["cpu"]
        ordered: list[str] = []
        if getattr(getattr(torch_mod, "backends", None), "mps", None) and torch_mod.backends.mps.is_available():
            ordered.append("mps")
        if hasattr(torch_mod, "cuda") and torch_mod.cuda.is_available() and "cuda" not in ordered:
            ordered.append("cuda")
        if not ordered:
            return ["cpu"]
        primary = ordered[0]
        device_snapshot = torch_device_memory_snapshot(primary, estimated_bytes=estimated_bytes)
        future_ratio = float(
            device_snapshot.get("future_pressure_ratio")
            or device_snapshot.get("pressure_ratio")
            or 0.0
        )
        if future_ratio >= 0.92:
            return ["cpu", *ordered]
        return [*ordered, "cpu"]
    except Exception:
        return ["cpu"]


def preferred_torch_device_name(
    settings: dict[str, Any] | None = None,
    *,
    task: str = "torch",
    estimated_bytes: int = 0,
) -> str:
    return str(torch_execution_backends(settings, task=task, estimated_bytes=estimated_bytes)[0] or "cpu")


def torch_acceleration_snapshot(
    settings: dict[str, Any] | None = None,
    *,
    task: str = "torch",
    estimated_bytes: int = 0,
) -> dict[str, Any]:
    ordered = torch_execution_backends(settings, task=task, estimated_bytes=estimated_bytes)
    non_cpu = [item for item in ordered if item != "cpu"]
    return {
        "enabled": torch_gpu_acceleration_enabled(settings),
        "ordered_backends": ordered,
        "primary_backend": ordered[0] if ordered else "cpu",
        "gpu_available": bool(non_cpu),
        "device_snapshots": {
            device: torch_device_memory_snapshot(device, estimated_bytes=estimated_bytes)
            for device in non_cpu
        },
    }


def _emit_accel_log(log_label: str, device_name: str) -> None:
    label = str(log_label or "Torch").strip() or "Torch"
    device = str(device_name or "cpu").strip().lower() or "cpu"
    key = (label, device)
    if device == "cpu" or key in _ACCEL_LOGGED:
        return
    _ACCEL_LOGGED.add(key)
    human = "Apple GPU(MPS)" if device == "mps" else "CUDA GPU" if device == "cuda" else device.upper()
    get_logger().log(f"⚡ [{label}] Torch 가속 활성화: {human}")


def move_torch_model_to_preferred_device(
    model: Any,
    *,
    settings: dict[str, Any] | None = None,
    log_label: str = "Torch",
    task: str = "torch",
    estimated_bytes: int = 0,
) -> str:
    device_name = preferred_torch_device_name(settings, task=task, estimated_bytes=estimated_bytes)
    if device_name != "cpu" and model is not None and hasattr(model, "to"):
        try:
            model.to(device_name)
        except Exception:
            device_name = "cpu"
    _emit_accel_log(log_label, device_name)
    return device_name


def move_torch_tensor_to_device(value: Any, device_name: str) -> Any:
    target = str(device_name or "cpu").strip().lower() or "cpu"
    if target == "cpu" or value is None or not hasattr(value, "to"):
        return value
    try:
        return value.to(target)
    except Exception:
        return value


def trim_torch_memory_caches(*, include_sync: bool = True) -> None:
    torch_mod = _torch_module()
    if torch_mod is None:
        return
    try:
        if hasattr(torch_mod, "mps"):
            if include_sync and hasattr(torch_mod.mps, "synchronize"):
                torch_mod.mps.synchronize()
            if allow_mps_empty_cache() and hasattr(torch_mod.mps, "empty_cache"):
                torch_mod.mps.empty_cache()
    except Exception:
        pass
    try:
        if hasattr(torch_mod, "cuda") and torch_mod.cuda.is_available():
            if include_sync:
                torch_mod.cuda.synchronize()
            torch_mod.cuda.empty_cache()
    except Exception:
        pass


__all__ = [
    "allow_mps_empty_cache",
    "move_torch_model_to_preferred_device",
    "move_torch_tensor_to_device",
    "preferred_torch_device_name",
    "torch_acceleration_snapshot",
    "torch_device_memory_snapshot",
    "torch_execution_backends",
    "torch_gpu_acceleration_enabled",
    "trim_torch_memory_caches",
]
