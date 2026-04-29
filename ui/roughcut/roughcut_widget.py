# Version: 03.00.34
# Phase: PHASE2
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.roughcut.roughcut_export import RoughcutExportMixin
from ui.roughcut.roughcut_format import TABLE_COLUMNS
from ui.roughcut.roughcut_preview import RoughcutPreviewMixin
from ui.roughcut.roughcut_state import RoughcutStateMixin
from ui.roughcut.roughcut_table import RoughcutTableMixin
from ui.style import COLORS, button_style, label_style, panel_style


class RoughcutWidget(
    RoughcutExportMixin,
    RoughcutPreviewMixin,
    RoughcutTableMixin,
    RoughcutStateMixin,
    QWidget,
):
    def __init__(self, owner=None, parent=None):
        super().__init__(parent)
        self.owner = owner
        self._result = None
        self._source_signature = ""
        self._row_chapter_ids: list[str] = []
        self._user_edits: dict[str, dict[str, str]] = {}
        self._updating_table = False
        self._preview_row = -1
        self._preview_end = 0.0
        self._preview_deadline_ms = 0
        self._preview_is_hover = False
        self._restore_volume: float | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._preview_tick)
        self.setStyleSheet(f"background: {COLORS['bg']}; color: {COLORS['text']};")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.bottom_panel = self._build_bottom_panel()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("QSplitter::handle { background: #0F1518; height: 2px; }")
        root.addWidget(splitter, stretch=1)

        self.table = self._build_table()
        splitter.addWidget(self.table)

        self.guide_text = QTextEdit()
        self.guide_text.setReadOnly(True)
        self.guide_text.setStyleSheet(
            "QTextEdit { background: #11181C; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 7px; padding: 10px; font-size: 11px; }"
        )
        splitter.addWidget(self.guide_text)
        splitter.setSizes([520, 260])

        self._set_empty_state()

    def _build_bottom_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self._build_toolbar())
        lay.addWidget(self._build_metrics())
        lay.addWidget(self._build_preview())
        return panel

    def _build_toolbar(self) -> QWidget:
        top = QWidget()
        top.setStyleSheet(panel_style("surface"))
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(12, 8, 12, 8)
        top_lay.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.title_lbl = QLabel("러프컷")
        self.title_lbl.setStyleSheet(label_style("text", 15, bold=True))
        self.source_lbl = QLabel("대기 중")
        self.source_lbl.setStyleSheet(label_style("muted", 10))
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.source_lbl)
        top_lay.addLayout(title_box, stretch=1)

        self.btn_refresh = QPushButton("분석")
        self.btn_refresh.setStyleSheet(button_style("primary", font_size="12px", padding="7px 14px"))
        self.btn_refresh.clicked.connect(lambda: self.refresh_from_editor(force_reanalyze=True))
        top_lay.addWidget(self.btn_refresh)

        for text, handler in (
            ("EDL", self._save_edl),
            ("가이드", self._save_guide),
            ("SRT", self._save_srt),
            ("렌더계획", self._save_render_plan),
        ):
            btn = QPushButton(text)
            btn.setStyleSheet(button_style("toolbar", font_size="12px", padding="7px 10px"))
            btn.clicked.connect(handler)
            top_lay.addWidget(btn)

        self.btn_back = QPushButton("에디터")
        self.btn_back.setStyleSheet(button_style("toolbar", font_size="12px", padding="7px 12px"))
        self.btn_back.clicked.connect(self._activate_editor)
        top_lay.addWidget(self.btn_back)
        return top

    def _build_metrics(self) -> QWidget:
        metrics = QWidget()
        metrics_lay = QHBoxLayout(metrics)
        metrics_lay.setContentsMargins(0, 0, 0, 0)
        metrics_lay.setSpacing(8)
        self.metric_labels = []
        for label in ("챕터", "EDL", "하이라이트", "검토", "출력"):
            metrics_lay.addWidget(self._metric_box(label), stretch=1)
        return metrics

    def _metric_box(self, title: str) -> QWidget:
        box = QFrame()
        box.setStyleSheet(panel_style("alt"))
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(2)
        name = QLabel(title)
        name.setStyleSheet(label_style("muted", 10, bold=True))
        value = QLabel("-")
        value.setStyleSheet(label_style("text", 14, bold=True))
        lay.addWidget(name)
        lay.addWidget(value)
        self.metric_labels.append(value)
        return box

    def _build_preview(self) -> QWidget:
        preview = QWidget()
        preview.setStyleSheet(panel_style("surface"))
        preview_lay = QHBoxLayout(preview)
        preview_lay.setContentsMargins(12, 8, 12, 8)
        preview_lay.setSpacing(8)

        thumb = QFrame()
        thumb.setFixedSize(96, 54)
        thumb.setStyleSheet("QFrame { background: #0A0F12; border: 1px solid #2D3942; border-radius: 6px; }")
        thumb_lay = QVBoxLayout(thumb)
        thumb_lay.setContentsMargins(4, 4, 4, 4)
        self.preview_thumb_lbl = QLabel("대표\n프레임")
        self.preview_thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_thumb_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        thumb_lay.addWidget(self.preview_thumb_lbl)
        preview_lay.addWidget(thumb)

        preview_text_box = QVBoxLayout()
        preview_text_box.setContentsMargins(0, 0, 0, 0)
        preview_text_box.setSpacing(2)
        self.preview_title_lbl = QLabel("세그먼트 선택 대기")
        self.preview_title_lbl.setStyleSheet(label_style("text", 12, bold=True))
        self.preview_time_lbl = QLabel("-")
        self.preview_time_lbl.setStyleSheet(label_style("muted", 10))
        self.preview_summary_lbl = QLabel("러프컷 행을 선택하면 해당 구간만 재생할 수 있습니다.")
        self.preview_summary_lbl.setStyleSheet(label_style("muted", 10))
        self.preview_summary_lbl.setWordWrap(True)
        preview_text_box.addWidget(self.preview_title_lbl)
        preview_text_box.addWidget(self.preview_time_lbl)
        preview_text_box.addWidget(self.preview_summary_lbl)
        preview_lay.addLayout(preview_text_box, stretch=1)

        self.btn_preview_play = QPushButton("구간 재생")
        self.btn_preview_play.setStyleSheet(button_style("primary", font_size="12px", padding="7px 12px"))
        self.btn_preview_play.clicked.connect(lambda: self._play_preview(self._preview_row, muted=False))
        preview_lay.addWidget(self.btn_preview_play)
        self.btn_preview_stop = QPushButton("정지")
        self.btn_preview_stop.setStyleSheet(button_style("toolbar", font_size="12px", padding="7px 12px"))
        self.btn_preview_stop.clicked.connect(self._stop_preview)
        preview_lay.addWidget(self.btn_preview_stop)
        return preview

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(TABLE_COLUMNS))
        table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        table.setMouseTracking(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        table.setStyleSheet(
            "QTableWidget { background: #11181C; color: #F5F7FA; border: 1px solid #2D3942; "
            "gridline-color: #2D3942; font-size: 11px; alternate-background-color: #151C20; } "
            "QHeaderView::section { background: #1B2429; color: #A9B0B7; border: 1px solid #2D3942; "
            "padding: 6px; font-weight: bold; } "
            "QTableWidget::item { border-bottom: 1px solid #2D3942; padding: 4px; } "
            "QTableWidget::item:selected { background: #1F3A56; color: #FFFFFF; }"
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        table.itemChanged.connect(self._on_table_item_changed)
        table.itemEntered.connect(self._on_table_item_entered)
        table.cellClicked.connect(self._on_table_cell_clicked)
        table.itemSelectionChanged.connect(self._on_table_selection_changed)
        return table
