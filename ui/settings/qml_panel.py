# Version: 03.17.00
# Phase: PHASE3
"""QML helpers for settings panels and shared dialog chrome."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor

from ui.gpu_rendering import scenegraph_enabled


def _create_quick_widget(
    parent,
    *,
    qml_name: str,
    scope: str,
    height: int,
    root_props: dict | None = None,
    mouse_transparent: bool = False,
):
    if not scenegraph_enabled(scope):
        return None
    qml_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "qml", qml_name))
    if not os.path.exists(qml_path):
        return None
    try:
        from PyQt6.QtQuickWidgets import QQuickWidget
    except Exception:
        return None
    try:
        widget = QQuickWidget(parent)
        widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, bool(mouse_transparent))
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        widget.setClearColor(QColor(0, 0, 0, 0))
        widget.setFixedHeight(int(height))
        widget.setSource(QUrl.fromLocalFile(qml_path))
        if widget.status() == QQuickWidget.Status.Error:
            widget.deleteLater()
            return None
        root = widget.rootObject()
        if root is not None:
            for key, value in dict(root_props or {}).items():
                root.setProperty(str(key), value)
        return widget
    except Exception:
        return None


def create_settings_header(parent, *, title: str, subtitle: str, badge: str = "QML"):
    """Return a transparent QQuickWidget header when SceneGraph is enabled."""
    return _create_quick_widget(
        parent,
        qml_name="settings_panel_header.qml",
        scope="settings",
        height=60,
        mouse_transparent=True,
        root_props={
            "titleText": str(title or "Settings"),
            "subtitleText": str(subtitle or "QML SceneGraph panel"),
            "badgeText": str(badge or "QML"),
        },
    )


def create_qml_tab_bar(parent, *, items: list[dict], current_index: int = 0, scope: str = "settings"):
    return _create_quick_widget(
        parent,
        qml_name="app_tab_bar.qml",
        scope=scope,
        height=44,
        root_props={
            "tabItems": list(items or []),
            "currentIndex": max(0, int(current_index or 0)),
        },
    )


def sync_qml_tab_bar(widget, *, items: list[dict] | None = None, current_index: int | None = None) -> None:
    if widget is None:
        return
    try:
        root = widget.rootObject()
        if root is None:
            return
        if items is not None:
            root.setProperty("tabItems", list(items))
        if current_index is not None:
            root.setProperty("currentIndex", max(0, int(current_index)))
    except Exception:
        pass


def attach_qml_tab_bar(parent, layout, tab_widget, *, scope: str = "settings", insert_index: int | None = None):
    items = [{"title": tab_widget.tabText(i)} for i in range(tab_widget.count())]
    bar = create_qml_tab_bar(
        parent,
        items=items,
        current_index=tab_widget.currentIndex(),
        scope=scope,
    )
    if bar is None:
        return None
    try:
        tab_widget.tabBar().hide()
        root = bar.rootObject()
        if root is not None:
            root.tabTriggered.connect(tab_widget.setCurrentIndex)
        tab_widget.currentChanged.connect(lambda idx: sync_qml_tab_bar(bar, current_index=idx))
        if insert_index is None:
            layout.addWidget(bar)
        else:
            layout.insertWidget(int(insert_index), bar)
        return bar
    except Exception:
        try:
            bar.deleteLater()
        except Exception:
            pass
        return None


def create_qml_action_bar(parent, *, actions: list[dict], compact: bool = False, scope: str = "settings"):
    return _create_quick_widget(
        parent,
        qml_name="app_action_bar.qml",
        scope=scope,
        height=38 if compact else 52,
        root_props={
            "actions": list(actions or []),
            "compact": bool(compact),
        },
    )
