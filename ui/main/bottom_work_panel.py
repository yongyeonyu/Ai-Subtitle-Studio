# Version: 03.01.04
# Phase: PHASE2
"""Bottom terminal and queue/roughcut panel assembly."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from core.settings import load_settings
from ui.log.terminal_log_widget import TerminalLogWidget
from ui.queue.queue_panel_widget import QueuePanelWidget
from ui.roughcut.roughcut_table_panel import RoughcutTablePanel
from ui.style import named_panel_style


class BottomWorkPanel(QWidget):
    """Bottom area that switches between queue and roughcut panels beside the terminal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("BottomLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        toggle_bar = QWidget()
        toggle_bar.setFixedHeight(0)
        toggle_bar.setStyleSheet("background: transparent; border: none;")
        tb_layout = QHBoxLayout(toggle_bar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        self.log_toggle_btn = QLabel("")
        layout.addWidget(toggle_bar)

        self.log_content = QWidget()
        self.log_content.setFixedHeight(190)
        content_layout = QVBoxLayout(self.log_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.log_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.log_splitter.setHandleWidth(2)
        self.log_splitter.setStyleSheet(
            "QSplitter::handle { background: #2D3942; width: 2px; }"
        )

        self.terminal_panel = TerminalLogWidget(self)
        self.bottom_right_stack = QStackedWidget(self)
        self.queue_panel = QueuePanelWidget(self)
        self.roughcut_panel = RoughcutTablePanel(self)
        self.bottom_right_stack.addWidget(self.queue_panel)
        self.bottom_right_stack.addWidget(self.roughcut_panel)

        self.log_splitter.addWidget(self.terminal_panel)
        self.log_splitter.addWidget(self.bottom_right_stack)
        self.log_splitter.setStretchFactor(0, 1)
        self.log_splitter.setStretchFactor(1, 1)
        self.log_splitter.setSizes([500, 500])
        content_layout.addWidget(self.log_splitter)
        layout.addWidget(self.log_content)

        settings = load_settings()
        self.log_visible = bool(settings.get("show_terminal_log", False))
        self.set_log_visible(self.log_visible)

    @property
    def log_text(self):
        return self.terminal_panel.log_text

    @property
    def queue_header_lbl(self):
        return self.queue_panel.queue_header_lbl

    @property
    def queue_table(self):
        return self.queue_panel.queue_table

    @property
    def roughcut_bottom_header_lbl(self):
        return self.roughcut_panel.roughcut_bottom_header_lbl

    @property
    def roughcut_bottom_host(self):
        return self.roughcut_panel.roughcut_bottom_host

    @property
    def roughcut_bottom_host_layout(self):
        return self.roughcut_panel.roughcut_bottom_host_layout

    def set_log_visible(self, visible: bool):
        self.log_visible = bool(visible)
        self.log_content.setVisible(self.log_visible)
        self.log_toggle_btn.setText("▼ 터미널 로그 숨기기" if self.log_visible else "▲ 터미널 로그 보기")

    def set_roughcut_widget(self, widget: QWidget):
        self.roughcut_panel.set_content_widget(widget)
        self.show_roughcut_table()

    def show_queue_table(self):
        self.bottom_right_stack.setCurrentWidget(self.queue_panel)

    def show_roughcut_table(self):
        self.bottom_right_stack.setCurrentWidget(self.roughcut_panel)
