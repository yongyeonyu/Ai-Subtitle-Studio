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
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from core.runtime import config


_FALSE_VALUES = {"0", "false", "no", "off"}
_TRUE_VALUES = {"1", "true", "yes", "on"}
_ALL_VALUES = {"all", "whole", "full", "global", "전체"}
_AUTO_VALUES = {"", "auto", "default", "system", "자동"}
_FRAME_VALUES = {"frame", "frames", "per-frame", "per_frame", "slot", "slots", "프레임"}
_OFF_VALUES = _FALSE_VALUES | {"none", "disabled", "disable", "끄기", "끔"}


def _env_enabled(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in _TRUE_VALUES


def _setting_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in _TRUE_VALUES:
        return True
    if text in _OFF_VALUES:
        return False
    return None


def _render_settings() -> dict:
    path = os.path.join(config.DATASET_DIR, "user_settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _settings_text(settings: dict, *keys: str) -> str:
    for key in keys:
        value = settings.get(key)
        if value is not None:
            text = str(value).strip().lower()
            if text:
                return text
    return ""


def _settings_frames(settings: dict) -> set[str]:
    raw = settings.get("editor_rendering_gpu_frames", settings.get("gpu_rendering_frames", ()))
    if isinstance(raw, str):
        values = raw.replace(";", ",").split(",")
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = ()
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _settings_gpu_runtime_enabled(feature_key: str) -> bool | None:
    settings = _render_settings()
    explicit = _setting_bool(settings.get("editor_rendering_gpu_enabled", settings.get("gpu_rendering_enabled")))
    if explicit is not None:
        return explicit
    scope = _settings_text(settings, "editor_rendering_gpu_scope", "gpu_rendering_scope")
    if scope in _AUTO_VALUES:
        return None
    if scope in _OFF_VALUES:
        return False
    if scope in _ALL_VALUES:
        return True
    if scope in _FRAME_VALUES:
        frames = _settings_frames(settings)
        if not frames:
            return False
        return (feature_key or "general") in frames or "all" in frames or "전체" in frames
    if scope in {"timeline", "video", "editor", "settings", "project", "general"}:
        return (feature_key or "general") == scope
    return None


def _settings_opengl_widgets_enabled(feature_key: str) -> bool | None:
    settings = _render_settings()
    feature_setting = _setting_bool(settings.get(f"editor_rendering_{feature_key}_opengl_widgets_enabled"))
    if feature_setting is not None:
        return feature_setting
    return _setting_bool(
        settings.get(
            "editor_rendering_opengl_widgets_enabled",
            settings.get("gpu_opengl_widgets_enabled"),
        )
    )


def _running_under_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _gpu_default_enabled(feature_key: str) -> str:
    # Stability first: macOS QtMultimedia + QOpenGLWidget/QQuickWidget can abort
    # the whole process before Python can catch it. Keep GPU widgets opt-in.
    return "0"


def gpu_runtime_enabled(feature: str | None = None) -> bool:
    if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
        return False
    feature_key = str(feature or "").strip().lower()
    feature_env = f"AI_SUBTITLE_{feature_key.upper()}_GPU_RENDERING" if feature_key else ""
    if feature_env and feature_env in os.environ:
        if _running_under_pytest():
            return _env_enabled(feature_env, "0")
        return _env_enabled(feature_env, _gpu_default_enabled(feature_key))
    if "AI_SUBTITLE_GPU_RENDERING" in os.environ:
        if _running_under_pytest():
            return _env_enabled("AI_SUBTITLE_GPU_RENDERING", "0")
        return _env_enabled("AI_SUBTITLE_GPU_RENDERING", _gpu_default_enabled(feature_key))
    if _running_under_pytest():
        legacy_feature_env = "AI_SUBTITLE_TIMELINE_GPU_RENDERING" if feature_key == "timeline" else "AI_SUBTITLE_GPU_RENDERING"
        if legacy_feature_env not in os.environ:
            return False
    setting = _settings_gpu_runtime_enabled(feature_key)
    if setting is not None:
        return setting
    return _env_enabled("AI_SUBTITLE_GPU_RENDERING", _gpu_default_enabled(feature_key))


def gpu_widgets_enabled(feature: str | None = None) -> bool:
    feature_key = str(feature or "").strip().lower()
    if not gpu_runtime_enabled(feature_key):
        return False
    feature_env = f"AI_SUBTITLE_{feature_key.upper()}_OPENGL_WIDGETS" if feature_key else ""
    if feature_env and feature_env in os.environ:
        return _env_enabled(feature_env, "1")
    setting = _settings_opengl_widgets_enabled(feature_key)
    if setting is not None:
        return setting
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
