# Version: 02.02.00
# Phase: PHASE1-B
"""
ui/main_window.py
[v02.02.00] Mixin 분리 완료: Home / EditorLifecycle / Workspace / Queue / Project / Cloud
"""
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QTextEdit, QFileDialog, QSplitter, QApplication,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont

from ui.queue_widget import QueueMixin
from ui.project_ui import ProjectUIMixin
from ui.cloud_ui import CloudUIMixin
from ui.home_ui import HomeUIMixin
from ui.editor_lifecycle import EditorLifecycleMixin
from ui.workspace_mixin import WorkspaceMixin

import config
from logger import get_logger
from core.cloud_sync import CloudSyncManager
from core.path_manager import (
    get_srt_path, get_last_folder, set_last_folder,
    get_icloud_path, ensure_nas_mounted,
    get_recent_folders, add_recent_folder,
    get_icloud_auto_detect, get_nas_auto_detect
)
from ui.folder_dialog import FolderDialog
from core.settings import load_settings, save_settings


class MainWindow(
    HomeUIMixin, EditorLifecycleMixin, WorkspaceMixin,
    QueueMixin, ProjectUIMixin, CloudUIMixin,
    QMainWindow
):
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
    def _add_recent_folder(self, folder_path):
        if not folder_path or not str(folder_path).strip(): return
        add_recent_folder(folder_path)
        self.recent_folders = get_recent_folders()
        settings = load_settings()
        recent = settings.get("recent_folders", [])
        if folder_path in recent: recent.remove(folder_path)
        recent.insert(0, folder_path)
        self.recent_folders = recent[:3]
        settings["recent_folders"] = self.recent_folders
        save_settings(settings)
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
        settings = load_settings(); self._log_visible = settings.get("show_terminal_log", False)
        if self._log_visible: self._log_content.show(); self._log_toggle_btn.setText("▼ 터미널 로그 숨기기")
        else: self._log_content.hide(); self._log_toggle_btn.setText("▲ 터미널 로그 보기")
        self._queue_anim_frames = ["📑", "📄", "📃", "📝"]; self._queue_anim_idx = 0
        self._queue_anim_timer = QTimer(self); self._queue_anim_timer.setInterval(250); self._queue_anim_timer.timeout.connect(self._animate_queue_status); self._queue_anim_timer.start()
        return container

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

    # ── 파일/폴더/최근 ──
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

    # ── 캐시 / 종료 / 로그 ──
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
        settings = load_settings(); settings["show_terminal_log"] = self._log_visible; save_settings(settings)
        if self._editor_widget and hasattr(self._editor_widget, 'set_terminal_visible_layout'): self._editor_widget.set_terminal_visible_layout(self._log_visible)
        QTimer.singleShot(10, self._refresh_video)

    def _refresh_video(self):
        if self._editor_widget and hasattr(self._editor_widget, 'video_player'): self._editor_widget.video_player.resizeEvent(None)