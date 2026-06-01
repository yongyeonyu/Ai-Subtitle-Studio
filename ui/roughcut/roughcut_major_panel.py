# Version: 03.02.00
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import QEvent, pyqtSignal, QSize, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.roughcut.roughcut_format import fmt_time
from ui.style import COLORS, button_style, label_style


class _MajorCardListWidget(QListWidget):
    orderChanged = pyqtSignal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setLayoutMode(QListView.LayoutMode.SinglePass)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSpacing(10)
        self.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; margin: 0px; padding: 0px; }"
        )

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        ordered_ids: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            segment_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if segment_id:
                ordered_ids.append(segment_id)
        if ordered_ids:
            self.orderChanged.emit(tuple(ordered_ids))

    def start_drag_for_segment(self, segment_id: str) -> None:
        target = str(segment_id or "")
        if not target:
            return
        for row in range(self.count()):
            item = self.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") != target:
                continue
            previous_mode = self.selectionMode()
            try:
                self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
                self.clearSelection()
                item.setSelected(True)
                self.setCurrentItem(item)
                self.startDrag(Qt.DropAction.MoveAction)
            finally:
                self.clearSelection()
                self.setSelectionMode(previous_mode)
            return


class _MinorCardListWidget(QListWidget):
    orderChanged = pyqtSignal(str, tuple)

    def __init__(self, segment_id: str, parent=None):
        super().__init__(parent)
        self._segment_id = str(segment_id or "")
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(4)
        self.setStyleSheet(
            "QListWidget { background: transparent; border: none; outline: none; }"
            "QListWidget::item { background: transparent; border: none; margin: 0px; padding: 0px; }"
        )

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        ordered_ids: list[str] = []
        for row in range(self.count()):
            item = self.item(row)
            chapter_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if chapter_id:
                ordered_ids.append(chapter_id)
        if ordered_ids:
            self.orderChanged.emit(self._segment_id, tuple(ordered_ids))

    def start_drag_for_chapter(self, chapter_id: str) -> None:
        target = str(chapter_id or "")
        if not target:
            return
        for row in range(self.count()):
            item = self.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") != target:
                continue
            previous_mode = self.selectionMode()
            try:
                self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
                self.clearSelection()
                item.setSelected(True)
                self.setCurrentItem(item)
                self.startDrag(Qt.DropAction.MoveAction)
            finally:
                self.clearSelection()
                self.setSelectionMode(previous_mode)
            return


