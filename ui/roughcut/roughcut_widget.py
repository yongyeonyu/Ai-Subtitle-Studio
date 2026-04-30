# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QComboBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.roughcut import build_title_suggestions, default_thumbnail_cache_dir, ensure_thumbnail
from ui.roughcut.roughcut_bottom_panel import RoughcutBottomPanel
from ui.roughcut.roughcut_export import RoughcutExportMixin
from ui.roughcut.roughcut_format import TABLE_COLUMNS
from ui.roughcut.roughcut_detail import RoughcutDetailMixin
from ui.roughcut.roughcut_log_panel import RoughcutLogPanel
from ui.roughcut.roughcut_major_panel import RoughcutMajorPanel
from ui.roughcut.roughcut_preview import RoughcutPreviewMixin
from ui.roughcut.roughcut_state import RoughcutStateMixin
from ui.roughcut.roughcut_style_panel import DEFAULT_ROUGHCUT_EXPORT_STYLE, RoughcutStylePanel
from ui.roughcut.roughcut_table import RoughcutTableMixin
from ui.roughcut.roughcut_title_panel import RoughcutTitlePanel
from ui.style import COLORS, button_style, label_style, line_icon, panel_style


class RoughcutWidget(
    RoughcutExportMixin,
    RoughcutDetailMixin,
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
        self._roughcut_candidates: list[dict] = []
        self._selected_candidate_id = ""
        self._refreshing_candidate_combo = False
        self._row_chapter_ids: list[str] = []
        self._user_edits: dict[str, dict[str, str]] = {}
        self._updating_table = False
        self._preview_row = -1
        self._preview_end = 0.0
        self._preview_deadline_ms = 0
        self._preview_is_hover = False
        self._preview_loop_enabled = False
        self._restore_volume: float | None = None
        self._render_thread = None
        self._render_worker = None
        self._last_render_plan = None
        self._last_failed_render_plan = None
        self._roughcut_export_style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        self._render_log_lines: list[str] = []
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._preview_tick)
        self.setStyleSheet(f"background: {COLORS['bg']}; color: {COLORS['text']};")
        self._build_ui()

    def run_main_action(self) -> None:
        """Route the global Start button to roughcut analysis while this page is active."""
        if self._subtitle_generation_active():
            self._set_roughcut_status("자막 생성 중")
            self.preview_summary_lbl.setText("자막 생성이 끝난 뒤 러프컷 분석을 시작할 수 있습니다.")
            return
        self._set_roughcut_status("읽는 중", 15)
        self._append_roughcut_log("에디터 자막을 러프컷 분석 입력으로 읽습니다.")
        self.refresh_from_editor(force_reanalyze=True, analyze_if_missing=True)
        self._set_roughcut_status("분석 완료" if self._result is not None else "분석 대기", 100 if self._result is not None else None)

    def _subtitle_generation_active(self) -> bool:
        owner = self.owner
        backend = getattr(owner, "backend", None) if owner is not None else None
        if bool(getattr(backend, "_active", False)):
            return True
        editor = self._active_editor()
        if editor is None:
            return False
        try:
            from core.state_manager import SubtitleStateManager

            return getattr(getattr(editor, "sm", None), "state", None) == SubtitleStateManager.ST_PROC
        except Exception:
            return bool(getattr(editor, "_is_ai_processing", False))

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.bottom_panel = self._build_bottom_panel()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("QSplitter::handle { background: #0F1518; height: 2px; }")
        root.addWidget(splitter, stretch=1)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setStyleSheet("QSplitter::handle { background: #0F1518; width: 2px; }")

        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #2D3942; border-radius: 7px; background: #11181C; } "
            "QTabBar::tab { background: #202A31; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-bottom: none; padding: 7px 12px; min-height: 24px; min-width: 78px; "
            "border-top-left-radius: 7px; border-top-right-radius: 7px; } "
            "QTabBar::tab:selected { background: #151C20; color: #F5F7FA; border-color: #34C759; }"
        )
        self.major_panel = RoughcutMajorPanel()
        self.major_panel.minorSelected.connect(self._select_chapter_id_from_major_panel)
        self.major_panel.previewRequested.connect(self._preview_chapter_id_from_major_panel)
        self.main_tabs.addTab(self.major_panel, "중분류")
        self.table = self._build_table()
        self.main_tabs.addTab(self.table, "기존 테이블")
        main_splitter.addWidget(self.main_tabs)

        side = QWidget()
        side.setStyleSheet("background: transparent; border: none;")
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 0)
        side_lay.setSpacing(8)
        self.log_panel = RoughcutLogPanel()
        self.title_panel = RoughcutTitlePanel()
        self.style_panel = RoughcutStylePanel()
        self.title_panel.refreshRequested.connect(self._refresh_title_suggestions)
        self.style_panel.styleSaved.connect(self._save_roughcut_export_style)
        side_lay.addWidget(self.log_panel, stretch=1)
        side_lay.addWidget(self.title_panel, stretch=1)
        side_lay.addWidget(self.style_panel, stretch=1)
        main_splitter.addWidget(side)
        main_splitter.setSizes([880, 320])
        splitter.addWidget(main_splitter)

        self.guide_text = QTextEdit()
        self.guide_text.setReadOnly(True)
        self.guide_text.setStyleSheet(
            "QTextEdit { background: #11181C; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 7px; padding: 10px; font-size: 11px; }"
        )
        self.bottom_tabs = RoughcutBottomPanel(self.bottom_panel)
        self.bottom_tabs.tabs.addTab(self.guide_text, "가이드")
        splitter.addWidget(self.bottom_tabs)
        splitter.setSizes([520, 300])

        self._set_empty_state()

    def _set_roughcut_status(self, text: str, progress: int | None = None) -> None:
        if hasattr(self, "render_status_lbl"):
            self.render_status_lbl.setText(str(text or "분석 대기"))
        if hasattr(self, "log_panel"):
            self.log_panel.set_status(str(text or "분석 대기"), progress)

    def _append_roughcut_log(self, text: str, level: str = "info") -> None:
        if hasattr(self, "log_panel"):
            self.log_panel.append_log(text, level)

    def _select_chapter_id_from_major_panel(self, chapter_id: str) -> None:
        chapter_id = str(chapter_id or "")
        if not chapter_id or chapter_id not in self._row_chapter_ids:
            return
        row = self._row_chapter_ids.index(chapter_id)
        self.table.selectRow(row)
        self._preview_row_data(row)
        self._play_preview(row, muted=False)

    def _preview_chapter_id_from_major_panel(self, chapter_id: str, hover: bool) -> None:
        chapter_id = str(chapter_id or "")
        if not chapter_id or chapter_id not in self._row_chapter_ids:
            return
        row = self._row_chapter_ids.index(chapter_id)
        if hover:
            self._prepare_thumbnail_for_row(row)
            self._play_preview(row, muted=True, hover=True, update_preview_data=False)
            return
        self._select_chapter_id_from_major_panel(chapter_id)

    def _prepare_thumbnail_for_row(self, row: int) -> None:
        if row < 0:
            return
        chapter = self._chapter_for_row(row)
        media_path = self._media_path()
        if chapter is None or not media_path:
            return
        midpoint = (float(chapter.start) + float(chapter.end)) / 2.0
        cache_dir = default_thumbnail_cache_dir(self._project_path())
        result = ensure_thumbnail(media_path, midpoint, cache_dir=cache_dir, width=360)
        if result.status in {"created", "cached"} and result.path:
            self.preview_thumb_lbl.setText(f"썸네일\n{midpoint:.1f}s")
        elif result.status not in {"missing_source", "missing"}:
            self._append_roughcut_log(f"썸네일 fallback: {result.reason}", "warning")

    def _save_roughcut_export_style(self, payload: dict) -> None:
        self._roughcut_export_style = dict(DEFAULT_ROUGHCUT_EXPORT_STYLE)
        self._roughcut_export_style.update(payload or {})
        self._append_roughcut_log("러프컷 export style을 프로젝트 상태에 저장했습니다.", "done")
        self._persist_roughcut_state()

    def _refresh_title_suggestions(self) -> None:
        if self._result is None:
            self._set_roughcut_status("분석 대기")
            return
        self._set_roughcut_status("제목 생성", 70)
        self._append_roughcut_log("러프컷 제목 후보를 새로 구성합니다.")
        suggestions = build_title_suggestions(
            self._result,
            settings=self._roughcut_settings_payload(),
        )
        self._result = replace(self._result, title_suggestions=tuple(suggestions))
        self.title_panel.set_suggestions(suggestions)
        self._persist_roughcut_state()
        self._set_roughcut_status("분석 완료", 100)

    def _build_bottom_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent; border: none;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self._build_control_panel())
        return panel

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(panel_style("surface"))
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        lay.addWidget(self._build_toolbar_row())
        lay.addWidget(self._build_preview_row())
        lay.addWidget(self._build_detail_panel())
        return panel

    def _build_toolbar_row(self) -> QWidget:
        top = QWidget()
        top.setStyleSheet("background: transparent; border: none;")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(6)

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

        self.candidate_combo = QComboBox()
        self.candidate_combo.setMinimumWidth(170)
        self.candidate_combo.setFixedHeight(32)
        self.candidate_combo.setToolTip("프로젝트에 저장된 러프컷 후보")
        self.candidate_combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        self.candidate_combo.currentIndexChanged.connect(self._on_candidate_combo_changed)
        top_lay.addWidget(self.candidate_combo)

        self.metric_labels = []
        for label in ("챕터", "EDL", "하이라이트", "검토", "출력"):
            top_lay.addWidget(self._metric_chip(label))

        self.render_status_lbl = QLabel("렌더 대기")
        self.render_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.render_status_lbl.setMinimumWidth(70)
        self.render_status_lbl.setStyleSheet(
            "QLabel { background: #10161A; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 6px 8px; font-size: 10px; font-weight: 700; }"
        )
        top_lay.addWidget(self.render_status_lbl)

        self.safety_filter_combo = QComboBox()
        self.safety_filter_combo.addItems(["전체", "ideal", "acceptable", "risky"])
        self.safety_filter_combo.setFixedHeight(32)
        self.safety_filter_combo.setMinimumWidth(104)
        self.safety_filter_combo.setStyleSheet(
            "QComboBox { background: #10161A; color: #F5F7FA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; }"
            "QComboBox::drop-down { border: none; width: 18px; }"
        )
        self.safety_filter_combo.currentTextChanged.connect(self._apply_safety_filter)
        top_lay.addWidget(self.safety_filter_combo)

        self.btn_refresh = self._panel_button("분석", "refresh", kind="primary")
        self.btn_refresh.clicked.connect(self.run_main_action)
        top_lay.addWidget(self.btn_refresh)

        for text, icon_name, handler in (
            ("EDL", "file", self._save_edl),
            ("가이드", "help", self._save_guide),
            ("SRT", "subtitle", self._save_srt),
            ("렌더계획", "video", self._save_render_plan),
        ):
            btn = self._panel_button(text, icon_name)
            btn.clicked.connect(handler)
            top_lay.addWidget(btn)

        self.btn_render_dry_run = self._panel_button("검증", "check")
        self.btn_render_dry_run.clicked.connect(self._dry_run_render_plan)
        top_lay.addWidget(self.btn_render_dry_run)

        self.btn_render_execute = self._panel_button("렌더", "play", kind="primary")
        self.btn_render_execute.clicked.connect(self._execute_render_plan)
        top_lay.addWidget(self.btn_render_execute)

        self.btn_render_retry = self._panel_button("복구", "restart")
        self.btn_render_retry.setEnabled(False)
        self.btn_render_retry.clicked.connect(self._retry_failed_render)
        top_lay.addWidget(self.btn_render_retry)

        return top

    def _metric_chip(self, title: str) -> QWidget:
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background: #151C20; border: 1px solid #2D3942; border-radius: 6px; }"
        )
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        box.setMinimumWidth(86)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(5)
        name = QLabel(title)
        name.setStyleSheet(label_style("muted", 9, bold=True))
        value = QLabel("-")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setStyleSheet(label_style("text", 11, bold=True))
        lay.addWidget(name)
        lay.addWidget(value, stretch=1)
        self.metric_labels.append(value)
        return box

    def _build_preview_row(self) -> QWidget:
        preview = QWidget()
        preview.setStyleSheet("background: transparent; border: none;")
        preview_lay = QHBoxLayout(preview)
        preview_lay.setContentsMargins(0, 0, 0, 0)
        preview_lay.setSpacing(8)

        thumb = QFrame()
        thumb.setFixedSize(78, 44)
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
        preview_lay.addLayout(preview_text_box, stretch=2)

        detail_box = QVBoxLayout()
        detail_box.setContentsMargins(0, 0, 0, 0)
        detail_box.setSpacing(3)
        detail_row = QHBoxLayout()
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_row.setSpacing(4)
        self.preview_action_lbl = self._detail_badge("판단", "-")
        self.preview_safety_lbl = self._detail_badge("안전", "-")
        self.preview_trim_lbl = self._detail_badge("Trim", "-")
        self.preview_role_lbl = self._detail_badge("Role", "-")
        self.preview_source_lbl = self._detail_badge("Clip", "-")
        for item in (
            self.preview_action_lbl,
            self.preview_safety_lbl,
            self.preview_trim_lbl,
            self.preview_role_lbl,
            self.preview_source_lbl,
        ):
            detail_row.addWidget(item)
        detail_box.addLayout(detail_row)
        self.preview_reason_lbl = QLabel("컷 근거 대기")
        self.preview_reason_lbl.setWordWrap(True)
        self.preview_reason_lbl.setStyleSheet(label_style("muted", 10))
        detail_box.addWidget(self.preview_reason_lbl)
        preview_lay.addLayout(detail_box, stretch=2)

        self.btn_prev_candidate = self._panel_button("이전", "prev")
        self.btn_prev_candidate.clicked.connect(lambda: self._move_preview_row(-1, autoplay=True))
        preview_lay.addWidget(self.btn_prev_candidate)

        self.btn_next_candidate = self._panel_button("다음", "next")
        self.btn_next_candidate.clicked.connect(lambda: self._move_preview_row(1, autoplay=True))
        preview_lay.addWidget(self.btn_next_candidate)

        self.btn_preview_loop = self._panel_button("반복", "refresh")
        self.btn_preview_loop.setCheckable(True)
        self.btn_preview_loop.toggled.connect(self._set_preview_loop_enabled)
        self.btn_preview_loop.setStyleSheet(
            button_style("toolbar", font_size="11px", padding="6px 9px")
            + " QPushButton:checked { background: #1F3A56; border: 1px solid #007AFF; color: #FFFFFF; }"
        )
        preview_lay.addWidget(self.btn_preview_loop)

        self.btn_preview_play = self._panel_button("구간 재생", "play", kind="primary")
        self.btn_preview_play.clicked.connect(lambda: self._play_preview(self._preview_row, muted=False))
        preview_lay.addWidget(self.btn_preview_play)
        self.btn_preview_stop = self._panel_button("정지", "stop")
        self.btn_preview_stop.clicked.connect(self._stop_preview)
        preview_lay.addWidget(self.btn_preview_stop)
        return preview

    def _panel_button(self, text: str, icon_name: str, *, kind: str = "toolbar") -> QPushButton:
        btn = QPushButton(text)
        icon_color = "#FFFFFF" if kind == "primary" else COLORS["muted"]
        btn.setIcon(line_icon(icon_name, icon_color, 16))
        btn.setStyleSheet(button_style(kind, font_size="11px", padding="6px 9px"))
        btn.setMinimumHeight(32)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return btn

    def _detail_badge(self, title: str, value: str) -> QLabel:
        label = QLabel(f"{title}: {value}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(82)
        label.setStyleSheet(
            "QLabel { background: #10161A; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 4px 6px; font-size: 10px; font-weight: 700; }"
        )
        return label

    def _set_preview_loop_enabled(self, enabled: bool) -> None:
        self._preview_loop_enabled = bool(enabled)

    def _visible_preview_rows(self) -> list[int]:
        if not hasattr(self, "table"):
            return []
        return [row for row in range(self.table.rowCount()) if not self.table.isRowHidden(row)]

    def _move_preview_row(self, delta: int, autoplay: bool = False) -> None:
        visible_rows = self._visible_preview_rows()
        if not visible_rows:
            return
        row = self._preview_row if self._preview_row >= 0 else self.table.currentRow()
        if row not in visible_rows:
            row = visible_rows[0]
        else:
            idx = visible_rows.index(row)
            idx = max(0, min(len(visible_rows) - 1, idx + int(delta)))
            row = visible_rows[idx]
        self.table.selectRow(row)
        self._preview_row_data(row)
        if autoplay:
            self._play_preview(row, muted=False)

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
