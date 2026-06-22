# Version: 03.09.08
# Phase: PHASE2
"""Sidebar queue summary panel with a Qt Quick front-end and QWidget fallback."""

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.queue.queue_formatting import DEFAULT_QUEUE_HEADER
from ui.style import COLORS


class SidebarQueuePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarQueuePanel")
        self.setMinimumHeight(134)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._quick = None
        self._header = DEFAULT_QUEUE_HEADER
        self._items = []
        self._last_focused_active_row = -1
        self._last_focused_item_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        quick = self._create_quick_panel()
        if quick is not None:
            self._quick = quick
            layout.addWidget(quick)
            return

        self._header_lbl = QLabel(self._header)
        self._header_lbl.setStyleSheet(
            "QLabel { background: #0F171B; color: #F5F7FA; border: 1px solid #31424A; "
            "border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; "
            "padding: 8px 10px; font-size: 11px; font-weight: 800; }"
        )
        layout.addWidget(self._header_lbl)

        self._table = QTableWidget(0, 2)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 86)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { background: #0F171B; color: #F5F7FA; border: 1px solid #31424A; "
            "border-top: none; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; "
            "font-size: 10px; } "
            "QTableWidget::item { padding: 5px 6px; border-bottom: 1px solid #1D2A31; } "
            f"QTableWidget::item:selected {{ background: {COLORS['warning_surface_alt']}; color: {COLORS['warning']}; }} "
            "QScrollBar:vertical { background: #0A1013; width: 8px; margin: 3px 2px 3px 0; "
            "border: none; border-radius: 4px; } "
            "QScrollBar::handle:vertical { background: #33424A; min-height: 28px; border-radius: 4px; } "
            "QScrollBar::handle:vertical:hover { background: #53636D; } "
            "QScrollBar::handle:vertical:pressed { background: #74A9FF; } "
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; background: transparent; } "
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        layout.addWidget(self._table)

    def _create_quick_panel(self):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return None
        try:
            from PyQt6.QtGui import QColor
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        qml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "qml", "sidebar_queue_panel.qml")
        if not os.path.exists(qml_path):
            return None
        try:
            quick = QQuickWidget(self)
            quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            quick.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            quick.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            quick.setAutoFillBackground(False)
            quick.setClearColor(QColor(Qt.GlobalColor.transparent))
            quick.setSource(QUrl.fromLocalFile(qml_path))
            if quick.status() == QQuickWidget.Status.Error:
                quick.deleteLater()
                return None
            return quick
        except Exception:
            return None

    def set_queue(self, header: str, items: list[dict]):
        self._header = str(header or DEFAULT_QUEUE_HEADER)
        self._items = list(items or [])
        if self._quick is not None:
            root = self._quick.rootObject()
            if root is not None:
                root.setProperty("headerText", self._header)
                root.setProperty("queueItems", self._items)
            return

        previous_scroll_value = 0
        previous_current_row = -1
        scrollbar = self._table.verticalScrollBar()
        if scrollbar is not None:
            try:
                previous_scroll_value = int(scrollbar.value())
            except Exception:
                previous_scroll_value = 0
        try:
            previous_current_row = int(self._table.currentRow())
        except Exception:
            previous_current_row = -1

        self._header_lbl.setText(self._header)
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        active_row = -1
        first_active_row = -1
        for row, item in enumerate(self._items):
            done = bool(item.get("done"))
            error = bool(item.get("error"))
            if first_active_row < 0 and bool(item.get("active")) and not done and not error:
                first_active_row = row
        for row, item in enumerate(self._items):
            self._table.insertRow(row)
            done = bool(item.get("done"))
            error = bool(item.get("error"))
            active = row == first_active_row and bool(item.get("active")) and not done and not error
            row_color = "#55D97A" if done else ("#FF6B78" if error else (COLORS["warning"] if active else "#9DB0BB"))
            row_bg = "#13261D" if done else ("#291719" if error else (COLORS["warning_surface_alt"] if active else "#121A1E"))
            if active:
                active_row = row
            status = item.get("statusDisplay") or item.get("status", "대기 중")
            file_text = str(item.get("file", "-") or "-")
            eta_text = str(item.get("eta", "-") or "-")
            order_text = str(item.get("order", row + 1) or row + 1)
            values = (
                "완료" if done else str(status or "대기 중"),
                f"{self._two_line_file_name(file_text, prefix=f'{self._keycap_order(order_text)} ')}\n{eta_text}",
            )
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value or "-"))
                cell.setForeground(QColor(row_color))
                cell.setBackground(QColor(row_bg))
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                    if col == 0
                    else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self._table.setItem(row, col, cell)
            self._table.setRowHeight(row, 68)
        self._table.setUpdatesEnabled(True)
        should_focus_active = (
            active_row >= 0
            and (
                active_row != int(self._last_focused_active_row)
                or len(self._items) != int(self._last_focused_item_count)
                or previous_current_row < 0
            )
        )
        if should_focus_active:
            self._table.setCurrentCell(active_row, 0)
            active_item = self._table.item(active_row, 0)
            if active_item is not None:
                self._table.scrollToItem(
                    active_item,
                    QAbstractItemView.ScrollHint.PositionAtCenter,
                )
        elif scrollbar is not None:
            try:
                scrollbar.setValue(max(scrollbar.minimum(), min(previous_scroll_value, scrollbar.maximum())))
            except Exception:
                pass
        self._last_focused_active_row = int(active_row)
        self._last_focused_item_count = len(self._items)

    def set_queue_payload(self, payload: dict | None):
        data = dict(payload or {})
        self.set_queue(
            str(data.get("header", DEFAULT_QUEUE_HEADER) or DEFAULT_QUEUE_HEADER),
            list(data.get("items", []) or []),
        )

    def _keycap_order(self, order) -> str:
        keycaps = {str(i): f"{i}\ufe0f\u20e3" for i in range(10)}
        text = str(order or "0")
        if text.isdigit():
            text = f"{int(text):02d}"
        return "".join(keycaps.get(ch, ch) for ch in text)

    def _two_line_file_name(self, file_name: str, prefix: str = "") -> str:
        text = str(file_name or "-")
        if "\n" in text:
            parts = [part for part in text.splitlines() if part]
            if not parts:
                return prefix + "-"
            parts[0] = prefix + parts[0]
            return "\n".join(parts[:2])
        if len(prefix + text) <= 26:
            return prefix + text
        stem, ext = os.path.splitext(text)
        if not stem or not ext:
            mid = max(10, min(len(text) - 1, len(text) // 2))
            rest = text[mid:]
            if len(rest) > 18:
                rest = rest[:17] + "…"
            return f"{prefix}{text[:mid]}\n{rest}"
        first = stem[: max(12, min(len(stem), 20))]
        rest = stem[len(first):] + ext
        if len(rest) > 18:
            rest = "…" + rest[-17:]
        return f"{prefix}{first}\n{rest or ext}"
