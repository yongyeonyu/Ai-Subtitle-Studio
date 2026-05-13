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
        item_spacing = 4
        heights = []
        for item in self._items:
            try:
                heights.append(max(26, int(item.get("height", 38 if item.get("progressVisible") else 26) or 26)))
            except Exception:
                heights.append(26)
        content_height = sum(heights) + max(0, len(heights) - 1) * item_spacing
        min_height = max(26, content_height)
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
            accent = str(item.get("accent", "#3F8CFF") or "#3F8CFF")
            progress_visible = bool(item.get("progressVisible"))
            progress_percent = max(0, min(100, int(item.get("progressPercent", 0) or 0)))
            item_height = max(26, int(item.get("height", 38 if progress_visible else 26) or 26))
            button.setMinimumHeight(item_height)
            button.setMaximumHeight(item_height)
            active = bool(item.get("active"))
            if progress_visible:
                fill = str(item.get("fillColor", "#153A25") or "#153A25")
                ratio = max(0.0, min(1.0, progress_percent / 100.0))
                base_bg = "transparent"
                hover_bg = "#0F171C"
                if ratio <= 0.0:
                    normal_ss = (
                        "QWidget#MenuButton { "
                        f"background: {base_bg}; border: 1px solid {accent}; border-radius: 8px; "
                        "}"
                    )
                    hover_ss = (
                        "QWidget#MenuButton { "
                        f"background: {hover_bg}; border: 1px solid {accent}; border-radius: 8px; "
                        "}"
                    )
                else:
                    stop = f"{ratio:.4f}"
                    cut = f"{min(1.0, ratio + 0.0001):.4f}"
                    normal_ss = (
                        "QWidget#MenuButton { "
                        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                        f"stop:0 {fill}, stop:{stop} {fill}, stop:{cut} {base_bg}, stop:1 {base_bg}); "
                        f"border: 1px solid {accent}; border-radius: 8px; "
                        "}"
                    )
                    hover_ss = (
                        "QWidget#MenuButton { "
                        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                        f"stop:0 {fill}, stop:{stop} {fill}, stop:{cut} {hover_bg}, stop:1 {hover_bg}); "
                        f"border: 1px solid {accent}; border-radius: 8px; "
                        "}"
                    )
            else:
                normal_ss = (
                    "QWidget#MenuButton { "
                    f"background: {'#26313A' if active else '#141C20'}; "
                    f"border: 1px solid {accent if active else '#223038'}; "
                    "border-radius: 8px; }"
                )
                hover_ss = (
                    "QWidget#MenuButton { "
                    f"background: {'#26313A' if active else '#1B2429'}; "
                    f"border: 1px solid {accent if active else '#34424B'}; "
                    "border-radius: 8px; }"
                )
            button._normal_ss = normal_ss
            button._hover_ss = hover_ss
            button.setStyleSheet(normal_ss)
            button.enterEvent = lambda _event, _w=button: _w.setStyleSheet(_w._hover_ss)
            button.leaveEvent = lambda _event, _w=button: _w.setStyleSheet(_w._normal_ss)

            row = QHBoxLayout(button)
            row.setContentsMargins(8, 4 if progress_visible else 0, 8, 4 if progress_visible else 0)
            row.setSpacing(7)
            badge = QLabel(str(item.get("badge", "") or ""), button)
            badge.setFixedSize(16, 16)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "color: "
                f"{accent if (active or progress_visible) else '#A9B0B7'}; "
                "font-size: 8px; font-weight: 700; "
                "background: #182126; border: 1px solid #243139; border-radius: 4px;"
            )
            row.addWidget(badge)
            if progress_visible:
                body = QWidget(button)
                body_layout = QVBoxLayout(body)
                body_layout.setContentsMargins(0, 0, 0, 0)
                body_layout.setSpacing(1)
                title_row = QHBoxLayout()
                title_row.setContentsMargins(0, 0, 0, 0)
                title_row.setSpacing(6)
                title = QLabel(str(item.get("title", "") or ""), body)
                title.setStyleSheet(
                    "color: #F5F7FA; font-size: 10px; font-weight: 700; background: transparent; border: none;"
                )
                title_row.addWidget(title, stretch=1)
                pct = QLabel(str(item.get("progressText", "") or ""), body)
                pct.setStyleSheet(
                    f"color: {accent}; font-size: 10px; font-weight: 800; background: transparent; border: none;"
                )
                title_row.addWidget(pct, stretch=0)
                body_layout.addLayout(title_row)
                subtitle_text = str(item.get("subtitle", "") or "")
                if subtitle_text:
                    subtitle = QLabel(subtitle_text, body)
                    subtitle.setStyleSheet(
                        "color: #B9C7D3; font-size: 8px; font-weight: 600; background: transparent; border: none;"
                    )
                    body_layout.addWidget(subtitle)
                row.addWidget(body, stretch=1)
            else:
                title = QLabel(str(item.get("title", "") or ""), button)
                title.setStyleSheet(
                    "color: "
                    f"{'#F5F7FA' if item.get('enabled', True) is not False else '#73808B'}; "
                    "font-size: 10px; font-weight: 700; background: transparent; border: none;"
                )
                row.addWidget(title, stretch=1)
            action_id = str(item.get("id", "") or "")
            enabled = item.get("enabled", True) is not False
            tooltip = str(item.get("tooltip", "") or "")
            if not enabled:
                button.setEnabled(False)
            elif tooltip:
                button.setToolTip(tooltip)

            def _on_click(event, value=action_id, is_enabled=enabled):
                if event.button() == Qt.MouseButton.LeftButton and is_enabled:
                    self.actionTriggered.emit(value)
                    event.accept()

            button.mousePressEvent = _on_click
            layout.addWidget(button)
