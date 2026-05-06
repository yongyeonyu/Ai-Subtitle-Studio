# Version: 03.07.01
# Phase: PHASE2
"""
Runtime performance helpers.

This module keeps tuning conservative and cross-platform. It avoids optional
third-party dependencies so performance features remain safe on Windows builds.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
_JSON_WRITE_LOCK = threading.Lock()


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _sysctl_int(name: str) -> int:
    if platform.system() != "Darwin":
        return 0
    try:
        proc = subprocess.run(
            ["sysctl", "-n", name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1.0,
        )
        return _positive_int((proc.stdout or "").strip(), 0)
    except Exception:
        return 0


@lru_cache(maxsize=1)
def hardware_profile() -> dict:
    logical = max(1, os.cpu_count() or 1)
    physical = _sysctl_int("hw.physicalcpu") or logical
    performance_cores = _sysctl_int("hw.perflevel0.physicalcpu")
    memory_bytes = _sysctl_int("hw.memsize")

    if performance_cores <= 0:
        # On Windows/Linux we do not assume hybrid core topology. Use physical
        # cores as a stability-first cap for CPU-bound worker defaults.
        performance_cores = physical

    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "logical_cores": logical,
        "physical_cores": max(1, physical),
        "performance_cores": max(1, performance_cores),
        "memory_bytes": max(0, memory_bytes),
    }


def bounded_worker_count(
    requested: Any = None,
    *,
    kind: str = "io",
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """Return a conservative worker count for the current machine.

    `requested` is honored when valid, then clamped to a platform-aware cap.
    """
    profile = hardware_profile()
    logical = int(profile["logical_cores"])
    physical = int(profile["physical_cores"])
    perf = int(profile["performance_cores"])

    if kind == "ffprobe":
        default = min(4, max(1, logical // 2))
        cap = min(8, max(1, logical))
    elif kind == "cpu":
        default = max(1, perf)
        cap = max(1, physical)
    elif kind == "llm":
        default = min(6, max(1, perf))
        cap = min(12, max(1, logical))
    else:
        default = min(12, max(4, logical))
        cap = min(16, max(1, logical))

    if maximum is not None:
        cap = min(cap, max(1, int(maximum)))
    minimum = max(1, int(minimum))
    value = _positive_int(requested, default)
    return max(minimum, min(value, cap))


def _safe_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔", "아니오"}
    return bool(value)


def _available_memory_bytes() -> int:
    try:
        import psutil  # type: ignore

        return max(0, int(psutil.virtual_memory().available))
    except Exception:
        pass
    if platform.system() == "Darwin":
        try:
            page_size = _sysctl_int("hw.pagesize") or 4096
            proc = subprocess.run(
                ["vm_stat"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1.0,
            )
            free_pages = 0
            for line in (proc.stdout or "").splitlines():
                if any(key in line for key in ("Pages free", "Pages inactive", "Pages speculative")):
                    number = "".join(ch for ch in line.split(":", 1)[-1] if ch.isdigit())
                    free_pages += _positive_int(number, 0)
            return max(0, free_pages * page_size)
        except Exception:
            return 0
    return 0


def _darwin_battery_state() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"on_battery": False, "battery_percent": None}
    try:
        proc = subprocess.run(
            ["pmset", "-g", "batt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=0.8,
        )
    except Exception:
        return {"on_battery": False, "battery_percent": None}
    text = proc.stdout or ""
    on_battery = "Battery Power" in text
    percent = None
    for token in text.replace(";", " ").split():
        if token.endswith("%"):
            percent = _positive_int(token.rstrip("%"), 0)
            break
    return {"on_battery": bool(on_battery), "battery_percent": percent if percent > 0 else None}


def _darwin_user_idle_seconds() -> float | None:
    if platform.system() != "Darwin":
        return None
    try:
        proc = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=0.8,
        )
    except Exception:
        return None
    for line in (proc.stdout or "").splitlines():
        if "HIDIdleTime" not in line:
            continue
        raw = line.split("=", 1)[-1].strip()
        try:
            return max(0.0, float(raw) / 1_000_000_000.0)
        except Exception:
            return None
    return None


def current_resource_snapshot() -> dict[str, Any]:
    profile = hardware_profile()
    logical = max(1, int(profile.get("logical_cores", 1) or 1))
    memory_bytes = max(0, int(profile.get("memory_bytes", 0) or 0))
    available = _available_memory_bytes()
    if memory_bytes <= 0:
        try:
            import psutil  # type: ignore

            memory_bytes = max(0, int(psutil.virtual_memory().total))
        except Exception:
            memory_bytes = 0
    try:
        load_1m = float(os.getloadavg()[0])
    except Exception:
        load_1m = 0.0
    load_ratio = max(0.0, load_1m / float(logical))
    available_ratio = (float(available) / float(memory_bytes)) if memory_bytes > 0 and available > 0 else 1.0
    battery = _darwin_battery_state()
    idle_seconds = _darwin_user_idle_seconds()
    user_active = bool(idle_seconds is not None and idle_seconds < 15.0)
    return {
        **profile,
        "cpu_load_1m": round(load_1m, 4),
        "cpu_load_ratio": round(load_ratio, 4),
        "available_memory_bytes": available,
        "available_memory_ratio": round(max(0.0, min(1.0, available_ratio)), 4),
        "on_battery": bool(battery.get("on_battery")),
        "battery_percent": battery.get("battery_percent"),
        "user_idle_seconds": None if idle_seconds is None else round(float(idle_seconds), 3),
        "user_active": user_active,
    }


def _resource_pressure_reduction(snapshot: dict[str, Any], settings: dict[str, Any] | None = None) -> tuple[int, list[str]]:
    settings = dict(settings or {})
    reduction = 0
    reasons: list[str] = []
    load_ratio = float(snapshot.get("cpu_load_ratio", 0.0) or 0.0)
    available_ratio = float(snapshot.get("available_memory_ratio", 1.0) or 1.0)
    available_gb = float(snapshot.get("available_memory_bytes", 0) or 0) / (1024 ** 3)
    if load_ratio >= 0.97:
        reduction += 2
        reasons.append("very_high_cpu_load")
    elif load_ratio >= 0.72:
        reduction += 1
        reasons.append("high_cpu_load")
    if (available_gb and available_gb < 2.0) or available_ratio < 0.15:
        reduction += 2
        reasons.append("very_low_memory")
    elif (available_gb and available_gb < 4.0) or available_ratio < 0.25:
        reduction += 1
        reasons.append("low_memory")
    if _safe_bool(settings.get("scheduler_reduce_on_battery"), True) and snapshot.get("on_battery"):
        reduction += 1
        reasons.append("battery_power")
    if _safe_bool(settings.get("scheduler_reduce_on_user_input"), True) and snapshot.get("user_active"):
        reduction += 1
        reasons.append("user_active")
    return reduction, reasons


def adaptive_worker_count(
    *,
    task: str,
    settings: dict[str, Any] | None = None,
    requested: Any = None,
    workload: int = 1,
    minimum: int = 1,
    maximum: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Choose non-LLM worker counts from resources, workload, battery, and user input."""
    settings = dict(settings or {})
    task_text = str(task or "worker").strip().lower()
    workload = max(1, int(workload or 1))
    auto_key = f"{task_text}_workers_auto_enabled"
    auto_enabled = _safe_bool(settings.get(auto_key, settings.get("runtime_scheduler_auto_enabled", True)), True)
    kind = "io" if task_text in {"io", "lora", "prefetch"} else "cpu"
    if task_text in {"cut_pioneer", "cut_follower", "stt"}:
        default_max = 4 if task_text.startswith("cut_") else 2
    elif task_text == "lora":
        default_max = 4
    else:
        default_max = maximum or 8
    max_cap = max(1, int(maximum or _positive_int(settings.get(f"{task_text}_workers_resource_max"), default_max) or default_max))
    base = bounded_worker_count(requested, kind=kind, minimum=minimum, maximum=max_cap)
    base = max(minimum, min(base, workload, max_cap))
    snapshot = current_resource_snapshot()
    if not auto_enabled:
        return base, {
            "schema": "ai_subtitle_studio.runtime_scheduler.v1",
            "task": task_text,
            "auto_enabled": False,
            "workers": base,
            "requested": requested,
            "workload": workload,
            "reason": "manual_compat",
            "resource": snapshot,
        }

    reduction, reasons = _resource_pressure_reduction(snapshot, settings)
    if workload <= 1:
        reasons.append("single_item_workload")
    workers = max(minimum, min(base - reduction, workload, max_cap))
    if task_text == "stt" and workload >= 2 and not reasons:
        workers = min(workers, 2)
    meta = {
        "schema": "ai_subtitle_studio.runtime_scheduler.v1",
        "task": task_text,
        "auto_enabled": True,
        "workers": workers,
        "requested": requested,
        "workload": workload,
        "reason": "resource_adaptive",
        "reductions": sorted(set(reasons)),
        "resource": snapshot,
    }
    return workers, meta


