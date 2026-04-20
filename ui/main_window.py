# Version: 02.01.00
# Phase: PHASE1-B
"""
ui/main_window.py
[v02.01.00] 리팩토링: Mixin 분리 + import 정리 + 버전 통합
"""

import os, json, re

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QTextEdit, QFileDialog, QSplitter, QApplication,
    QDialog, QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from ui.queue_widget import QueueMixin
from ui.project_ui import ProjectUIMixin
from ui.cloud_ui import CloudUIMixin

import config
from logger import get_logger
from core.cloud_sync import CloudSyncManager
from core.project_manager import load_project, get_boundary_times
from core.path_manager import (
    get_srt_path, get_last_folder, set_last_folder,
    get_icloud_path, ensure_nas_mounted,
    get_recent_folders, add_recent_folder,
    get_icloud_auto_detect, get_nas_auto_detect
)
from ui.folder_dialog import FolderDialog

DATASET_DIR   = "dataset"
SETTINGS_FILE = os.path.join(DATASET_DIR, "user_settings.json")


class MainWindow(QueueMixin, ProjectUIMixin, CloudUIMixin, QMainWindow):
    _sig_show_home           = pyqtSignal()
    _sig_append_segments     = pyqtSignal(list)
    _sig_update_status       = pyqtSignal(int, int)
    _sig_open_editor         = pyqtSignal(str, object, object, object, object, bool)
    _sig_set_vad_segments    = pyqtSignal(list)
    _sig_update_queue        = pyqtSignal(int, str, str, str, str)
    _sig_update_queue_header = pyqtSignal(int, int, int, str)
    _sig_auto_start_pipeline = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 AI Subtitle Studio")
        self.setMinimumSize(600, 500)
        self.recent_folders = []; self.add_recent_folder_callback = None
        self._editor_widget = None; self.backend = None
        self._backup_nums = {}
        self._preview_containers = []
        self._expected_seconds = {}
        self._file_start_times = {}
        self._current_file_idx = 1
        self._total_files = 1
        self._is_auto_pipeline = False
        self._current_project_path = None
        self._project_boundary_times = []

        self._is_icloud_auto_mode = get_icloud_auto_detect()
        self._is_nas_auto_mode = get_nas_auto_detect()

        self._live_timer = QTimer()
        self._live_timer.timeout.connect(self._update_live_queue_header)

        self._build_ui(); self._connect_signals()

        self._cloud_sync_manager = CloudSyncManager(get_icloud_path(), self._on_files_detected, self._is_app_busy)
        if getattr(self, '_is_icloud_auto_mode', False):
            self._cloud_sync_manager.start()

    # ── 설정 ──
    def _load_local_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except Exception: pass
        return {}

    def _save_local_settings(self, data):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def _add_recent_folder(self, folder_path):
        if not folder_path or not str(folder_path).strip(): return
        add_recent_folder(folder_path)
        self.recent_folders = get_recent_folders()
        settings = self._load_local_settings()
        recent = settings.get("recent_folders", [])
        if folder_path in recent: recent.remove(folder_path)
        recent.insert(0, folder_path)
        self.recent_folders = recent[:3]
        settings["recent_folders"] = self.recent_folders
        self._save_local_settings(settings)
        if self.add_recent_folder_callback: self.add_recent_folder_callback(folder_path)

    # ── UI 빌드 ──
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        self.stack = QStackedWidget(); self.stack.setStyleSheet(f"background: {config.BG};")
        main_layout.addWidget(self.stack, stretch=1)
        self.home_page = QWidget(); self.stack.addWidget(self.home_page)
        self.editor_page = QWidget(); self.stack.addWidget(self.editor_page)
        log_panel = self._build_log_panel(); main_layout.addWidget(log_panel)
        self.show_home()

    def _build_log_panel(self):
        container = QWidget(); container.setStyleSheet(f"background: {config.BG2};")
        layout = QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        toggle_bar = QWidget(); toggle_bar.setFixedHeight(28); toggle_bar.setStyleSheet(f"background: {config.BG3};"); toggle_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        tb_layout = QHBoxLayout(toggle_bar); tb_layout.setContentsMargins(20, 0, 0, 0)
        self._log_toggle_btn = QLabel("▲ 터미널 로그 보기"); self._log_toggle_btn.setStyleSheet(f"color: {config.FG2}; font-size: 11px; font-weight: bold;")
        tb_layout.addWidget(self._log_toggle_btn); tb_layout.addStretch(); layout.addWidget(toggle_bar)
        toggle_bar.mousePressEvent = lambda e: self._toggle_log()
        self._log_content = QWidget(); self._log_content.setFixedHeight(220)
        lc_layout_main = QVBoxLayout(self._log_content); lc_layout_main.setContentsMargins(0, 0, 0, 0)
        self.log_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.log_splitter.setStyleSheet(f"QSplitter::handle {{ background: {config.BG3}; width: 2px; }}")
        term_widget = QWidget(); term_layout = QVBoxLayout(term_widget); term_layout.setContentsMargins(0, 0, 0, 0)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setFont(QFont("Menlo", 10))
        self.log_text.setStyleSheet(f"background: {config.BG2}; color: {config.FG2}; border: none; padding: 8px;")
        term_layout.addWidget(self.log_text)
        queue_widget = QWidget(); queue_layout = QVBoxLayout(queue_widget); queue_layout.setContentsMargins(5, 5, 5, 5)
        self.queue_header_lbl = QLabel("📋 처리할 파일 리스트")
        self.queue_header_lbl.setStyleSheet(f"color: {config.FG}; font-weight: bold; font-size: 12px;")
        queue_layout.addWidget(self.queue_header_lbl)
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["  상태  ", "  파일명  ", "  영상정보  ", "  영상길이  ", "  예상시간  "])
        self.queue_table.setWordWrap(True); self.queue_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed); self.queue_table.setColumnWidth(4, 140)
        self.queue_table.verticalHeader().setVisible(False); self.queue_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded); self.queue_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.queue_table.setShowGrid(True); self.queue_table.setGridStyle(Qt.PenStyle.SolidLine)
        self.queue_table.setStyleSheet(f"QTableWidget {{ background: {config.BG2}; color: {config.FG}; border: none; font-size: 11px; gridline-color: #FFFFFF; }} QTableWidget::item {{ padding: 6px 12px; }} QHeaderView::section {{ background: {config.BG3}; color: {config.FG2}; border: none; border-right: 1px solid #FFFFFF; border-bottom: 1px solid #FFFFFF; padding: 8px 12px; }}")
        queue_layout.addWidget(self.queue_table); self.log_splitter.addWidget(term_widget); self.log_splitter.addWidget(queue_widget)
        self.log_splitter.setStretchFactor(0, 1); self.log_splitter.setStretchFactor(1, 1); self.log_splitter.setSizes([500, 500])
        lc_layout_main.addWidget(self.log_splitter); layout.addWidget(self._log_content)
        settings = self._load_local_settings(); self._log_visible = settings.get("show_terminal_log", False)
        if self._log_visible: self._log_content.show(); self._log_toggle_btn.setText("▼ 터미널 로그 숨기기")
        else: self._log_content.hide(); self._log_toggle_btn.setText("▲ 터미널 로그 보기")
        self._queue_anim_frames = ["📑", "📄", "📃", "📝"]; self._queue_anim_idx = 0
        self._queue_anim_timer = QTimer(self); self._queue_anim_timer.setInterval(250); self._queue_anim_timer.timeout.connect(self._animate_queue_status); self._queue_anim_timer.start()
        return container

    # ── 홈 화면 ──
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
        if valid_folders:
            recent_container = QWidget(); recent_container.setObjectName("MenuButton")
            recent_container.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}")
            recent_layout = QVBoxLayout(recent_container); recent_layout.setContentsMargins(20, 10, 20, 10); recent_layout.setSpacing(4)
            recent_lbl = QLabel("📂 최근 폴더"); recent_lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); recent_layout.addWidget(recent_lbl)
            self._recent_buttons = []
            max_visible = 1 if getattr(self, '_log_visible', False) else 3
            for i, folder in enumerate(valid_folders[:3]):
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

    # ── iCloud / NAS 헬퍼 ──

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

    # ── 시그널 ──
    def _connect_signals(self):
        self._sig_show_home.connect(self.show_home); self._sig_append_segments.connect(self._do_append_segments); self._sig_update_status.connect(self._do_update_status); self._sig_open_editor.connect(self._do_open_editor)
        self._sig_set_vad_segments.connect(lambda v: self._editor_widget.set_vad_segments(v) if self._editor_widget else None)
        self._sig_update_queue.connect(self.update_queue_status); self._sig_update_queue_header.connect(self.update_queue_header); self._sig_auto_start_pipeline.connect(self._do_auto_start_pipeline)

    # ── 홈 / 에디터 전환 ──
    def show_home(self):
        self.stack.setCurrentIndex(0)
        if self._editor_widget:
            self._trash_bin = getattr(self, '_trash_bin', []); self._trash_bin.append(self._editor_widget)
            if len(self._trash_bin) > 3: self._trash_bin.pop(0)
        self._editor_widget = None; self._build_home_content()

    def request_show_home(self): self._sig_show_home.emit()
    def append_segments_to_editor(self, segments): self._sig_append_segments.emit(segments)
    def update_editor_status(self, c_idx, t_total): self._sig_update_status.emit(c_idx, t_total)
    def append_log(self, msg): self.log_text.append(msg); self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def _do_append_segments(self, segments):
        if self._editor_widget: self._editor_widget.append_segments(segments)

    def _do_update_status(self, c_idx, t_total):
        if self._editor_widget:
            if hasattr(self._editor_widget, 'update_progress'): self._editor_widget.update_progress(c_idx, t_total)

    def open_editor_for_file(self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
        self._sig_open_editor.emit(target_file, on_save, on_start, on_prev, on_exit, is_batch)

    def _do_open_editor(self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
        self._on_save_cb = on_save; self._on_start_cb = on_start; self._on_prev_cb = on_prev; self._on_exit_cb = on_exit
        self._target_file = target_file; self._init_editor(target_file, is_batch)

    # ── 파일/폴더/최근 (프로젝트 잔재 초기화 포함) ──
    def select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 선택", get_last_folder() or os.path.expanduser("~"), "Media/SRT Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.srt)")
        if not paths: return
        set_last_folder(os.path.dirname(paths[0])); self._add_recent_folder(os.path.dirname(paths[0]))
        self._is_auto_pipeline = False; self._current_project_path = None; self._project_boundary_times = []
        srt = [p for p in paths if p.lower().endswith(".srt")]; vid = [p for p in paths if not p.lower().endswith(".srt")]
        if srt: self._open_srt_in_editor(srt[0])
        elif vid and self.backend: self.backend.start_pipeline(vid)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택", get_last_folder() or os.path.expanduser("~"))
        if not folder or not ensure_nas_mounted(folder): return
        set_last_folder(folder); self._add_recent_folder(folder)
        self._is_auto_pipeline = False; self._current_project_path = None; self._project_boundary_times = []
        dlg = FolderDialog(folder, self)
        if dlg.exec() and dlg.selected_files: self.backend.start_pipeline(dlg.selected_files, folder=folder)

    def _open_recent(self, folder):
        if not os.path.exists(folder):
            if not ensure_nas_mounted(folder): QMessageBox.warning(self, "오류", f"폴더를 찾을 수 없습니다:\n{folder}"); return
        set_last_folder(folder); self._add_recent_folder(folder)
        self._is_auto_pipeline = False; self._current_project_path = None; self._project_boundary_times = []
        dlg = FolderDialog(folder, self)
        if dlg.exec() and dlg.selected_files: self.backend.start_pipeline(dlg.selected_files, folder=folder)

    def open_editor_directly(self):
        path, _ = QFileDialog.getOpenFileName(self, "SRT 파일 선택", get_last_folder() or os.path.expanduser("~"), "SRT Files (*.srt)")
        if path: set_last_folder(os.path.dirname(path)); self._add_recent_folder(os.path.dirname(path)); self._open_srt_in_editor(path)

    # ── 경로 설정 ──
    def _show_path_settings(self):
        dlg = QDialog(self); dlg.setWindowTitle("경로설정"); dlg.setMinimumWidth(450); dlg.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
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

    # ── 캐시 / 종료 ──
    def _clear_cache(self):
        reply = QMessageBox.question(self, '캐쉬 삭제', 'output 폴더 내의 임시 파일들을 모두 삭제하시겠습니까?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            import shutil; output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
            try:
                if os.path.exists(output_dir): shutil.rmtree(output_dir); os.makedirs(output_dir, exist_ok=True)
                from core.auto_tracker import TRACKER_FILE
                if os.path.exists(TRACKER_FILE): os.remove(TRACKER_FILE)
                if hasattr(self, '_cloud_sync_manager'): mgr = self._cloud_sync_manager; mgr._size_cache.clear(); mgr._in_flight.clear()
                QMessageBox.information(self, "완료", "🗑️ 캐쉬 삭제 완료"); self.show_home()
            except Exception as e: QMessageBox.warning(self, "오류", f"삭제 중 오류: {e}")

    def _quick_exit(self):
        if self.backend: self.backend.stop()
        QApplication.quit()

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible: self._log_content.show(); self._log_toggle_btn.setText("▼ 터미널 로그 숨기기")
        else: self._log_content.hide(); self._log_toggle_btn.setText("▲ 터미널 로그 보기")
        for c in getattr(self, '_preview_containers', []):
            try: c.setVisible(not self._log_visible)
            except: pass
        for i, btn in enumerate(getattr(self, '_recent_buttons', [])):
            try: btn.setVisible(i == 0 if self._log_visible else True)
            except: pass
        settings = self._load_local_settings(); settings["show_terminal_log"] = self._log_visible; self._save_local_settings(settings)
        if self._editor_widget and hasattr(self._editor_widget, 'set_terminal_visible_layout'): self._editor_widget.set_terminal_visible_layout(self._log_visible)
        QTimer.singleShot(10, self._refresh_video)

    def _refresh_video(self):
        if self._editor_widget and hasattr(self._editor_widget, 'video_player'): self._editor_widget.video_player.resizeEvent(None)

    # ── SRT 에디터 (항상 단일 파일) ──
    def _open_srt_in_editor(self, srt_path):
        from core.srt_parser import parse_srt
        segments = parse_srt(srt_path)
        from ui.editor_widget import EditorWidget
        self._remove_old_editor()
        base_path = os.path.splitext(srt_path)[0]; media_extensions = ['.mp4', '.mov', '.MOV', '.MP4', '.wav', '.m4a', '.m2a', '.mp3', '.aac']
        media_path = next((base_path + ext for ext in media_extensions if os.path.exists(base_path + ext)), srt_path)
        editor = EditorWidget(video_name=os.path.basename(srt_path), segments=segments, media_path=media_path, parent=self)
        editor._project_clips = None
        def _save_and_home(segs=None):
            if segs is not None: self._save_srt(srt_path, segs)
            QTimer.singleShot(0, self.show_home)
        editor.sig_save.connect(lambda segs: self._save_srt(srt_path, segs)); editor.sig_auto_save.connect(lambda segs: self._save_srt(srt_path, segs)); editor.sig_next.connect(_save_and_home); editor.sig_exit.connect(lambda _: self.close())
        self._editor_widget = editor
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        if hasattr(editor, 'timeline') and self._project_boundary_times: editor.timeline.set_boundary_times(self._project_boundary_times)
        self.stack.insertWidget(1, editor); self.stack.setCurrentIndex(1)

    # ── SRT 저장 ──
    def _save_srt(self, srt_path, segments):
        try:
            from core.subtitle_engine import save_srt; save_srt(segments, srt_path, apply_offset=False)
            get_logger().log(f"✅ {os.path.basename(srt_path)} 저장 완료")
        except Exception as e: get_logger().log(f"❌ SRT 저장 실패: {e}")

    def _backup_srt(self, srt_path, segments):
        try:
            from core.subtitle_engine import save_srt; import datetime
            base = os.path.splitext(os.path.basename(srt_path))[0]; date_str = datetime.date.today().strftime("%Y%m%d"); num = self._backup_nums.get(srt_path, 1)
            backup_dir = os.path.join(os.path.dirname(srt_path), "자막백업"); os.makedirs(backup_dir, exist_ok=True)
            save_srt(segments, os.path.join(backup_dir, f"{base}_{date_str}_{num:03d}.srt"), apply_offset=False)
        except Exception as e: get_logger().log(f"⚠️ 백업 저장 실패: {e}")
    # ✅ [수정] closeEvent — dirty 기반 판단 + 저장 직후 스킵
    def closeEvent(self, event):
        if self._editor_widget and self.stack.currentIndex() == 1:
            # 생성 중이면 먼저 중단
            if hasattr(self._editor_widget, 'sm') and self._editor_widget.sm.is_locked:
                if hasattr(self._editor_widget, '_stop_pipeline'):
                    self._editor_widget._stop_pipeline()

            # ✅ 저장 직후 스킵 플래그 확인
            if getattr(self._editor_widget, '_skip_prev_confirm_once', False):
                self._editor_widget._skip_prev_confirm_once = False
                event.accept()
            else:
                # ✅ dirty 기반 판단 (기존: segs 존재 여부)
                is_dirty = False
                try:
                    if hasattr(self._editor_widget, 'sm'):
                        is_dirty = bool(self._editor_widget.sm.is_dirty)
                except Exception:
                    pass

                if is_dirty:
                    msg_box = QMessageBox(self)
                    msg_box.setWindowTitle("종료 확인")
                    msg_box.setText("저장되지 않은 변경사항이 있습니다.\n저장하시겠습니까?")
                    msg_box.setStandardButtons(
                        QMessageBox.StandardButton.Yes |
                        QMessageBox.StandardButton.No |
                        QMessageBox.StandardButton.Cancel
                    )
                    msg_box.button(QMessageBox.StandardButton.Yes).setText("예")
                    msg_box.button(QMessageBox.StandardButton.No).setText("아니요")
                    msg_box.button(QMessageBox.StandardButton.Cancel).setText("취소")
                    reply = msg_box.exec()

                    if reply == QMessageBox.StandardButton.Yes:
                        if hasattr(self._editor_widget, '_on_save'):
                            self._editor_widget._on_save()
                        event.accept()
                    elif reply == QMessageBox.StandardButton.No:
                        event.accept()
                    else:
                        event.ignore()
                        return
                else:
                    event.accept()
        else:
            event.accept()

        get_logger().clear_ui_callback()
        self.blockSignals(True)
        if self._editor_widget and hasattr(self._editor_widget, 'video_player'):
            try:
                vp = self._editor_widget.video_player
                if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                if hasattr(vp, '_worker') and vp._worker:
                    vp._worker.stop()
                    vp._worker.wait(200)
            except: pass
        if self.backend: self.backend.stop()
        QTimer.singleShot(100, lambda: os._exit(0))

    def _remove_old_editor(self):
        old = self.stack.widget(1)
        if old:
            if hasattr(old, '_cleanup'):
                try: old._cleanup()
                except: pass
            if hasattr(old, 'video_player'):
                try:
                    vp = old.video_player
                    if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                    if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                    if hasattr(vp, '_worker') and getattr(vp, '_worker', None): vp._worker.stop(); vp._worker.wait(200)
                except: pass
            self.stack.removeWidget(old); old.hide()
            if not hasattr(self, '_trash_bin'): self._trash_bin = []
            self._trash_bin.append(old)
            if len(self._trash_bin) > 3: self._trash_bin.pop(0).deleteLater()

    # ✅ [v01.00.08] _init_editor: handle_prev 다이얼로그 제거 (EditorPipeline._on_prev가 단일 처리)
    def _init_editor(self, target_file, is_batch=False):
        from ui.editor_widget import EditorWidget
        vname = os.path.basename(target_file); self._remove_old_editor()
        editor = EditorWidget(video_name=vname, segments=[], media_path=target_file, parent=self)
        editor.is_auto_start = is_batch; self._editor_widget = editor

        editor._project_clips = None
        if self._current_project_path and self.backend:
            n_files = len(getattr(self.backend, 'files_to_process', []))
            if n_files > 1:
                pd = load_project(self._current_project_path)
                if pd and "timeline" in pd:
                    clips = pd["timeline"].get("tracks", [{}])[0].get("clips", [])
                    if len(clips) > 1: editor._project_clips = clips

        if is_batch: editor.sm.init_auto_state()
        else: editor.sm.init_state()
        if hasattr(editor, 'btn_start'): editor.btn_start.setText("🧠 시작")
        if is_batch: QTimer.singleShot(600, lambda e=editor: e.btn_start.click() if hasattr(e, 'btn_start') else None)

        def safe_home(*args): QTimer.singleShot(0, self.show_home)
        def force_exit_app(*args): self.close()

        # ✅ handle_prev: 다이얼로그 없음 (EditorPipeline._on_prev가 처리)
        def handle_prev(*args):
            if self._on_prev_cb: self._on_prev_cb()
            safe_home()

        if self._on_start_cb: editor.sig_start.connect(self._on_start_cb)
        editor.sig_prev.connect(handle_prev); editor.sig_exit.connect(force_exit_app)
        if self._on_save_cb: editor.sig_next.connect(self._on_save_cb)
        else: editor.sig_next.connect(safe_home)
        srt_save_path = get_srt_path(target_file)
        editor.sig_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))
        editor.sig_auto_save.connect(lambda segs, p=srt_save_path: self._save_srt(p, segs))
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        self.stack.insertWidget(1, editor)
        if hasattr(editor, 'timeline'): editor.timeline.set_boundary_times(self._project_boundary_times or [])
        self.stack.setCurrentIndex(1)