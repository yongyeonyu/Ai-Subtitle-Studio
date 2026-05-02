# Version: 03.06.21
# Phase: PHASE2
"""
ui/gpu_rendering.py
Small helpers for optional GPU-backed Qt widgets.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def gpu_widgets_enabled() -> bool:
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return False
    return str(os.environ.get("AI_SUBTITLE_GPU_RENDERING", "1")).lower() not in {"0", "false", "no"}


def accelerated_widget_base():
    if not gpu_widgets_enabled():
        return QWidget
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception:
        return QWidget
    return QOpenGLWidget


def gpu_backend_name() -> str:
    return "opengl" if accelerated_widget_base() is not QWidget else "qwidget"


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
