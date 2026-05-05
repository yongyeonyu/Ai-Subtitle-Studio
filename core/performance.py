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
