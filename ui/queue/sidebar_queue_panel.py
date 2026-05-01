# Version: 03.04.01
# Phase: PHASE2
"""Sidebar queue summary panel with a Qt Quick front-end and QWidget fallback."""

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SidebarQueuePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarQueuePanel")
        self.setMinimumHeight(134)
        self.setMaximumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._quick = None
        self._header = "큐 리스트 : (0/0) - 0% 완료"
        self._items = []

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
            "QLabel { background: #11181C; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-bottom: none; border-top-left-radius: 7px; border-top-right-radius: 7px; "
            "padding: 6px 8px; font-size: 10px; font-weight: 800; }"
        )
        layout.addWidget(self._header_lbl)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["순서", "파일명", "예상시간"])
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 36)
        self._table.setColumnWidth(2, 68)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(
            "QTableWidget { background: #11181C; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-top: none; border-bottom-left-radius: 7px; border-bottom-right-radius: 7px; "
            "font-size: 9px; } "
            "QHeaderView::section { background: #151C20; color: #8E98A3; border: none; padding: 3px; } "
            "QTableWidget::item { padding: 2px 3px; }"
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
        self._header = str(header or "큐 리스트 : (0/0) - 0% 완료")
        self._items = list(items or [])
        if self._quick is not None:
            root = self._quick.rootObject()
            if root is not None:
                root.setProperty("headerText", self._header)
                root.setProperty("queueItems", self._items)
            return

        self._header_lbl.setText(self._header)
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(0)
        for row, item in enumerate(self._items):
            self._table.insertRow(row)
            done = bool(item.get("done")) or "완료" in str(item.get("status", "") or "")
            row_color = "#34C759" if done else "#FFCC44"
            for col, key in enumerate(("order", "file", "eta")):
                cell = QTableWidgetItem(str(item.get(key, "") or "-"))
                cell.setForeground(QColor(row_color))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col == 0 else Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, col, cell)
            self._table.setRowHeight(row, 36)
        self._table.setUpdatesEnabled(True)
