# Version: 03.24.02
# Phase: PHASE2
"""QML-backed home sidebar navigation."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ui.gpu_rendering import scenegraph_enabled


class HomeSidebarNavWidget(QWidget):
    actionTriggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeSidebarNavWidget")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._items: list[dict] = []
        self._quick = None
        self._fallback_layout = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        quick = self._create_quick_panel()
        if quick is not None:
            self._quick = quick
            layout.addWidget(quick)
        else:
            fallback = QWidget(self)
            fallback_layout = QVBoxLayout(fallback)
            fallback_layout.setContentsMargins(0, 0, 0, 0)
            fallback_layout.setSpacing(4)
            self._fallback_layout = fallback_layout
            layout.addWidget(fallback)

    def _create_quick_panel(self):
        if not scenegraph_enabled("project"):
            return None
        qml_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "qml", "home_sidebar_nav.qml")
        )
        if not os.path.exists(qml_path):
            return None
        try:
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        try:
            quick = QQuickWidget(self)
            quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            quick.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            quick.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            quick.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            quick.setAutoFillBackground(False)
            quick.setClearColor(QColor(Qt.GlobalColor.transparent))
            quick.setSource(QUrl.fromLocalFile(qml_path))
            if quick.status() == QQuickWidget.Status.Error:
                quick.deleteLater()
                return None
            root = quick.rootObject()
            if root is not None and hasattr(root, "actionTriggered"):
                root.actionTriggered.connect(self.actionTriggered.emit)
            return quick
        except Exception:
            return None

    def set_items(self, items: list[dict]):
        self._items = [dict(item or {}) for item in (items or [])]
        item_height = 26
        item_spacing = 4
        min_height = max(item_height, len(self._items) * item_height + max(0, len(self._items) - 1) * item_spacing)
        self.setMinimumHeight(min_height)
        self.setMaximumHeight(min_height)
        if self._quick is not None:
            root = self._quick.rootObject()
            if root is not None:
                root.setProperty("menuItems", self._items)
            return
        self._render_fallback_items()

    def _render_fallback_items(self):
        layout = self._fallback_layout
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for item in self._items:
            button = QWidget(self)
            button.setObjectName("MenuButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(26)
            button.setMaximumHeight(26)
            accent = str(item.get("accent", "#3F8CFF") or "#3F8CFF")
            active = bool(item.get("active"))
            button.setStyleSheet(
                "QWidget#MenuButton { "
                f"background: {'#26313A' if active else '#141C20'}; "
                f"border: 1px solid {accent if active else '#223038'}; "
                "border-radius: 8px; }"
            )
            row = QHBoxLayout(button)
            row.setContentsMargins(8, 0, 8, 0)
            row.setSpacing(7)
            badge = QLabel(str(item.get("badge", "") or ""), button)
            badge.setFixedSize(16, 16)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "color: "
                f"{accent if active else '#A9B0B7'}; "
                "font-size: 8px; font-weight: 700; "
                "background: #182126; border: 1px solid #243139; border-radius: 4px;"
            )
            title = QLabel(str(item.get("title", "") or ""), button)
            title.setStyleSheet(
                "color: "
                f"{'#F5F7FA' if item.get('enabled', True) is not False else '#73808B'}; "
                "font-size: 10px; font-weight: 700; background: transparent; border: none;"
            )
            row.addWidget(badge)
            row.addWidget(title, stretch=1)
            action_id = str(item.get("id", "") or "")
            enabled = item.get("enabled", True) is not False
            if not enabled:
                button.setEnabled(False)

            def _on_click(event, value=action_id, is_enabled=enabled):
                if event.button() == Qt.MouseButton.LeftButton and is_enabled:
                    self.actionTriggered.emit(value)
                    event.accept()

            button.mousePressEvent = _on_click
            layout.addWidget(button)