class _DragHandleLabel(QLabel):
    dragRequested = pyqtSignal()
    dragDelta = pyqtSignal(int)

    def __init__(self, tooltip: str, parent=None, *, axis: str = "vertical"):
        super().__init__("⋮⋮", parent)
        self._press_pos = None
        self._last_pos = None
        self._axis = "horizontal" if str(axis or "").lower().startswith("h") else "vertical"
        self._drag_started = False
        self.setToolTip(str(tooltip or "드래그로 순서 변경"))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedWidth(16)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "QLabel { color: #7F8A94; font-size: 10px; font-weight: 900; "
            "background: transparent; border: none; padding: 0px; }"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._last_pos = self._press_pos
            self._drag_started = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_pos is not None:
            self._last_pos = event.position().toPoint()
        if (
            self._press_pos is not None
            and bool(event.buttons() & Qt.MouseButton.LeftButton)
            and (event.position().toPoint() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()
        ):
            if not self._drag_started:
                self._drag_started = True
                self.dragRequested.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._press_pos is not None and self._last_pos is not None and not self._drag_started:
            delta_value = (
                self._last_pos.x() - self._press_pos.x()
                if self._axis == "horizontal"
                else self._last_pos.y() - self._press_pos.y()
            )
            if abs(delta_value) >= QApplication.startDragDistance():
                self.dragDelta.emit(int(delta_value))
        self._press_pos = None
        self._last_pos = None
        self._drag_started = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class _DragStartFrame(QFrame):
    dragRequested = pyqtSignal()
    dragDelta = pyqtSignal(int)

    def __init__(self, parent=None, *, axis: str = "vertical"):
        super().__init__(parent)
        self._press_pos = None
        self._last_pos = None
        self._axis = "horizontal" if str(axis or "").lower().startswith("h") else "vertical"
        self._drag_started = False

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._last_pos = self._press_pos
            self._drag_started = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_pos is not None:
            self._last_pos = event.position().toPoint()
        if (
            self._press_pos is not None
            and bool(event.buttons() & Qt.MouseButton.LeftButton)
            and (event.position().toPoint() - self._press_pos).manhattanLength() >= QApplication.startDragDistance()
        ):
            if not self._drag_started:
                self._drag_started = True
                self.dragRequested.emit()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._press_pos is not None and self._last_pos is not None and not self._drag_started:
            delta_value = (
                self._last_pos.x() - self._press_pos.x()
                if self._axis == "horizontal"
                else self._last_pos.y() - self._press_pos.y()
            )
            if abs(delta_value) >= QApplication.startDragDistance():
                self.dragDelta.emit(int(delta_value))
        self._press_pos = None
        self._last_pos = None
        self._drag_started = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class RoughcutMajorPanel(QWidget):
    minorSelected = pyqtSignal(str)
    previewRequested = pyqtSignal(str, bool)
    segmentOrderChanged = pyqtSignal(tuple)
    chapterOrderChanged = pyqtSignal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minor_buttons: dict[str, QPushButton] = {}
        self._preview_buttons: dict[str, QPushButton] = {}
        self._card_frames: dict[str, QFrame] = {}
        self._card_topicless: dict[str, bool] = {}
        self._minor_lists: dict[str, _MinorCardListWidget] = {}
        self._segment_items: dict[str, QListWidgetItem] = {}
        self._segment_cards: dict[str, dict[str, object]] = {}
        self._chapter_segment_lookup: dict[str, str] = {}
        self._thumbnail_lookup: dict[str, str] = {}
        self._selected_chapter_id = ""
        self._editor_segments: tuple[dict, ...] = ()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QFrame()
        header.setStyleSheet("QFrame { background: #11181C; border: 1px solid #2D3942; border-radius: 8px; }")
        header_lay = QGridLayout(header)
        header_lay.setContentsMargins(10, 6, 10, 6)
        header_lay.setHorizontalSpacing(8)
        header_lay.setVerticalSpacing(1)
        self.summary_lbl = QLabel("LLM 카드 0 / 세그먼트 0 / 검토 0")
        self.summary_lbl.setStyleSheet(label_style("text", 11, bold=True))
        self.selection_lbl = QLabel("선택 대기")
        self.selection_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.selection_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        self.hint_lbl = QLabel("위 러프컷 제안을 누르면, 아래에서 해당 제안의 카드 세그먼트를 가로로 정리합니다.")
        self.hint_lbl.setStyleSheet(label_style("muted", 9))
        header_lay.addWidget(self.summary_lbl, 0, 0)
        header_lay.addWidget(self.selection_lbl, 0, 1)
        header_lay.addWidget(self.hint_lbl, 1, 0, 1, 2)
        root.addWidget(header)

        self.card_list = _MajorCardListWidget()
        self.card_list.orderChanged.connect(self._on_major_order_changed)
        root.addWidget(self.card_list, stretch=1)
        self.clear()

    def clear(self) -> None:
        self.card_list.clear()
        self._minor_buttons = {}
        self._preview_buttons = {}
        self._card_frames = {}
        self._card_topicless = {}
        self._minor_lists = {}
        self._segment_items = {}
        self._segment_cards = {}
        self._chapter_segment_lookup = {}
        self._thumbnail_lookup = {}
        self._editor_segments = ()
        self.summary_lbl.setText("LLM 카드 0 / 세그먼트 0 / 검토 0")
        self.selection_lbl.setText("선택 대기")
        self._add_empty_card("중분류 분석 결과 없음")

    def set_result(self, result, editor_segments=(), thumbnail_lookup=None) -> None:
        self.card_list.clear()
        self._minor_buttons = {}
        self._preview_buttons = {}
        self._card_frames = {}
        self._card_topicless = {}
        self._minor_lists = {}
        self._segment_items = {}
        self._segment_cards = {}
        self._chapter_segment_lookup = {}
        self._thumbnail_lookup = {
            str(key): str(value)
            for key, value in dict(thumbnail_lookup or {}).items()
            if str(key or "") and str(value or "")
        }
        self._editor_segments = tuple(editor_segments or ())
        segments = tuple(getattr(result, "segments", ()) or ())
        if not segments:
            self.clear()
            return
        chapters_by_id = {
            chapter.chapter_id: chapter
            for chapter in tuple(getattr(result, "chapters", ()) or ())
        }
        for index, segment in enumerate(segments, start=1):
            item = QListWidgetItem()
            segment_id = self._segment_id(segment, index)
            item.setData(Qt.ItemDataRole.UserRole, segment_id)
            card = self._build_major_card(index, segment, chapters_by_id)
            item.setSizeHint(card.sizeHint())
            self.card_list.addItem(item)
            self.card_list.setItemWidget(item, card)
            self._segment_items[segment_id] = item
        minor_count = sum(len(tuple(getattr(segment, "minor_groups", ()) or ())) for segment in segments)
        review_count = sum(
            1
            for chapter in tuple(getattr(result, "chapters", ()) or ())
            if bool(getattr(chapter, "needs_review", False))
        )
        self.summary_lbl.setText(f"LLM 카드 {len(segments)} / 세그먼트 {minor_count} / 검토 {review_count}")
        if self._selected_chapter_id:
            self.set_selected_chapter(self._selected_chapter_id)
        else:
            first = self._first_chapter_id(segments[0])
            if first:
                self.set_selected_chapter(first)

    def set_selected_chapter(self, chapter_id: str) -> None:
        self._selected_chapter_id = str(chapter_id or "")
        for key, button in self._minor_buttons.items():
            button.setStyleSheet(self._minor_button_style(selected=key == self._selected_chapter_id))
        active_card = self._card_frames.get(self._selected_chapter_id)
        for key, frame in self._card_frames.items():
            frame.setStyleSheet(self._card_style(selected=frame is active_card, topicless=self._card_topicless.get(key, False)))
        self._refresh_card_density()
        self.selection_lbl.setText(f"선택 {self._selected_chapter_id}" if self._selected_chapter_id else "선택 대기")

    def _add_empty_card(self, text: str) -> None:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #11181C; border: 1px solid #2D3942; border-radius: 10px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 14, 14, 14)
        empty = QLabel(text)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(label_style("muted", 12, bold=True))
        lay.addWidget(empty)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        item.setSizeHint(frame.sizeHint())
        self.card_list.addItem(item)
        self.card_list.setItemWidget(item, frame)

    def _segment_id(self, segment, index: int) -> str:
        return str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")

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

    def _card_style(self, *, selected: bool, topicless: bool) -> str:
        if topicless:
            background = "#15181C"
            border = "#6B7280" if not selected else "#FFD60A"
        else:
            background = "#11181C" if not selected else "#12261A"
            border = "#2D3942" if not selected else COLORS["accent"]
        return (
            "QFrame { "
            f"background: {background}; border: 1px solid {border}; border-radius: 12px; "
            "} QLabel { background: transparent; }"
        )

    def _build_major_card(self, index: int, segment, chapters_by_id: dict) -> QFrame:
        card = _DragStartFrame(axis="horizontal")
        is_topicless_placeholder = self._is_topicless_cut_placeholder(segment)
        segment_id = self._segment_id(segment, index)
        card.setMinimumWidth(288)
        card.setMaximumWidth(372)
        card.setMinimumHeight(100)
        card.setMaximumHeight(188)
        card.setObjectName("roughcutMajorCardSurface")
        card.setCursor(Qt.CursorShape.OpenHandCursor)
        card.setStyleSheet(self._card_style(selected=False, topicless=is_topicless_placeholder))
        card.dragRequested.connect(lambda sid=segment_id: self.card_list.start_drag_for_segment(sid))
        card.dragDelta.connect(lambda delta, sid=segment_id: self._move_segment_by_drag_delta(sid, delta))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        major_id = getattr(segment, "major_id", "") or f"{chr(64 + min(index, 26))}"
        title = getattr(segment, "title", "") or f"중분류 {major_id}"
        title_lbl = QLabel(f"LLM {major_id} · {title}")
        title_lbl.setStyleSheet(
            "color:#D1D5DB; font-size:12px; font-weight:900; background:transparent;"
            if is_topicless_placeholder
            else label_style("text", 12, bold=True)
        )
        title_lbl.setWordWrap(True)
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        chunk_lbl = QLabel(f"카드 {index}")
        chunk_lbl.setStyleSheet(self._meta_chip_style("accent"))
        chunk_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        status_lbl = QLabel(self._status_text(getattr(segment, "status", "")))
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_lbl.setStyleSheet(self._badge_style(getattr(segment, "status", "")))
        status_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        drag_handle = _DragHandleLabel("카드 드래그로 순서 변경", card, axis="horizontal")
        drag_handle.setObjectName("roughcutMajorDragHandle")
        drag_handle.setFixedWidth(22)
        drag_handle.dragRequested.connect(lambda sid=segment_id: self.card_list.start_drag_for_segment(sid))
        drag_handle.dragDelta.connect(lambda delta, sid=segment_id: self._move_segment_by_drag_delta(sid, delta))
        head.addWidget(title_lbl, stretch=1)
        head.addWidget(chunk_lbl, stretch=0)
        head.addWidget(status_lbl, stretch=0)
        head.addWidget(drag_handle, stretch=0)
        lay.addLayout(head)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addWidget(self._chip_for_segment(segment, is_topicless_placeholder), stretch=0)
        time_lbl = QLabel(f"{fmt_time(segment.start)} - {fmt_time(segment.end)}")
        time_lbl.setStyleSheet(self._meta_chip_style("muted"))
        time_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        meta_row.addWidget(time_lbl, stretch=0)
        minor_count = len(tuple(getattr(segment, "minor_groups", ()) or ()))
        item_lbl = QLabel(f"세그먼트 {minor_count}")
        item_lbl.setStyleSheet(self._meta_chip_style("muted"))
        item_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        meta_row.addWidget(item_lbl, stretch=0)
        meta_row.addStretch(1)
        lay.addLayout(meta_row)

        summary = QLabel(str(getattr(segment, "summary", "") or getattr(segment, "llm_summary", "") or "요약 대기"))
        summary.setWordWrap(True)
        summary.setMaximumHeight(24)
        summary.setStyleSheet(
            "color:#9CA3AF; font-size:8px; background:transparent;"
            if is_topicless_placeholder
            else label_style("muted", 8)
        )
        summary.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(summary)

        section_box = QFrame()
        section_box.setStyleSheet("QFrame { background: #0C1216; border: 1px solid #243038; border-radius: 10px; }")
        section_lay = QVBoxLayout(section_box)
        section_lay.setContentsMargins(6, 4, 6, 4)
        section_lay.setSpacing(2)
        section_head = QHBoxLayout()
        section_head.setContentsMargins(0, 0, 0, 0)
        section_head.setSpacing(4)
        group_title = QLabel("카드 세그먼트")
        group_title.setStyleSheet(label_style("text", 8, bold=True))
        group_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        group_hint = QLabel("썸네일 재생 · 드래그로 순서 변경")
        group_hint.setStyleSheet(label_style("muted", 7))
        group_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        section_head.addWidget(group_title)
        section_head.addWidget(group_hint, stretch=1)
        section_lay.addLayout(section_head)

        minor_groups = tuple(getattr(segment, "minor_groups", ()) or ())
        if minor_groups:
            minor_list = _MinorCardListWidget(segment_id, card)
            minor_list.orderChanged.connect(self._on_minor_order_changed)
            self._minor_lists[segment_id] = minor_list
            for minor in minor_groups:
                chapter_id = (tuple(getattr(minor, "chapter_ids", ()) or ("",))[0] or "").strip()
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, chapter_id)
                row = self._build_minor_row(minor, chapters_by_id, card, is_topicless_placeholder, segment_id)
                item.setSizeHint(row.sizeHint())
                minor_list.addItem(item)
                minor_list.setItemWidget(item, row)
            section_lay.addWidget(minor_list)
        else:
            label = QLabel("소분류 없음")
            label.setStyleSheet(label_style("muted", 10))
            section_lay.addWidget(label)
        lay.addWidget(section_box)
        self._segment_cards[segment_id] = {
            "card": card,
            "summary": summary,
            "section_box": section_box,
            "group_hint": group_hint,
            "minor_list": minor_list if minor_groups else None,
            "minor_count": len(minor_groups),
        }
        self._apply_card_density(segment_id, expanded=False)

        return card

    def _on_minor_order_changed(self, _segment_id: str, _chapter_ids: tuple) -> None:
        self._emit_chapter_order()

    def _on_major_order_changed(self, segment_ids: tuple) -> None:
        self.segmentOrderChanged.emit(tuple(segment_ids))
        self._emit_chapter_order()

    def _emit_chapter_order(self) -> None:
        ordered_ids: list[str] = []
        for row in range(self.card_list.count()):
            item = self.card_list.item(row)
            segment_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            minor_list = self._minor_lists.get(segment_id)
            if minor_list is None:
                continue
            for index in range(minor_list.count()):
                minor_item = minor_list.item(index)
                chapter_id = str(minor_item.data(Qt.ItemDataRole.UserRole) or "")
                if chapter_id:
                    ordered_ids.append(chapter_id)
        if ordered_ids:
            self.chapterOrderChanged.emit(tuple(ordered_ids))

    def _build_minor_row(self, minor, chapters_by_id: dict, card: QFrame, topicless: bool, segment_id: str) -> QFrame:
        chapter_id = (tuple(getattr(minor, "chapter_ids", ()) or ("",))[0] or "").strip()
        chapter = chapters_by_id.get(chapter_id)
        code = getattr(minor, "code", "") or getattr(chapter, "minor_code", "") or "-"
        title = getattr(minor, "title", "") or getattr(chapter, "title", "") or "-"
        status = getattr(minor, "status", "") or getattr(chapter, "boundary_status", "")
        safety = getattr(minor, "safety", "") or "-"

        row_frame = _DragStartFrame()
        row_frame.setObjectName("roughcutMinorRowSurface")
        row_frame.setCursor(Qt.CursorShape.OpenHandCursor)
        row_frame.setStyleSheet("QFrame { background: #0D1418; border: 1px solid #243038; border-radius: 8px; }")
        row_frame.dragRequested.connect(lambda sid=segment_id, cid=chapter_id: self._start_minor_drag(sid, cid))
        row_frame.dragDelta.connect(lambda delta, sid=segment_id, cid=chapter_id: self._move_chapter_by_drag_delta(sid, cid, delta))
        row_lay = QHBoxLayout(row_frame)
        row_lay.setContentsMargins(4, 3, 4, 3)
        row_lay.setSpacing(4)

        thumb_btn = QPushButton()
        thumb_btn.setToolTip("카드 세그먼트 썸네일 재생")
        thumb_btn.setObjectName("roughcutMinorThumbnailButton")
        thumb_btn.setFixedSize(56, 28)
        thumb_btn.setProperty("roughcut_chapter_id", chapter_id)
        thumb_btn.clicked.connect(lambda _checked=False, cid=chapter_id: self.previewRequested.emit(cid, False))
        thumb_btn.installEventFilter(self)
        thumb_btn.setStyleSheet(
            "QPushButton { background: #0A0F12; color: #A9B0B7; border: 1px solid #243038; "
            "border-radius: 7px; padding: 0px; font-size: 9px; font-weight: 700; } "
            "QPushButton:hover { border-color: #34C759; color: #D9FFE3; }"
        )
        self._apply_thumbnail_button(thumb_btn, chapter_id)
        row_lay.addWidget(thumb_btn, stretch=0)

        code_btn = QPushButton(code)
        code_btn.setToolTip("카드 세그먼트 선택")
        code_btn.setStyleSheet(self._minor_button_style(selected=chapter_id == self._selected_chapter_id))
        code_btn.clicked.connect(lambda _checked=False, cid=chapter_id: self.minorSelected.emit(cid))
        row_lay.addWidget(code_btn, stretch=0)
        self._minor_buttons[chapter_id] = code_btn
        if chapter_id:
            self._card_frames[chapter_id] = card
            self._card_topicless[chapter_id] = bool(topicless)

        text_lay = QVBoxLayout()
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(0)
        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setMaximumHeight(12)
        title_lbl.setStyleSheet(label_style("text", 8, bold=True))
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        meta_lbl = QLabel(f"{fmt_time(minor.start)} - {fmt_time(minor.end)} · {self._status_text(status)} · {safety}")
        meta_lbl.setWordWrap(True)
        meta_lbl.setStyleSheet(label_style("muted", 7))
        meta_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lay.addWidget(title_lbl)
        text_lay.addWidget(meta_lbl)
        subtitle_count, subtitle_text = self._subtitle_payload_for_minor(minor, chapter)
        subtitle_row = QHBoxLayout()
        subtitle_row.setContentsMargins(0, 0, 0, 0)
        subtitle_row.setSpacing(4)
        subtitle_badge = QLabel(f"자막 {subtitle_count}")
        subtitle_badge.setObjectName("roughcutSubtitleCountBadge")
        subtitle_badge.setStyleSheet(self._meta_chip_style("muted"))
        subtitle_badge.setMinimumWidth(42)
        subtitle_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        subtitle_lbl = QLabel(subtitle_text)
        subtitle_lbl.setObjectName("roughcutSubtitleSnippetLabel")
        subtitle_lbl.setWordWrap(True)
        subtitle_lbl.setMaximumHeight(18)
        subtitle_lbl.setStyleSheet(label_style("muted", 7))
        subtitle_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        subtitle_row.addWidget(subtitle_badge, stretch=0)
        subtitle_row.addWidget(subtitle_lbl, stretch=1)
        text_lay.addLayout(subtitle_row)
        row_lay.addLayout(text_lay, stretch=1)
        drag_handle = _DragHandleLabel("카드 세그먼트 드래그로 순서 변경", row_frame)
        drag_handle.setObjectName("roughcutMinorDragHandle")
        drag_handle.setFixedWidth(22)
        drag_handle.dragRequested.connect(lambda cid=chapter_id, sid=segment_id: self._start_minor_drag(sid, cid))
        drag_handle.dragDelta.connect(lambda delta, cid=chapter_id, sid=segment_id: self._move_chapter_by_drag_delta(sid, cid, delta))
        row_lay.addWidget(drag_handle, stretch=0)
        self._preview_buttons[chapter_id] = thumb_btn
        self._chapter_segment_lookup[chapter_id] = str(segment_id or "")
        return row_frame

    def _start_minor_drag(self, segment_id: str, chapter_id: str) -> None:
        minor_list = self._minor_lists.get(str(segment_id or ""))
        if minor_list is None:
            return
        minor_list.start_drag_for_chapter(chapter_id)

    def _move_segment_by_drag_delta(self, segment_id: str, delta_y: int) -> None:
        order: list[str] = []
        for row in range(self.card_list.count()):
            item = self.card_list.item(row)
            value = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if value:
                order.append(value)
        target_id = str(segment_id or "")
        if target_id not in order:
            return
        step_size = 72
        steps = max(1, int(round(abs(int(delta_y)) / step_size)))
        current_index = order.index(target_id)
        target_index = max(0, min(len(order) - 1, current_index + (steps if delta_y > 0 else -steps)))
        if target_index == current_index:
            return
        moving = order.pop(current_index)
        order.insert(target_index, moving)
        self.segmentOrderChanged.emit(tuple(order))

    def _move_chapter_by_drag_delta(self, segment_id: str, chapter_id: str, delta_y: int) -> None:
        minor_list = self._minor_lists.get(str(segment_id or ""))
        if minor_list is None:
            return
        order: list[str] = []
        for row in range(minor_list.count()):
            item = minor_list.item(row)
            value = str(item.data(Qt.ItemDataRole.UserRole) or "")
            if value:
                order.append(value)
        target_id = str(chapter_id or "")
        if target_id not in order:
            return
        step_size = 32
        steps = max(1, int(round(abs(int(delta_y)) / step_size)))
        current_index = order.index(target_id)
        target_index = max(0, min(len(order) - 1, current_index + (steps if delta_y > 0 else -steps)))
        if target_index == current_index:
            return
        moving = order.pop(current_index)
        order.insert(target_index, moving)
        self.chapterOrderChanged.emit(tuple(order))

    def _refresh_card_density(self) -> None:
        active_segment_id = self._chapter_segment_lookup.get(self._selected_chapter_id, "")
        if not active_segment_id and self.card_list.count():
            item = self.card_list.item(0)
            active_segment_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        for segment_id in self._segment_cards:
            self._apply_card_density(segment_id, expanded=segment_id == active_segment_id)

    def _apply_card_density(self, segment_id: str, *, expanded: bool) -> None:
        config = self._segment_cards.get(segment_id) or {}
        card = config.get("card")
        summary = config.get("summary")
        section_box = config.get("section_box")
        group_hint = config.get("group_hint")
        minor_list = config.get("minor_list")
        minor_count = int(config.get("minor_count") or 0)
        visible_rows = 1
        row_height = 26 if expanded else 24
        if isinstance(minor_list, _MinorCardListWidget):
            if expanded:
                visible_rows = min(4, max(1, minor_count))
            else:
                visible_rows = 1
        if isinstance(card, QFrame):
            extra_rows = max(0, visible_rows - 1)
            card.setFixedWidth(360 if expanded else 304)
            card.setFixedHeight((126 if expanded else 100) + (extra_rows * (row_height + 4)))
        if isinstance(summary, QLabel):
            summary.setVisible(expanded)
        if isinstance(section_box, QFrame):
            section_box.setVisible(True)
        if isinstance(group_hint, QLabel):
            group_hint.setVisible(expanded)
        if isinstance(minor_list, _MinorCardListWidget):
            minor_list.setMinimumHeight((row_height * visible_rows) + 8)
            minor_list.setMaximumHeight((row_height * visible_rows) + 10)
        item = self._segment_items.get(segment_id)
        if item is not None and isinstance(card, QFrame):
            card.adjustSize()
            width = max(int(card.width() or 0), int(card.sizeHint().width() or 0))
            item.setSizeHint(QSize(width, card.height()))
            self.card_list.updateGeometries()

    def _apply_thumbnail_button(self, button: QPushButton, chapter_id: str) -> None:
        thumb_path = str(self._thumbnail_lookup.get(str(chapter_id or ""), "") or "")
        if thumb_path:
            pixmap = QPixmap(thumb_path)
            if not pixmap.isNull():
                button.setIconSize(QSize(max(0, button.width() - 4), max(0, button.height() - 4)))
                button.setIcon(QIcon(pixmap))
                button.setText("")
                return
        button.setIcon(QIcon())
        button.setText(f"썸네일\n{chapter_id or '-'}")

    def _subtitle_snippets_for_segment(self, segment, chapters_by_id: dict) -> list[str]:
        snippets: list[str] = []
        chapter_ids: list[str] = []
        for minor in tuple(getattr(segment, "minor_groups", ()) or ()):
            chapter_ids.extend([str(chapter_id or "") for chapter_id in tuple(getattr(minor, "chapter_ids", ()) or ()) if str(chapter_id or "")])
        if chapter_ids:
            for chapter_id in chapter_ids[:3]:
                chapter = chapters_by_id.get(chapter_id)
                if chapter is None:
                    continue
                for snippet in self._subtitle_snippets(float(chapter.start), float(chapter.end), limit=2):
                    if snippet not in snippets:
                        snippets.append(snippet)
                    if len(snippets) >= 4:
                        return snippets
        return self._subtitle_snippets(float(segment.start), float(segment.end), limit=4)

    def _subtitle_payload_for_minor(self, minor, chapter) -> tuple[int, str]:
        start = float(getattr(chapter, "start", getattr(minor, "start", 0.0)) or 0.0)
        end = float(getattr(chapter, "end", getattr(minor, "end", start)) or start)
        snippets = self._subtitle_snippets(start, end, limit=2)
        count = self._subtitle_overlap_count(start, end)
        if not snippets:
            return max(0, count), "자막 세그먼트 없음"
        return max(len(snippets), count), " / ".join(snippets)

    def _subtitle_snippets(self, start: float, end: float, limit: int = 3) -> list[str]:
        snippets: list[str] = []
        for segment in self._editor_segments:
            seg_start = float(segment.get("start", 0.0) or 0.0)
            seg_end = float(segment.get("end", seg_start) or seg_start)
            if seg_end <= start or seg_start >= end:
                continue
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            if len(text) > 42:
                text = text[:39].rstrip() + "..."
            snippets.append(text)
            if len(snippets) >= limit:
                break
        return snippets

    def _subtitle_overlap_count(self, start: float, end: float) -> int:
        count = 0
        for segment in self._editor_segments:
            seg_start = float(segment.get("start", 0.0) or 0.0)
            seg_end = float(segment.get("end", seg_start) or seg_start)
            if seg_end <= start or seg_start >= end:
                continue
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            count += 1
        return count

    def _chip_for_segment(self, segment, topicless: bool) -> QLabel:
        label = QLabel(
            "컷경계"
            if topicless
            else (str(getattr(segment, "llm_label", "") or getattr(segment, "segment_type", "") or "LLM 분류"))
        )
        label.setStyleSheet(self._meta_chip_style("accent"))
        return label

    def _clear_layout(self) -> None:
        self.card_list.clear()

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
            return "대표 썸네일 재생"
        return f"대표 장면 재생 · {fmt_time(segment.start)}"

    def _minor_button_style(self, *, selected: bool = False) -> str:
        base = button_style("toolbar", font_size="10px", padding="5px 9px")
        if not selected:
            return base
        return base + f" QPushButton {{ background: #173D28; border-color: {COLORS['accent']}; color: #D9FFE3; }}"

    def _meta_chip_style(self, tone: str) -> str:
        if tone == "accent":
            color = "#D9FFE3"
            border = COLORS["accent"]
            background = "#123322"
        else:
            color = "#B8C0C8"
            border = "#2D3942"
            background = "#10161A"
        return (
            "QLabel { "
            f"background: {background}; color: {color}; border: 1px solid {border}; "
            "border-radius: 7px; padding: 4px 7px; font-size: 10px; font-weight: 700; }"
        )

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
