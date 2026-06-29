# Version: 03.01.04
# Phase: PHASE2
"""Main workspace stack widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QStackedWidget

from ui.style import COLORS, app_stylesheet


class MainWorkspaceStack(QStackedWidget):
    """Center workspace stack with object-scoped panel styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWorkspaceStack")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            app_stylesheet()
            + (
                "#MainWorkspaceStack { "
                f"background: {COLORS['sidebar']}; "
                "border: none; "
                "border-radius: 0px; "
                "} "
            )
        )
