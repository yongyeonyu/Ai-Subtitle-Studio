# Version: 03.04.01
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
    except Exception:
        pass
