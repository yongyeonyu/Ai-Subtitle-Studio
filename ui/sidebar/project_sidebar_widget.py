# Version: 03.01.04
# Phase: PHASE2
"""Project sidebar shell widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from ui.style import named_panel_style


class ProjectSidebarWidget(QWidget):
    """Left project sidebar container with shared panel styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectSidebarPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(204)
        self.setMaximumWidth(218)
        self.setStyleSheet(named_panel_style("ProjectSidebarPanel", "sidebar", radius=0))
