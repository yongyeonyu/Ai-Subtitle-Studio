# Version: 03.14.27
# Phase: PHASE2
"""
ui/home_ui.py
MainWindow 홈 화면 빌드 Mixin
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox,
    QToolButton, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QColor

from core.runtime import config
from core.path_manager import (
    get_icloud_path,
    get_nas_path, get_local_path,
    ensure_nas_mounted,
    get_nas_excluded_folders
)
from core.settings import load_settings, save_settings
from core.work_mode import EDITOR_MODE, ROUGHCUT_MODE, SHORTFORM_MODE
from ui.home_sidebar import HomeSidebarMixin
from ui.sidebar.home_sidebar_nav_widget import HomeSidebarNavWidget
from ui.style import button_style, label_style, line_icon, tool_button_style


class HomeUIMixin(HomeSidebarMixin):
    def _home_auto_source_payload(self, scope: str):
        cache = dict(getattr(self, "_home_auto_source_cache", {}) or {})
        cached = cache.get(str(scope or ""))
        if cached is not None:
            return cached
        if bool(getattr(self, "_initial_home_scan_deferred", False)):
            return [], "불러오는 중", ""
        getter = self._get_nas_folders if str(scope or "") == "nas" else self._get_icloud_files
        result = getter()
        cache[str(scope or "")] = result
        self._home_auto_source_cache = cache
        return result

    def _build_home_content(self):
        self._preview_containers = []
        self._watchdog_labels = []
        self._subtitle_quality_combos = []
        refresh_sources = getattr(self, "_start_initial_home_auto_source_refresh", None)
        if callable(refresh_sources) and bool(getattr(self, "_initial_home_scan_deferred", False)):
            refresh_sources(delay_ms=0)
        overlay = getattr(self, "_project_info_overlay", None)
        if overlay is not None:
            try:
                overlay.setParent(None)
                overlay.deleteLater()
            except RuntimeError:
                pass
            self._project_info_overlay = None
        for attr in (
            "status_rail",
            "saved_status_label",
            "sidebar_nav_menu",
            "sidebar_settings_label",
            "sidebar_runtime_label",
            "sidebar_terminal_panel",
            "sidebar_preset_panel",
            "sidebar_subtitle_quality_combo",
            "sidebar_subtitle_quality_save_btn",
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                try:
                    widget.setParent(None)
                except RuntimeError:
                    if attr == "status_rail" and not bool(getattr(self, "_unified_dashboard", False)):
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
                        elif attr == "sidebar_runtime_label":
                            self.sidebar_runtime_label = QLabel("", self.home_page)
                            self.sidebar_runtime_label.setWordWrap(True)
                            self.sidebar_runtime_label.setTextFormat(Qt.TextFormat.RichText)
                            self.sidebar_runtime_label.setStyleSheet("color: #A9B0B7; font-size: 8px; font-weight: bold; background: transparent; border: none;")
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
        icloud_files, count_str, comp_str = self._home_auto_source_payload("icloud")
        nas_folders, nas_count, nas_comp = self._home_auto_source_payload("nas")
        if is_unified:
            if not hasattr(self, "saved_status_label"):
                self.saved_status_label = QLabel("", self.home_page)
                self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
            self.saved_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.saved_status_label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold; background: transparent; border: none;")
            self._refresh_saved_status_label()
            layout.addWidget(self.saved_status_label)
            rail = getattr(self, "status_rail", None)
            if rail is not None:
                try:
                    rail.hide()
                    rail.setParent(None)
                except RuntimeError:
                    pass
            self.status_rail = None
            if hasattr(self, "global_menu_bar"):
                try:
                    self.global_menu_bar.set_status_rail(None)
                except Exception:
                    pass
        else:
            if getattr(self, "status_rail", None) is None:
                from ui.menu_bar import StatusRail

                self.status_rail = StatusRail(self.home_page)
                if hasattr(self, "global_menu_bar"):
                    try:
                        self.global_menu_bar.set_status_rail(self.status_rail)
                    except Exception:
                        pass
            title = QLabel("AI Subtitle Studio")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
            layout.addWidget(title)
            layout.addSpacing(6)
        columns = QVBoxLayout() if is_unified else QHBoxLayout()
        columns.setSpacing(8)
        left_widget = QWidget(); left_col = QVBoxLayout(left_widget); left_col.setContentsMargins(0, 0, 0, 0); left_col.setSpacing(2 if is_unified else 4)
        if is_unified:
            left_col.addWidget(self._ensure_sidebar_nav_menu())
            left_col.addSpacing(2)
            left_col.addWidget(self._icloud_btn("☁ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
            left_col.addWidget(self._icloud_btn("▣ NAS 자동 처리", nas_folders, self._open_nas_root, is_nas=True, subtitle=nas_count, comp_title=nas_comp))
            left_col.addWidget(self._ensure_sidebar_queue_panel(), stretch=7)
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
        if not is_unified:
            right_col.addWidget(self._icloud_btn("☁️ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
        if not is_unified:
            right_col.addWidget(self._icloud_btn("🗄️ NAS 자동 처리", nas_folders, self._open_nas_root, is_nas=True, subtitle=nas_count, comp_title=nas_comp))
        if not is_unified:
            right_col.addStretch()
        columns.addWidget(left_widget, stretch=1)
        if not is_unified:
            columns.addWidget(right_widget, stretch=1)
        if is_unified:
            layout.addLayout(columns, stretch=1)
        else:
            layout.addLayout(columns)
            layout.addStretch()
        if is_unified:
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
        from core.runtime.config import APP_VERSION
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
            btn_auto_start = QPushButton(self._auto_start_label()); btn_auto_start.setStyleSheet(self._auto_start_style()); btn_auto_start.clicked.connect(self._toggle_auto_start_enabled)
            btn_clear_cache = QPushButton("🗑️ 캐쉬삭제"); btn_clear_cache.setStyleSheet(button_style("toolbar")); btn_clear_cache.clicked.connect(self._clear_cache)
            btn_exit = QPushButton("❌ 종료"); btn_exit.setStyleSheet(button_style("danger")); btn_exit.clicked.connect(self._quick_exit)
            bottom_bar.addWidget(btn_auto_start); bottom_bar.addWidget(btn_clear_cache); bottom_bar.addWidget(btn_exit)
        if not is_unified:
            layout.addLayout(bottom_bar)
        self._ensure_watchdog_timer()


    def _sidebar_status_card(self):
        card = QWidget()
        card.setMinimumHeight(144)
        card.setStyleSheet("background: #1B2429; border: 1px solid #2D3942; border-radius: 7px;")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 6, 10, 5)
        lay.setSpacing(3)

        if not hasattr(self, "saved_status_label"):
            self.saved_status_label = QLabel("", self.home_page)
            self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        if not hasattr(self, "sidebar_settings_label"):
            self.sidebar_settings_label = QLabel("", self.home_page)
        if not hasattr(self, "sidebar_runtime_label"):
            self.sidebar_runtime_label = QLabel("", self.home_page)
        self.sidebar_settings_label.setWordWrap(True)
        self.sidebar_settings_label.setMinimumWidth(0)
        self.sidebar_settings_label.setMinimumHeight(100)
        self.sidebar_settings_label.setTextFormat(Qt.TextFormat.RichText)
        self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        self.sidebar_runtime_label.setWordWrap(True)
        self.sidebar_runtime_label.setMinimumWidth(0)
        self.sidebar_runtime_label.setMinimumHeight(30)
        self.sidebar_runtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.sidebar_runtime_label.setStyleSheet("color: #A9B0B7; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        self._refresh_sidebar_engine_info()
        if hasattr(self, "_refresh_sidebar_runtime_monitor"):
            self._refresh_sidebar_runtime_monitor()
        lay.addWidget(self._create_sidebar_subtitle_quality_row(card))
        lay.addWidget(self.sidebar_settings_label)
        lay.addWidget(self.sidebar_runtime_label)
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

    def _sidebar_nav_items(self) -> list[dict]:
        sidebar_mode = self._sidebar_active_mode()
        return [
            self._sidebar_generation_nav_item(),
            {
                "id": "home",
                "title": "홈",
                "badge": "HM",
                "accent": "#74A9FF",
                "active": sidebar_mode == "home",
                "enabled": True,
            },
            {
                "id": "editor",
                "title": "에디터",
                "badge": "ED",
                "accent": "#34C759",
                "active": sidebar_mode == "editor",
                "enabled": True,
            },
            {
                "id": "roughcut",
                "title": "러프컷",
                "badge": "RC",
                "accent": "#FF9500",
                "active": sidebar_mode == "roughcut",
                "enabled": True,
            },
            {
                "id": "shortform",
                "title": "숏폼",
                "badge": "SF",
                "accent": "#A678F4",
                "active": False,
                "enabled": True,
            },
        ]

    def _ensure_sidebar_nav_menu(self):
        panel = getattr(self, "sidebar_nav_menu", None)
        if not isinstance(panel, HomeSidebarNavWidget):
            panel = HomeSidebarNavWidget(self.home_page)
            panel.actionTriggered.connect(self._handle_sidebar_nav_action)
            self.sidebar_nav_menu = panel
        panel.set_items(self._sidebar_nav_items())
        return panel

    def _refresh_sidebar_nav_menu(self):
        panel = getattr(self, "sidebar_nav_menu", None)
        if not isinstance(panel, HomeSidebarNavWidget):
            return
        try:
            panel.set_items(self._sidebar_nav_items())
        except RuntimeError:
            self.sidebar_nav_menu = None

    def _handle_sidebar_nav_action(self, action_id: str):
        actions = {
            "generation_status": self._open_editor_screen,
            "home": self.show_home,
            "editor": self._open_editor_screen,
            "roughcut": self._open_roughcut_helper,
            "shortform": self._open_shortform_maker,
        }
        action = actions.get(str(action_id or ""))
        if action is None:
            return
        self._defer_home_action(getattr(self, "sidebar_nav_menu", self.home_page), action)

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
        layout.setContentsMargins(6 if is_unified else 20, 4 if is_unified else 14, 10 if is_unified else 20, 4 if is_unified else 14)
        layout.setSpacing(2 if is_unified else 6)
        active = getattr(self, '_is_nas_auto_mode', False) if is_nas else getattr(self, '_is_icloud_auto_mode', False)
        text_color = "#FFFFFF" if is_unified else ("#1D1D1F" if active else "#6E6E73")
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(4 if is_unified else 6)
        header = QLabel()
        header.setText(text)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header.setStyleSheet(
            f"color: {text_color}; font-size: {10 if is_unified else 14}px; font-weight: 700; "
            "background: transparent; border: none; padding: 0;"
        )
        header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_row.addWidget(header, stretch=1)
        wd_lbl = QLabel("")
        wd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wd_lbl.setFixedSize(58 if is_unified else 92, 16 if is_unified else 22)
        wd_lbl.setStyleSheet(
            "color: #E6EDF3; font-size: 8px; font-weight: 800; "
            "background: #59636B; border: none; border-radius: 8px; padding: 0 4px;"
            if is_unified else
            "color: #FFFFFF; font-size: 10px; font-weight: 800; "
            "background: #8E8E93; border: none; border-radius: 11px; padding: 0 8px;"
        )
        wd_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        wd_lbl.setVisible(False)
        if hasattr(self, "_make_subtitle_quality_combo"):
            quality_combo = self._make_subtitle_quality_combo(
                w,
                width=68 if is_unified else 94,
                height=20 if is_unified else 24,
                scope="nas" if is_nas else "icloud",
            )
            quality_combo.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
            quality_combo.setToolTip("Mode")
            header_row.addWidget(quality_combo)
        header_row.addWidget(wd_lbl)
        layout.addLayout(header_row)

        status_box = QWidget()
        status_box.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        status_layout = QVBoxLayout(status_box)
        status_layout.setContentsMargins(8 if is_unified else 18, 0, 0, 0)
        status_layout.setSpacing(0 if is_unified else 2)

        def add_status_label(value, color, size=None):
            label = QLabel(value)
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setStyleSheet(
                f"color: {color}; font-size: {size or (8 if is_unified else 11)}px; "
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
            w.setFixedHeight(30 if not desc else 40)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(7 if is_unified else 20, 3 if is_unified else 14, 7 if is_unified else 20, 3 if is_unified else 14)
        layout.setSpacing(0 if is_unified else 4)
        main_color = "#74A9FF" if active and is_unified else ("#FFFFFF" if is_unified else "#1D1D1F")
        icon_color = "#74A9FF" if active and is_unified else ("#E8EEF5" if is_unified else main_color)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6 if is_unified else 6)
        if icon_name:
            icon_lbl = QLabel()
            icon_size = 12 if is_unified else 14
            icon_lbl.setPixmap(line_icon(icon_name, icon_color, icon_size).pixmap(icon_size, icon_size))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_unified:
                icon_lbl.setFixedSize(17, 15)
                icon_lbl.setStyleSheet("background-color: #11181C; border: none; border-radius: 2px;")
            else:
                icon_lbl.setFixedSize(16, 16)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(icon_lbl)
        lbl = QLabel(text)
        lbl.setMinimumWidth(0)
        lbl.setStyleSheet(f"color: {main_color}; font-size: {10 if is_unified else 14}px; font-weight: bold; border: none; background: transparent;")
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
            *([("개인화", "ai", self._open_main_personalization_learning)] if config.IS_MAC else []),
            ("화자", "speaker", self._open_main_speaker_settings),
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
            ("자동시작", "sliders", self._toggle_auto_start_enabled),
            ("캐쉬삭제", "trash", self._clear_cache),
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
                profile = self._current_responsive_profile() if hasattr(self, "_current_responsive_profile") else None
                MENU_BUTTON_HEIGHT = int(getattr(profile, "menu_button_height", 0) or 0)
            except Exception:
                MENU_BUTTON_HEIGHT = 0
            if MENU_BUTTON_HEIGHT <= 0:
                try:
                    from ui.menu_bar import MENU_BUTTON_HEIGHT as DEFAULT_MENU_BUTTON_HEIGHT
                    MENU_BUTTON_HEIGHT = DEFAULT_MENU_BUTTON_HEIGHT
                except Exception:
                    MENU_BUTTON_HEIGHT = 38
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
        if hasattr(self, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(0, self._release_ai_models_for_editor_mode)
        activate_editor_idle = getattr(self, "_activate_editor_idle_mode", None)
        if callable(activate_editor_idle):
            activate_editor_idle(reason="editor_screen")
        self._refresh_work_mode_ui()

    def _open_roughcut_helper(self):
        self._current_work_mode = ROUGHCUT_MODE
        stop_idle = getattr(self, "_stop_post_completion_idle_timer", None)
        if callable(stop_idle):
            stop_idle()
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
        if hasattr(self, "_release_ai_models_for_editor_mode"):
            QTimer.singleShot(0, self._release_ai_models_for_editor_mode)
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
        self._open_main_ai_settings()

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

    def _open_main_personalization_learning(self):
        from ui.settings.settings_personalization import PersonalizationLearningDialog

        dlg = PersonalizationLearningDialog(self)
        dlg.exec()

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
