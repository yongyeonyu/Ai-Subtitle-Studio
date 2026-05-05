# Version: 03.17.00
# Phase: PHASE3
"""QML helpers for settings panels."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor

from ui.gpu_rendering import scenegraph_enabled


def create_settings_header(parent, *, title: str, subtitle: str, badge: str = "QML"):
    """Return a transparent QQuickWidget header when SceneGraph is enabled."""
    if not scenegraph_enabled("settings"):
        return None
    qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "qml", "settings_panel_header.qml"))
    if not os.path.exists(qml_path):
        return None
    try:
        from PyQt6.QtQuickWidgets import QQuickWidget
    except Exception:
        return None
    try:
        header = QQuickWidget(parent)
        header.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        header.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        header.setClearColor(QColor(0, 0, 0, 0))
        header.setFixedHeight(72)
        header.setSource(QUrl.fromLocalFile(qml_path))
        if header.status() == QQuickWidget.Status.Error:
            header.deleteLater()
            return None
        root = header.rootObject()
        if root is not None:
            root.setProperty("titleText", str(title or "Settings"))
            root.setProperty("subtitleText", str(subtitle or "QML SceneGraph panel"))
            root.setProperty("badgeText", str(badge or "QML"))
        return header
    except Exception:
        return None
