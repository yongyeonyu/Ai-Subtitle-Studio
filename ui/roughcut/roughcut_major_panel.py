# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import QEvent, pyqtSignal, Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ui.roughcut.roughcut_format import fmt_time
from ui.style import COLORS, button_style, label_style, panel_style


class RoughcutMajorPanel(QWidget):
    minorSelected = pyqtSignal(str)
    previewRequested = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minor_buttons: dict[str, QPushButton] = {}
        self._preview_buttons: dict[str, QPushButton] = {}
        self._selected_chapter_id = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.body = QWidget()
        self.body.setStyleSheet("background: transparent; border: none;")
        self.layout = QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll)
        self.clear()

    def clear(self) -> None:
        self._clear_layout()
        self._minor_buttons = {}
        self._preview_buttons = {}
        empty = QLabel("중분류 분석 결과 없음")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(label_style("muted", 12, bold=True))
        self.layout.addWidget(empty, stretch=1)

    def set_result(self, result) -> None:
        self._clear_layout()
        self._minor_buttons = {}
        self._preview_buttons = {}
        segments = tuple(getattr(result, "segments", ()) or ())
        if not segments:
            self.clear()
            return
        chapters_by_id = {
            chapter.chapter_id: chapter
            for chapter in tuple(getattr(result, "chapters", ()) or ())
        }
        for index, segment in enumerate(segments, start=1):
            self.layout.addWidget(self._build_major_card(index, segment, chapters_by_id))
        self.layout.addStretch(1)
        if self._selected_chapter_id:
            self.set_selected_chapter(self._selected_chapter_id)

    def set_selected_chapter(self, chapter_id: str) -> None:
        self._selected_chapter_id = str(chapter_id or "")
        for key, button in self._minor_buttons.items():
            button.setStyleSheet(self._minor_button_style(selected=key == self._selected_chapter_id))


    def _is_topicless_cut_placeholder(self, segment) -> bool:
        title = str(getattr(segment, "title", "") or "")
        summary = str(getattr(segment, "summary", "") or "")
        status = str(getattr(segment, "status", "") or "")
        tags = tuple(getattr(segment, "tags", ()) or ())
        return (
            title == "주제없음"
            or "주제없음" in summary
            or "주제없음" in tags
            or (status == "provisional" and "컷경계" in tags)
        )

    def _topicless_card_style(self) -> str:
        return (
            "QFrame { background:#15181C; border:1px solid #4A4F55; border-radius:9px; } "
            "QLabel { background:transparent; }"
        )


    def _build_major_card(self, index: int, segment, chapters_by_id: dict) -> QFrame:
        card = QFrame()
        is_topicless_placeholder = self._is_topicless_cut_placeholder(segment)
        card.setStyleSheet(self._topicless_card_style() if is_topicless_placeholder else panel_style("surface"))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(7)

        head = QGridLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setHorizontalSpacing(8)
        major_id = getattr(segment, "major_id", "") or f"{chr(64 + min(index, 26))}"
        title = getattr(segment, "title", "") or f"중분류 {major_id}"
        title_lbl = QLabel(f"{major_id} | {title}")
        title_lbl.setStyleSheet(
            "color:#D1D5DB; font-size:13px; font-weight:800; background:transparent;"
            if is_topicless_placeholder
            else label_style("text", 13, bold=True)
        )
        title_lbl.setWordWrap(True)
        time_lbl = QLabel(f"{fmt_time(segment.start)} - {fmt_time(segment.end)}")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        status_lbl = QLabel(self._status_text(getattr(segment, "status", "")))
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_lbl.setStyleSheet(self._badge_style(getattr(segment, "status", "")))
        head.addWidget(title_lbl, 0, 0, 1, 2)
        head.addWidget(time_lbl, 0, 2)
        head.addWidget(status_lbl, 0, 3)
        lay.addLayout(head)

        summary = QLabel(str(getattr(segment, "summary", "") or getattr(segment, "llm_summary", "") or "요약 대기"))
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "color:#9CA3AF; font-size:10px; background:transparent;"
            if is_topicless_placeholder
            else label_style("muted", 10)
        )
        lay.addWidget(summary)

        tags = ", ".join(getattr(segment, "tags", ()) or ())
        meta = QLabel(
            f"확신 {float(getattr(segment, 'boundary_confidence', 0.0) or 0.0):.2f}"
            f" · 안전 {getattr(segment, 'safety', '-')}"
            f" · 중요 {float(max(getattr(segment, 'importance', 0.0) or 0.0, getattr(segment, 'importance_score', 0.0) or 0.0)):.2f}"
            + (f" · {tags}" if tags else "")
        )
        meta.setWordWrap(True)
        meta.setStyleSheet(label_style("muted", 10))
        lay.addWidget(meta)

        preview_id = self._first_chapter_id(segment)
        preview_btn = QPushButton(self._thumbnail_text(segment))
        preview_btn.setMinimumHeight(54)
        preview_btn.setToolTip("중분류 preview")
        preview_btn.setMouseTracking(True)
        preview_btn.setStyleSheet(
            "QPushButton { background: #0A0F12; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-radius: 7px; padding: 6px; font-size: 10px; font-weight: 700; text-align: center; } "
            "QPushButton:hover { background: #13221A; border-color: #34C759; color: #D9FFE3; }"
        )
        preview_btn.clicked.connect(lambda _checked=False, cid=preview_id: self.previewRequested.emit(cid, False))
        preview_btn.installEventFilter(self)
        preview_btn.setProperty("roughcut_chapter_id", preview_id)
        self._preview_buttons[preview_id] = preview_btn
        lay.addWidget(preview_btn)

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        headers = ("소분류", "시간", "주제", "상태", "확신/안전/중요")
        for col, text in enumerate(headers):
            label = QLabel(text)
            label.setStyleSheet(label_style("muted", 9, bold=True))
            grid.addWidget(label, 0, col)
        minor_groups = tuple(getattr(segment, "minor_groups", ()) or ())
        if minor_groups:
            for row, minor in enumerate(minor_groups, start=1):
                self._add_minor_row(grid, row, minor, chapters_by_id)
        else:
            label = QLabel("소분류 없음")
            label.setStyleSheet(label_style("muted", 10))
            grid.addWidget(label, 1, 0, 1, 5)
        lay.addLayout(grid)
        return card

    def _add_minor_row(self, grid: QGridLayout, row: int, minor, chapters_by_id: dict) -> None:
        chapter_id = (tuple(getattr(minor, "chapter_ids", ()) or ("",))[0] or "").strip()
        chapter = chapters_by_id.get(chapter_id)
        code = getattr(minor, "code", "") or getattr(chapter, "minor_code", "") or "-"
        title = getattr(minor, "title", "") or getattr(chapter, "title", "") or "-"
        status = getattr(minor, "status", "") or getattr(chapter, "boundary_status", "")
        confidence = float(getattr(minor, "confidence", 0.0) or getattr(chapter, "confidence", 0.0) or 0.0)
        safety = getattr(minor, "safety", "") or "-"
        importance = float(getattr(chapter, "importance_score", 0.0) or 0.0)

        code_btn = QPushButton(code)
        code_btn.setToolTip("소분류 행 선택")
        code_btn.setStyleSheet(self._minor_button_style(selected=chapter_id == self._selected_chapter_id))
        code_btn.clicked.connect(lambda _checked=False, cid=chapter_id: self.minorSelected.emit(cid))
        grid.addWidget(code_btn, row, 0)
        self._minor_buttons[chapter_id] = code_btn

        values = (
            f"{fmt_time(minor.start)} - {fmt_time(minor.end)}",
            title,
            self._status_text(status),
            f"{confidence:.2f} / {safety} / {importance:.2f}",
        )
        for col, value in enumerate(values, start=1):
            label = QLabel(value)
            label.setWordWrap(True)
            label.setStyleSheet(label_style("text" if col == 2 else "muted", 10, bold=col == 2))
            if col in (1, 3, 4):
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, row, col)

    def _clear_layout(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Enter:
            chapter_id = str(watched.property("roughcut_chapter_id") or "")
            if chapter_id:
                self.previewRequested.emit(chapter_id, True)
        return False

    def _first_chapter_id(self, segment) -> str:
        for minor in tuple(getattr(segment, "minor_groups", ()) or ()):
            chapter_ids = tuple(getattr(minor, "chapter_ids", ()) or ())
            if chapter_ids:
                return str(chapter_ids[0])
        return str(getattr(segment, "segment_id", "") or "")

    def _thumbnail_text(self, segment) -> str:
        thumb = getattr(segment, "thumbnail_path", "") or ""
        if thumb:
            return f"썸네일\n{thumb}"
        return f"Hover Preview\n{fmt_time(segment.start)}"

    def _minor_button_style(self, *, selected: bool = False) -> str:
        base = button_style("toolbar", font_size="10px", padding="4px 7px")
        if not selected:
            return base
        return base + f" QPushButton {{ background: #173D28; border-color: {COLORS['accent']}; color: #D9FFE3; }}"

    def _status_text(self, status: str) -> str:
        return {
            "reading": "읽는 중",
            "confirmed": "확정",
            "provisional": "임시",
            "needs_review": "검토",
        }.get(str(status or ""), str(status or "-"))

    def _badge_style(self, status: str) -> str:
        color = COLORS["muted"]
        border = COLORS["separator"]
        if status == "confirmed":
            color = "#9AF0B0"
            border = "#2B5A3A"
        elif status == "reading":
            color = "#BBDFFF"
            border = "#24527A"
        elif status == "needs_review":
            color = COLORS["warning"]
            border = COLORS["warning_border"]
        return (
            "QLabel { background: #10161A; "
            f"color: {color}; border: 1px solid {border}; border-radius: 6px; "
            "padding: 4px 7px; font-size: 10px; font-weight: 700; }"
        )


__all__ = ["RoughcutMajorPanel"]
