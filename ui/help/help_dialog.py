# Version: 03.00.27
# Phase: PHASE2
"""Tabbed in-app help dialog."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.help.help_content import HELP_TABS
from ui.style import COLORS, button_style, label_style, settings_dialog_stylesheet


class HelpDialog(QDialog):
    """Feature guide with tabbed categories and reserved screenshot slots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("도움말")
        self.setMinimumSize(860, 620)
        self.resize(980, 700)
        self.setStyleSheet(settings_dialog_stylesheet())
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("AI Subtitle Studio 도움말")
        title.setStyleSheet(label_style("text", 18, bold=True))
        subtitle = QLabel("현재 구현된 기능을 카테고리별로 정리했습니다. 이미지 영역은 추후 화면 예시를 넣을 자리입니다.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(label_style("muted", 11))
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.setStyleSheet(button_style("toolbar"))
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        for tab in HELP_TABS:
            self.tabs.addTab(self._build_tab(tab), tab["title"])
        root.addWidget(self.tabs, stretch=1)

    def _build_tab(self, tab):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        summary = QLabel(tab.get("summary", ""))
        summary.setWordWrap(True)
        summary.setStyleSheet(label_style("text", 13, bold=True))
        layout.addWidget(summary)

        layout.addWidget(self._section("사용 방법", tab.get("steps", [])))
        layout.addWidget(self._section("사용 예시", tab.get("examples", [])))
        layout.addWidget(self._section("단축키 / 특정 상황", tab.get("shortcuts", [])))
        layout.addWidget(self._screenshot_placeholder())
        layout.addStretch()

        scroll.setWidget(body)
        return scroll

    def _section(self, title, items):
        container = QFrame()
        container.setObjectName("HelpSection")
        container.setStyleSheet(
            "QFrame#HelpSection { "
            f"background: {COLORS['surface']}; border: 1px solid {COLORS['separator']}; "
            "border-radius: 7px; "
            "}"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        heading = QLabel(title)
        heading.setStyleSheet(label_style("info", 12, bold=True))
        layout.addWidget(heading)

        for idx, item in enumerate(items, 1):
            line = QLabel(f"{idx}. {item}")
            line.setWordWrap(True)
            line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            line.setStyleSheet(label_style("text", 11))
            layout.addWidget(line)
        return container

    def _screenshot_placeholder(self):
        frame = QFrame()
        frame.setObjectName("HelpScreenshotPlaceholder")
        frame.setMinimumHeight(150)
        frame.setStyleSheet(
            "QFrame#HelpScreenshotPlaceholder { "
            "background: #10161A; border: 1px dashed #465663; border-radius: 7px; "
            "}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        label = QLabel("스크린샷 자리")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(label_style("muted", 12, bold=True))
        note = QLabel("추후 실제 화면 캡처, 오류 상황 예시, 단계별 이미지가 들어갈 공간입니다.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet(label_style("muted", 10))
        layout.addStretch()
        layout.addWidget(label)
        layout.addWidget(note)
        layout.addStretch()
        return frame
