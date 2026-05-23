# Version: 04.00.01
"""Qt runtime setup helpers.

This module is intentionally small and import-light because it can run before
QApplication exists. macOS defaults favor Metal/SceneGraph paths and avoid
forcing OpenGL unless the user explicitly opts in.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from core.json_file import read_json_file
from core.runtime.hardware_profile import hardware_profile
from core.runtime.setting_utils import setting_bool as _setting_bool
from core.settings_profiles import hardcoded_default_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _safe_bool(value: Any, default: bool = True) -> bool:
    return _setting_bool(
        value,
        default,
        false_values={"0", "false", "off", "no", "끔", "아니오"},
        false_only_strings=True,
        empty_is_default=False,
    )


def _qt_gpu_rendering_settings_request() -> tuple[bool | None, bool | None, str]:
    try:
        from core.runtime import config as runtime_config

        settings_path = Path(runtime_config.DATASET_DIR) / "user_settings.json"
        dataset_dir = runtime_config.DATASET_DIR
    except Exception:
        settings_path = PROJECT_ROOT / "dataset" / "user_settings.json"
        dataset_dir = str(settings_path.parent)
    settings = hardcoded_default_settings(
        dataset_dir=dataset_dir,
        include_custom_defaults=True,
        include_folder_settings=False,
    )
    data = read_json_file(settings_path, default={}, expected_type=dict, context="qt_gpu_settings", log_errors=False)
    if isinstance(data, dict):
        settings.update(data)
    scope = str(settings.get("editor_rendering_gpu_scope", settings.get("gpu_rendering_scope", "")) or "").strip().lower()
    gpu_requested = True if scope in {"all", "whole", "full", "global", "전체"} else None
    force_requested = None
    if "editor_rendering_force_qt_opengl" in settings:
        force_requested = _safe_bool(settings.get("editor_rendering_force_qt_opengl"), False)
    elif "force_qt_opengl" in settings:
        force_requested = _safe_bool(settings.get("force_qt_opengl"), False)
    backend = str(
        settings.get(
            "editor_rendering_qt_backend",
            settings.get("gpu_qt_backend", "auto"),
        )
        or "auto"
    ).strip().lower()
    if backend not in {"auto", "metal", "opengl"}:
        backend = "auto"
    return gpu_requested, force_requested, backend


def qt_application_font_family() -> str:
    """Return the concrete Qt application font for the current platform."""
    try:
        from core.runtime import config

        configured = str(getattr(config, "FONT", "") or "").strip()
    except Exception:
        configured = ""
    if platform.system() == "Darwin":
        return configured or "Apple SD Gothic Neo"
    return configured


def configure_qt_application_font() -> str:
    """Pin QApplication to a real platform font before widgets trigger aliases."""
    family = qt_application_font_family()
    if not family:
        return ""
    try:
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QApplication
    except Exception:
        return ""
    app = QApplication.instance()
    if app is None:
        return ""
    try:
        font = QFont(app.font())
        if str(font.family() or "") == family:
            return family
        font.setFamily(family)
        app.setFont(font)
        return family
    except Exception:
        return ""


def qt_tooltip_stylesheet() -> str:
    return (
        "QToolTip, QTipLabel { "
        "background-color: #202A31; color: #F5F7FA; "
        "border: 1px solid #3A4650; border-radius: 6px; "
        "padding: 6px; font-size: 12px; opacity: 245; "
        "}"
    )


def configure_qt_tooltip_theme(*, append_stylesheet: bool = False) -> str:
    """Keep native Qt tooltips readable on macOS when widget stylesheets refresh."""
    try:
        from PyQt6.QtGui import QColor, QPalette
        from PyQt6.QtWidgets import QApplication, QToolTip
    except Exception:
        return ""
    app = QApplication.instance()
    if app is None:
        return ""
    rule = qt_tooltip_stylesheet()
    try:
        palette = QToolTip.palette()
        for group in (
            QPalette.ColorGroup.Active,
            QPalette.ColorGroup.Inactive,
            QPalette.ColorGroup.Disabled,
        ):
            palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#202A31"))
            palette.setColor(group, QPalette.ColorRole.ToolTipText, QColor("#F5F7FA"))
        QToolTip.setPalette(palette)
    except Exception:
        pass
    if append_stylesheet:
        try:
            current = str(app.styleSheet() or "")
            marker = "/* AI_SUBTITLE_DARK_TOOLTIP */"
            if marker not in current:
                app.setStyleSheet((current.rstrip() + "\n" + marker + "\n" + rule).strip())
        except Exception:
            pass
    return rule


def configure_qt_runtime() -> None:
    """Tune Qt global caches after QApplication is created."""
    configure_qt_application_font()
    configure_qt_tooltip_theme()
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
    settings_gpu, settings_force, settings_backend = _qt_gpu_rendering_settings_request()
    gpu_value = os.environ.get("AI_SUBTITLE_GPU_RENDERING")
    gpu_requested = (
        str(gpu_value if gpu_value is not None else gpu_default).lower() in {"1", "true", "yes", "on"}
        if gpu_value is not None or settings_gpu is None
        else bool(settings_gpu)
    )
    if not gpu_requested:
        return
    force_value = os.environ.get("AI_SUBTITLE_FORCE_QT_OPENGL")
    force_requested = (
        str(force_value if force_value is not None else "0").lower() in {"1", "true", "yes", "on"}
        if force_value is not None or settings_force is None
        else bool(settings_force)
    )
    backend_value = str(os.environ.get("AI_SUBTITLE_QT_GPU_BACKEND", settings_backend or "auto") or "auto").strip().lower()
    if backend_value not in {"auto", "metal", "opengl"}:
        backend_value = "auto"
    if platform.system() == "Darwin" and force_value is None and backend_value != "opengl":
        force_requested = False
    if force_requested:
        backend_value = "opengl"
    if backend_value == "auto":
        backend_value = "metal" if platform.system() == "Darwin" else "opengl"

    if backend_value == "metal" and platform.system() == "Darwin":
        os.environ.setdefault("QSG_RHI_BACKEND", "metal")
        if str(os.environ.get("QT_QUICK_BACKEND", "") or "").strip().lower() == "hardware":
            os.environ.pop("QT_QUICK_BACKEND", None)
        return

    if not force_requested:
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
