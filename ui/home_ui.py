# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/home_ui.py
MainWindow 홈 화면 빌드 Mixin
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialog, QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt

import config
from core.path_manager import (
    get_icloud_path, get_recent_folders,
    get_icloud_auto_detect, get_nas_auto_detect,
    set_icloud_path, set_nas_path, get_nas_path,
    set_icloud_auto_detect, set_nas_auto_detect
)


class HomeUIMixin:

    def _build_home_content(self):
        self._preview_containers = []
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
        left_col.addWidget(self._btn("✂️ cut 편집 도우미", "개발 중", self._dummy_action))
        left_col.addStretch()
        right_widget = QWidget(); right_col = QVBoxLayout(right_widget); right_col.setContentsMargins(0, 0, 0, 0); right_col.setSpacing(8)
        icloud_files, count_str, comp_str = self._get_icloud_files()
        right_col.addWidget(self._icloud_btn("☁️ iCloud 자동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
        nas_folders = self._get_nas_folders()
        right_col.addWidget(self._icloud_btn("🗄️ NAS 자동처리", nas_folders, self._open_nas_root, is_nas=True))
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
                file_lbl.mousePressEvent = (lambda e, f=folder: self._open_recent(f) if e.button() == Qt.MouseButton.LeftButton else None)
                if i >= max_visible: file_lbl.setVisible(False)
                recent_layout.addWidget(file_lbl); self._recent_buttons.append(file_lbl)
            right_col.addWidget(recent_container)
        else: self._recent_buttons = []
        right_col.addStretch(); columns.addWidget(left_widget, stretch=1); columns.addWidget(right_widget, stretch=1); layout.addLayout(columns); layout.addStretch()
        bottom_bar = QHBoxLayout()
        from config import APP_VERSION
        version_lbl = QLabel(f"v{APP_VERSION}")
        version_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px;")
        btn_settings = QPushButton("⚙️ 경로설정"); btn_settings.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_settings.clicked.connect(self._show_path_settings)
        btn_clear_cache = QPushButton("🗑️ 캐쉬삭제"); btn_clear_cache.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_clear_cache.clicked.connect(self._clear_cache)
        btn_exit = QPushButton("❌ 종료"); btn_exit.setStyleSheet(f"background: #882222; color: #FFF; font-weight: bold; border: none; padding: 6px 12px; border-radius: 4px;"); btn_exit.clicked.connect(self._quick_exit)
        bottom_bar.addWidget(version_lbl); bottom_bar.addStretch(); bottom_bar.addWidget(btn_settings); bottom_bar.addWidget(btn_clear_cache); bottom_bar.addWidget(btn_exit)
        layout.addLayout(bottom_bar)

    def _icloud_btn(self, text, file_data, default_cmd, is_nas=False, subtitle="", comp_title=""):
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}"); w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(6)
        active = getattr(self, '_is_nas_auto_mode', False) if is_nas else getattr(self, '_is_icloud_auto_mode', False)
        text_color = config.FG if active else config.FG2
        title_row = QHBoxLayout(); lbl = QLabel(text); lbl.setStyleSheet(f"color: {text_color}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); title_row.addWidget(lbl)
        if subtitle: sub_lbl = QLabel(subtitle); sub_lbl.setStyleSheet(f"color: {config.ACCENT}; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 10px;"); title_row.addWidget(sub_lbl)
        if comp_title: comp_lbl = QLabel(comp_title); comp_lbl.setStyleSheet(f"color: #4AFF80; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 15px;"); title_row.addWidget(comp_lbl)
        title_row.addStretch(); layout.addLayout(title_row)
        preview_container = QWidget(); preview_layout = QVBoxLayout(preview_container); preview_layout.setContentsMargins(0, 0, 0, 0); preview_layout.setSpacing(8)
        if not file_data: empty_lbl = QLabel("대기 중인 파일이 없습니다."); empty_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none;"); preview_layout.addWidget(empty_lbl)
        else:
            for name, fpath in file_data[:5]:
                display_name = f"📁 {name}" if is_nas else name; file_lbl = QLabel(display_name); file_lbl.setStyleSheet(f"QLabel {{ color: {config.FG2}; font-size: 11px; border: none; padding: 2px 4px; background: transparent; }} QLabel:hover {{ color: #4AFF80; background: #3d3d3d; border-radius: 4px; }}")
                file_lbl.mousePressEvent = (lambda e, p=fpath: self._open_srt_in_editor(p) if p.endswith(".srt") else self.backend.start_pipeline([p])); preview_layout.addWidget(file_lbl)
        layout.addWidget(preview_container); w.mousePressEvent = (lambda e: default_cmd()); self._preview_containers.append(preview_container); preview_container.setVisible(not getattr(self, '_log_visible', False))
        return w

    def _btn(self, text, desc, cmd):
        w = QWidget(); w.setObjectName("MenuButton"); w.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}"); w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(4)
        lbl = QLabel(text); lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(lbl)
        if desc: sub = QLabel(desc); sub.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none; background: transparent;"); sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(sub)
        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton: cmd(); e.accept()
        w.mousePressEvent = _on_w_click; return w

    def _dummy_action(self): pass

    def _show_path_settings(self):
        dlg = QDialog(self); dlg.setWindowTitle("경로설정"); dlg.setMinimumWidth(450); dlg.setStyleSheet(f"""
            QDialog {{ background-color: {config.BG}; color: {config.FG}; }}
            QLabel {{ color: {config.FG}; }}
            QCheckBox {{ color: {config.FG}; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid #FFFFFF; border-radius: 3px; background-color: transparent; }}
            QCheckBox::indicator:checked {{ background-color: #4AFF80; border: 2px solid #4AFF80; }}
        """)

        layout = QVBoxLayout(dlg); layout.addWidget(QLabel("NAS 루트 경로:"))
        nas_input = QLineEdit(get_nas_path()); nas_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;"); layout.addWidget(nas_input)
        layout.addWidget(QLabel("iCloud 동기화 경로:"))
        icloud_input = QLineEdit(get_icloud_path()); icloud_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;"); layout.addWidget(icloud_input)
        icl_chk = QCheckBox("자동감지 및 처리활성화 iCloud"); icl_chk.setChecked(get_icloud_auto_detect()); layout.addWidget(icl_chk)
        nas_chk = QCheckBox("자동감지 및 처리활성화 NAS"); nas_chk.setChecked(get_nas_auto_detect()); layout.addWidget(nas_chk)
        btn_layout = QHBoxLayout(); btn_save = QPushButton("저장"); btn_save.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px;")
        def save_all():
            set_nas_path(nas_input.text()); set_icloud_path(icloud_input.text())
            set_icloud_auto_detect(icl_chk.isChecked()); self._is_icloud_auto_mode = icl_chk.isChecked()
            if self._is_icloud_auto_mode: self._cloud_sync_manager.dropzone_path = icloud_input.text(); self._cloud_sync_manager.start()
            else: self._cloud_sync_manager.stop()
            set_nas_auto_detect(nas_chk.isChecked()); self._is_nas_auto_mode = nas_chk.isChecked()
            dlg.accept(); self.show_home()
        btn_save.clicked.connect(save_all); btn_layout.addStretch(); btn_layout.addWidget(btn_save); layout.addLayout(btn_layout); dlg.exec()