def _model_size_penalty(model: str) -> int:
    text = str(model or "").lower()
    if any(token in text for token in ("70b", "72b", "34b", "32b", "27b", "22b", "14b")):
        return 2
    if any(token in text for token in ("13b", "12b", "10b", "8b", "7.8b", "7b")):
        return 1
    return 0


def adaptive_llm_worker_count(
    *,
    settings: dict[str, Any] | None = None,
    requested: Any = None,
    workload: int = 1,
    provider: str = "ollama",
    model: str = "",
    task: str = "subtitle",
) -> tuple[int, dict[str, Any]]:
    """Choose LLM workers from current machine resources and workload.

    API providers stay single-worker to avoid rate-limit/cost surprises. Local
    providers are allowed to scale up only when CPU load and memory headroom are
    healthy.
    """
    settings = dict(settings or {})
    workload = max(1, int(workload or 1))
    provider_text = str(provider or "").strip().lower()
    task_text = str(task or "subtitle").strip().lower()
    auto_key = "roughcut_llm_threads_auto_enabled" if task_text == "roughcut" else "llm_threads_auto_enabled"
    auto_enabled = _safe_bool(settings.get(auto_key), True)
    is_api = provider_text in {"openai", "google", "gemini", "anthropic"} or "gemini" in str(model or "").lower() or str(model or "").lower().startswith("gpt")

    if is_api:
        meta = {
            "auto_enabled": auto_enabled,
            "provider": provider_text or "api",
            "model": str(model or ""),
            "task": task_text,
            "workload": workload,
            "reason": "api_single_worker",
        }
        return 1, meta

    if not auto_enabled:
        workers = max(1, _positive_int(requested, bounded_worker_count(kind="llm", minimum=1, maximum=16)))
        return workers, {
            "auto_enabled": False,
            "provider": provider_text or "ollama",
            "model": str(model or ""),
            "task": task_text,
            "workload": workload,
            "reason": "manual_compat",
        }

    snapshot = current_resource_snapshot()
    perf = max(1, int(snapshot.get("performance_cores", 1) or 1))
    logical = max(1, int(snapshot.get("logical_cores", 1) or 1))
    memory_gb = float(snapshot.get("memory_bytes", 0) or 0) / (1024 ** 3)
    available_gb = float(snapshot.get("available_memory_bytes", 0) or 0) / (1024 ** 3)
    available_ratio = float(snapshot.get("available_memory_ratio", 1.0) or 1.0)
    load_ratio = float(snapshot.get("cpu_load_ratio", 0.0) or 0.0)

    base = max(1, min(4 if task_text == "subtitle" else 3, max(1, perf // 2)))
    if logical >= 12 and memory_gb >= 24 and load_ratio <= 0.55 and available_ratio >= 0.35:
        base += 1
    if workload <= 2:
        base = 1
    elif workload <= 8:
        base = min(base, 2)
    reductions, reduction_reasons = _resource_pressure_reduction(snapshot, settings)
    base -= reductions
    base -= _model_size_penalty(model)

    maximum = _positive_int(settings.get("llm_threads_resource_max"), 0) or 6
    if task_text == "roughcut":
        maximum = _positive_int(settings.get("roughcut_llm_threads_resource_max"), 0) or min(maximum, 4)
    workers = max(1, min(int(base), int(maximum), workload))
    meta = {
        "auto_enabled": True,
        "provider": provider_text or "ollama",
        "model": str(model or ""),
        "task": task_text,
        "workload": workload,
        "workers": workers,
        "reason": "resource_adaptive",
        "reductions": sorted(set(reduction_reasons)),
        "resource": snapshot,
    }
    return workers, meta


def ffprobe_worker_count(file_count: int) -> int:
    return max(1, min(int(file_count or 1), bounded_worker_count(kind="ffprobe")))


def media_probe_cache_dir() -> Path:
    cache_root = PROJECT_ROOT / "output" / ".media_probe_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


def atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        with _JSON_WRITE_LOCK:
            os.replace(tmp_name, target)
    except Exception:
        try:
            os.remove(tmp_name)
        except Exception:
            pass
        raise


def configure_qt_runtime() -> None:
    """Tune Qt global caches after QApplication is created."""
    try:
        from PyQt6.QtGui import QPixmapCache
    except Exception:
        return

    profile = hardware_profile()
    memory_gb = float(profile.get("memory_bytes") or 0) / (1024 ** 3)
    if memory_gb >= 32:
        limit_kb = 131072
    elif memory_gb >= 16:
        limit_kb = 65536
    else:
        limit_kb = 32768
    try:
        QPixmapCache.setCacheLimit(max(QPixmapCache.cacheLimit(), limit_kb))
    except Exception:
        pass


def configure_qt_gpu_rendering_before_app() -> None:
    """Apply Qt OpenGL setup before QApplication is created.

    Normal app launches default to GPU compositing/OpenGL. Tests and offscreen
    runs remain conservative unless the caller explicitly opts in with env vars.
    """
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return
    # Default off in real app runs too. On macOS, forcing global Qt OpenGL can
    # crash QtMultimedia/video widgets with Segmentation fault: 11.
    gpu_default = "0"
    if str(os.environ.get("AI_SUBTITLE_GPU_RENDERING", gpu_default)).lower() not in {"1", "true", "yes", "on"}:
        return
    if str(os.environ.get("AI_SUBTITLE_FORCE_QT_OPENGL", "0")).lower() not in {"1", "true", "yes", "on"}:
        return

    os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QSurfaceFormat
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return

    for attr in (
        getattr(Qt.ApplicationAttribute, "AA_ShareOpenGLContexts", None),
        getattr(Qt.ApplicationAttribute, "AA_UseDesktopOpenGL", None),
    ):
        if attr is None:
            continue
        try:
            QApplication.setAttribute(attr, True)
        except Exception:
            pass

    try:
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        if platform.system() == "Darwin":
            fmt.setVersion(3, 2)
        else:
            fmt.setVersion(3, 3)
        fmt.setDepthBufferSize(0)
        fmt.setStencilBufferSize(0)
        fmt.setSamples(0)
        fmt.setSwapInterval(0)
        QSurfaceFormat.setDefaultFormat(fmt)
    except Exception:
        pass
