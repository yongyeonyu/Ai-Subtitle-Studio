# Version: 03.14.31
# Phase: PHASE2
"""Small helpers for GPU-backed Qt widgets.

The app uses Qt's OpenGL-backed widgets for the heavy custom-rendered surfaces.
Tests and offscreen runs stay on QWidget unless GPU rendering is explicitly
requested, because Qt can abort in native platform drivers before Python can
catch the failure.
"""
from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


_FALSE_VALUES = {"0", "false", "no", "off"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in _TRUE_VALUES


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _gpu_default_enabled(feature_key: str) -> str:
    if _running_under_pytest():
        return "0"
    return "1"


def gpu_runtime_enabled(feature: str | None = None) -> bool:
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return False
    feature_key = str(feature or "").strip().lower()
    if feature_key == "timeline":
        if _running_under_pytest() and "AI_SUBTITLE_TIMELINE_GPU_RENDERING" not in os.environ:
            return False
        return _env_enabled("AI_SUBTITLE_TIMELINE_GPU_RENDERING", _gpu_default_enabled(feature_key))
    if _running_under_pytest() and "AI_SUBTITLE_GPU_RENDERING" not in os.environ:
        return False
    return _env_enabled("AI_SUBTITLE_GPU_RENDERING", _gpu_default_enabled(feature_key))


def gpu_widgets_enabled(feature: str | None = None) -> bool:
    feature_key = str(feature or "").strip().lower()
    if not gpu_runtime_enabled(feature_key):
        return False
    if feature_key == "timeline":
        return _env_enabled("AI_SUBTITLE_TIMELINE_OPENGL_WIDGETS", "1") or _env_enabled(
            "AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS",
            "0",
        )
    return _env_enabled("AI_SUBTITLE_OPENGL_WIDGETS", "1") or _env_enabled(
        "AI_SUBTITLE_EXPERIMENTAL_OPENGL_WIDGETS",
        "0",
    )


def opengl_partial_update_enabled(feature: str | None = None) -> bool:
    feature_key = str(feature or "").strip().lower()
    if feature_key:
        env_name = f"AI_SUBTITLE_{feature_key.upper()}_OPENGL_PARTIAL_UPDATE"
        if env_name in os.environ:
            return _env_enabled(env_name, "1")
    return _env_enabled("AI_SUBTITLE_OPENGL_PARTIAL_UPDATE", "1")


def scenegraph_enabled(feature: str | None = None) -> bool:
    feature_key = str(feature or "").strip().lower()
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return False
    if _running_under_pytest() and f"AI_SUBTITLE_{feature_key.upper()}_SCENEGRAPH" not in os.environ:
        return False
    if not gpu_runtime_enabled(feature_key):
        return False
    if feature_key:
        env_name = f"AI_SUBTITLE_{feature_key.upper()}_SCENEGRAPH"
        if env_name in os.environ:
            return _env_enabled(env_name, "1")
    return _env_enabled("AI_SUBTITLE_SCENEGRAPH", "1")


def accelerated_widget_base(feature: str | None = None):
    if not gpu_widgets_enabled(feature):
        return QWidget
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception:
        return QWidget
    return QOpenGLWidget


def gpu_backend_name(feature: str | None = None) -> str:
    return "opengl-widget" if gpu_widgets_enabled(feature) else "qwidget"


def configure_lightweight_paint(widget: QWidget, *, opaque: bool = True) -> None:
    try:
        widget.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        if opaque:
            widget.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    except Exception:
        pass


def configure_opengl_widget(widget: QWidget, feature: str | None = None) -> None:
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget

        if isinstance(widget, QOpenGLWidget):
            behavior = (
                QOpenGLWidget.UpdateBehavior.PartialUpdate
                if opengl_partial_update_enabled(feature)
                else QOpenGLWidget.UpdateBehavior.NoPartialUpdate
            )
            widget.setUpdateBehavior(behavior)
            widget.setAutoFillBackground(False)
    except Exception:
        pass


def make_accelerated_viewport(parent=None, feature: str | None = None) -> QWidget | None:
    if not gpu_widgets_enabled(feature):
        return None
    try:
        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    except Exception:
        return None
    viewport = QOpenGLWidget(parent)
    configure_opengl_widget(viewport, feature)
    return viewport
