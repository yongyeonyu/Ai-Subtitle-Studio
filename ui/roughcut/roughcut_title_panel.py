# Version: 03.01.30
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.style import COLORS, button_style, label_style, panel_style


class RoughcutTitlePanel(QWidget):
    refreshRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suggestions = ()
        self.setStyleSheet(panel_style("surface"))
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 9, 10, 9)
        root.setSpacing(7)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel("추천 유튜브 제목")
        self.title_lbl.setStyleSheet(label_style("text", 12, bold=True))
        head.addWidget(self.title_lbl, stretch=1)
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.setStyleSheet(button_style("toolbar", font_size="10px", padding="4px 8px"))
        self.refresh_btn.clicked.connect(self.refreshRequested.emit)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent; border: none;")
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, stretch=1)
        self.clear()

    def clear(self) -> None:
        self._suggestions = ()
        self._clear_layout()
        empty = QLabel("제목 후보 없음")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(label_style("muted", 11, bold=True))
        self.layout.addWidget(empty, stretch=1)

    def set_suggestions(self, suggestions) -> None:
        self._suggestions = tuple(suggestions or ())
        self._clear_layout()
        if not self._suggestions:
            self.clear()
            return
        for index, suggestion in enumerate(self._suggestions, start=1):
            self.layout.addWidget(self._build_title_card(index, suggestion))
        self.layout.addStretch(1)

    def _build_title_card(self, index: int, suggestion) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #10161A; border: 1px solid #2D3942; border-radius: 7px; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 7, 8, 7)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        rank = QLabel(str(index))
        rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rank.setFixedWidth(24)
        rank.setStyleSheet(
            f"QLabel {{ background: #17251B; color: {COLORS['accent']}; border: 1px solid #2B5A3A; "
            "border-radius: 6px; padding: 3px; font-size: 10px; font-weight: 800; }"
        )
        top.addWidget(rank)
        title = QLabel(str(getattr(suggestion, "title", "") or "-"))
        title.setWordWrap(True)
        title.setStyleSheet(label_style("text", 11, bold=True))
        top.addWidget(title, stretch=1)
        copy_btn = QPushButton("복사")
        copy_btn.setStyleSheet(button_style("toolbar", font_size="10px", padding="4px 8px"))
        title_text = title.text()
        copy_btn.clicked.connect(lambda _checked=False, text=title_text, btn=copy_btn: self._copy_title(text, btn))
        top.addWidget(copy_btn)
        lay.addLayout(top)

        score = float(getattr(suggestion, "score", 0.0) or 0.0)
        reach = str(getattr(suggestion, "expected_reach", "") or "-")
        reason = str(getattr(suggestion, "reason", "") or "근거 없음")
        meta = QLabel(f"예상 조회수 {reach} · 점수 {score:.2f} · {reason}")
        meta.setWordWrap(True)
        meta.setStyleSheet(label_style("muted", 10))
        lay.addWidget(meta)

        tags = tuple(getattr(suggestion, "tags", ()) or ())
        if tags:
            tag_lbl = QLabel(" ".join(f"#{tag}" for tag in tags[:5]))
            tag_lbl.setWordWrap(True)
            tag_lbl.setStyleSheet(label_style("muted", 10))
            lay.addWidget(tag_lbl)
        return card

    def _copy_title(self, text: str, button: QPushButton) -> None:
        QApplication.clipboard().setText(str(text or ""))
        button.setText("복사됨")

    def _clear_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


__all__ = ["RoughcutTitlePanel"]
