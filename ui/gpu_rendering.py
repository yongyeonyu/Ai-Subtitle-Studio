# Version: 03.07.01
# Phase: PHASE2
"""Small helpers for optional GPU-backed Qt widgets.

OpenGL widgets are opt-in because macOS/QtMultimedia can crash in the platform
driver before Python can catch anything. Keep the default path boring and stable.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


_FALSE_VALUES = {"0", "false", "no", "off"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in _TRUE_VALUES


def gpu_runtime_enabled() -> bool:
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return False
    return _env_enabled("AI_SUBTITLE_GPU_RENDERING", "0")


def gpu_widgets_enabled() -> bool:
    if not gpu_runtime_enabled():
        return False
    return _env_enabled("AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS", "0")


def accelerated_widget_base():
    if not gpu_widgets_enabled():
        return QWidget
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception:
        return QWidget
    return QOpenGLWidget


def gpu_backend_name() -> str:
    return "opengl-widget" if gpu_widgets_enabled() else "qwidget"


def configure_lightweight_paint(widget: QWidget, *, opaque: bool = True) -> None:
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        if opaque:
            widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    except Exception:
        pass


def configure_opengl_widget(widget: QWidget) -> None:
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget

        if isinstance(widget, QOpenGLWidget):
            widget.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
            widget.setAutoFillBackground(False)
    except Exception:
        pass


def make_accelerated_viewport(parent=None) -> QWidget | None:
    if not gpu_widgets_enabled():
        return None
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception:
        return None
    viewport = QOpenGLWidget(parent)
    configure_opengl_widget(viewport)
    return viewport
