# Version: 03.02.10
# Phase: PHASE2
"""Bottom queue/roughcut panel assembly."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from ui.queue.queue_panel_widget import QueuePanelWidget
from ui.roughcut.roughcut_table_panel import RoughcutTablePanel
from ui.style import named_panel_style


class BottomWorkPanel(QWidget):
    """Bottom area that switches between queue and roughcut panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomLogPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("BottomLogPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

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

        self.log_splitter = self.log_content
        self.bottom_right_stack = QStackedWidget(self)
        self.queue_panel = QueuePanelWidget(self)
        self.roughcut_panel = RoughcutTablePanel(self)
        self.bottom_right_stack.addWidget(self.queue_panel)
        self.bottom_right_stack.addWidget(self.roughcut_panel)
        content_layout.addWidget(self.bottom_right_stack)
        layout.addWidget(self.log_content)
        self.log_visible = True

    @property
    def log_text(self):
        return None

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
        self.log_visible = True
        self.log_content.setVisible(True)
        self.log_toggle_btn.setText("")

    def set_roughcut_widget(self, widget: QWidget):
        self.roughcut_panel.set_content_widget(widget)
        self.show_roughcut_table()

    def show_queue_table(self):
        self.bottom_right_stack.setCurrentWidget(self.queue_panel)

    def show_roughcut_table(self):
        self.bottom_right_stack.setCurrentWidget(self.roughcut_panel)
