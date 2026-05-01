# Version: 03.02.14
# Phase: PHASE2
"""
ui/home_ui.py
MainWindow 홈 화면 빌드 Mixin
"""
import os
import re
from html import escape
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QCheckBox, QScrollArea, QComboBox, QMessageBox,
    QToolButton, QSizePolicy, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QSize, QDateTime
from PyQt6.QtGui import QIcon, QColor, QCursor

import config
from core.path_manager import (
    get_icloud_path,
    get_icloud_auto_detect, get_nas_auto_detect,
    set_icloud_path, set_nas_path, get_nas_path, get_local_path,
    set_icloud_auto_detect, set_nas_auto_detect, ensure_nas_mounted,
    get_nas_excluded_folders
)
from core.settings import load_settings, save_settings
from core.audio.audio_presets import apply_audio_preset, load_audio_presets
from core.audio.stt_quality_presets import (
    apply_stt_quality_preset,
    load_stt_quality_presets,
    normalize_stt_quality_key,
)
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE
from ui.style import button_style, label_style, line_icon, tool_button_style, settings_dialog_stylesheet


ROUGHCUT_LLM_MIN_PARAMETERS_B = 7.0
ROUGHCUT_LLM_MIN_SIZE_BYTES = 3_500_000_000
ROUGHCUT_CAPABLE_CLOUD_TOKENS = (
    "gemini 2.5 pro",
    "gpt-5.2",
    "gpt-5.5",
)
ROUGHCUT_BLOCKED_CLOUD_TOKENS = (
    "flash",
    "nano",
    "mini",
)
ROUGHCUT_CAPABLE_LOCAL_LATEST = (
    "exaone3.5:latest",
    "gemma2:latest",
    "llama3:latest",
    "llama3.1:latest",
    "mistral:latest",
    "qwen2.5:latest",
)


