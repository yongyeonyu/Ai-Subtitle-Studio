# Version: 03.01.35
# Phase: PHASE2
"""
ui/home_ui.py
MainWindow 홈 화면 빌드 Mixin
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QCheckBox, QScrollArea, QComboBox, QMessageBox,
    QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize, QDateTime
from PyQt6.QtGui import QIcon

import config
from core.path_manager import (
    get_icloud_path, get_recent_folders,
    get_icloud_auto_detect, get_nas_auto_detect,
    set_icloud_path, set_nas_path, get_nas_path, get_local_path,
    set_icloud_auto_detect, set_nas_auto_detect, ensure_nas_mounted,
    get_nas_excluded_folders
)
from core.settings import load_settings, save_settings
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE
from ui.style import button_style, label_style, line_icon, tool_button_style, settings_dialog_stylesheet


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
        for attr in ("status_rail", "saved_status_label", "sidebar_settings_label"):
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
                        self.sidebar_settings_label = QLabel("", self.home_page)
                        self.sidebar_settings_label.setWordWrap(True)
                        self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        old_layout = self.home_page.layout()
        if old_layout is not None: QWidget().setLayout(old_layout)
        is_unified = bool(getattr(self, "_unified_dashboard", False))
        layout = QVBoxLayout(self.home_page)
        layout.setContentsMargins(8 if is_unified else 30, 12 if is_unified else 20, 8 if is_unified else 30, 8 if is_unified else 15)
        layout.setSpacing(5)
        if not is_unified:
            layout.addSpacing(40)
        title = QLabel("AI Subtitle Studio")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft if is_unified else Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: #FFFFFF; font-size: {14 if is_unified else 24}px; font-weight: bold;")
        layout.addWidget(title)
        if is_unified:
            sub_title = QLabel("Dashboard")
            sub_title.setStyleSheet("color: #8E8E93; font-size: 10px; font-weight: bold; border: none; background: transparent;")
            layout.addWidget(sub_title)
            if hasattr(self, "status_rail"):
                layout.addWidget(self.status_rail)
        else:
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
            left_col.addWidget(self._btn("최근 작업", "", self._dummy_action, icon_name="clock"))
            icloud_files, count_str, comp_str = self._get_icloud_files()
            nas_folders, nas_count, nas_comp = self._get_nas_folders()
            left_col.addSpacing(6)
            left_col.addWidget(self._icloud_btn("☁ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
            left_col.addWidget(self._icloud_btn("▣ NAS 자동 처리", nas_folders, self._open_nas_root, is_nas=True, subtitle=nas_count, comp_title=nas_comp))
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
        valid_folders = [f for f in get_recent_folders() if f and f.strip()]
        
        # ✅ 중복 제거 (순서 유지)
        seen = set()
        unique_folders = []
        for f in valid_folders:
            norm = os.path.normpath(f)
            if norm not in seen:
                seen.add(norm)
                unique_folders.append(f)
        valid_folders = unique_folders[:10]

        if valid_folders and not is_unified:
            recent_container = QWidget(); recent_container.setObjectName("MenuButton")
            recent_container.setStyleSheet("QWidget#MenuButton { background-color: #1B2429; border: 1px solid #2D3942; border-radius: 7px; }")
            recent_layout = QVBoxLayout(recent_container); recent_layout.setContentsMargins(10, 8, 10, 8); recent_layout.setSpacing(3)
            recent_lbl = QLabel("📂 최근 폴더"); recent_lbl.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; border: none; background: transparent;"); recent_layout.addWidget(recent_lbl)
            self._recent_buttons = []
            max_visible = 3 if getattr(self, '_log_visible', False) else 10
            for i, folder in enumerate(valid_folders[:10]):
                display_name = os.path.basename(folder.rstrip('\\/')) or folder
                file_lbl = QLabel(f"📁 {display_name}"); file_lbl.setStyleSheet("QLabel { color: #D1D1D6; font-size: 10px; border: none; padding: 2px 4px; background: transparent; } QLabel:hover { color: #FFFFFF; background: #26313A; border-radius: 4px; }"); file_lbl.setCursor(Qt.CursorShape.PointingHandCursor); file_lbl.setToolTip(folder)
                def _on_recent_click(e, f=folder, lbl=file_lbl):
                    if e.button() == Qt.MouseButton.LeftButton:
                        self._defer_home_action(lbl, lambda: self._open_recent(f))
                        e.accept()
                file_lbl.mousePressEvent = _on_recent_click
                if i >= max_visible: file_lbl.setVisible(False)
                recent_layout.addWidget(file_lbl); self._recent_buttons.append(file_lbl)
            right_col.addWidget(recent_container)
        else: self._recent_buttons = []
        if not is_unified:
            right_col.addStretch()
        columns.addWidget(left_widget, stretch=1)
        if not is_unified:
            columns.addWidget(right_widget, stretch=1)
        layout.addLayout(columns)
        layout.addStretch()
        if is_unified:
            layout.addWidget(self._project_info_card(expanded=False))
            if bool(getattr(self, "_project_info_expanded", False)):
                QTimer.singleShot(0, self._show_project_info_overlay)
            layout.addWidget(self._sidebar_status_card())
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

    def _is_workspace_dirty(self) -> bool:
        editor = self._active_editor()
        if editor is None:
            return bool(getattr(self, "_is_dirty", False))
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
        idle_text = self._post_completion_idle_status_text()
        idle_html = (
            f" <span style='color:#7F8C96; font-size:10px;'>· {idle_text}</span>"
            if idle_text else ""
        )
        label.setText(
            f"<span style='color:{dot_color}; font-size:13px;'>●</span> "
            f"<span style='color:#D1D1D6;'>v{APP_VERSION}</span>"
            f"{idle_html}"
        )
        label.setToolTip(tooltip)

    def _post_completion_idle_status_text(self) -> str:
        remaining_getter = getattr(self, "_post_completion_idle_remaining_ms", None)
        if not callable(remaining_getter):
            return ""
        if self._is_subtitle_generation_running() and not bool(getattr(self, "_post_completion_idle_enabled", False)):
            return "홈 대기"
        if not bool(getattr(self, "_post_completion_idle_enabled", False)):
            return ""
        remaining = max(0, int(remaining_getter()))
        total_sec = (remaining + 999) // 1000
        minute, second = divmod(total_sec, 60)
        return f"홈 {minute:02d}:{second:02d}"

    def _format_engine_info_text(self, text: str) -> str:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        return "\n".join(lines)

    def _current_engine_info_text(self) -> str:
        editor = self._active_editor()
        if editor is not None:
            engine = getattr(editor, "engine_lbl", None)
            if engine is not None:
                try:
                    text = self._format_engine_info_text(engine.text())
                    if text:
                        return text
                except Exception:
                    pass
        settings = load_settings()
        vad_model = {
            "silero": "Silero",
            "webrtc": "WebRTC",
            "pyannote": "Pyannote",
            "none": "미사용",
        }.get(settings.get("selected_vad", "none"), "미사용")
        audio_ai = {
            "deepfilter": "DeepFilter",
            "demucs": "Demucs",
            "none": "미사용",
        }.get(settings.get("selected_audio_ai", "none"), "미사용")
        stt_model = str(settings.get("selected_whisper_model", getattr(config, "WHISPER_MODEL", "기본")) or "기본")
        stt_model = stt_model.replace("mlx-community/", "").replace("-mlx", "")
        llm_model = str(settings.get("selected_model", getattr(config, "OLLAMA_MODEL", "기본")) or "기본")
        return f"[VAD] : {vad_model}\n[음성] : {audio_ai}\n[STT] : {stt_model}\n[LLM] : {llm_model}"

    def _refresh_sidebar_engine_info(self, text=None):
        label = getattr(self, "sidebar_settings_label", None)
        if label is None:
            return
        formatted = self._format_engine_info_text(text) if text is not None else self._current_engine_info_text()
        label.setText(formatted)
        label.setToolTip(formatted)

    def _sidebar_status_card(self):
        card = QWidget()
        card.setStyleSheet("background: #1B2429; border: 1px solid #2D3942; border-radius: 7px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(4)

        if not hasattr(self, "saved_status_label"):
            self.saved_status_label = QLabel("", self.home_page)
            self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.saved_status_label.setStyleSheet("color: #A9B0B7; font-size: 10px; background: transparent; border: none;")
        self._refresh_saved_status_label()
        lay.addWidget(self.saved_status_label)

        if not hasattr(self, "sidebar_settings_label"):
            self.sidebar_settings_label = QLabel("", self.home_page)
        self.sidebar_settings_label.setWordWrap(True)
        self.sidebar_settings_label.setMinimumWidth(0)
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
        return "터미널 로그 숨기기" if getattr(self, "_log_visible", False) else "터미널 로그 보기"

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
                label.setText("Watchdog 대기중")
                label.setVisible(self._is_auto_start_enabled())
                continue
            interval = self._watchdog_interval_for(is_nas)
            key = "_nas_watchdog_left" if is_nas else "_icloud_watchdog_left"
            left = int(getattr(self, key, interval) or interval)
            left = interval if left <= 1 else left - 1
            setattr(self, key, left)
            label.setText(f"Watchdog {left:02d}s")
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
        header = QLabel()
        header.setText(text)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setStyleSheet(
            f"color: {text_color}; font-size: {11 if is_unified else 14}px; font-weight: 700; "
            "background: transparent; border: none; padding: 0;"
        )
        header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(header)

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
        if active and self._is_auto_start_enabled():
            wd_lbl = add_status_label("", config.ACCENT, 9 if is_unified else 11)
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
        card = QWidget()
        card.setStyleSheet(
            "background: #1B2429; border: 1px solid #3A4650; border-radius: 7px;"
            if overlay else
            "background: #1B2429; border: 1px solid #2D3942; border-radius: 7px;"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        expanded = bool(getattr(self, "_project_info_expanded", False)) if expanded is None else bool(expanded)
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
                lbl = QLabel(text)
                lbl.setWordWrap(True)
                lbl.setStyleSheet(label_style("muted", 9))
                lay.addWidget(lbl)

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

        add_section("프로젝트", [project_name, project_path])
        add_section("영상", [f"파일: {media_name}", f"길이: {duration:0.1f}s" if duration else "길이: -", "해상도/프레임: 로드 후 표시"])
        add_section("자막", [f"세그먼트: {seg_count}", f"화자: {len(speakers) if speakers else 0}", "상태: 편집 대기"])
        return card

    def _show_project_info_overlay(self):
        if not getattr(self, "_unified_dashboard", False):
            return
        overlay = self._project_info_card(expanded=True, overlay=True)
        overlay.setParent(self.home_page)
        overlay.setObjectName("ProjectInfoOverlay")
        overlay.setMinimumWidth(max(190, self.home_page.width() - 16))
        overlay.setMaximumWidth(max(190, self.home_page.width() - 16))
        overlay.adjustSize()
        h = min(max(260, overlay.sizeHint().height()), max(220, self.home_page.height() - 92))
        y = max(66, self.home_page.height() - h - 54)
        overlay.setGeometry(8, y, max(190, self.home_page.width() - 16), h)
        overlay.raise_()
        overlay.show()
        self._project_info_overlay = overlay

    def _toggle_project_info_card(self):
        self._project_info_expanded = not bool(getattr(self, "_project_info_expanded", False))
        self._build_home_content()

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
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        self._refresh_work_mode_ui()

    def _open_roughcut_helper(self):
        self._current_work_mode = ROUGHCUT_MODE
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
        if hasattr(self, "_apply_log_visible") and not getattr(self, "_log_visible", False):
            self._apply_log_visible(True)
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
            save_settings(dlg.result_settings)

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
            if d.exec(): save_settings(d.result_settings)
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
