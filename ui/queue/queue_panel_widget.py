# Version: 03.01.04
# Phase: PHASE2
"""Bottom queue table panel widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QHeaderView, QTableWidget, QVBoxLayout, QWidget

from ui.queue.queue_formatting import DEFAULT_QUEUE_HEADER
from ui.style import COLORS, label_style, named_panel_style


class QueuePanelWidget(QWidget):
    """Queue table panel with the header/table controls kept together."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomQueuePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("BottomQueuePanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)

        self.queue_header_lbl = QLabel(DEFAULT_QUEUE_HEADER)
        self.queue_header_lbl.setStyleSheet(label_style("normal", 9, bold=True))
        layout.addWidget(self.queue_header_lbl)

        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(
            ["  상태  ", "  파일명  ", "  영상정보  ", "  영상길이  ", "  예상시간  "]
        )
        self.queue_table.setWordWrap(True)
        self.queue_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.queue_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Fixed
        )
        self.queue_table.setColumnWidth(4, 140)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.queue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_table.setShowGrid(True)
        self.queue_table.setGridStyle(Qt.PenStyle.SolidLine)
        # Keep this QSS syntactically strict; Qt logs parser warnings for unmatched braces during startup.
        self.queue_table.setStyleSheet(
            f"QTableWidget {{ background: {COLORS['surface']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['separator']}; border-radius: 6px; font-size: 11px; gridline-color: #3A4650; }} "
            "QTableWidget::item { padding: 2px 8px; } "
            f"QHeaderView::section {{ background: {COLORS['surface_alt']}; color: {COLORS['muted']}; "
            "border: none; border-right: 1px solid #3A4650; "
            "border-bottom: 1px solid #3A4650; padding: 3px 8px; }"
        )
        layout.addWidget(self.queue_table)