class HomeUIMixin:

    def _build_home_content(self):
        self._preview_containers = []
        self._watchdog_labels = []
        overlay = getattr(self, "_project_info_overlay", None)
        if overlay is not None:
            try:
                overlay.setParent(None)
                overlay.deleteLater()
            except RuntimeError:
                pass
            self._project_info_overlay = None
        for attr in ("status_rail", "saved_status_label", "sidebar_settings_label", "sidebar_terminal_panel", "sidebar_preset_panel"):
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.setParent(None)
                except RuntimeError:
                    if attr == "status_rail":
                        from ui.menu_bar import StatusRail
                        self.status_rail = StatusRail(self.home_page)
                        if hasattr(self, "global_menu_bar"):
                            self.global_menu_bar.set_status_rail(self.status_rail)
                    elif attr == "saved_status_label":
                        self.saved_status_label = QLabel("", self.home_page)
                        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
                        self.saved_status_label.setStyleSheet("color: #A9B0B7; font-size: 11px; background: transparent;")
                    else:
                        if attr == "sidebar_settings_label":
                            self.sidebar_settings_label = QLabel("", self.home_page)
                            self.sidebar_settings_label.setWordWrap(True)
                            self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 9px; font-weight: bold; background: transparent; border: none;")
                        elif attr == "sidebar_terminal_panel" and hasattr(self, "_create_sidebar_terminal_panel"):
                            self._create_sidebar_terminal_panel()
        old_layout = self.home_page.layout()
        if old_layout is not None: QWidget().setLayout(old_layout)
        is_unified = bool(getattr(self, "_unified_dashboard", False))
        layout = QVBoxLayout(self.home_page)
        layout.setContentsMargins(8 if is_unified else 30, 12 if is_unified else 20, 8 if is_unified else 30, 8 if is_unified else 15)
        layout.setSpacing(5)
        if not is_unified:
            layout.addSpacing(40)
        if is_unified:
            if not hasattr(self, "saved_status_label"):
                self.saved_status_label = QLabel("", self.home_page)
                self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
            self.saved_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.saved_status_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold; background: transparent; border: none;")
            self._refresh_saved_status_label()
            layout.addWidget(self.saved_status_label)
            if hasattr(self, "status_rail"):
                layout.addWidget(self.status_rail)
        else:
            title = QLabel("AI Subtitle Studio")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
            layout.addWidget(title)
            layout.addSpacing(6)
        columns = QVBoxLayout() if is_unified else QHBoxLayout()
        columns.setSpacing(8)
        left_widget = QWidget(); left_col = QVBoxLayout(left_widget); left_col.setContentsMargins(0, 0, 0, 0); left_col.setSpacing(4)
        if is_unified:
            sidebar_mode = self._sidebar_active_mode()
            left_col.addWidget(self._btn("홈", "", self.show_home, active=sidebar_mode == "home", icon_name="home"))
            left_col.addWidget(self._btn("에디터", "", self._open_editor_screen, active=sidebar_mode == "editor", icon_name="subtitle"))
            left_col.addWidget(self._btn("러프컷", "", self._open_roughcut_helper, active=sidebar_mode == "roughcut", icon_name="roughcut"))
            left_col.addWidget(self._btn("숏폼", "", self._open_shortform_maker, icon_name="shortform"))
            left_col.addSpacing(8)
            icloud_files, count_str, comp_str = self._get_icloud_files()
            nas_folders, nas_count, nas_comp = self._get_nas_folders()
            left_col.addWidget(self._icloud_btn("☁ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
            left_col.addWidget(self._icloud_btn("▣ NAS 자동 처리", nas_folders, self._open_nas_root, is_nas=True, subtitle=nas_count, comp_title=nas_comp))
            left_col.addWidget(self._ensure_sidebar_queue_panel())
        else:
            left_col.addWidget(self._btn("📂 파일 선택", "영상/음성/srt 직접 선택", self.select_files))
            left_col.addWidget(self._btn("📁 폴더 선택", "폴더에서 영상 일괄 선택", self.select_folder))
            left_col.addWidget(self._btn("📝 프로젝트 만들기", "영상 묶어서 프로젝트 관리", self._create_project))
            left_col.addWidget(self._btn("📦 프로젝트 열기", "기존 프로젝트 불러오기", self._open_project))
            left_col.addWidget(self._btn("✂️ 러프컷", "PHASE2 핵심 기능", self._open_roughcut_helper))
            left_col.addWidget(self._btn("📱 숏폼 제작기", "PHASE3 개발 예정", self._open_shortform_maker))
        if not is_unified:
            left_col.addStretch()
        right_widget = QWidget(); right_col = QVBoxLayout(right_widget); right_col.setContentsMargins(0, 0, 0, 0); right_col.setSpacing(8)
        icloud_files, count_str, comp_str = self._get_icloud_files()
        if not is_unified:
            right_col.addWidget(self._icloud_btn("☁️ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
        nas_folders, nas_count, nas_comp = self._get_nas_folders()
        if not is_unified:
            right_col.addWidget(self._icloud_btn("🗄️ NAS 자동 처리", nas_folders, self._open_nas_root, is_nas=True, subtitle=nas_count, comp_title=nas_comp))
        if not is_unified:
            right_col.addStretch()
        columns.addWidget(left_widget, stretch=1)
        if not is_unified:
            columns.addWidget(right_widget, stretch=1)
        layout.addLayout(columns)
        layout.addStretch()
        if is_unified:
            layout.addWidget(self._ensure_sidebar_preset_panel())
            layout.addWidget(self._sidebar_status_card())
            terminal_panel = (
                self._ensure_sidebar_terminal_panel()
                if hasattr(self, "_ensure_sidebar_terminal_panel")
                else getattr(self, "sidebar_terminal_panel", None)
            )
            if terminal_panel is not None:
                terminal_panel.setVisible(bool(getattr(self, "_log_visible", True)))
                layout.addWidget(terminal_panel, stretch=1)
            layout.addWidget(self._project_info_card(expanded=False))
            if bool(getattr(self, "_project_info_expanded", False)):
                QTimer.singleShot(0, self._show_project_info_overlay)
        bottom_bar = QHBoxLayout()
        from config import APP_VERSION
        if not is_unified:
            version_lbl = QLabel(f"v{APP_VERSION}")
            version_lbl.setStyleSheet("color: #D1D1D6; font-size: 11px;")
            bottom_bar.addWidget(version_lbl)
        if not is_unified:
            bottom_bar.addWidget(self._editor_shortcuts_row())
            bottom_bar.addStretch()
        else:
            bottom_bar.addStretch()
        if not is_unified:
            btn_settings = QPushButton("⚙️ 자동설정"); btn_settings.setStyleSheet(button_style("toolbar")); btn_settings.clicked.connect(self._show_path_settings)
            btn_auto_start = QPushButton(self._auto_start_label()); btn_auto_start.setStyleSheet(self._auto_start_style()); btn_auto_start.clicked.connect(self._toggle_auto_start_enabled)
            btn_clear_cache = QPushButton("🗑️ 캐쉬삭제"); btn_clear_cache.setStyleSheet(button_style("toolbar")); btn_clear_cache.clicked.connect(self._clear_cache)
            btn_log = QPushButton(self._terminal_log_label()); btn_log.setStyleSheet(button_style("toolbar")); btn_log.clicked.connect(self._toggle_log)
            btn_exit = QPushButton("❌ 종료"); btn_exit.setStyleSheet(button_style("danger")); btn_exit.clicked.connect(self._quick_exit)
            bottom_bar.addWidget(btn_settings); bottom_bar.addWidget(btn_auto_start); bottom_bar.addWidget(btn_clear_cache); bottom_bar.addWidget(btn_log); bottom_bar.addWidget(btn_exit)
        if not is_unified:
            layout.addLayout(bottom_bar)
        self._ensure_watchdog_timer()


    def _is_auto_start_enabled(self):
        return bool(load_settings().get("auto_start_enabled", True))

    def _current_status_time_text(self) -> str:
        text = QDateTime.currentDateTime().toString("AP h:mm")
        return text.replace("AM", "오전").replace("PM", "오후")

    def _ensure_sidebar_queue_panel(self):
        from ui.queue.sidebar_queue_panel import SidebarQueuePanel

        panel = getattr(self, "sidebar_queue_panel", None)
        if panel is not None:
            try:
                if panel.parent() is None:
                    panel.setParent(self.home_page)
                self._sync_sidebar_queue_panel()
                return panel
            except RuntimeError:
                pass
        panel = SidebarQueuePanel(self.home_page)
        self.sidebar_queue_panel = panel
        self._sync_sidebar_queue_panel()
        return panel

    def _queue_sidebar_header_text(self) -> str:
        label = getattr(self, "queue_header_lbl", None)
        raw = ""
        if label is not None:
            try:
                raw = str(label.text() or "")
            except RuntimeError:
                raw = ""
        if raw:
            raw = raw.replace("📋 처리할 파일 리스트", "큐 리스트").replace("진행 중", "").strip()
            raw = raw.replace("  ", " ")
            return raw
        total = int(getattr(self, "_total_files", 0) or 0)
        current = int(getattr(self, "_current_file_idx", 0) or 0)
        pct = int(getattr(self, "_real_pct", 0) or 0)
        return f"큐 리스트 : ({current}/{total}) - {pct}% 완료"

    def _sidebar_queue_items(self) -> list[dict]:
        table = getattr(self, "queue_table", None)
        if table is None:
            return []
        items = []
        try:
            for row in range(table.rowCount()):
                status_item = table.item(row, 0)
                file_item = table.item(row, 1)
                eta_item = table.item(row, 4)
                status = self._plain_queue_status(str(status_item.text() if status_item else "-"))
                items.append({
                    "order": str(row + 1),
                    "status": status,
                    "done": "완료" in status,
                    "file": str(file_item.text() if file_item else "-"),
                    "eta": str(eta_item.text() if eta_item else "-"),
                })
        except RuntimeError:
            return []
        return items

    def _plain_queue_status(self, status: str) -> str:
        text = str(status or "").strip()
        text = re.sub(r"^[^\w가-힣\[]+\s*", "", text)
        text = re.sub(r"[\u2600-\u27BF\U0001F300-\U0001FAFF]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or "-"

    def _sync_sidebar_queue_panel(self):
        panel = getattr(self, "sidebar_queue_panel", None)
        if panel is None:
            return
        try:
            panel.set_queue(self._queue_sidebar_header_text(), self._sidebar_queue_items())
        except RuntimeError:
            self.sidebar_queue_panel = None

    def _sidebar_preset_combo_style(self) -> str:
        return (
            "QComboBox { background:#11181C; color:#F5F7FA; border:1px solid #2D3942; "
            "border-radius:5px; padding:2px 7px; font-size:9px; font-weight:700; "
            "min-height:22px; max-height:22px; } "
            "QComboBox:hover { border-color:#465663; background:#151C20; } "
            "QComboBox::drop-down { width:18px; border:none; } "
            "QComboBox QAbstractItemView { background:#151C20; color:#F5F7FA; "
            "selection-background-color:#0B84FF; border:1px solid #2D3942; }"
        )

    def _ensure_sidebar_preset_panel(self):
        panel = getattr(self, "sidebar_preset_panel", None)
        if panel is not None:
            try:
                if panel.parent() is None:
                    panel.setParent(self.home_page)
                self._sync_sidebar_preset_panel()
                return panel
            except RuntimeError:
                pass

        panel = QWidget(self.home_page)
        panel.setObjectName("SidebarPresetPanel")
        panel.setStyleSheet(
            "QWidget#SidebarPresetPanel { background:#151C20; border:1px solid #2D3942; border-radius:7px; }"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(9, 7, 9, 7)
        lay.setSpacing(5)

        title = QLabel("인식 프리셋")
        title.setStyleSheet("color:#F5F7FA; font-size:10px; font-weight:800; border:none; background:transparent;")
        lay.addWidget(title)

        self.sidebar_stt_quality_combo = QComboBox(panel)
        for key, preset in load_stt_quality_presets().items():
            label = str(preset.get("label") or key)
            self.sidebar_stt_quality_combo.addItem(label, key)
            desc = str(preset.get("description") or "")
            if desc:
                self.sidebar_stt_quality_combo.setItemData(
                    self.sidebar_stt_quality_combo.count() - 1,
                    desc,
                    Qt.ItemDataRole.ToolTipRole,
                )
        self.sidebar_stt_quality_combo.setStyleSheet(self._sidebar_preset_combo_style())
        self.sidebar_stt_quality_combo.currentIndexChanged.connect(self._on_sidebar_stt_quality_changed)
        lay.addWidget(self._sidebar_preset_row("정밀인식", self.sidebar_stt_quality_combo))

        self.sidebar_audio_preset_combo = QComboBox(panel)
        self.sidebar_audio_preset_combo.addItem("직접 설정", "")
        for name, preset in load_audio_presets().items():
            self.sidebar_audio_preset_combo.addItem(name, name)
            desc = str(preset.get("description") or "")
            if desc:
                self.sidebar_audio_preset_combo.setItemData(
                    self.sidebar_audio_preset_combo.count() - 1,
                    desc,
                    Qt.ItemDataRole.ToolTipRole,
                )
        self.sidebar_audio_preset_combo.setStyleSheet(self._sidebar_preset_combo_style())
        self.sidebar_audio_preset_combo.currentIndexChanged.connect(self._on_sidebar_audio_preset_changed)
        lay.addWidget(self._sidebar_preset_row("오디오", self.sidebar_audio_preset_combo))

        panel.setMaximumHeight(104)
        self.sidebar_preset_panel = panel
        self._sync_sidebar_preset_panel()
        return panel

    def _sidebar_preset_row(self, label_text: str, combo: QComboBox) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent; border:none;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        label = QLabel(label_text)
        label.setFixedWidth(48)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet("color:#A9B0B7; font-size:9px; font-weight:800; border:none; background:transparent;")
        lay.addWidget(label)
        lay.addWidget(combo, stretch=1)
        return row

    def _set_combo_data_silent(self, combo: QComboBox | None, value: str) -> None:
        if combo is None:
            return
        combo.blockSignals(True)
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == value:
                    combo.setCurrentIndex(i)
                    return
        finally:
            combo.blockSignals(False)

    def _sync_sidebar_preset_panel(self, settings: dict | None = None):
        settings = dict(settings or load_settings())
        self._set_combo_data_silent(
            getattr(self, "sidebar_stt_quality_combo", None),
            normalize_stt_quality_key(settings.get("stt_quality_preset", "balanced")),
        )
        self._set_combo_data_silent(
            getattr(self, "sidebar_audio_preset_combo", None),
            str(settings.get("audio_preset", "") or ""),
        )

    def _apply_sidebar_settings_update(self, updates: dict | None = None, preset_applier=None):
        settings = dict(load_settings())
        if callable(preset_applier):
            settings = dict(preset_applier(settings))
        if updates:
            settings.update(updates)
        self._apply_ai_settings(settings)
        self._sync_sidebar_preset_panel(settings)
        return settings

    def _on_sidebar_stt_quality_changed(self, *args):
        combo = getattr(self, "sidebar_stt_quality_combo", None)
        if combo is None:
            return
        self._apply_sidebar_settings_update(
            preset_applier=lambda settings: apply_stt_quality_preset(
                settings,
                combo.currentData() or "balanced",
            )
        )

    def _on_sidebar_audio_preset_changed(self, *args):
        combo = getattr(self, "sidebar_audio_preset_combo", None)
        if combo is None:
            return
        preset_name = combo.currentData() or ""
        if preset_name:
            self._apply_sidebar_settings_update(
                preset_applier=lambda settings: apply_audio_preset(settings, preset_name)
            )
        else:
            self._apply_sidebar_settings_update({"audio_preset": ""})

    def _is_workspace_dirty(self) -> bool:
        editor = self._active_editor()
        if editor is None:
            return bool(getattr(self, "_is_dirty", False))
        dirty_checker = getattr(editor, "_has_unsaved_changes", None)
        if callable(dirty_checker):
            try:
                return bool(dirty_checker())
            except Exception:
                pass
        state_manager = getattr(editor, "sm", None)
        if state_manager is not None:
            return bool(getattr(state_manager, "is_dirty", False))
        return bool(getattr(editor, "_is_dirty", False))

    def _is_subtitle_generation_running(self) -> bool:
        editor = self._active_editor()
        if editor is not None:
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None:
                if str(getattr(state_manager, "state", "") or "") == "ST_PROC":
                    return True
                if bool(getattr(state_manager, "is_locked", False)):
                    return True
            if bool(getattr(editor, "_is_ai_processing", False)):
                return True
        backend = getattr(self, "backend", None)
        for attr in ("_active", "is_running", "running"):
            value = getattr(backend, attr, False)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    value = False
            if bool(value):
                return True
        return bool(getattr(self, "_auto_processing_active", False))

    def _subtitle_status_text(self) -> str:
        if self._is_subtitle_generation_running():
            return "생성 중"
        editor = self._active_editor()
        if editor is not None:
            state_manager = getattr(editor, "sm", None)
            state = str(getattr(state_manager, "state", "") or "")
            if state in {"ST_COMP", "ST_SAVED"}:
                return "완료"
        return "대기"

    def _roughcut_status_text(self) -> str:
        editor = self._active_editor()
        if editor is None:
            return "대기"
        if not bool(getattr(editor, "_roughcut_draft_runtime_enabled", lambda: False)()):
            return "비활성"
        status = str(getattr(editor, "_roughcut_draft_status", "") or "")
        count = getattr(editor, "_last_roughcut_draft_major_count", None)
        if status == "queued":
            return "예약"
        if status == "running":
            return "생성 중"
        if status == "saving":
            return "저장 중"
        if status == "failed":
            return "실패"
        if status == "done":
            return f"완료 {count}개" if count is not None else "완료"
        if count is not None:
            return f"완료 {count}개"
        return "대기"

    def _ensure_saved_status_blink_timer(self):
        if hasattr(self, "_saved_status_blink_timer"):
            return
        self._saved_status_blink_on = True
        self._saved_status_blink_timer = QTimer(self)
        self._saved_status_blink_timer.setInterval(1000)
        self._saved_status_blink_timer.timeout.connect(self._tick_saved_status_blink)

    def _tick_saved_status_blink(self):
        self._saved_status_blink_on = not bool(getattr(self, "_saved_status_blink_on", True))
        self._refresh_saved_status_label(is_dirty=getattr(self, "_last_saved_status_dirty", None))
        if getattr(self, "sidebar_settings_label", None) is not None:
            self._refresh_sidebar_engine_info()

    def _sync_saved_status_blink_timer(self, active: bool):
        self._ensure_saved_status_blink_timer()
        timer = self._saved_status_blink_timer
        if active:
            if not timer.isActive():
                self._saved_status_blink_on = True
                timer.start()
        else:
            if timer.isActive():
                timer.stop()
            self._saved_status_blink_on = True

    def _refresh_saved_status_label(self, is_dirty=None, touch_saved_time=False):
        label = getattr(self, "saved_status_label", None)
        if label is None:
            return
        dirty = self._is_workspace_dirty() if is_dirty is None else bool(is_dirty)
        self._last_saved_status_dirty = dirty
        if not hasattr(self, "_last_saved_status_time"):
            self._last_saved_status_time = self._current_status_time_text()
        if not dirty and touch_saved_time:
            self._last_saved_status_time = self._current_status_time_text()

        generating = self._is_subtitle_generation_running()
        self._sync_saved_status_blink_timer(generating)
        if generating:
            dot_color = "#FF453A" if bool(getattr(self, "_saved_status_blink_on", True)) else "#5A1F24"
            tooltip = "자막 생성 중입니다."
        else:
            dot_color = "#FF453A" if dirty else "#34C759"
            tooltip = "저장되지 않은 변경사항이 있습니다." if dirty else "저장된 상태입니다."
        label.setTextFormat(Qt.TextFormat.RichText)
        from config import APP_VERSION
        label.setText(
            f"<span style='color:{dot_color}; font-size:13px;'>●</span> "
            f"<span style='color:#FFFFFF; font-size:14px; font-weight:700;'>AI Subtitle Studio</span> "
            f"<span style='color:#D1D1D6; font-size:11px; font-weight:600;'>v{APP_VERSION}</span>"
        )
        label.setToolTip(tooltip)

    def _format_engine_info_text(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        return "\n".join(lines)

    def _short_model_name(self, model: str) -> str:
        text = str(model or "").strip()
        if not text:
            return "미사용"
        if "사용 안함" in text:
            return "미사용"
        for prefix in ("mlx-community/", "Systran/", "youngouk/", "ghost613/", "o0dimplz0o/"):
            text = text.replace(prefix, "")
        text = text.replace("-mlx", "")
        return text

    def _audio_model_name(self, settings: dict) -> str:
        return {
            "deepfilter": "DeepFilter",
            "rnnoise": "RNNoise",
            "resemble_enhance": "Resemble",
            "clearvoice": "ClearVoice",
            "none": "미사용",
        }.get(settings.get("selected_audio_ai", "none"), "미사용")

    def _vad_model_name(self, settings: dict) -> tuple[str, str]:
        vad_model = {
            "silero": "Silero",
            "ten_vad": "TEN VAD",
            "webrtc": "WebRTC",
            "pyannote": "Pyannote",
            "none": "미사용",
        }.get(settings.get("selected_vad", "none"), "미사용")
        if vad_model == "미사용":
            return vad_model, "검수 안 함"
        if settings.get("vad_pre_split_enabled", False):
            return vad_model, "STT 선분할"
        if settings.get("vad_post_stt_align_enabled", True):
            return vad_model, "자막 위치 재계산"
        return vad_model, "자막/음성 겹침 검수"

    def _roughcut_llm_name(self, settings: dict, subtitle_llm: str) -> tuple[str, str]:
        if not bool(settings.get("roughcut_llm_enabled", False)):
            return "미사용", "러프컷 규칙 기반"
        model = str(settings.get("roughcut_llm_model", "") or "").strip()
        if not model or model.lower() == "inherit" or "사용 안함" in model:
            return "미사용", "러프컷 규칙 기반"
        return self._short_model_name(model), "러프컷 전용"

    def _pipeline_rows(self, settings: dict) -> list[tuple[str, str, str]]:
        subtitle_llm = str(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "기본")) or "기본")
        vad_model, _vad_role = self._vad_model_name(settings)
        roughcut_llm, _roughcut_role = self._roughcut_llm_name(settings, subtitle_llm)
        stt1_model = self._short_model_name(settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "기본")))
        stt2_model = "미사용"
        if settings.get("stt_ensemble_enabled"):
            stt2_model = self._short_model_name(settings.get("selected_whisper_model_secondary", ""))
        return [
            ("preprocess", "전처리", "FFMPEG"),
            ("audio", "음성", self._audio_model_name(settings)),
            ("stt1", "STT 1", stt1_model),
            ("stt2", "STT 2", stt2_model),
            ("vad", "VAD", vad_model),
            ("subtitle_llm", "자막 LLM", self._short_model_name(subtitle_llm)),
            ("roughcut_llm", "러프컷 LLM", roughcut_llm),
        ]

    def _pipeline_status_blob(self) -> str:
        parts = []
        for attr in ("queue_header_lbl", "saved_status_label"):
            label = getattr(self, attr, None)
            if label is None:
                continue
            try:
                parts.append(str(label.text() or ""))
            except RuntimeError:
                pass
        table = getattr(self, "queue_table", None)
        if table is not None:
            try:
                if table.rowCount() > 0:
                    for col in (0, 2, 4):
                        item = table.item(0, col)
                        if item is not None:
                            parts.append(str(item.text() or ""))
            except RuntimeError:
                pass
        return " ".join(parts).lower()

    def _roughcut_draft_status_value(self) -> str:
        editor = self._active_editor()
        if editor is None:
            return ""
        return str(getattr(editor, "_roughcut_draft_status", "") or "")

    def _pipeline_current_stage_keys(self, settings: dict) -> set[str]:
        roughcut_status = self._roughcut_draft_status_value()
        if roughcut_status in {"queued", "running", "saving"}:
            return {"roughcut_llm"}
        if not self._is_subtitle_generation_running():
            return set()

        blob = self._pipeline_status_blob()
        if any(token in blob for token in ("[전처리]", "오디오 추출", "ffmpeg 오디오", "전처리")):
            return {"preprocess"}
        if any(token in blob for token in ("[음성]", "음량", "필터", "deepfilter", "rnnoise", "resemble", "clearvoice", "노이즈", "보컬")):
            return {"audio"}
        if "[stt+자막 llm]" in blob:
            keys = {"stt1", "subtitle_llm"}
            if settings.get("stt_ensemble_enabled"):
                keys.add("stt2")
            return keys
        if any(token in blob for token in ("[자막 llm]", "llm", "최적화", "교정", "분리")):
            return {"subtitle_llm"}
        if any(token in blob for token in ("[vad]", "silero", "검수", "위치 재계산", "음성 섹터")):
            return {"vad"}
        if any(token in blob for token in ("[stt", "whisper", "stt", "자막 생성")):
            keys = {"stt1"}
            if settings.get("stt_ensemble_enabled"):
                keys.add("stt2")
            return keys
        keys = {"stt1"}
        if settings.get("stt_ensemble_enabled"):
            keys.add("stt2")
        return keys

    def _pipeline_completed_stage_keys(self, settings: dict, current_keys: set[str]) -> set[str]:
        rows = self._pipeline_rows(settings)
        order = [key for key, _stage, _model in rows]
        completed: set[str] = set()
        blob = self._pipeline_status_blob()
        editor = self._active_editor()
        state_manager = getattr(editor, "sm", None) if editor is not None else None
        editor_state = str(getattr(state_manager, "state", "") or "")
        generation_running = self._is_subtitle_generation_running()
        generation_done = (
            not generation_running
            and (editor_state in {"ST_COMP", "ST_SAVED"} or "자막 생성 완료" in blob)
        )

        if generation_done:
            completed.update(key for key in order if key != "roughcut_llm")
        elif current_keys:
            current_indexes = [order.index(key) for key in current_keys if key in order]
            if current_indexes:
                completed.update(order[:min(current_indexes)])
            if current_keys == {"vad"} and any(token in blob for token in ("준비", "스캔", "캐시")):
                completed.difference_update({"stt1", "stt2", "subtitle_llm"})

        roughcut_status = self._roughcut_draft_status_value()
        editor_count = getattr(editor, "_last_roughcut_draft_major_count", None) if editor is not None else None
        if roughcut_status == "done" or editor_count is not None:
            completed.add("roughcut_llm")
        if self._roughcut_status_text().startswith("완료"):
            completed.add("roughcut_llm")

        if not settings.get("stt_ensemble_enabled", False):
            completed.discard("stt2")
        if settings.get("selected_vad", "none") == "none":
            completed.discard("vad")
        return completed

    def _pipeline_model_link(self, key: str, text: str, *, current: bool = False, completed: bool = False) -> str:
        color = "#00D46A" if completed else ("#FFD60A" if current else "#F5F7FA")
        dropdown_icon = " ▾" if key in {"audio", "stt1", "stt2", "vad", "subtitle_llm", "roughcut_llm"} else ""
        return (
            f"<a href='model:{escape(key)}' "
            f"style='color:{color}; text-decoration:none; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;'>"
            f"{escape(text)}<span style='color:#8EA4B8; font-weight:400;'>{dropdown_icon}</span></a>"
        )

    def _pipeline_info_html(self, settings: dict) -> str:
        rows = []
        model_links = {
            "음성": "audio",
            "STT 1": "stt1",
            "STT 2": "stt2",
            "VAD": "vad",
            "자막 LLM": "subtitle_llm",
            "러프컷 LLM": "roughcut_llm",
        }
        current_keys = self._pipeline_current_stage_keys(settings)
        completed_keys = self._pipeline_completed_stage_keys(settings, current_keys)
        for idx, (key, stage, model) in enumerate(self._pipeline_rows(settings), 1):
            current = key in current_keys
            completed = key in completed_keys
            bg_style = " background-color:#12362A;" if current else ""
            num_color = "#00D46A" if completed else ("#FFD60A" if current else "#6F7A83")
            stage_color = num_color if (completed or current) else "#DCE3EA"
            model_color = num_color if (completed or current) else "#F5F7FA"
            model_html = (
                self._pipeline_model_link(model_links[stage], model, current=current, completed=completed)
                if stage in model_links
                else escape(model)
            )
            rows.append(
                "<tr>"
                f"<td style='color:{num_color}; padding:1px 6px 1px 0; font-weight:800;{bg_style}'>{idx}</td>"
                f"<td style='color:{stage_color}; padding:1px 10px 1px 0; font-weight:800;{bg_style}'>{escape(stage)}</td>"
                f"<td style='color:{model_color}; padding:1px 0; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;{bg_style}'>{model_html}</td>"
                "</tr>"
            )
        return (
            "<table cellspacing='0' cellpadding='0' style='font-size:9px;'>"
            "<tr>"
            "<td></td>"
            "<td style='color:#00D46A; padding:0 10px 2px 0; font-weight:800;'>단계</td>"
            "<td style='color:#00D46A; padding:0 0 2px 0; font-family:Menlo, Monaco, Consolas, monospace; font-weight:400;'>모델</td>"
            "</tr>"
            + "".join(rows)
            + "</table>"
        )

    def _pipeline_info_plain(self, settings: dict) -> str:
        return "\n".join(
            f"{idx}. [{stage}] {model}"
            for idx, (_key, stage, model) in enumerate(self._pipeline_rows(settings), 1)
        )

    def _current_engine_info_text(self) -> str:
        settings = load_settings()
        return self._pipeline_info_html(settings)

    def _refresh_sidebar_engine_info(self, text=None, settings: dict | None = None):
        label = getattr(self, "sidebar_settings_label", None)
        if label is None:
            return
        settings = dict(settings or load_settings())
        formatted = self._pipeline_info_html(settings)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(False)
        try:
            label.linkActivated.disconnect()
        except Exception:
            pass
        label.linkActivated.connect(self._on_sidebar_model_link)
        label.setText(formatted)
        label.setToolTip(self._pipeline_info_plain(settings))
        self._sync_sidebar_preset_panel(settings)

    def _apply_ai_settings(self, settings: dict):
        save_settings(settings)
        editor = self._active_editor()
        if editor is not None:
            try:
                editor.settings = dict(settings)
                editor.selected_model = settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "exaone3.5:7.8b"))
                if hasattr(editor, "_update_engine_label_text"):
                    editor._update_engine_label_text()
                    engine_label = getattr(editor, "engine_lbl", None)
                    if engine_label is not None:
                        self._refresh_sidebar_engine_info(engine_label.text(), settings=settings)
                        return
            except Exception:
                pass
        self._refresh_sidebar_engine_info()

    def _whisper_model_items(self) -> list[str]:
        try:
            from ui.settings.settings_common import DEFAULT_WHISPER_MODELS
            models = list(DEFAULT_WHISPER_MODELS)
        except Exception:
            models = [getattr(config, "WHISPER_MODEL", "large-v3")]
        hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if os.path.exists(hf_cache_dir):
            try:
                for folder_name in os.listdir(hf_cache_dir):
                    if folder_name.startswith("models--") and "whisper" in folder_name.lower():
                        repo_name = folder_name.replace("models--", "", 1).replace("--", "/", 1)
                        if repo_name not in models:
                            models.append(repo_name)
            except Exception:
                pass
        return models

    def _stt1_model_items(self) -> list[str]:
        blocked = ("ghost613", "zeroth")
        return [
            model for model in self._whisper_model_items()
            if not any(token in str(model).lower() for token in blocked)
        ]

    def _stt2_model_items(self) -> list[str]:
        picked = []
        for model in self._whisper_model_items():
            model_l = str(model).lower()
            if "ghost613" not in model_l and "zeroth" not in model_l:
                continue
            if model not in picked:
                picked.append(model)
        return picked

    def _llm_model_items(self) -> list[dict]:
        items = [
            {
                "name": "사용 안함 (Whisper 단독 진행)",
                "display_name": "사용 안함 (Whisper 단독 진행)",
                "details": {"provider": "none"},
            }
        ]
        try:
            from ui.settings.settings_common import _fetch_models
            for item in _fetch_models():
                row = dict(item)
                details = dict(row.get("details", {}) or {})
                details.setdefault("provider", "ollama")
                row["details"] = details
                row.setdefault("display_name", row.get("name", ""))
                items.append(row)
        except Exception:
            pass
        try:
            from core.llm.provider_registry import cloud_model_items
            items.extend(cloud_model_items())
        except Exception:
            pass
        return items

    def _roughcut_llm_parameter_b(self, item: dict) -> float | None:
        details = item.get("details", {}) or {}
        parts = [
            str(item.get("name") or ""),
            str(item.get("display_name") or ""),
            str(details.get("parameter_size") or ""),
            str(details.get("family") or ""),
        ]
        for text in parts:
            for match in re.finditer(r"(?<!\d)(\d+(?:\.\d+)?)\s*b\b", text.lower()):
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def _roughcut_llm_is_capable(self, item: dict) -> bool:
        details = item.get("details", {}) or {}
        provider = str(details.get("provider") or "ollama").lower()
        name = str(item.get("name") or "")
        display_name = str(item.get("display_name") or name)
        label_l = f"{name} {display_name}".lower()
        if provider == "none" or "사용 안함" in label_l:
            return False

        if provider in {"google", "openai"}:
            if any(re.search(rf"\b{re.escape(token)}\b", label_l) for token in ROUGHCUT_BLOCKED_CLOUD_TOKENS):
                return False
            return any(token in label_l for token in ROUGHCUT_CAPABLE_CLOUD_TOKENS) or "gpt-5" in label_l

        params_b = self._roughcut_llm_parameter_b(item)
        if params_b is not None:
            return params_b >= ROUGHCUT_LLM_MIN_PARAMETERS_B

        if any(token in label_l for token in ROUGHCUT_CAPABLE_LOCAL_LATEST):
            return True

        try:
            return int(item.get("size") or 0) >= ROUGHCUT_LLM_MIN_SIZE_BYTES
        except (TypeError, ValueError):
            return False

    def _roughcut_llm_items(self) -> list[dict]:
        return [item for item in self._llm_model_items() if self._roughcut_llm_is_capable(item)]

    def _apply_sidebar_model_selection(self, updates: dict):
        self._apply_sidebar_settings_update(updates)

    def _add_action(self, menu: QMenu, label: str, callback, *, checked: bool = False):
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(bool(checked))
        action.triggered.connect(callback)
        return action

    def _on_sidebar_model_link(self, href: str):
        key = str(href or "").replace("model:", "", 1)
        settings = load_settings()
        menu = QMenu(getattr(self, "home_page", None))

        if key == "audio":
            choices = [
                ("DeepFilter", "deepfilter"),
                ("RNNoise", "rnnoise"),
                ("Resemble Enhance", "resemble_enhance"),
                ("ClearVoice", "clearvoice"),
                ("미사용", "none"),
            ]
            current = settings.get("selected_audio_ai", "none")
            for label, value in choices:
                self._add_action(
                    menu,
                    label,
                    lambda _=False, v=value: self._apply_sidebar_model_selection({"selected_audio_ai": v}),
                    checked=value == current,
                )

        elif key == "vad":
            choices = [("Silero", "silero"), ("TEN VAD", "ten_vad"), ("미사용", "none")]
            current = settings.get("selected_vad", "silero")
            for label, value in choices:
                self._add_action(
                    menu,
                    label,
                    lambda _=False, v=value: self._apply_sidebar_model_selection({"selected_vad": v}),
                    checked=value == current,
                )

        elif key in {"stt", "stt1", "stt2"}:
            ensemble = bool(settings.get("stt_ensemble_enabled", False))
            current1 = settings.get("selected_whisper_model", "")
            current2 = settings.get("selected_whisper_model_secondary", "")
            if key == "stt2":
                self._add_action(
                    menu,
                    "STT2 앙상블 사용",
                    lambda checked=False: self._apply_sidebar_model_selection({"stt_ensemble_enabled": bool(checked)}),
                    checked=ensemble,
                )
                menu.addSeparator()
            models = self._stt1_model_items() if key in {"stt", "stt1"} else self._stt2_model_items()
            for model in models:
                label = self._short_model_name(model)
                if key in {"stt", "stt1"}:
                    self._add_action(
                        menu,
                        label,
                        lambda _=False, m=model: self._apply_sidebar_model_selection({"selected_whisper_model": m}),
                        checked=model == current1,
                    )
                    continue
                self._add_action(
                    menu,
                    label,
                    lambda _=False, m=model: self._apply_sidebar_model_selection({"selected_whisper_model_secondary": m, "stt_ensemble_enabled": True}),
                    checked=model == current2,
                )

        elif key in {"subtitle_llm", "roughcut_llm"}:
            if key == "roughcut_llm":
                self._add_action(
                    menu,
                    "사용 안함",
                    lambda _=False: self._apply_sidebar_model_selection({
                        "roughcut_llm_enabled": False,
                        "roughcut_llm_use_override": True,
                        "roughcut_llm_provider": "none",
                        "roughcut_llm_model": "사용 안함",
                    }),
                    checked=not bool(settings.get("roughcut_llm_enabled", False)),
                )
                menu.addSeparator()

            current = settings.get("selected_model", "") if key == "subtitle_llm" else settings.get("roughcut_llm_model", "")
            model_items = self._roughcut_llm_items() if key == "roughcut_llm" else self._llm_model_items()
            for item in model_items:
                name = str(item.get("name") or "")
                label = str(item.get("display_name") or name)
                provider = str((item.get("details", {}) or {}).get("provider") or "ollama")
                if key == "subtitle_llm":
                    updates = {"selected_model": name, "selected_llm_provider": provider}
                else:
                    updates = {
                        "roughcut_llm_enabled": True,
                        "roughcut_llm_use_override": True,
                        "roughcut_llm_provider": provider,
                        "roughcut_llm_model": name,
                    }
                self._add_action(
                    menu,
                    label,
                    lambda _=False, u=updates: self._apply_sidebar_model_selection(u),
                    checked=name == current,
                )

        if menu.actions():
            menu.exec(QCursor.pos())

    def _sidebar_status_card(self):
        card = QWidget()
        card.setStyleSheet("background: #1B2429; border: 1px solid #2D3942; border-radius: 7px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(4)

        if not hasattr(self, "saved_status_label"):
            self.saved_status_label = QLabel("", self.home_page)
            self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        if not hasattr(self, "sidebar_settings_label"):
            self.sidebar_settings_label = QLabel("", self.home_page)
        self.sidebar_settings_label.setWordWrap(True)
        self.sidebar_settings_label.setMinimumWidth(0)
        self.sidebar_settings_label.setTextFormat(Qt.TextFormat.RichText)
        self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        self._refresh_sidebar_engine_info()
        lay.addWidget(self.sidebar_settings_label)
        return card

    def _toggle_sidebar_stt_mode(self):
        self._current_work_mode = EDITOR_MODE
        editor = getattr(self, "_editor_widget", None)
        if editor is not None and hasattr(editor, "_toggle_stt_mode"):
            editor._toggle_stt_mode()
        elif hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()

    def _auto_start_label(self):
        return "자동시작 ON" if self._is_auto_start_enabled() else "자동시작 OFF"

    def _terminal_log_label(self):
        return "사이드바 숨기기" if getattr(self, "_log_visible", True) else "사이드바 보기"

    def _auto_start_style(self):
        if self._is_auto_start_enabled():
            return "background: #4AFF80; color: #000; font-weight: bold; border: none; padding: 6px 12px; border-radius: 4px;"
        return "background: #555; color: #FFF; font-weight: bold; border: none; padding: 6px 12px; border-radius: 4px;"

    def _ensure_watchdog_timer(self):
        if not hasattr(self, "_home_watchdog_timer"):
            self._home_watchdog_timer = QTimer(self)
            self._home_watchdog_timer.timeout.connect(self._tick_home_watchdog_labels)
        if self._watchdog_labels and self._is_auto_start_enabled():
            if not self._home_watchdog_timer.isActive():
                self._home_watchdog_timer.start(1000)
            self._tick_home_watchdog_labels()
        elif self._home_watchdog_timer.isActive():
            self._home_watchdog_timer.stop()

    def _watchdog_interval_for(self, is_nas: bool) -> int:
        manager = getattr(self, "_nas_sync_manager" if is_nas else "_cloud_sync_manager", None)
        if manager is not None:
            return max(1, int(getattr(manager, "scan_interval", 60 if is_nas else 3) or 1))
        return 60 if is_nas else 3

    def _tick_home_watchdog_labels(self):
        if not getattr(self, "_watchdog_labels", None):
            return
        for label, is_nas in list(self._watchdog_labels):
            if bool(getattr(self, "_auto_processing_active", False)):
                label.setText("대기중")
                label.setVisible(self._is_auto_start_enabled())
                continue
            interval = self._watchdog_interval_for(is_nas)
            key = "_nas_watchdog_left" if is_nas else "_icloud_watchdog_left"
            left = int(getattr(self, key, interval) or interval)
            left = interval if left <= 1 else left - 1
            setattr(self, key, left)
            label.setText(f"WD {left:02d}s")
            label.setVisible(self._is_auto_start_enabled())

    def _toggle_auto_start_enabled(self):
        settings = load_settings()
        enabled = not bool(settings.get("auto_start_enabled", True))
        settings["auto_start_enabled"] = enabled
        self._auto_start_on = enabled
        save_settings(settings)
        if enabled:
            self._icloud_watchdog_left = self._watchdog_interval_for(False)
            self._nas_watchdog_left = self._watchdog_interval_for(True)
            self._start_configured_watchers()
        else:
            if hasattr(self, "_cloud_sync_manager"):
                self._cloud_sync_manager.stop()
            if hasattr(self, "_nas_sync_manager"):
                self._nas_sync_manager.stop()
        self._refresh_after_auto_start_toggle()
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()

    def _refresh_after_auto_start_toggle(self):
        try:
            self._build_home_content()
        except Exception:
            pass
        try:
            self._ensure_watchdog_timer()
        except Exception:
            pass
        try:
            self._refresh_saved_status_label()
        except Exception:
            pass

    def _start_configured_watchers(self):
        if not self._is_auto_start_enabled():
            return
        if hasattr(self, "_cloud_sync_manager"):
            if getattr(self, "_is_icloud_auto_mode", False):
                self._cloud_sync_manager.dropzone_path = get_icloud_path()
                self._cloud_sync_manager.start()
            else:
                self._cloud_sync_manager.stop()
        if hasattr(self, "_nas_sync_manager"):
            if getattr(self, "_is_icloud_auto_mode", False):
                self._nas_sync_manager.stop()
            elif getattr(self, "_is_nas_auto_mode", False) and ensure_nas_mounted(get_nas_path()):
                self._nas_sync_manager.dropzone_path = get_local_path(get_nas_path())
                self._nas_sync_manager.configure(mode="nas", scan_interval=60, stable_seconds=300, exclude_callback=get_nas_excluded_folders)
                self._nas_sync_manager.start()
            else:
                self._nas_sync_manager.stop()

    def _defer_home_action(self, widget, action):
        # F fix v2: 모든 MenuButton hover 강제 리셋
        try:
            for child in self.home_page.findChildren(QWidget, "MenuButton"):
                if hasattr(child, "_normal_ss"):
                    child.setStyleSheet(child._normal_ss)
            widget.unsetCursor()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass
        QTimer.singleShot(100, action)

    def _icloud_btn(self, text, file_data, default_cmd, is_nas=False, subtitle="", comp_title=""):
        is_unified = bool(getattr(self, "_unified_dashboard", False))
        _normal_ss = "QWidget#MenuButton { background-color: #1B2429; border: 1px solid #2D3942; border-radius: 7px; }" if getattr(self, "_unified_dashboard", False) else "QWidget#MenuButton { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 12px; }"
        _hover_ss = "QWidget#MenuButton { background-color: #26313A; border: 1px solid #3F8CFF; border-radius: 7px; }" if getattr(self, "_unified_dashboard", False) else "QWidget#MenuButton { background-color: #FFFFFF; border: 2px solid #007AFF; border-radius: 12px; }"
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(_normal_ss)
        w._normal_ss = _normal_ss; w._hover_ss = _hover_ss
        w.enterEvent = lambda e, _w=w: _w.setStyleSheet(_w._hover_ss)
        w.leaveEvent = lambda e, _w=w: _w.setStyleSheet(_w._normal_ss)
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(10 if is_unified else 20, 7 if is_unified else 14, 10 if is_unified else 20, 7 if is_unified else 14)
        layout.setSpacing(4 if is_unified else 6)
        active = getattr(self, '_is_nas_auto_mode', False) if is_nas else getattr(self, '_is_icloud_auto_mode', False)
        text_color = "#FFFFFF" if is_unified else ("#1D1D1F" if active else "#6E6E73")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        header = QLabel()
        header.setText(text)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setStyleSheet(
            f"color: {text_color}; font-size: {11 if is_unified else 14}px; font-weight: 700; "
            "background: transparent; border: none; padding: 0;"
        )
        header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_row.addWidget(header, stretch=1)
        wd_lbl = QLabel("")
        wd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wd_lbl.setFixedSize(76 if is_unified else 92, 18 if is_unified else 22)
        wd_lbl.setStyleSheet(
            "color: #E6EDF3; font-size: 9px; font-weight: 800; "
            "background: #59636B; border: none; border-radius: 9px; padding: 0 6px;"
            if is_unified else
            "color: #FFFFFF; font-size: 10px; font-weight: 800; "
            "background: #8E8E93; border: none; border-radius: 11px; padding: 0 8px;"
        )
        wd_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        wd_lbl.setVisible(False)
        header_row.addWidget(wd_lbl)
        layout.addLayout(header_row)

        status_box = QWidget()
        status_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(15 if is_unified else 18, 0, 0, 0)
        status_layout.setSpacing(1 if is_unified else 2)

        def add_status_label(value, color, size=None):
            label = QLabel(value)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setStyleSheet(
                f"color: {color}; font-size: {size or (9 if is_unified else 11)}px; "
                "font-weight: bold; border: none; background: transparent;"
            )
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            status_layout.addWidget(label)
            return label

        if subtitle:
            add_status_label(subtitle, "#3F8CFF" if is_unified else "#007AFF")
        if comp_title:
            add_status_label(comp_title, "#34C759")
        if active:
            self._watchdog_labels.append((wd_lbl, is_nas))
        if status_layout.count() > 0:
            layout.addWidget(status_box)

        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._defer_home_action(w, default_cmd)
                e.accept()
        w.mousePressEvent = _on_w_click

        if is_unified:
            return w

        preview_container = QWidget(); preview_layout = QVBoxLayout(preview_container); preview_layout.setContentsMargins(0, 0, 0, 0); preview_layout.setSpacing(6)
        if not file_data:
            empty_lbl = QLabel("대기 중인 항목이 없습니다."); empty_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none;"); preview_layout.addWidget(empty_lbl)
        else:
            rows = file_data if is_nas else file_data[:5]
            for name, fpath in rows:
                display_name = f"📁 {name}" if is_nas else name
                file_lbl = QLabel(display_name); file_lbl.setToolTip(fpath)
                file_lbl.setStyleSheet("QLabel { color: #A9B0B7; font-size: 10px; border: none; padding: 2px 4px; background: transparent; } QLabel:hover { color: #FFFFFF; background: #26313A; border-radius: 5px; }" if getattr(self, "_unified_dashboard", False) else "QLabel { color: #6E6E73; font-size: 11px; border: none; padding: 2px 4px; background: transparent; } QLabel:hover { color: #007AFF; background: #F2F2F7; border-radius: 6px; }")
                def _on_preview_click(e, p=fpath, lbl=file_lbl):
                    if e.button() == Qt.MouseButton.LeftButton:
                        if p.endswith(".srt"):
                            self._defer_home_action(lbl, lambda: self._open_srt_in_editor(p))
                        elif os.path.isdir(p):
                            self._defer_home_action(lbl, lambda: self._open_recent(p))
                        else:
                            self._defer_home_action(lbl, lambda: self.backend.start_pipeline([p]))
                        e.accept()
                file_lbl.mousePressEvent = _on_preview_click
                preview_layout.addWidget(file_lbl)
        if is_nas:
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame); scroll.setMaximumHeight(130 if getattr(self, "_unified_dashboard", False) else 170)
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { background: #26313A; width: 6px; }" if getattr(self, "_unified_dashboard", False) else "QScrollArea { background: transparent; border: none; } QScrollBar:vertical { background: #E5E5EA; width: 8px; }")
            scroll.setWidget(preview_container); layout.addWidget(scroll); self._preview_containers.append(scroll)
            scroll.setVisible(not getattr(self, '_log_visible', False))
        else:
            layout.addWidget(preview_container); self._preview_containers.append(preview_container)
            preview_container.setVisible(not getattr(self, '_log_visible', False))
        return w

    def _btn(self, text, desc, cmd, active=False, icon_name=None):
        is_unified = getattr(self, "_unified_dashboard", False)
        if is_unified:
            bg = "#26313A" if active else "transparent"
            border = "#3F8CFF" if active else "transparent"
            _normal_ss = f"QWidget#MenuButton {{ background-color: {bg}; border: 1px solid {border}; border-radius: 7px; }}"
            _hover_ss = "QWidget#MenuButton { background-color: #26313A; border: 1px solid #3F8CFF; border-radius: 7px; }"
        else:
            _normal_ss = "QWidget#MenuButton { background-color: #FFFFFF; border: 1px solid #E5E5EA; border-radius: 12px; }"
            _hover_ss = "QWidget#MenuButton { background-color: #FFFFFF; border: 2px solid #007AFF; border-radius: 12px; }"
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(_normal_ss)
        w._normal_ss = _normal_ss; w._hover_ss = _hover_ss
        w.enterEvent = lambda e, _w=w: _w.setStyleSheet(_w._hover_ss)
        w.leaveEvent = lambda e, _w=w: _w.setStyleSheet(_w._normal_ss)
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_unified:
            w.setFixedHeight(44 if not desc else 58)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(9 if is_unified else 20, 7 if is_unified else 14, 9 if is_unified else 20, 7 if is_unified else 14)
        layout.setSpacing(2 if is_unified else 4)
        main_color = "#74A9FF" if active and is_unified else ("#FFFFFF" if is_unified else "#1D1D1F")
        icon_color = "#74A9FF" if active and is_unified else ("#E8EEF5" if is_unified else main_color)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8 if is_unified else 6)
        if icon_name:
            icon_lbl = QLabel()
            icon_size = 15 if is_unified else 14
            icon_lbl.setPixmap(line_icon(icon_name, icon_color, icon_size).pixmap(icon_size, icon_size))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_unified:
                icon_lbl.setFixedSize(24, 24)
                icon_lbl.setStyleSheet("background-color: #11181C; border: none; border-radius: 2px;")
            else:
                icon_lbl.setFixedSize(16, 16)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(icon_lbl)
        lbl = QLabel(text)
        lbl.setMinimumWidth(0)
        lbl.setStyleSheet(f"color: {main_color}; font-size: {12 if is_unified else 14}px; font-weight: bold; border: none; background: transparent;")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(lbl, stretch=1)
        layout.addLayout(row)
        if desc:
            sub = QLabel(desc)
            sub.setFixedHeight(14 if is_unified else 18)
            sub.setStyleSheet("color: #7EE787; font-size: 9px; font-weight: bold; border: none; background: transparent; margin-left: 32px;" if is_unified else "color: #6E6E73; font-size: 11px; border: none; background: transparent;")
            sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(sub)
        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._defer_home_action(w, cmd)
                e.accept()
        w.mousePressEvent = _on_w_click
        return w

    def _editor_shortcuts_row(self):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        actions = [
            ("AI", "ai", self._open_main_ai_settings),
            ("상세설정", "settings", self._open_main_adv_settings),
            ("화자", "speaker", self._open_main_speaker_settings),
            ("화각", "sliders", self._dummy_action),
            ("간격", "timeline", self._open_main_gap_settings),
            ("비디오", "video", self._toggle_main_video),
            ("자막출력", "export", self._open_main_export_dialog),
        ]
        for text, icon, cmd in actions:
            btn = QToolButton()
            btn.setText(text)
            btn.setIcon(self._nav_icon(icon, "#A9B0B7" if text != "AI" else "#34C759"))
            btn.setIconSize(QSize(20, 20))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumSize(42, 46)
            btn.setStyleSheet(tool_button_style("toolbar"))
            btn.clicked.connect(cmd)
            layout.addWidget(btn)
        return row

    def _utility_shortcuts_row(self):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        actions = [
            ("자동설정", "settings", self._show_path_settings),
            ("자동시작", "sliders", self._toggle_auto_start_enabled),
            ("캐쉬삭제", "trash", self._clear_cache),
            ("로그", "terminal", self._toggle_log),
            ("종료", "power", self._quick_exit),
        ]
        for text, icon, cmd in actions:
            btn = QToolButton()
            btn.setText(text)
            btn.setIcon(self._nav_icon(icon, "#FF3B30" if text == "종료" else "#A9B0B7"))
            btn.setIconSize(QSize(18, 18))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setMinimumSize(38, 42)
            btn.setStyleSheet(tool_button_style("danger" if text == "종료" else "toolbar"))
            btn.clicked.connect(cmd)
            layout.addWidget(btn)
        return row

    def _project_info_card(self, expanded=None, overlay=False):
        if expanded is None:
            expanded = bool(getattr(self, "_project_info_expanded", False))
        else:
            expanded = bool(expanded)
        if not expanded and not overlay:
            try:
                from ui.menu_bar import MENU_BUTTON_HEIGHT
            except Exception:
                MENU_BUTTON_HEIGHT = 44
            btn = QToolButton()
            btn.setText("프로젝트 정보")
            btn.setIcon(line_icon("project", "#E8EEF5", 15))
            btn.setIconSize(QSize(15, 15))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setFixedHeight(MENU_BUTTON_HEIGHT)
            btn.setStyleSheet(
                "QToolButton { "
                "background: #1B2429; color: #F5F7FA; "
                "border: 1px solid #2D3942; border-radius: 7px; "
                "padding: 0 10px; font-size: 12px; font-weight: 700; "
                "text-align: left; "
                "} "
                "QToolButton:hover { background: #202A31; border-color: #465663; }"
                "QToolButton::menu-indicator { image: none; }"
            )
            btn.clicked.connect(self._toggle_project_info_card)
            self._project_info_button_card = btn
            return btn

        card = QWidget()
        card.setStyleSheet(
            "background: #1B2429; border: 1px solid #3A4650; border-radius: 7px;"
            if overlay else
            "background: #1B2429; border: 1px solid #2D3942; border-radius: 7px;"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        header = QToolButton()
        header.setText("프로젝트 정보")
        header.setCheckable(True)
        header.setChecked(expanded)
        header.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setStyleSheet(
            "QToolButton { color: #F5F7FA; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none; padding: 2px 0; text-align: left; }"
            "QToolButton::right-arrow { width: 11px; height: 11px; }"
            "QToolButton::down-arrow { width: 11px; height: 11px; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        header.clicked.connect(self._toggle_project_info_card)
        lay.addWidget(header)
        if not expanded:
            card.setMaximumHeight(36)
            return card

        def add_section(name, rows):
            section = QLabel(name)
            section.setStyleSheet(label_style("accent", 10, bold=True))
            lay.addWidget(section)
            for text in rows:
                lbl = QLabel(str(text))
                lbl.setWordWrap(True)
                lbl.setStyleSheet(label_style("muted", 9))
                lay.addWidget(lbl)

        for section in self._project_info_sections():
            add_section(section["title"], section["rows"])
        return card

    def _project_info_sections(self) -> list[dict]:
        def add_section(name, rows):
            return {"title": str(name), "rows": [str(row) for row in rows]}

        editor = self._active_editor()
        project_name = os.path.basename(str(getattr(self, "_current_project_path", "") or "인터뷰_홍길동.assp"))
        project_path = str(getattr(self, "_current_project_path", "") or "/Volumes/NAS/Project")
        media_name = str(getattr(editor, "video_name", "") or "열린 영상 없음")
        video_player = getattr(editor, "video_player", None) if editor is not None else None
        duration = float(getattr(video_player, "total_time", 0.0) or 0.0)
        seg_count = 0
        speakers = set()
        if editor is not None and hasattr(editor, "_get_current_segments"):
            try:
                segs = editor._get_current_segments()
                seg_count = len([s for s in segs if not s.get("is_gap")])
                speakers = {str(s.get("spk") or s.get("speaker") or "00") for s in segs if not s.get("is_gap")}
            except Exception:
                seg_count = 0

        return [
            add_section("프로젝트", [project_name, project_path]),
            add_section("영상", [f"파일: {media_name}", f"길이: {duration:0.1f}s" if duration else "길이: -", "해상도/프레임: 로드 후 표시"]),
            add_section("자막", [f"세그먼트: {seg_count}", f"화자: {len(speakers) if speakers else 0}", "상태: 편집 대기"]),
        ]

    def _on_project_info_button_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_project_info_card()
            event.accept()

    def _show_project_info_overlay(self):
        if not getattr(self, "_unified_dashboard", False):
            return
        old_overlay = getattr(self, "_project_info_overlay", None)
        if old_overlay is not None:
            try:
                old_overlay.setParent(None)
                old_overlay.deleteLater()
            except RuntimeError:
                pass
            self._project_info_overlay = None
        overlay = self._create_project_info_quick_overlay()
        if overlay is None:
            overlay = self._project_info_card(expanded=True, overlay=True)
            overlay.setParent(self.home_page)
        overlay.setObjectName("ProjectInfoOverlay")
        x, y, w, h = self._project_info_overlay_geometry(overlay)
        overlay.setMinimumWidth(w)
        overlay.setMaximumWidth(w)
        overlay.setGeometry(x, y, w, h)
        overlay.raise_()
        overlay.show()
        self._project_info_overlay = overlay

    def _create_project_info_quick_overlay(self):
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return None
        try:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtQuickWidgets import QQuickWidget
        except Exception:
            return None
        qml_path = os.path.join(os.path.dirname(__file__), "qml", "project_info_overlay.qml")
        if not os.path.exists(qml_path):
            return None
        try:
            overlay = QQuickWidget(self.home_page)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            overlay.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            overlay.setAutoFillBackground(False)
            overlay.setClearColor(QColor(Qt.GlobalColor.transparent))
            overlay.setStyleSheet("background: transparent; border: none;")
            overlay.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            overlay.rootContext().setContextProperty("projectInfoSections", self._project_info_sections())
            overlay.setSource(QUrl.fromLocalFile(qml_path))
            if overlay.status() == QQuickWidget.Status.Error:
                overlay.deleteLater()
                return None
            return overlay
        except Exception:
            return None

    def _project_info_overlay_geometry(self, overlay):
        width = max(190, self.home_page.width() - 16)
        try:
            overlay.adjustSize()
        except Exception:
            pass
        hint_h = 260
        try:
            hint_h = max(220, int(overlay.sizeHint().height()))
        except Exception:
            pass
        height = min(max(260, hint_h), max(220, self.home_page.height() - 92))
        button = getattr(self, "_project_info_button_card", None)
        button_y = self.home_page.height() - 54
        if button is not None:
            try:
                button_y = button.y()
            except RuntimeError:
                button_y = self.home_page.height() - 54
        y = max(66, button_y - height - 8)
        return 8, y, width, height

    def _toggle_project_info_card(self):
        expanded = bool(getattr(self, "_project_info_expanded", False))
        self._project_info_expanded = not expanded
        if expanded:
            overlay = getattr(self, "_project_info_overlay", None)
            if overlay is not None:
                try:
                    overlay.setParent(None)
                    overlay.deleteLater()
                except RuntimeError:
                    pass
            self._project_info_overlay = None
            return
        self._show_project_info_overlay()

    def _nav_icon(self, name: str, color="#A9B0B7") -> QIcon:
        return line_icon(name, color)

    def _show_development_notice(self, title, phase):
        QMessageBox.information(
            self,
            title,
            f"{title}는 {phase}에서 제공될 예정입니다.\n현재 기능은 기존 자막 편집 흐름에 영향을 주지 않습니다."
        )

    def _sidebar_active_mode(self):
        current = None
        try:
            current = self.stack.currentWidget()
        except Exception:
            current = None
        roughcut = getattr(self, "_roughcut_widget", None)
        editor = self._active_editor()
        if roughcut is not None and current is roughcut:
            return ROUGHCUT_MODE
        if editor is not None and current is editor:
            return EDITOR_MODE
        return "home"

    def _refresh_work_mode_ui(self):
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()
        try:
            self._build_home_content()
        except Exception:
            pass

    def _open_editor_screen(self):
        editor = self._active_editor()
        if editor is None:
            self._current_work_mode = EDITOR_MODE
            if hasattr(self, "global_menu_bar"):
                self.global_menu_bar.refresh()
            self.select_files()
            return
        self._current_work_mode = EDITOR_MODE
        try:
            self.stack.setCurrentWidget(editor)
        except Exception:
            try:
                self.stack.setCurrentIndex(1)
            except Exception:
                pass
        if hasattr(self, "_attach_global_menu_to_editor"):
            self._attach_global_menu_to_editor(editor)
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._refresh_work_mode_ui()

    def _open_roughcut_helper(self):
        self._current_work_mode = ROUGHCUT_MODE
        if hasattr(self, "_dock_global_menu_to_workspace"):
            self._dock_global_menu_to_workspace()
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()
        page = getattr(self, "_roughcut_widget", None)
        if page is None:
            from ui.roughcut.roughcut_widget import RoughcutWidget

            page = RoughcutWidget(owner=self, parent=self)
            self._roughcut_widget = page
            self.stack.addWidget(page)
        if hasattr(self, "_set_roughcut_bottom_widget"):
            self._set_roughcut_bottom_widget(getattr(page, "bottom_panel", None))
        elif hasattr(self, "_show_bottom_roughcut_table"):
            self._show_bottom_roughcut_table()
        self.stack.setCurrentWidget(page)
        page.refresh_from_editor(analyze_if_missing=False)
        self._refresh_work_mode_ui()

    def _open_shortform_maker(self):
        self._current_work_mode = SHORTFORM_MODE
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()
        self._show_development_notice("숏폼 제작기", "PHASE3")

    def _dummy_action(self):
        self._show_development_notice("개발 중 기능", "후속 단계")

    def _active_editor(self):
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return None
        try:
            if editor.parent() is None:
                return None
        except Exception:
            pass
        return editor

    def _show_editor_required_message(self, action_name):
        QMessageBox.information(
            self,
            action_name,
            "현재 열린 에디터가 없습니다.\n파일이나 프로젝트를 먼저 열어주세요."
        )

    def _activate_editor_for_main_action(self):
        editor = self._active_editor()
        if editor is None:
            return None
        self._current_work_mode = EDITOR_MODE
        try:
            self.stack.setCurrentWidget(editor)
        except Exception:
            try:
                self.stack.setCurrentIndex(1)
            except Exception:
                pass
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._refresh_work_mode_ui()
        return editor

    def _open_main_ai_settings(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_settings"):
            editor._show_settings()
            return
        from ui.settings.settings_dialog import SettingsDialog
        settings = load_settings()
        dlg = SettingsDialog(settings, self)
        if dlg.exec():
            self._apply_ai_settings(dlg.result_settings)

    def _open_main_adv_settings(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_adv_settings"):
            editor._show_adv_settings()
            return
        from ui.settings.settings_dialog import AdvancedSettingsDialog
        settings = load_settings()
        dlg = AdvancedSettingsDialog(settings, self)
        if dlg.exec():
            settings.update(dlg.result)
            save_settings(settings)

    def _open_main_speaker_settings(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_speaker_settings"):
            editor._show_speaker_settings()
            return
        from ui.settings.settings_dialog import SpeakerDialog
        settings = load_settings()
        dlg = SpeakerDialog(settings, self)
        if dlg.exec():
            settings.update(dlg.result)
            save_settings(settings)

    def _open_main_gap_settings(self):
        editor = self._active_editor()
        if editor is not None and hasattr(editor, "_show_gap_settings"):
            editor._show_gap_settings()
            return
        from ui.settings.settings_dialog import GapSettingsDialog
        settings = load_settings()
        dlg = GapSettingsDialog(settings, self)
        if dlg.exec():
            settings.update(dlg.result)
            save_settings(settings)

    def _toggle_main_video(self):
        editor = self._activate_editor_for_main_action()
        if editor is None or not hasattr(editor, "_toggle_video"):
            self._show_editor_required_message("비디오")
            return
        editor._toggle_video()

    def _open_main_export_dialog(self):
        editor = self._activate_editor_for_main_action()
        if editor is None or not hasattr(editor, "_show_export_dialog"):
            self._show_editor_required_message("자막출력")
            return
        editor._show_export_dialog()

    def _show_path_settings(self):
        dlg = QDialog(self); dlg.setWindowTitle("자동설정"); dlg.setMinimumWidth(520); dlg.setStyleSheet(settings_dialog_stylesheet())
        settings = load_settings()
        layout = QVBoxLayout(dlg); layout.addWidget(QLabel("NAS 루트 경로:"))
        nas_input = QLineEdit(get_nas_path()); layout.addWidget(nas_input)
        layout.addWidget(QLabel("iCloud 동기화 경로:"))
        icloud_input = QLineEdit(get_icloud_path()); layout.addWidget(icloud_input)
        icl_chk = QCheckBox("자동감지 및 처리활성화 iCloud"); icl_chk.setChecked(get_icloud_auto_detect()); layout.addWidget(icl_chk)
        nas_chk = QCheckBox("자동감지 및 처리활성화 NAS"); nas_chk.setChecked(get_nas_auto_detect()); layout.addWidget(nas_chk)
        layout.addWidget(QLabel("자동 처리 모드:"))
        mode_combo = QComboBox(); mode_combo.addItem("빠른모드", "fast"); mode_combo.addItem("품질모드", "quality"); mode_combo.addItem("프리셋 모드", "preset")
        current_mode = settings.get("auto_start_mode", "quality")
        for i in range(mode_combo.count()):
            if mode_combo.itemData(i) == current_mode:
                mode_combo.setCurrentIndex(i); break
        layout.addWidget(mode_combo)
        shortcut_row = QHBoxLayout(); btn_ai = QPushButton("AI 설정"); btn_detail = QPushButton("상세설정")
        def open_ai_settings():
            from ui.settings.settings_dialog import SettingsDialog
            s = load_settings(); d = SettingsDialog(s, self)
            if d.exec(): self._apply_ai_settings(d.result_settings)
        def open_advanced_settings():
            from ui.settings.settings_dialog import AdvancedSettingsDialog
            s = load_settings(); d = AdvancedSettingsDialog(s, self)
            if d.exec(): save_settings(d.result)
        btn_ai.clicked.connect(open_ai_settings); btn_detail.clicked.connect(open_advanced_settings)
        shortcut_row.addWidget(btn_ai); shortcut_row.addWidget(btn_detail); layout.addLayout(shortcut_row)
        btn_layout = QHBoxLayout(); btn_save = QPushButton("저장"); btn_save.setStyleSheet(button_style("primary"))
        def save_all():
            set_nas_path(nas_input.text()); set_icloud_path(icloud_input.text())
            set_icloud_auto_detect(icl_chk.isChecked()); self._is_icloud_auto_mode = icl_chk.isChecked()
            set_nas_auto_detect(nas_chk.isChecked()); self._is_nas_auto_mode = nas_chk.isChecked()
            s = load_settings(); s["auto_start_mode"] = mode_combo.currentData() or "quality"; s.setdefault("auto_start_enabled", True); save_settings(s)
            self._start_configured_watchers()
            dlg.accept(); self._refresh_work_mode_ui()
        btn_save.clicked.connect(save_all); btn_layout.addStretch(); btn_layout.addWidget(btn_save); layout.addLayout(btn_layout); dlg.exec()
