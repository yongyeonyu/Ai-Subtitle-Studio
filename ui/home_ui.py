# Version: 02.03.04
# Phase: PHASE1-B
"""
ui/home_ui.py
MainWindow 홈 화면 빌드 Mixin
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QCheckBox, QScrollArea, QComboBox, QMessageBox,
    QGridLayout
)
from PyQt6.QtCore import Qt, QTimer

import config
from core.path_manager import (
    get_icloud_path, get_recent_folders,
    get_icloud_auto_detect, get_nas_auto_detect,
    set_icloud_path, set_nas_path, get_nas_path, get_local_path,
    set_icloud_auto_detect, set_nas_auto_detect, ensure_nas_mounted,
    get_nas_excluded_folders
)
from core.settings import load_settings, save_settings


class HomeUIMixin:

    def _build_home_content(self):
        self._preview_containers = []
        self._watchdog_labels = []
        old_layout = self.home_page.layout()
        if old_layout is not None: QWidget().setLayout(old_layout)
        layout = QVBoxLayout(self.home_page); layout.setContentsMargins(30, 20, 30, 15); layout.setSpacing(8); layout.addSpacing(40)
        title = QLabel("🎬 AI Subtitle Studio"); title.setAlignment(Qt.AlignmentFlag.AlignCenter); title.setStyleSheet(f"color: {config.FG}; font-size: 24px; font-weight: bold;"); layout.addWidget(title); layout.addSpacing(6)
        columns = QHBoxLayout(); columns.setSpacing(8)
        left_widget = QWidget(); left_col = QVBoxLayout(left_widget); left_col.setContentsMargins(0, 0, 0, 0); left_col.setSpacing(8)
        left_col.addWidget(self._btn("📂 파일 선택", "영상/음성/srt 직접 선택", self.select_files))
        left_col.addWidget(self._btn("📁 폴더 선택", "폴더에서 영상 일괄 선택", self.select_folder))
        left_col.addWidget(self._btn("📝 프로젝트 만들기", "영상 묶어서 프로젝트 관리", self._create_project))
        left_col.addWidget(self._btn("📦 프로젝트 열기", "기존 프로젝트 불러오기", self._open_project))
        left_col.addWidget(self._editor_shortcuts_panel())
        left_col.addWidget(self._btn("✂️ cut 편집 도우미", "개발 중", self._dummy_action))
        left_col.addStretch()
        right_widget = QWidget(); right_col = QVBoxLayout(right_widget); right_col.setContentsMargins(0, 0, 0, 0); right_col.setSpacing(8)
        icloud_files, count_str, comp_str = self._get_icloud_files()
        right_col.addWidget(self._icloud_btn("☁️ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
        nas_folders, nas_count, nas_comp = self._get_nas_folders()
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

        if valid_folders:
            recent_container = QWidget(); recent_container.setObjectName("MenuButton")
            recent_container.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}")
            recent_layout = QVBoxLayout(recent_container); recent_layout.setContentsMargins(20, 10, 20, 10); recent_layout.setSpacing(4)
            recent_lbl = QLabel("📂 최근 폴더"); recent_lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); recent_layout.addWidget(recent_lbl)
            self._recent_buttons = []
            max_visible = 3 if getattr(self, '_log_visible', False) else 10
            for i, folder in enumerate(valid_folders[:10]):
                display_name = os.path.basename(folder.rstrip('\\/')) or folder
                file_lbl = QLabel(f"📁 {display_name}"); file_lbl.setStyleSheet(f"QLabel {{ color: {config.FG2}; font-size: 11px; border: none; padding: 2px 4px; background: transparent; }} QLabel:hover {{ color: #4AFF80; background: #3d3d3d; border-radius: 4px; }}"); file_lbl.setCursor(Qt.CursorShape.PointingHandCursor); file_lbl.setToolTip(folder)
                def _on_recent_click(e, f=folder, lbl=file_lbl):
                    if e.button() == Qt.MouseButton.LeftButton:
                        self._defer_home_action(lbl, lambda: self._open_recent(f))
                        e.accept()
                file_lbl.mousePressEvent = _on_recent_click
                if i >= max_visible: file_lbl.setVisible(False)
                recent_layout.addWidget(file_lbl); self._recent_buttons.append(file_lbl)
            right_col.addWidget(recent_container)
        else: self._recent_buttons = []
        right_col.addStretch(); columns.addWidget(left_widget, stretch=1); columns.addWidget(right_widget, stretch=1); layout.addLayout(columns); layout.addStretch()
        bottom_bar = QHBoxLayout()
        from config import APP_VERSION
        version_lbl = QLabel(f"v{APP_VERSION}")
        version_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px;")
        btn_settings = QPushButton("⚙️ 자동설정"); btn_settings.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_settings.clicked.connect(self._show_path_settings)
        btn_auto_start = QPushButton(self._auto_start_label()); btn_auto_start.setStyleSheet(self._auto_start_style()); btn_auto_start.clicked.connect(self._toggle_auto_start_enabled)
        btn_clear_cache = QPushButton("🗑️ 캐쉬삭제"); btn_clear_cache.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_clear_cache.clicked.connect(self._clear_cache)
        btn_exit = QPushButton("❌ 종료"); btn_exit.setStyleSheet(f"background: #882222; color: #FFF; font-weight: bold; border: none; padding: 6px 12px; border-radius: 4px;"); btn_exit.clicked.connect(self._quick_exit)
        bottom_bar.addWidget(version_lbl); bottom_bar.addStretch(); bottom_bar.addWidget(btn_settings); bottom_bar.addWidget(btn_auto_start); bottom_bar.addWidget(btn_clear_cache); bottom_bar.addWidget(btn_exit)
        layout.addLayout(bottom_bar)
        self._ensure_watchdog_timer()


    def _is_auto_start_enabled(self):
        return bool(load_settings().get("auto_start_enabled", True))

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
        self.show_home()

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
        _normal_ss = f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }}"
        _hover_ss = f"QWidget#MenuButton {{ background-color: #333333; border: 2px solid #4AFF80; border-radius: 8px; }}"
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(_normal_ss)
        w._normal_ss = _normal_ss; w._hover_ss = _hover_ss
        w.enterEvent = lambda e, _w=w: _w.setStyleSheet(_w._hover_ss)
        w.leaveEvent = lambda e, _w=w: _w.setStyleSheet(_w._normal_ss)
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(6)
        active = getattr(self, '_is_nas_auto_mode', False) if is_nas else getattr(self, '_is_icloud_auto_mode', False)
        text_color = config.FG if active else config.FG2
        title_row = QHBoxLayout(); lbl = QLabel(text); lbl.setStyleSheet(f"color: {text_color}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); title_row.addWidget(lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle); sub_lbl.setStyleSheet(f"color: {config.ACCENT}; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 10px;"); title_row.addWidget(sub_lbl)
        if comp_title:
            comp_lbl = QLabel(comp_title); comp_lbl.setStyleSheet("color: #4AFF80; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 15px;"); title_row.addWidget(comp_lbl)
        if active and self._is_auto_start_enabled():
            wd_lbl = QLabel()
            wd_lbl.setStyleSheet("color: #4AFF80; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 12px;")
            title_row.addWidget(wd_lbl)
            self._watchdog_labels.append((wd_lbl, is_nas))
        title_row.addStretch(); layout.addLayout(title_row)
        preview_container = QWidget(); preview_layout = QVBoxLayout(preview_container); preview_layout.setContentsMargins(0, 0, 0, 0); preview_layout.setSpacing(6)
        if not file_data:
            empty_lbl = QLabel("대기 중인 항목이 없습니다."); empty_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none;"); preview_layout.addWidget(empty_lbl)
        else:
            rows = file_data if is_nas else file_data[:5]
            for name, fpath in rows:
                display_name = f"📁 {name}" if is_nas else name
                file_lbl = QLabel(display_name); file_lbl.setToolTip(fpath)
                file_lbl.setStyleSheet(f"QLabel {{ color: {config.FG2}; font-size: 11px; border: none; padding: 2px 4px; background: transparent; }} QLabel:hover {{ color: #4AFF80; background: #3d3d3d; border-radius: 4px; }}")
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
            scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.Shape.NoFrame); scroll.setMaximumHeight(170)
            scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} QScrollBar:vertical {{ background: {config.BG3}; width: 8px; }}")
            scroll.setWidget(preview_container); layout.addWidget(scroll); self._preview_containers.append(scroll)
            scroll.setVisible(not getattr(self, '_log_visible', False))
        else:
            layout.addWidget(preview_container); self._preview_containers.append(preview_container)
            preview_container.setVisible(not getattr(self, '_log_visible', False))
        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._defer_home_action(w, default_cmd)
                e.accept()
        w.mousePressEvent = _on_w_click
        return w

    def _btn(self, text, desc, cmd):
        _normal_ss = f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }}"
        _hover_ss = f"QWidget#MenuButton {{ background-color: #333333; border: 2px solid #4AFF80; border-radius: 8px; }}"
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(_normal_ss)
        w._normal_ss = _normal_ss; w._hover_ss = _hover_ss
        w.enterEvent = lambda e, _w=w: _w.setStyleSheet(_w._hover_ss)
        w.leaveEvent = lambda e, _w=w: _w.setStyleSheet(_w._normal_ss)
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(4)
        lbl = QLabel(text); lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(lbl)
        if desc: sub = QLabel(desc); sub.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none; background: transparent;"); sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(sub)
        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._defer_home_action(w, cmd)
                e.accept()
        w.mousePressEvent = _on_w_click
        return w

    def _editor_shortcuts_panel(self):
        panel = QWidget()
        panel.setStyleSheet(f"background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px;")
        layout = QGridLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(6)
        actions = [
            ("⚙️ AI", self._open_main_ai_settings),
            ("🛠️ 상세설정", self._open_main_adv_settings),
            ("🗣️ 화자", self._open_main_speaker_settings),
            ("⏱️ 간격", self._open_main_gap_settings),
            ("🎬 비디오", self._toggle_main_video),
            ("🎥 자막출력", self._open_main_export_dialog),
        ]
        for idx, (text, cmd) in enumerate(actions):
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(30)
            btn.setStyleSheet(
                f"QPushButton {{ background: {config.BG3}; color: {config.FG}; "
                "border: none; padding: 5px 8px; border-radius: 4px; font-weight: bold; } "
                "QPushButton:hover { background: #3d3d3d; color: #4AFF80; }"
            )
            btn.clicked.connect(cmd)
            layout.addWidget(btn, idx // 2, idx % 2)
        return panel

    def _dummy_action(self): pass

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
        try:
            self.stack.setCurrentWidget(editor)
        except Exception:
            try:
                self.stack.setCurrentIndex(1)
            except Exception:
                pass
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
        dlg = QDialog(self); dlg.setWindowTitle("자동설정"); dlg.setMinimumWidth(520); dlg.setStyleSheet(f"""
            QDialog {{ background-color: {config.BG}; color: {config.FG}; }}
            QLabel {{ color: {config.FG}; }}
            QCheckBox {{ color: {config.FG}; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid #FFFFFF; border-radius: 3px; background-color: transparent; }}
            QCheckBox::indicator:checked {{ background-color: #4AFF80; border: 2px solid #4AFF80; }}
            QComboBox {{ background: {config.BG2}; color: {config.FG}; border: 1px solid {config.BG3}; padding: 4px; }}
        """)
        settings = load_settings()
        layout = QVBoxLayout(dlg); layout.addWidget(QLabel("NAS 루트 경로:"))
        nas_input = QLineEdit(get_nas_path()); nas_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;"); layout.addWidget(nas_input)
        layout.addWidget(QLabel("iCloud 동기화 경로:"))
        icloud_input = QLineEdit(get_icloud_path()); icloud_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;"); layout.addWidget(icloud_input)
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
        btn_ai.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; padding: 6px; border-radius: 4px;")
        btn_detail.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; padding: 6px; border-radius: 4px;")
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
        btn_layout = QHBoxLayout(); btn_save = QPushButton("저장"); btn_save.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px;")
        def save_all():
            set_nas_path(nas_input.text()); set_icloud_path(icloud_input.text())
            set_icloud_auto_detect(icl_chk.isChecked()); self._is_icloud_auto_mode = icl_chk.isChecked()
            set_nas_auto_detect(nas_chk.isChecked()); self._is_nas_auto_mode = nas_chk.isChecked()
            s = load_settings(); s["auto_start_mode"] = mode_combo.currentData() or "quality"; s.setdefault("auto_start_enabled", True); save_settings(s)
            self._start_configured_watchers()
            dlg.accept(); self.show_home()
        btn_save.clicked.connect(save_all); btn_layout.addStretch(); btn_layout.addWidget(btn_save); layout.addLayout(btn_layout); dlg.exec()
