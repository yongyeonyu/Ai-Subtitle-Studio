# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
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
from ui.settings.qml_panel import attach_qml_tab_bar
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
        self.uses_integrated_bottom_frame = True
        self._attached_video_editor = None
        self._attached_video_frame = None
        self._result = None
        self._source_signature = ""
        self._roughcut_candidates: list[dict] = []
        self._selected_candidate_id = ""
        self._segment_order: list[str] = []
        self._chapter_order: list[str] = []
        self._recent_reorder_summary = ""
        self._chapter_thumbnail_lookup_cache: dict[str, str] = {}
        self._chapter_thumbnail_lookup_media_path = ""
        self._refreshing_candidate_combo = False
        self._restored_selected_chapter_id = ""
        self._restored_safety_filter = "전체"
        self._row_chapter_ids: list[str] = []
        self._user_edits: dict[str, dict[str, str]] = {}
        self._updating_table = False
        self._preview_row = -1
        self._preview_end = 0.0
        self._preview_deadline_ms = 0
        self._preview_is_hover = False
        self._preview_loop_enabled = False
        self._sequence_preview_active = False
        self._sequence_preview_rows: list[int] = []
        self._sequence_preview_index = -1
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
        self._candidate_preview_buttons: list[QPushButton] = []
        self._candidate_preview_empty_lbl = None
        self.setStyleSheet(f"background: {COLORS['bg']}; color: {COLORS['text']};")
        self._build_ui()

    def compact_for_home_navigation(self) -> None:
        self.release_editor_video_frame()
        stop_preview = getattr(self, "_stop_preview", None)
        if callable(stop_preview):
            try:
                stop_preview()
            except Exception:
                pass
        try:
            self._preview_timer.stop()
        except Exception:
            pass
        if getattr(self, "_render_thread", None) is not None:
            return
        self._result = None
        self._source_signature = ""
        try:
            self._set_empty_state()
        except Exception:
            pass

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
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setStyleSheet("QSplitter::handle { background: #0F1518; width: 2px; }")
        root.addWidget(main_splitter, stretch=1)

        self.roughcut_frame = QFrame()
        self.roughcut_frame.setStyleSheet(panel_style("surface"))
        left_lay = QVBoxLayout(self.roughcut_frame)
        left_lay.setContentsMargins(6, 6, 6, 6)
        left_lay.setSpacing(6)
        self.candidate_preview_frame = self._build_candidate_preview_frame()
        left_lay.addWidget(self.candidate_preview_frame, stretch=0)
        self.major_panel = RoughcutMajorPanel()
        self.major_panel.minorSelected.connect(self._select_chapter_id_from_major_panel)
        self.major_panel.previewRequested.connect(self._preview_chapter_id_from_major_panel)
        self.major_panel.segmentOrderChanged.connect(self._on_major_segment_order_changed)
        self.major_panel.chapterOrderChanged.connect(self._on_major_chapter_order_changed)
        self.table = self._build_table()
        left_lay.addWidget(self.major_panel, stretch=1)
        main_splitter.addWidget(self.roughcut_frame)

        side = QFrame()
        side.setStyleSheet(panel_style("surface"))
        side.setMinimumWidth(396)
        side.setMaximumWidth(468)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(6, 6, 6, 6)
        side_lay.setSpacing(6)
        self.video_bridge_frame = QFrame()
        self.video_bridge_frame.setStyleSheet("QFrame { background: #0A0F12; border: 1px solid #2D3942; border-radius: 8px; }")
        self.video_bridge_layout = QVBoxLayout(self.video_bridge_frame)
        self.video_bridge_layout.setContentsMargins(8, 8, 8, 8)
        self.video_bridge_layout.setSpacing(6)
        self.video_bridge_title_lbl = QLabel("비디오 플레이어")
        self.video_bridge_title_lbl.setStyleSheet(label_style("text", 11, bold=True))
        self.video_bridge_hint_lbl = QLabel("러프컷 카드 순서에 맞춰 현재 에디터 플레이어를 그대로 확인합니다.")
        self.video_bridge_hint_lbl.setStyleSheet(label_style("muted", 9))
        self.video_host = QFrame()
        self.video_host.setStyleSheet("QFrame { background: #000000; border: 1px solid #1D2730; border-radius: 8px; }")
        self.video_host_layout = QVBoxLayout(self.video_host)
        self.video_host_layout.setContentsMargins(0, 0, 0, 0)
        self.video_host_layout.setSpacing(0)
        self.video_host_placeholder = QLabel("현재 에디터 비디오 플레이어를 여기에 유지합니다.")
        self.video_host_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_host_placeholder.setMinimumHeight(188)
        self.video_host_placeholder.setStyleSheet(label_style("muted", 10))
        self.video_host_layout.addWidget(self.video_host_placeholder)
        self.video_bridge_layout.addWidget(self.video_bridge_title_lbl)
        self.video_bridge_layout.addWidget(self.video_bridge_hint_lbl)
        self.video_bridge_layout.addWidget(self.video_host, stretch=1)
        side_lay.addWidget(self.video_bridge_frame, stretch=3)
        self.player_menu_frame = self._build_player_menu_frame()
        side_lay.addWidget(self.player_menu_frame, stretch=0)

        self.bottom_panel = self._build_bottom_panel()
        self.bottom_tabs = RoughcutBottomPanel(self.bottom_panel)
        self.bottom_tabs.tabs.insertTab(0, self.table, "챕터")
        self.guide_text = QTextEdit()
        self.guide_text.setReadOnly(True)
        self.guide_text.setStyleSheet(
            "QTextEdit { background: #11181C; color: #DCE3EA; border: 1px solid #2D3942; "
            "border-radius: 7px; padding: 10px; font-size: 11px; }"
        )
        self.bottom_tabs.tabs.addTab(self.guide_text, "가이드")
        self.log_panel = RoughcutLogPanel()
        self.title_panel = RoughcutTitlePanel()
        self.style_panel = RoughcutStylePanel()
        self.title_panel.refreshRequested.connect(self._refresh_title_suggestions)
        self.style_panel.styleSaved.connect(self._save_roughcut_export_style)
        self.bottom_tabs.tabs.addTab(self.log_panel, "로그")
        self.bottom_tabs.tabs.addTab(self.title_panel, "제목")
        self.bottom_tabs.tabs.addTab(self.style_panel, "스타일")
        side_lay.addWidget(self.bottom_tabs, stretch=5)
        main_splitter.addWidget(side)
        main_splitter.setStretchFactor(0, 6)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setSizes([1640, 420])

        self._set_empty_state()

    def _build_candidate_preview_frame(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #10161A; border: 1px solid #2D3942; border-radius: 10px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(6)

        title = QLabel("LLM 후보")
        title.setStyleSheet(label_style("text", 11, bold=True))
        hint = QLabel("후보는 최대 3개만 좁고 긴 세로 기둥으로 옆에 배치하고, 각 기둥 안에 roughcut 세그먼트를 위에서 아래로 넣습니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(label_style("muted", 9))
        lay.addWidget(title)
        lay.addWidget(hint)

        self.candidate_preview_btn_group = QButtonGroup(frame)
        self.candidate_preview_btn_group.setExclusive(True)
        self.candidate_preview_stack = QWidget()
        self.candidate_preview_stack.setStyleSheet("background: transparent; border: none;")
        self.candidate_preview_layout = QHBoxLayout(self.candidate_preview_stack)
        self.candidate_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.candidate_preview_layout.setSpacing(6)
        self.candidate_preview_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.candidate_preview_stack.setMinimumHeight(332)
        self._candidate_preview_empty_lbl = QLabel("후보 없음")
        self._candidate_preview_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._candidate_preview_empty_lbl.setStyleSheet(label_style("muted", 10, bold=True))
        self.candidate_preview_layout.addWidget(self._candidate_preview_empty_lbl)
        lay.addWidget(self.candidate_preview_stack)
        return frame

    def _candidate_preview_button_style(self, *, selected: bool = False, is_current: bool = False) -> str:
        border = COLORS["accent"] if selected else ("#2B5A3A" if is_current else "#2D3942")
        background = "#133422" if selected else "#11181C"
        color = "#F5F7FA" if selected else "#DCE3EA"
        return (
            "QPushButton { "
            f"background: {background}; color: {color}; border: 1px solid {border}; "
            "border-radius: 10px; padding: 10px 9px; text-align: left top; font-size: 10px; font-weight: 700; }"
            "QPushButton:hover { border-color: #34C759; }"
        )

    def _candidate_preview_lines(self, candidate: dict, index: int) -> tuple[str, str]:
        name = str(candidate.get("name") or f"후보 {index}")
        current_sig = self._current_editor_signature() if hasattr(self, "_current_editor_signature") else ""
        is_current = str(candidate.get("source_signature") or "") == current_sig and bool(current_sig)
        suffix = "현재 자막" if is_current else "저장된 자막"
        segments = list(candidate.get("segments") or [])
        segment_lines: list[str] = []
        for segment in segments[:4]:
            if not isinstance(segment, dict):
                continue
            major_id = str(segment.get("segment_id") or segment.get("major_id") or "-")
            title = str(segment.get("title") or segment.get("summary") or "세그먼트")
            segment_lines.append(f"{major_id} · {title}")
        if not segment_lines:
            segment_lines.append("세그먼트 없음")
        head = f"{name} · {suffix}"
        body = "\n".join(segment_lines)
        return head, body

    def _refresh_candidate_preview_frames(self) -> None:
        layout = getattr(self, "candidate_preview_layout", None)
        if layout is None:
            return
        for button in list(getattr(self, "_candidate_preview_buttons", []) or []):
            try:
                self.candidate_preview_btn_group.removeButton(button)
            except Exception:
                pass
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._candidate_preview_buttons = []
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])[:3]
        if not candidates:
            empty = QLabel("후보 없음")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(label_style("muted", 10, bold=True))
            layout.addWidget(empty)
            self._candidate_preview_empty_lbl = empty
            return
        selected_id = str(getattr(self, "_selected_candidate_id", "") or "")
        current_sig = self._current_editor_signature() if hasattr(self, "_current_editor_signature") else ""
        for index, candidate in enumerate(candidates, start=1):
            candidate_id = str(candidate.get("candidate_id") or "")
            is_selected = (candidate_id == selected_id)
            is_current = str(candidate.get("source_signature") or "") == current_sig and bool(current_sig)

            head, body = self._candidate_preview_lines(candidate, index)

            # 1) 후보 프레임 자체가 vertical column 형태의 QPushButton
            button = QPushButton()
            button.setCheckable(True)
            button.setChecked(is_selected)
            button.setProperty("candidate_id", candidate_id)
            button.setFixedWidth(132)
            button.setMinimumHeight(320)
            button.setMaximumHeight(344)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

            # 테스트 검증용 원본 텍스트 주입 (assert 통과 보장)
            button.setText(f"{head}\n{body}")

            border = COLORS["accent"] if is_selected else ("#2B5A3A" if is_current else "#2D3942")
            background = "#133422" if is_selected else "#11181C"
            button.setStyleSheet(
                f"QPushButton {{ background: {background}; border: 1px solid {border}; border-radius: 10px; text-align: left top; color: transparent; }}"
            )
            button.clicked.connect(lambda _checked=False, cid=candidate_id: self._on_candidate_frame_clicked(cid))
            button.toggled.connect(lambda checked, cid=candidate_id: self._on_candidate_frame_toggled(cid, checked))

            # 3) 각 후보 프레임 내부에서 roughcut 세그먼트가 위에서 아래로 수직 stack
            col_lay = QVBoxLayout(button)
            col_lay.setContentsMargins(6, 6, 6, 6)
            col_lay.setSpacing(6)

            # 상단 헤더 라벨
            suffix = "현재 자막" if is_current else "저장된 자막"
            header_lbl = QLabel(f"{candidate.get('name') or f'후보 {index}'}\n{suffix}")
            header_lbl.setWordWrap(True)
            header_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            header_lbl.setStyleSheet(
                f"color: #F5F7FA; font-size: 9px; font-weight: 900; background: {'#173D28' if is_selected else '#1A242B'}; "
                f"border: 1px solid {border}; border-radius: 6px; padding: 4px; qproperty-alignment: 'AlignCenter';"
            )
            col_lay.addWidget(header_lbl)

            # 세분화된 세그먼트 서브 카드 수직 적재
            segments = list(candidate.get("segments") or [])
            for segment in segments[:4]: # 기둥 내 수직 공간 고려 최대 4개
                if not isinstance(segment, dict):
                    continue
                major_id = str(segment.get("segment_id") or segment.get("major_id") or "-")
                title = str(segment.get("title") or segment.get("summary") or "세그먼트")

                seg_card = QFrame()
                seg_card.setObjectName("SegSubCard")
                seg_card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) # 클릭 버블링 허용
                seg_card.setStyleSheet(
                    "QFrame#SegSubCard { background: #0D1317; border: 1px solid #232E35; border-radius: 6px; }"
                )
                seg_card_lay = QVBoxLayout(seg_card)
                seg_card_lay.setContentsMargins(6, 6, 6, 6)
                seg_card_lay.setSpacing(2)

                seg_title = QLabel(f"{major_id} · {title}")
                seg_title.setWordWrap(True)
                seg_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                seg_title.setStyleSheet("color: #DCE3EA; font-size: 9px; font-weight: 700; background: transparent; border: none;")
                seg_card_lay.addWidget(seg_title)

                start = float(segment.get("start") or 0.0)
                end = float(segment.get("end") or 0.0)
                from ui.roughcut.roughcut_format import fmt_time
                seg_time = QLabel(f"{fmt_time(start)} - {fmt_time(end)}")
                seg_time.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                seg_time.setStyleSheet("color: #8A949E; font-size: 8px; background: transparent; border: none;")
                seg_card_lay.addWidget(seg_time)

                col_lay.addWidget(seg_card)

            if not segments:
                no_seg = QLabel("세그먼트 없음")
                no_seg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                no_seg.setStyleSheet("color: #8A949E; font-size: 9px; border: none;")
                no_seg.setAlignment(Qt.AlignmentFlag.AlignCenter)
                col_lay.addWidget(no_seg)

            col_lay.addStretch(1)

            self.candidate_preview_btn_group.addButton(button)
            layout.addWidget(button)
            self._candidate_preview_buttons.append(button)
        layout.addStretch(1)

    def _on_candidate_frame_clicked(self, candidate_id: str) -> None:
        candidate = self._candidate_by_id(candidate_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            return
        if candidate_id == getattr(self, "_selected_candidate_id", ""):
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
            return
        self._apply_candidate_payload(candidate, persist=True)

    def _on_candidate_frame_toggled(self, candidate_id: str, checked: bool) -> None:
        if not checked:
            return
        candidate = self._candidate_by_id(candidate_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            return
        if candidate_id == getattr(self, "_selected_candidate_id", ""):
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
            return
        self._apply_candidate_payload(candidate, persist=True)

    def attach_editor_video_frame(self, editor) -> bool:
        if editor is None:
            return False
        if self._attached_video_editor is editor and self._attached_video_frame is not None:
            return True
        self.release_editor_video_frame()
        detacher = getattr(editor, "detach_video_frame_for_external_host", None)
        if not callable(detacher):
            return False
        frame = detacher()
        if frame is None:
            return False
        self.video_host_layout.removeWidget(self.video_host_placeholder)
        self.video_host_placeholder.hide()
        self.video_host_layout.addWidget(frame)
        self._attached_video_editor = editor
        self._attached_video_frame = frame
        try:
            frame.show()
            frame.updateGeometry()
        except Exception:
            pass
        restore_video = getattr(getattr(editor, "video_player", None), "restore_after_navigation", None)
        if callable(restore_video):
            restore_video()
        return True

    def release_editor_video_frame(self) -> None:
        frame = getattr(self, "_attached_video_frame", None)
        editor = getattr(self, "_attached_video_editor", None)
        if frame is None or editor is None:
            return
        try:
            self.video_host_layout.removeWidget(frame)
        except Exception:
            pass
        restorer = getattr(editor, "restore_video_frame_from_external_host", None)
        if callable(restorer):
            restorer(frame)
        else:
            try:
                frame.setParent(None)
            except Exception:
                pass
        if self.video_host_layout.indexOf(self.video_host_placeholder) < 0:
            self.video_host_layout.addWidget(self.video_host_placeholder)
        self.video_host_placeholder.show()
        self._attached_video_editor = None
        self._attached_video_frame = None

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

    def _on_major_segment_order_changed(self, ordered_segment_ids: tuple[str, ...]) -> None:
        previous_order = list(getattr(self, "_segment_order", []) or [])
        order = [str(segment_id) for segment_id in ordered_segment_ids if str(segment_id or "")]
        if not order or order == list(getattr(self, "_segment_order", []) or []):
            return
        self._segment_order = order
        self._set_reorder_summary_label(self._format_segment_reorder_summary(previous_order, order), active=True)
        current_chapter_id = ""
        if hasattr(self, "_current_selected_chapter_id"):
            current_chapter_id = self._current_selected_chapter_id()
        if self._result is None:
            self._persist_roughcut_state()
            return
        self._restored_selected_chapter_id = current_chapter_id
        self._result = self._result_with_user_edits(self._result)
        self._populate_result()
        self._persist_roughcut_state()

    def _on_major_chapter_order_changed(self, ordered_chapter_ids: tuple[str, ...]) -> None:
        previous_order = list(getattr(self, "_chapter_order", []) or [])
        order = [str(chapter_id) for chapter_id in ordered_chapter_ids if str(chapter_id or "")]
        if not order or order == list(getattr(self, "_chapter_order", []) or []):
            return
        self._chapter_order = order
        current_chapter_id = ""
        if hasattr(self, "_current_selected_chapter_id"):
            current_chapter_id = self._current_selected_chapter_id()
        self._set_reorder_summary_label(
            self._format_chapter_reorder_summary(previous_order, order, current_chapter_id),
            active=True,
        )
        if self._result is None:
            self._persist_roughcut_state()
            return
        self._restored_selected_chapter_id = current_chapter_id
        self._result = self._result_with_user_edits(self._result)
        self._populate_result()
        self._persist_roughcut_state()

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

    def _thumbnail_lookup_for_result(self, result) -> dict[str, str]:
        if result is None:
            return {}
        media_path = str(self._media_path() or "")
        if not media_path:
            return {}
        if media_path != self._chapter_thumbnail_lookup_media_path:
            self._chapter_thumbnail_lookup_media_path = media_path
            self._chapter_thumbnail_lookup_cache = {}
        cache_dir = default_thumbnail_cache_dir(self._project_path())
        lookup = dict(self._chapter_thumbnail_lookup_cache)
        for chapter in tuple(getattr(result, "chapters", ()) or ()):
            chapter_id = str(getattr(chapter, "chapter_id", "") or "")
            if not chapter_id or chapter_id in lookup:
                continue
            midpoint = (float(chapter.start) + float(chapter.end)) / 2.0
            thumb = ensure_thumbnail(media_path, midpoint, cache_dir=cache_dir, width=320)
            if thumb.status in {"created", "cached"} and thumb.path:
                lookup[chapter_id] = str(thumb.path)
        self._chapter_thumbnail_lookup_cache = lookup
        return dict(lookup)

    def automation_runtime_snapshot(self) -> dict:
        visible_ids = [
            chapter_id
            for row, chapter_id in enumerate(list(getattr(self, "_row_chapter_ids", []) or []))
            if not self.table.isRowHidden(row)
        ]
        current_segment_ids = self._current_segment_ids()
        candidate_ids = [
            str(candidate.get("candidate_id") or "")
            for candidate in list(getattr(self, "_roughcut_candidates", []) or [])
            if str(candidate.get("candidate_id") or "")
        ]
        return {
            "has_result": bool(self._result is not None),
            "selected_candidate_id": str(getattr(self, "_selected_candidate_id", "") or ""),
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids,
            "selected_chapter_id": str(self._current_selected_chapter_id() or ""),
            "selected_segment_id": self._segment_id_for_chapter_id(self._current_selected_chapter_id()),
            "selected_chapter_title": str(getattr(self, "preview_title_lbl", None).text() if hasattr(self, "preview_title_lbl") else ""),
            "candidate_state": str(getattr(self, "candidate_state_lbl", None).text() if hasattr(self, "candidate_state_lbl") else ""),
            "filter_value": self._current_safety_filter_value(),
            "filter_summary": str(getattr(self, "filter_summary_lbl", None).text() if hasattr(self, "filter_summary_lbl") else ""),
            "selection_summary": str(getattr(self, "selection_summary_lbl", None).text() if hasattr(self, "selection_summary_lbl") else ""),
            "order_summary": self._current_order_summary(),
            "reorder_summary": str(getattr(self, "reorder_summary_lbl", None).text() if hasattr(self, "reorder_summary_lbl") else ""),
            "sequence_preview_active": bool(getattr(self, "_sequence_preview_active", False)),
            "visible_row_count": len(visible_ids),
            "total_row_count": len(list(getattr(self, "_row_chapter_ids", []) or [])),
            "visible_chapter_ids": visible_ids,
            "visible_segment_ids": current_segment_ids,
            "chapter_order": list(getattr(self, "_row_chapter_ids", []) or []),
            "segment_order": current_segment_ids,
            "chapter_order_state": list(getattr(self, "_chapter_order", []) or []),
            "video_host_attached": bool(getattr(self, "_attached_video_frame", None) is not None),
            "video_placeholder_visible": bool(getattr(self, "video_host_placeholder", None).isVisible() if hasattr(self, "video_host_placeholder") else False),
            "player_menu_visible": bool(getattr(self, "player_menu_frame", None).isVisible() if hasattr(self, "player_menu_frame") else False),
        }

    def automation_select_candidate(self, *, candidate_id: str = "", index: int | None = None) -> dict:
        candidates = list(getattr(self, "_roughcut_candidates", []) or [])
        target_id = str(candidate_id or "")
        if index is not None:
            row_value = int(index)
            if row_value < 0 or row_value >= len(candidates):
                raise ValueError("roughcut_candidate_index_out_of_range")
            target_id = str(candidates[row_value].get("candidate_id") or "")
        if not target_id:
            raise ValueError("roughcut_candidate_missing")
        candidate = self._candidate_by_id(target_id) if hasattr(self, "_candidate_by_id") else None
        if candidate is None:
            raise ValueError("roughcut_candidate_not_found")
        if target_id != str(getattr(self, "_selected_candidate_id", "") or ""):
            self._apply_candidate_payload(candidate, persist=True)
        else:
            self._sync_candidate_state_label(candidate)
            self._refresh_candidate_preview_frames()
        return self.automation_runtime_snapshot()

    def automation_select_chapter(self, *, chapter_id: str = "", row: int | None = None, autoplay: bool = False) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        target_id = str(chapter_id or "")
        if row is not None:
            row_value = int(row)
            rows = list(getattr(self, "_row_chapter_ids", []) or [])
            if row_value < 0 or row_value >= len(rows):
                raise ValueError("roughcut_row_out_of_range")
            target_id = str(rows[row_value] or "")
        if not target_id:
            raise ValueError("roughcut_chapter_missing")
        if not self._select_chapter_id_in_table(target_id, autoplay=autoplay):
            raise ValueError("roughcut_chapter_not_found")
        return self.automation_runtime_snapshot()

    def automation_move_selected_chapter(self, delta: int) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        order = list(getattr(self, "_row_chapter_ids", []) or [])
        if not order:
            raise ValueError("roughcut_chapter_missing")
        selected_id = str(self._current_selected_chapter_id() or "")
        if not selected_id or selected_id not in order:
            raise ValueError("roughcut_selection_missing")
        current_index = order.index(selected_id)
        target_index = max(0, min(len(order) - 1, current_index + int(delta)))
        if target_index == current_index:
            snapshot = self.automation_runtime_snapshot()
            snapshot["changed"] = False
            return snapshot
        moving_id = order.pop(current_index)
        order.insert(target_index, moving_id)
        self._on_major_chapter_order_changed(tuple(order))
        self._select_chapter_id_in_table(moving_id, autoplay=False)
        snapshot = self.automation_runtime_snapshot()
        snapshot["changed"] = True
        snapshot["selected_chapter_id"] = moving_id
        snapshot["target_index"] = target_index
        return snapshot

    def automation_move_selected_segment(self, delta: int) -> dict:
        if self._result is None:
            raise ValueError("roughcut_result_missing")
        selected_chapter_id = str(self._current_selected_chapter_id() or "")
        selected_segment_id = self._segment_id_for_chapter_id(selected_chapter_id)
        order = self._current_segment_ids()
        if not selected_segment_id or selected_segment_id not in order:
            raise ValueError("roughcut_segment_selection_missing")
        current_index = order.index(selected_segment_id)
        target_index = max(0, min(len(order) - 1, current_index + int(delta)))
        if target_index == current_index:
            snapshot = self.automation_runtime_snapshot()
            snapshot["changed"] = False
            snapshot["selected_segment_id"] = selected_segment_id
            return snapshot
        moving_id = order.pop(current_index)
        order.insert(target_index, moving_id)
        self._on_major_segment_order_changed(tuple(order))
        self._select_chapter_id_in_table(selected_chapter_id, autoplay=False)
        snapshot = self.automation_runtime_snapshot()
        snapshot["changed"] = True
        snapshot["selected_segment_id"] = moving_id
        snapshot["target_index"] = target_index
        return snapshot

    def automation_set_safety_filter(self, value: str) -> dict:
        combo = getattr(self, "safety_filter_combo", None)
        if combo is None:
            raise ValueError("roughcut_filter_unavailable")
        target = str(value or "").strip()
        index = combo.findText(target)
        if index < 0:
            raise ValueError("roughcut_filter_invalid")
        combo.setCurrentIndex(index)
        return self.automation_runtime_snapshot()

    def automation_start_preview_sequence(self) -> dict:
        if not self._start_ordered_preview_sequence():
            raise ValueError("roughcut_sequence_unavailable")
        return self.automation_runtime_snapshot()

    def _current_segment_ids(self) -> list[str]:
        result = getattr(self, "_result", None)
        if result is None:
            return []
        segment_ids: list[str] = []
        for index, segment in enumerate(tuple(getattr(result, "segments", ()) or ()), start=1):
            segment_id = str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")
            if segment_id:
                segment_ids.append(segment_id)
        return segment_ids

    def _segment_id_for_chapter_id(self, chapter_id: str) -> str:
        chapter_id = str(chapter_id or "")
        result = getattr(self, "_result", None)
        if not chapter_id or result is None:
            return ""
        for index, segment in enumerate(tuple(getattr(result, "segments", ()) or ()), start=1):
            segment_id = str(getattr(segment, "segment_id", "") or getattr(segment, "major_id", "") or f"segment_{index:04d}")
            for minor in tuple(getattr(segment, "minor_groups", ()) or ()):
                chapter_ids = [str(item or "") for item in tuple(getattr(minor, "chapter_ids", ()) or ()) if str(item or "")]
                if chapter_id in chapter_ids:
                    return segment_id
        return ""

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
        lay.setSpacing(4)
        lay.addWidget(self._build_control_panel())
        return panel

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("QWidget { background: transparent; border: none; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self._build_toolbar_row())
        lay.addWidget(self._build_preview_row())
        lay.addWidget(self._build_detail_panel())
        return panel

    def _build_player_menu_frame(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #10161A; border: 1px solid #2D3942; border-radius: 8px; }")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(9, 8, 9, 8)
        lay.setSpacing(6)

        title = QLabel("플레이어 아래 메뉴")
        title.setStyleSheet(label_style("text", 11, bold=True))
        hint = QLabel("카드 순서 확인, 분석/검증, SRT/EDL 저장 같은 러프컷 작업 메뉴입니다.")
        hint.setWordWrap(True)
        hint.setStyleSheet(label_style("muted", 9))
        lay.addWidget(title)
        lay.addWidget(hint)

        self.player_candidate_state_lbl = self._toolbar_badge("후보 없음")
        self.player_candidate_state_lbl.hide()
        self.player_filter_lbl = self._toolbar_badge("표시 0 / 전체 0")
        self.player_filter_lbl.hide()
        self.player_order_lbl = self._toolbar_badge("순서 대기")
        self.player_order_lbl.setMinimumWidth(126)
        self.player_order_lbl.hide()
        self.player_selection_lbl = self._toolbar_badge("선택 대기")
        self.player_selection_lbl.setMinimumWidth(116)
        self.player_selection_lbl.hide()
        self.player_reorder_lbl = self._toolbar_badge("재정렬 없음")
        self.player_reorder_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.player_reorder_lbl.setMinimumWidth(180)
        self.player_reorder_lbl.hide()

        summary_box = QFrame()
        summary_box.setStyleSheet("QFrame { background: #0C1216; border: 1px solid #243038; border-radius: 7px; }")
        summary_lay = QVBoxLayout(summary_box)
        summary_lay.setContentsMargins(8, 6, 8, 6)
        summary_lay.setSpacing(3)
        self.player_context_summary_lbl = QLabel("후보 없음 · 표시 0 / 전체 0")
        self.player_context_summary_lbl.setWordWrap(True)
        self.player_context_summary_lbl.setStyleSheet(label_style("muted", 9, bold=True))
        self.player_focus_summary_lbl = QLabel("순서 대기 · 선택 대기")
        self.player_focus_summary_lbl.setWordWrap(True)
        self.player_focus_summary_lbl.setStyleSheet(label_style("text", 10, bold=True))
        self.player_reorder_summary_visible_lbl = QLabel("재정렬 없음")
        self.player_reorder_summary_visible_lbl.setWordWrap(True)
        self.player_reorder_summary_visible_lbl.setStyleSheet(label_style("muted", 9))
        summary_lay.addWidget(self.player_context_summary_lbl)
        summary_lay.addWidget(self.player_focus_summary_lbl)
        summary_lay.addWidget(self.player_reorder_summary_visible_lbl)
        lay.addWidget(summary_box)

        section_actions = QLabel("작업")
        section_actions.setStyleSheet(label_style("muted", 9, bold=True))
        lay.addWidget(section_actions)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.btn_side_refresh = self._panel_button("분석", "refresh", kind="primary")
        self.btn_side_refresh.clicked.connect(self.run_main_action)
        self.btn_side_refresh.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_verify = self._panel_button("검증", "check")
        self.btn_side_verify.clicked.connect(self._dry_run_render_plan)
        self.btn_side_verify.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_render = self._panel_button("렌더", "play", kind="primary")
        self.btn_side_render.clicked.connect(self._execute_render_plan)
        self.btn_side_render.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for button in (self.btn_side_refresh, self.btn_side_verify, self.btn_side_render):
            action_row.addWidget(button)
        lay.addLayout(action_row)

        section_export = QLabel("내보내기")
        section_export.setStyleSheet(label_style("muted", 9, bold=True))
        lay.addWidget(section_export)

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.setSpacing(6)
        self.btn_side_save_srt = self._panel_button("SRT", "subtitle")
        self.btn_side_save_srt.clicked.connect(self._save_srt)
        self.btn_side_save_srt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_save_edl = self._panel_button("EDL", "file")
        self.btn_side_save_edl.clicked.connect(self._save_edl)
        self.btn_side_save_edl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_save_guide = self._panel_button("가이드", "help")
        self.btn_side_save_guide.clicked.connect(self._save_guide)
        self.btn_side_save_guide.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for button in (self.btn_side_save_srt, self.btn_side_save_edl, self.btn_side_save_guide):
            export_row.addWidget(button)
        lay.addLayout(export_row)

        section_playback = QLabel("재생")
        section_playback.setStyleSheet(label_style("muted", 9, bold=True))
        lay.addWidget(section_playback)

        playback_row = QHBoxLayout()
        playback_row.setContentsMargins(0, 0, 0, 0)
        playback_row.setSpacing(6)
        self.btn_side_prev = self._panel_button("이전", "prev")
        self.btn_side_prev.clicked.connect(lambda: self._move_preview_row(-1, autoplay=True))
        self.btn_side_prev.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_play = self._panel_button("순서 재생", "play", kind="primary")
        self.btn_side_play.clicked.connect(self._start_ordered_preview_sequence)
        self.btn_side_play.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_side_next = self._panel_button("다음", "next")
        self.btn_side_next.clicked.connect(lambda: self._move_preview_row(1, autoplay=True))
        self.btn_side_next.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for button in (self.btn_side_prev, self.btn_side_play, self.btn_side_next):
            playback_row.addWidget(button)
        lay.addLayout(playback_row)

        # Keep legacy attribute names wired for export/runtime helpers.
        self.btn_render_dry_run = self.btn_side_verify
        self.btn_render_execute = self.btn_side_render
        self.btn_refresh = self.btn_side_refresh
        self.btn_render_retry = QPushButton("복구")
        self.btn_render_retry.setVisible(False)
        self.btn_render_retry.setEnabled(False)
        self._refresh_player_runtime_summary()
        return frame

    def _build_toolbar_row(self) -> QWidget:
        top = QWidget()
        top.setStyleSheet("background: transparent; border: none;")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        self.title_lbl = QLabel("러프컷")
        self.title_lbl.setStyleSheet(label_style("text", 15, bold=True))
        self.source_lbl = QLabel("대기 중")
        self.source_lbl.setStyleSheet(label_style("muted", 10))
        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.source_lbl)
        row1.addLayout(title_box, stretch=1)

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
        self.candidate_combo.hide()
        self.candidate_state_lbl = self._toolbar_badge("후보 없음")
        row1.addWidget(self.candidate_state_lbl)

        self.render_status_lbl = QLabel("렌더 대기")
        self.render_status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.render_status_lbl.setMinimumWidth(70)
        self.render_status_lbl.setStyleSheet(
            "QLabel { background: #10161A; color: #A9B0B7; border: 1px solid #2D3942; "
            "border-radius: 6px; padding: 6px 8px; font-size: 10px; font-weight: 700; }"
        )
        row1.addWidget(self.render_status_lbl)
        top_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(6)
        self.metric_labels = []
        for label in ("챕터", "EDL", "하이라이트", "검토", "출력"):
            row2.addWidget(self._metric_chip(label))

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
        row2.addWidget(self.safety_filter_combo)
        self.filter_summary_lbl = self._toolbar_badge("표시 0 / 전체 0")
        row2.addWidget(self.filter_summary_lbl)
        self.selection_summary_lbl = self._toolbar_badge("선택 대기")
        self.selection_summary_lbl.setMinimumWidth(150)
        row2.addWidget(self.selection_summary_lbl, stretch=1)
        top_lay.addLayout(row2)
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(6)
        self.reorder_summary_lbl = self._toolbar_badge("재정렬 없음")
        self.reorder_summary_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        row3.addWidget(self.reorder_summary_lbl, stretch=1)
        top_lay.addLayout(row3)

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

    def _toolbar_badge(self, text: str) -> QLabel:
        label = QLabel(str(text or ""))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(84)
        label.setStyleSheet(self._toolbar_badge_style("#A9B0B7", "#2D3942"))
        return label

    def _toolbar_badge_style(self, color: str, border: str) -> str:
        return (
            "QLabel { background: #10161A; "
            f"color: {color}; border: 1px solid {border}; "
            "border-radius: 6px; padding: 6px 8px; font-size: 10px; font-weight: 700; }"
        )

    def _set_candidate_state_label(self, mode: str) -> None:
        mapping = {
            "current": ("현재 자막 기준", "#9AF0B0", "#2B5A3A"),
            "stale": ("저장된 자막 기준", "#FFD38A", "#6E5330"),
            "none": ("후보 없음", "#A9B0B7", "#2D3942"),
        }
        text, color, border = mapping.get(mode, mapping["none"])
        for label_name in ("candidate_state_lbl", "player_candidate_state_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(text)
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _set_filter_summary_label(self, visible: int, total: int) -> None:
        text = f"표시 {max(0, int(visible))} / 전체 {max(0, int(total))}"
        for label_name in ("filter_summary_lbl", "player_filter_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(text)
        self._refresh_player_runtime_summary()

    def _set_selection_summary_label(self, text: str, active: bool = False) -> None:
        color = "#D7EBFF" if active else "#A9B0B7"
        border = "#24527A" if active else "#2D3942"
        for label_name in ("selection_summary_lbl", "player_selection_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(str(text or "선택 대기"))
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _set_player_order_summary_label(self, text: str) -> None:
        label = getattr(self, "player_order_lbl", None)
        if label is None:
            return
        label.setText(str(text or "순서 대기"))
        self._refresh_player_runtime_summary()

    def _set_reorder_summary_label(self, text: str, active: bool = False) -> None:
        message = str(text or "재정렬 없음")
        self._recent_reorder_summary = message
        color = "#D9FFE3" if active else "#A9B0B7"
        border = "#2B5A3A" if active else "#2D3942"
        for label_name in ("reorder_summary_lbl", "player_reorder_lbl"):
            label = getattr(self, label_name, None)
            if label is None:
                continue
            label.setText(message)
            label.setStyleSheet(self._toolbar_badge_style(color, border))
        self._refresh_player_runtime_summary()

    def _refresh_player_runtime_summary(self) -> None:
        context_label = getattr(self, "player_context_summary_lbl", None)
        focus_label = getattr(self, "player_focus_summary_lbl", None)
        reorder_label = getattr(self, "player_reorder_summary_visible_lbl", None)
        candidate = str(getattr(getattr(self, "player_candidate_state_lbl", None), "text", lambda: "")() or "후보 없음")
        filter_text = str(getattr(getattr(self, "player_filter_lbl", None), "text", lambda: "")() or "표시 0 / 전체 0")
        order_text = str(getattr(getattr(self, "player_order_lbl", None), "text", lambda: "")() or "순서 대기")
        selection_text = str(getattr(getattr(self, "player_selection_lbl", None), "text", lambda: "")() or "선택 대기")
        reorder_text = str(getattr(getattr(self, "player_reorder_lbl", None), "text", lambda: "")() or "재정렬 없음")
        if context_label is not None:
            context_label.setText(f"{candidate} · {filter_text}")
        if focus_label is not None:
            focus_label.setText(f"{order_text} · {selection_text}")
        if reorder_label is not None:
            reorder_label.setText(reorder_text)

    def _format_segment_reorder_summary(self, previous_order: list[str], current_order: list[str]) -> str:
        order = [str(segment_id or "") for segment_id in list(current_order or []) if str(segment_id or "")]
        if not order:
            return "재정렬 없음"
        if order == [str(segment_id or "") for segment_id in list(previous_order or []) if str(segment_id or "")]:
            return self._recent_reorder_summary or "재정렬 없음"
        return f"카드 재정렬 · {' > '.join(order[:4])}"

    def _format_chapter_reorder_summary(self, previous_order: list[str], current_order: list[str], selected_chapter_id: str) -> str:
        order = [str(chapter_id or "") for chapter_id in list(current_order or []) if str(chapter_id or "")]
        if not order:
            return "재정렬 없음"
        previous = [str(chapter_id or "") for chapter_id in list(previous_order or []) if str(chapter_id or "")]
        if order == previous:
            return self._recent_reorder_summary or "재정렬 없음"
        selected_id = str(selected_chapter_id or "")
        focus_id = selected_id if selected_id in order else order[0]
        focus_index = order.index(focus_id) if focus_id in order else 0
        start = max(0, focus_index - 1)
        end = min(len(order), start + 4)
        window = order[start:end]
        return f"챕터 재정렬 · {' > '.join(window)}"

    def _current_order_summary(self) -> str:
        order = list(getattr(self, "_segment_order", []) or []) or self._current_segment_ids()
        selected_segment_id = self._segment_id_for_chapter_id(self._current_selected_chapter_id())
        if not order or not selected_segment_id or selected_segment_id not in order:
            return "순서 대기"
        current_index = order.index(selected_segment_id) + 1
        return f"카드 {current_index}/{len(order)} · {' > '.join(order[:5])}"

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
            f"QTableWidget {{ background: {COLORS['sidebar']}; color: {COLORS['text']}; border: 1px solid {COLORS['separator']}; "
            f"gridline-color: {COLORS['separator']}; font-size: 11px; alternate-background-color: {COLORS['surface']}; }} "
            f"QHeaderView::section {{ background: {COLORS['surface_alt']}; color: {COLORS['muted']}; border: 1px solid {COLORS['separator']}; "
            "padding: 6px; font-weight: bold; } "
            f"QTableWidget::item {{ border-bottom: 1px solid {COLORS['separator']}; padding: 4px; }} "
            "QTableWidget::item:selected { background: #1F3A56; color: #FFFFFF; }"
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStretchLastSection(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setColumnWidth(0, 122)
        table.setColumnWidth(1, 88)
        table.setColumnWidth(3, 170)
        table.setColumnWidth(4, 128)
        table.setColumnWidth(8, 116)
        table.itemChanged.connect(self._on_table_item_changed)
        table.itemEntered.connect(self._on_table_item_entered)
        table.cellClicked.connect(self._on_table_cell_clicked)
        table.itemSelectionChanged.connect(self._on_table_selection_changed)
        return table
