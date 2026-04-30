# Version: 03.01.05
# Phase: PHASE2
"""Bottom roughcut table host panel."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.style import label_style, named_panel_style


class RoughcutTablePanel(QWidget):
    """Host panel for the active roughcut table/control widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BottomRoughcutPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(named_panel_style("BottomRoughcutPanel", "surface", radius=7))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.setSpacing(4)

        self.roughcut_bottom_header_lbl = QLabel("✂ 러프컷 테이블")
        self.roughcut_bottom_header_lbl.setStyleSheet(label_style("normal", 9, bold=True))
        layout.addWidget(self.roughcut_bottom_header_lbl)

        self.roughcut_bottom_host = QWidget()
        self._roughcut_widget = None
        self.roughcut_bottom_host_layout = QVBoxLayout(self.roughcut_bottom_host)
        self.roughcut_bottom_host_layout.setContentsMargins(0, 0, 0, 0)
        self.roughcut_bottom_host_layout.setSpacing(0)

        placeholder = QLabel("러프컷 화면을 열면 분석/출력/구간 재생 패널이 표시됩니다.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet(label_style("muted", 10))
        self.roughcut_bottom_host_layout.addWidget(placeholder)
        layout.addWidget(self.roughcut_bottom_host, stretch=1)

    def set_content_widget(self, widget: QWidget):
        if widget is None:
            return
        self._roughcut_widget = widget
        while self.roughcut_bottom_host_layout.count():
            item = self.roughcut_bottom_host_layout.takeAt(0)
            old = item.widget()
            if old is not None and old is not widget:
                old.setParent(None)
        self.roughcut_bottom_host_layout.addWidget(widget)
