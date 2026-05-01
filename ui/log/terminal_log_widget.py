# Version: 03.01.04
# Phase: PHASE2
"""Terminal log panel widget."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from ui.style import named_panel_style


class TerminalLogWidget(QWidget):
    """Terminal log panel that owns the QTextEdit used by MainWindow logging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TerminalLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("TerminalLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Menlo", 8))
        self.log_text.document().setMaximumBlockCount(800)
        self.log_text.setStyleSheet(
            "background: #151C20; color: #A9B0B7; border: none; padding: 4px 8px;"
        )
        layout.addWidget(self.log_text)
