# Version: 01.00.04
"""
ui/main_window.py
[v01.00.04 ?�정?�항]
- 부?�목 "?�설가?�모???�용 ?�막 ?�동 ?�성�? ?�스???�거
- 최근 ?�더 버튼: _recent_buttons 추적, 로그 ?�릴 ??1개만 ?�시
- closeEvent: ???�니??취소 StandardButton 방식?�로 editor_pipeline�??�일
- _init_editor: 중복 ?�그???�결 코드 ?�거
"""
import os, json, re
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QStackedWidget, QTextEdit, QFileDialog, QSplitter, QFrame, QApplication, QDialog, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from core.cloud_sync import CloudSyncManager

import config
from logger import get_logger

from core.path_manager import (
    get_video_files, get_pending_videos, get_srt_path, get_last_folder, set_last_folder, 
    get_nas_path, set_nas_path, get_icloud_path, set_icloud_path, ensure_nas_mounted,
    get_recent_folders, add_recent_folder,
    # ?�� [?�정] ?�래 4개로 ?�실?�게 교체??주세??
    get_icloud_auto_detect, set_icloud_auto_detect, 
    get_nas_auto_detect, set_nas_auto_detect
)

from ui.folder_dialog import FolderDialog

DATASET_DIR   = "dataset"
SETTINGS_FILE = os.path.join(DATASET_DIR, "user_settings.json")

class MainWindow(QMainWindow):
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
        self.setWindowTitle("AI Subtitle Studio")
        self.setMinimumSize(600, 500)
        self.recent_folders = []; self.add_recent_folder_callback = None
        self._editor_widget = None; self.backend = None
        self._backup_nums = {}
        self._preview_containers = []
        self._expected_seconds = {}  
        self._file_start_times = {}  
        self._current_file_idx = 1
        self._total_files = 1
        
        # [MainWindow.__init__ ?��? ?�정]
        self._is_icloud_auto_mode = get_icloud_auto_detect() # iCloud ?�용
        self._is_nas_auto_mode = get_nas_auto_detect()       # NAS ?�용

        self._live_timer = QTimer()
        self._live_timer.timeout.connect(self._update_live_queue_header)

        self._build_ui(); self._connect_signals()
        
        # ?�� [?�치독 ?�착 부�??�정]
        # ??번째 ?�자�?self._is_app_busy�??�겨주어??'?�치 보기' 기능???�동?�니??
        self._cloud_sync_manager = CloudSyncManager(get_icloud_path(), self._on_files_detected, self._is_app_busy)
        if getattr(self, '_is_icloud_auto_mode', False):
            self._cloud_sync_manager.start()

    def _on_files_detected(self, files_list):
        get_logger().log(f"?? ?�동 처리 ??진입: {len(files_list)}�??�일")
        # ?�� [?�심] ?�?�머(QTimer) ?�???�전??무전�?Signal)�??�서 메인 ?�레?�로 ?�깁?�다!
        self._sig_auto_start_pipeline.emit(files_list)

    def _do_auto_start_pipeline(self, files_list):
        if self.backend:
            # 1. ?�진 ?�작
            self.backend.start_pipeline(files_list, is_auto_start=True)
            
            # 2. ?�� [?�정] ?�?�머 ?�이 즉시 ?�태 반영 (?�디?��? ?��? ?�있??경우)
            if self._editor_widget and hasattr(self._editor_widget, 'update_status'):
                self._editor_widget.update_status("?? AI ?�진???�작?�었?�니?? (?�동 감�?)")

    def _is_app_busy(self) -> bool:
        """?�재 ?�디?��? ?�려?�거???�업 중인지 ?�인?�니??"""
        if self._editor_widget is not None: return True
        if self.backend and getattr(self.backend, '_active', False): return True
        return False
    
    def mark_cloud_file_done(self, filepath: str):
        """backend 처리 ?�료 ??CloudSyncManager _in_flight �?tracker ?�태 ?�제"""
        if hasattr(self, '_cloud_sync_manager'):
            self._cloud_sync_manager.mark_done(filepath)

    def _load_local_settings(self) -> dict:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
            except Exception: pass
        return {}

    def _save_local_settings(self, data: dict):
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

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        self.stack = QStackedWidget(); self.stack.setStyleSheet(f"background: {config.BG};")
        main_layout.addWidget(self.stack, stretch=1)
        self.home_page = QWidget(); self.stack.addWidget(self.home_page)
        self.editor_page = QWidget(); self.stack.addWidget(self.editor_page)
        log_panel = self._build_log_panel(); main_layout.addWidget(log_panel)
        self.show_home()

    def _build_log_panel(self) -> QWidget:
        container = QWidget(); container.setStyleSheet(f"background: {config.BG2};")
        layout = QVBoxLayout(container); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        toggle_bar = QWidget(); toggle_bar.setFixedHeight(28); toggle_bar.setStyleSheet(f"background: {config.BG3};"); toggle_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        tb_layout = QHBoxLayout(toggle_bar); tb_layout.setContentsMargins(20, 0, 0, 0)
        self._log_toggle_btn = QLabel("???��???로그 보기"); self._log_toggle_btn.setStyleSheet(f"color: {config.FG2}; font-size: 11px; font-weight: bold;")
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
        self.queue_header_lbl = QLabel("?�� 처리???�일 리스??)
        self.queue_header_lbl.setStyleSheet(f"color: {config.FG}; font-weight: bold; font-size: 12px;")
        queue_layout.addWidget(self.queue_header_lbl)
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["  ?�태  ", "  ?�일�? ", "  ?�상?�보  ", "  ?�상길이  ", "  ?�상?�간  "])
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
        if self._log_visible: self._log_content.show(); self._log_toggle_btn.setText("???��???로그 ?�기�?)
        else: self._log_content.hide(); self._log_toggle_btn.setText("???��???로그 보기")
        self._queue_anim_frames = ["?��", "?��", "?��", "?��"]; self._queue_anim_idx = 0
        self._queue_anim_timer = QTimer(self); self._queue_anim_timer.setInterval(250); self._queue_anim_timer.timeout.connect(self._animate_queue_status); self._queue_anim_timer.start()
        return container

    # [ui/main_window.py] _get_icloud_files ?�수 교체
    def _get_icloud_files(self) -> tuple[list, str, str]:
        path = get_icloud_path()
        if not path or not os.path.exists(path):
            path = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/AI_EDIT")
            if not os.path.exists(path): return [], "경로 ?�음", ""
        
        v_exts = {'.mov', '.mp4', '.m4v', '.MOV', '.MP4', '.M4V', '.lrf', '.LRF'}
        a_exts = {'.wav', '.m4a', '.mp3', '.aac', '.m2a'}
        v_count, a_count = 0, 0
        comp_v_count, comp_a_count = 0, 0 # ?�료???�일 카운??
        files = []
        
        try:
            from core.auto_tracker import AutoTracker
            tracker = AutoTracker()
        except ImportError: tracker = None
        
        try:
            for f in os.listdir(path):
                if f.startswith('.') or "_?�막?�스.mov" in f: continue
                ext = os.path.splitext(f)[1].lower()
                file_path = os.path.join(path, f)
                
                # ?�� [?�심] 추적기에??'?�료' ?�태?��? ?�인?�니??
                status = tracker.get_status(file_path) if tracker else None
                if status == "?�료":
                    if ext in v_exts: comp_v_count += 1
                    elif ext in a_exts: comp_a_count += 1
                    continue # ?�기열 리스??files)?�는 ?��? ?�습?�다!
                
                if ext in v_exts: 
                    v_count += 1
                    files.append((f, file_path))
                elif ext in a_exts: 
                    a_count += 1
                    files.append((f, file_path))
                elif ext == '.srt':
                    files.append((f, file_path))
            
            count_str = f"?��?: ?�상 {v_count:02d}�?/ ?�성 {a_count:02d}�?
            comp_str = f"???�업?�료 : ?�상 {comp_v_count:02d}�?/ ?�성 {comp_a_count:02d}�?
            return sorted(files), count_str, comp_str
        except Exception: 
            return [], "?�류", ""

    def _icloud_btn(self, text, file_data, default_cmd, is_nas=False, subtitle="", comp_title=""):
        w = QWidget(); w.setObjectName("MenuButton")
        w.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}")
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(6) 
        
        # ?�� [?�심] ?�동 감�? ?�정(self._is_auto_mode)???�라 글?�색 결정
        if is_nas:
            active = getattr(self, '_is_nas_auto_mode', False)
        else:
            active = getattr(self, '_is_icloud_auto_mode', False)
            
        text_color = config.FG if active else config.FG2
        
        title_row = QHBoxLayout()
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {text_color}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        title_row.addWidget(lbl)
        
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(f"color: {config.ACCENT}; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 10px;")
            title_row.addWidget(sub_lbl)
            
        # ?�� [?�규 추�?] ?�업 ?�료 ?�스?��? 초록?�으�??�쁘�??�워줍니??
        if comp_title:
            comp_lbl = QLabel(comp_title)
            comp_lbl.setStyleSheet(f"color: #4AFF80; font-size: 11px; font-weight: bold; border: none; background: transparent; padding-left: 15px;")
            title_row.addWidget(comp_lbl)
            
        title_row.addStretch()
        layout.addLayout(title_row)
        
        preview_container = QWidget(); preview_layout = QVBoxLayout(preview_container); preview_layout.setContentsMargins(0, 0, 0, 0); preview_layout.setSpacing(8)
        if not file_data:
            empty_lbl = QLabel("?��?중인 ?�일???�습?�다."); empty_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none;"); preview_layout.addWidget(empty_lbl)
        else:
            for name, path in file_data[:5]: 
                display_name = f"?�� {name}" if is_nas else name
                file_lbl = QLabel(display_name); file_lbl.setStyleSheet(f"QLabel {{ color: {config.FG2}; font-size: 11px; border: none; padding: 2px 4px; background: transparent; }} QLabel:hover {{ color: #4AFF80; background: #3d3d3d; border-radius: 4px; }}")
                file_lbl.mousePressEvent = (lambda e, p=path: self._open_srt_in_editor(p) if p.endswith(".srt") else self.backend.start_pipeline([p]))
                preview_layout.addWidget(file_lbl)
        
        layout.addWidget(preview_container); w.mousePressEvent = (lambda e: default_cmd())
        self._preview_containers.append(preview_container)
        preview_container.setVisible(not getattr(self, '_log_visible', False))
        return w

    def _animate_queue_status(self):
        self._queue_anim_idx = (self._queue_anim_idx + 1) % len(self._queue_anim_frames)
        for i in range(self.queue_table.rowCount()):
            item = self.queue_table.item(i, 0)
            if item:
                txt = item.text()
                # ?�� ?�태???�라 ?�니메이???��)???�르�?붙여줍니??
                if "?�막 ?�성 �? in txt:
                    item.setText(f"{self._queue_anim_frames[self._queue_anim_idx]} ?�막 ?�성 �?)
                elif "?�막?�상출력" in txt or "?�상출력" in txt:
                    item.setText(f"{self._queue_anim_frames[self._queue_anim_idx]} ?�막?�상출력(mov)")
                    
    def _build_home_content(self):
        self._preview_containers = []
        old_layout = self.home_page.layout()
        if old_layout is not None: QWidget().setLayout(old_layout) 
        
        layout = QVBoxLayout(self.home_page); layout.setContentsMargins(40, 30, 40, 30); layout.setSpacing(16); layout.addStretch()
        
        # ?�?��? ?�역
        title = QLabel("?�� AI PD Studio"); title.setAlignment(Qt.AlignmentFlag.AlignCenter); title.setStyleSheet(f"color: {config.FG}; font-size: 28px; font-weight: bold;"); layout.addWidget(title)
        layout.addSpacing(12)
        
        # 1. ?�일/?�더 ?�택 메뉴??
        standard_menus = [
            ("?�� ?�일 ?�택", "?�상/?�성/srt ?�일 직접 ?�택", self.select_files), 
            ("?�� ?�더 ?�택", "?�이?�로그에???�상 ?�일 ?�괄/부�??�택", self.select_folder), 
            ("?�️ cut ?�집 ?�우�?, "개발 �?, self._dummy_action)
        ]
        for t, d, s in standard_menus: 
            layout.addWidget(self._btn(t, d, s))
        
        # 2. ?�� [?�심] iCloud ?�동 처리 (중복 ?�거 �?개수 ?�시 ?�용)
        # ?�� [?�정 ?? comp_str??추�??�서 3개�? 받아???�니??
        icloud_files, count_str, comp_str = self._get_icloud_files()
        layout.addWidget(self._icloud_btn("?�️ iCloud ?�동 처리", icloud_files, self.start_icloud_sync, subtitle=count_str, comp_title=comp_str))
        
        # 3. NAS ?�동처리 버튼
        nas_folders = self._get_nas_folders()
        layout.addWidget(self._icloud_btn("?���?NAS ?�동처리", nas_folders, self._open_nas_root, is_nas=True))

        # 4. 최근 ?�더 리스??구역
        valid_folders = [f for f in get_recent_folders() if f and f.strip()]
        if valid_folders:
            recent_container = QWidget(); recent_container.setObjectName("MenuButton")
            recent_container.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}")
            recent_layout = QVBoxLayout(recent_container); recent_layout.setContentsMargins(20, 14, 20, 14); recent_layout.setSpacing(8)

            recent_lbl = QLabel("?�� 최근 ?�더"); recent_lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;"); recent_layout.addWidget(recent_lbl)
            desc_lbl = QLabel("최근???�업???�더 리스??); desc_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none; background: transparent;"); recent_layout.addWidget(desc_lbl)

            # [v01.00.04] 로그 ?�널???�려 ?�으�?1개만, ?��? ?�으�?최�? 3�??�시
            self._recent_buttons = []
            max_visible = 1 if getattr(self, '_log_visible', False) else 3
            for i, folder in enumerate(valid_folders[:3]):
                display_name = os.path.basename(folder.rstrip('\\/')) or folder
                # �?경로??말줄?�표�?처리
                full_text = f"?�� {display_name}  ({folder})"
                file_lbl = QLabel(full_text)
                file_lbl.setStyleSheet(f"QLabel {{ color: {config.FG2}; font-size: 11px; border: none; padding: 4px 6px; background: transparent; }} QLabel:hover {{ color: #4AFF80; background: #3d3d3d; border-radius: 4px; }}")
                file_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                file_lbl.setMaximumWidth(600)
                file_lbl.setWordWrap(False)
                file_lbl.mousePressEvent = (lambda e, f=folder: self._open_recent(f) if e.button() == Qt.MouseButton.LeftButton else None)
                # 로그 ?�림 ?�태?�서??�?번째�??�시
                if i >= max_visible:
                    file_lbl.setVisible(False)
                recent_layout.addWidget(file_lbl)
                self._recent_buttons.append(file_lbl)
            layout.addWidget(recent_container)

        layout.addStretch()
        
        # 5. ?�단 �?(버전 ?�보 �??�정/종료 버튼)
        bottom_bar = QHBoxLayout()
        version_lbl = QLabel("v0.1.0 (Build 01.00.00)"); version_lbl.setStyleSheet(f"color: {config.FG2}; font-size: 11px;")
        btn_settings = QPushButton("?�️ 경로?�정"); btn_settings.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_settings.clicked.connect(self._show_path_settings)
        btn_clear_cache = QPushButton("?���?캐쉬??��"); btn_clear_cache.setStyleSheet(f"background: {config.BG3}; color: {config.FG}; border: none; padding: 6px 12px; border-radius: 4px;"); btn_clear_cache.clicked.connect(self._clear_cache)
        btn_exit = QPushButton("??종료"); btn_exit.setStyleSheet(f"background: #882222; color: #FFF; font-weight: bold; border: none; padding: 6px 12px; border-radius: 4px;"); btn_exit.clicked.connect(self._quick_exit)
        
        bottom_bar.addWidget(version_lbl); bottom_bar.addStretch(); bottom_bar.addWidget(btn_settings); bottom_bar.addWidget(btn_clear_cache); bottom_bar.addWidget(btn_exit)
        layout.addLayout(bottom_bar)

    # [ui/main_window.py] init_queue_list �?update_queue_status 교체
    def init_queue_list(self, files: list):
        self._current_file_idx = 1
        self._total_files = len(files)
        self._expected_seconds = {}
        self._file_start_times = {}
        self.queue_table.setRowCount(0)
        
        # ?�� [문구 교체] ?�작 ?�에???�전?�게 '?��?�??�로 ?�시?�니??
        self.queue_header_lbl.setText(f"?�� 처리???�일 리스??(1 / {len(files)} ?��?�? - 0% ?�료 [?�️ 00:00 / 00:00]")        
        for i, f in enumerate(files):
            self.queue_table.insertRow(i)
            def make_item(text):
                it = QTableWidgetItem(text); it.setTextAlignment(Qt.AlignmentFlag.AlignCenter); return it
                
            self.queue_table.setItem(i, 0, make_item("???��?�?))
            self.queue_table.setItem(i, 1, QTableWidgetItem(os.path.basename(f)))
            self.queue_table.setItem(i, 2, make_item("분석 �?.."))
            self.queue_table.setItem(i, 3, make_item("-"))
            self.queue_table.setItem(i, 4, make_item("계산 �?))
            
        self._live_timer.start(1000)

    def update_queue_status(self, idx: int, status: str, time_txt: str = "", info_txt: str = "", len_txt: str = ""):
        if idx < self.queue_table.rowCount():
            def make_item(text):
                it = QTableWidgetItem(text); it.setTextAlignment(Qt.AlignmentFlag.AlignCenter); return it
            
            # ?�간 ?�식 변???�수 (�?-> MM:SS)
            def fmt_mm_ss(sec):
                try:
                    s = float(sec)
                    m, s = divmod(int(s), 60)
                    h, m = divmod(m, 60)
                    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                except: return "00:00"

            if status: 
                self.queue_table.setItem(idx, 0, make_item(status))
                # ?�� "?�막 ?�성 �????�작?�는 ?�간???�각 기록
                if "?�막 ?�성 �? in status and idx not in self._file_start_times:
                    import time
                    self._file_start_times[idx] = time.time()

            if info_txt: self.queue_table.setItem(idx, 2, make_item(info_txt))
            if len_txt: self.queue_table.setItem(idx, 3, make_item(len_txt))
            
            if time_txt:
                # 백엔?�에?????�자�??�?�하�?초기 ?�시
                try: 
                    sec_val = float(time_txt)
                    self._expected_seconds[idx] = sec_val
                    self.queue_table.setItem(idx, 4, make_item(fmt_mm_ss(sec_val)))
                except:
                    self.queue_table.setItem(idx, 4, make_item(time_txt))



    # [ui/main_window.py] _update_live_queue_header ?�수 ?�체 교체
    def _update_live_queue_header(self):
        import time
        if not self.backend or not getattr(self.backend, '_active', False) or getattr(self.backend, 'pipeline_start_time', 0) == 0:
            return
        
        now = time.time()
        elapsed_total = now - self.backend.pipeline_start_time
        expected_total = getattr(self.backend, 'total_expected_time', 0.0)
        
        def fmt_mm_ss(sec):
            m, s = divmod(int(sec), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

        # ?�� [?�단 ?�더] ?�체 ?�간 ?�계 ?�시 (Total Elapsed / Total Expected)
        c = getattr(self, '_current_file_idx', 1)
        t = getattr(self, '_total_files', 1)
        pct = min(99, int((elapsed_total / expected_total) * 100)) if expected_total > 0 else 0
        self.queue_header_lbl.setText(f"?�� 처리???�일 리스??({c} / {t} 진행 �? - {pct}% ?�료   [?�️ {fmt_mm_ss(elapsed_total)} / {fmt_mm_ss(expected_total)}]")

        # ?�� [???�이�? ?�재 진행 중인 ?�일???�간 ?�더�?
        for i in range(self.queue_table.rowCount()):
            status_item = self.queue_table.item(i, 0)
            if status_item and "?�막 ?�성 �? in status_item.text():
                # ?�당 ?�일???�작???�각 기�? 경과 ?�간 계산
                start_t = self._file_start_times.get(i, now)
                elapsed_file = now - start_t
                expected_file = self._expected_seconds.get(i, 0)
                
                time_cell = self.queue_table.item(i, 4)
                if time_cell:
                    # ?�� [?�시 ?�식] 03:44 / 11:36
                    time_cell.setText(f"{fmt_mm_ss(elapsed_file)} / {fmt_mm_ss(expected_file)}")

    def _clear_cache(self):
        reply = QMessageBox.question(
            self, '캐쉬 ??��', 
            'output ?�더 ?�의 ?�시 ?�일?�을 모두 ??��?�시겠습?�까?\n(진행 중인 ?�업???�을 ?�만 ?�용?�세??)', 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            import shutil
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
            
            # ?�� [교정] 중첩??try�??�거?�고 문법 구조�??�석?��?바로?�았?�니??
            try:
                # 1. 물리???�일 ??��
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                    os.makedirs(output_dir, exist_ok=True)
                
                # 2. ?�막 추적 ?��?(JSON) ??��
                from core.auto_tracker import TRACKER_FILE
                if os.path.exists(TRACKER_FILE): 
                    os.remove(TRACKER_FILE)
                
                # 3. 감시 ?�원(CloudSyncManager)??머릿??메모�???비우�?
                if hasattr(self, '_cloud_sync_manager'):
                    mgr = self._cloud_sync_manager
                    mgr._size_cache.clear()   # ?�일 ?�기 기억 ??��
                    mgr._in_flight.clear()    # ?�재 ?�업 �?목록 ??��
                    if hasattr(mgr.tracker, '_data'):
                        mgr.tracker._data.clear() # 추적�??��? ?�이????��
                
                get_logger().log("?�� 모든 캐시?� 감시??메모리�? 리셋?�었?�니??")
                QMessageBox.information(self, "?�료", "?���?캐쉬 �??�동 모드 기록??초기?�되?�습?�다.")
                self.show_home() # ?�면 갱신
                
            except Exception as e:
                get_logger().log(f"??캐시 ??�� �??�류 발생: {e}")
                QMessageBox.warning(self, "?�류", f"??�� �??�류가 발생?�습?�다: {e}")

    # ?�� [?�심] ?�료 (100%) ???�?�머 중단 �?최종 ?�벨 ?�정
    def update_queue_header(self, current: int, total: int, pct: int, eta_str: str = ""):
        self._current_file_idx = current
        self._total_files = total
        
        if pct == 100:
            if hasattr(self, '_live_timer'):
                self._live_timer.stop()
            self.queue_header_lbl.setText(f"?�� 처리???�일 리스??({total} / {total} ?�료) - 100% ?�료")

    def _connect_signals(self):
        self._sig_show_home.connect(self.show_home)
        self._sig_append_segments.connect(self._do_append_segments)
        self._sig_update_status.connect(self._do_update_status)
        self._sig_open_editor.connect(self._do_open_editor)
        self._sig_set_vad_segments.connect(lambda v: self._editor_widget.set_vad_segments(v) if self._editor_widget else None)
        self._sig_update_queue.connect(self.update_queue_status) 
        self._sig_update_queue_header.connect(self.update_queue_header)
        # ?�� [?�규 추�?] 무전기�? ?�리�?_do_auto_start_pipeline???�행?�도�??�결?�니??
        self._sig_auto_start_pipeline.connect(self._do_auto_start_pipeline)

    def _open_recent(self, folder):
        if not os.path.exists(folder):
            if not ensure_nas_mounted(folder):
                QMessageBox.warning(self, "?�류", f"?�더�?찾을 ???�습?�다:\n{folder}")
                return
        
        set_last_folder(folder)
        self._add_recent_folder(folder) 
        
        dlg = FolderDialog(folder, self)
        if dlg.exec() and dlg.selected_files:
            self.backend.start_pipeline(dlg.selected_files, folder=folder)

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible: self._log_content.show(); self._log_toggle_btn.setText("???��???로그 ?�기�?)
        else: self._log_content.hide(); self._log_toggle_btn.setText("???��???로그 보기")

        for container in getattr(self, '_preview_containers', []):
            try: container.setVisible(not self._log_visible)
            except Exception: pass

        # [v01.00.04] 로그 ?�릴 ??최근 ?�더 1개만, ?�힐 ??최�? 3�??�시
        for i, btn in enumerate(getattr(self, '_recent_buttons', [])):
            try:
                btn.setVisible(i == 0 if self._log_visible else True)
            except Exception:
                pass

        settings = self._load_local_settings(); settings["show_terminal_log"] = self._log_visible; self._save_local_settings(settings)
        if self._editor_widget and hasattr(self._editor_widget, 'set_terminal_visible_layout'): self._editor_widget.set_terminal_visible_layout(self._log_visible)
        QTimer.singleShot(10, self._refresh_video)

    def _refresh_video(self):
        ed = self._editor_widget
        if ed and hasattr(ed, 'video_player'): vp = ed.video_player; vp.resizeEvent(None)

    def append_log(self, msg: str):
        self.log_text.append(msg); self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def show_home(self):
        self.stack.setCurrentIndex(0)
        
        # ?�� [?�심 버그 ?�정] ?�림창이 ?�있?????�이??GC가 메모리�? 
        # 강제 ??��?�여 발생?�는 C++ 충돌(SIGABRT) 방�?
        if self._editor_widget:
            self._trash_bin = getattr(self, '_trash_bin', [])
            self._trash_bin.append(self._editor_widget)
            if len(self._trash_bin) > 3:
                self._trash_bin.pop(0) # ?�래??메모리�????�전?�게 비우�?
                
        self._editor_widget = None
        self._build_home_content()

    def request_show_home(self): self._sig_show_home.emit()
    def append_segments_to_editor(self, segments: list[dict]): self._sig_append_segments.emit(segments)
    def update_editor_status(self, c_idx: int, t_total: int): self._sig_update_status.emit(c_idx, t_total)
    
    def _do_append_segments(self, segments: list[dict]):
        if self._editor_widget: self._editor_widget.append_segments(segments)

    def _do_update_status(self, c_idx: int, t_total: int):
        if self._editor_widget:
            if hasattr(self._editor_widget, 'update_progress'): self._editor_widget.update_progress(c_idx, t_total)
            else:
                if c_idx < t_total: self._editor_widget.update_status(f"??처리�?.. ({c_idx:02d}/{t_total:02d}�?�?��)")
                else: self._editor_widget.update_status("???�성 ?�료! 마음�??�집?�세??")

    def open_editor_for_file(self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
        self._sig_open_editor.emit(target_file, on_save, on_start, on_prev, on_exit, is_batch)

    def _do_open_editor(self, target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
        self._on_save_cb  = on_save; self._on_start_cb = on_start; self._on_prev_cb  = on_prev; self._on_exit_cb  = on_exit
        self._target_file = target_file
        self._init_editor(target_file, is_batch)

    def _btn(self, text, desc, cmd):
        w = QWidget(); w.setObjectName("MenuButton")
        w.setStyleSheet(f"QWidget#MenuButton {{ background-color: {config.BG2}; border: 1px solid {config.BG3}; border-radius: 8px; }} QWidget#MenuButton:hover {{ background-color: #333333; border: 2px solid #4AFF80; }}")
        w.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(w); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(4) 
        lbl = QLabel(text); lbl.setStyleSheet(f"color: {config.FG}; font-size: 14px; font-weight: bold; border: none; background: transparent;")
        lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(lbl)
        if desc:
            sub = QLabel(desc); sub.setStyleSheet(f"color: {config.FG2}; font-size: 11px; border: none; background: transparent;")
            sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents); layout.addWidget(sub)
        def _on_w_click(e):
            if e.button() == Qt.MouseButton.LeftButton: cmd(); e.accept()
        w.mousePressEvent = _on_w_click
        return w

    def _dummy_action(self): pass

    def _get_nas_folders(self) -> list:
        nas_path = get_nas_path()
        if not nas_path: return []
        if nas_path.startswith("smb://"):
            clean = nas_path.replace("smb://", "")
            parts = clean.split("/")
            share = parts[1] if len(parts) > 1 else "video"
            local_path = f"/Volumes/{share}"
        else:
            local_path = nas_path
            
        if not os.path.exists(local_path): return []
        try:
            folders = []
            for f in os.listdir(local_path):
                full_path = os.path.join(local_path, f)
                if not f.startswith('.') and os.path.isdir(full_path): folders.append((f, full_path))
            return sorted(folders)
        except Exception: return []

    def _open_nas_root(self):
        nas_url = get_nas_path()
        if not nas_url:
            QMessageBox.warning(self, "?�류", "NAS 경로가 ?�정?��? ?�았?�니?? ?�정 메뉴�??�인?�세??")
            return
        if not ensure_nas_mounted(nas_url):
            QMessageBox.warning(self, "?�류", "NAS 마운?�에 ?�패?�습?�다.")
            return
            
        if nas_url.startswith("smb://"):
            clean = nas_url.replace("smb://", "")
            share = clean.split("/")[1] if len(clean.split("/")) > 1 else "video"
            local_path = f"/Volumes/{share}"
        else:
            local_path = nas_url
            
        dlg = FolderDialog(local_path, self)
        if dlg.exec() and dlg.selected_files: 
            self._add_recent_folder(local_path)
            self.backend.start_pipeline(dlg.selected_files, folder=local_path)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "?�더 ?�택", get_last_folder() or os.path.expanduser("~"))
        if not folder or not ensure_nas_mounted(folder): return
        set_last_folder(folder)
        self._add_recent_folder(folder) 
        
        dlg = FolderDialog(folder, self)
        if dlg.exec() and dlg.selected_files: self.backend.start_pipeline(dlg.selected_files, folder=folder)

    def select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "?�일 ?�택", get_last_folder() or os.path.expanduser("~"), "Media/SRT Files (*.mp4 *.mov *.MOV *.MP4 *.wav *.m4a *.m2a *.mp3 *.aac *.srt)")
        if not paths: return
        
        folder = os.path.dirname(paths[0])
        set_last_folder(folder)
        self._add_recent_folder(folder)
        
        video_files = [p for p in paths if not p.endswith(".srt")]
        srt_files = [p for p in paths if p.endswith(".srt")]
        if srt_files: self._open_srt_in_editor(srt_files[0])
        elif video_files: self.backend.start_pipeline(video_files)

    def open_editor_directly(self):
        path, _ = QFileDialog.getOpenFileName(self, "SRT ?�일 ?�택", get_last_folder() or os.path.expanduser("~"), "SRT Files (*.srt)")
        if path: 
            folder = os.path.dirname(path)
            set_last_folder(folder)
            self._add_recent_folder(folder)
            self._open_srt_in_editor(path)

    def start_icloud_sync(self):
        self.backend.start_pipeline([], is_icloud=True)

    def _show_path_settings(self):
        """[경로?�정] 버튼 ?�릭 ???��??�는 ?�정 ?�이?�로�?""
        dlg = QDialog(self)
        dlg.setWindowTitle("경로?�정")
        dlg.setMinimumWidth(450)
        dlg.setStyleSheet(f"background-color: {config.BG}; color: {config.FG};")
        
        layout = QVBoxLayout(dlg)
        
        layout.addWidget(QLabel("NAS 루트 경로 (?? smb://DDuDDu_NAS._smb._tcp.local/video):"))
        nas_input = QLineEdit(get_nas_path())
        nas_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;")
        layout.addWidget(nas_input)
        
        layout.addWidget(QLabel("iCloud ?�기??경로:"))
        icloud_input = QLineEdit(get_icloud_path())
        icloud_input.setStyleSheet(f"background: {config.BG2}; border: 1px solid {config.BG3}; padding: 4px;")
        layout.addWidget(icloud_input)
        
        # ?�� [?�심] iCloud 체크박스
        icloud_auto_chk = QCheckBox("?�동감�? �?처리?�성??iCloud")
        icloud_auto_chk.setStyleSheet(f"color: {config.FG}; font-weight: bold; margin-top: 10px;")
        icloud_auto_chk.setChecked(get_icloud_auto_detect())
        layout.addWidget(icloud_auto_chk)
        
        # ?�� [?�심] NAS 체크박스
        nas_auto_chk = QCheckBox("?�동감�? �?처리?�성??NAS")
        nas_auto_chk.setStyleSheet(f"color: {config.FG}; font-weight: bold; margin-top: 5px;")
        nas_auto_chk.setChecked(get_nas_auto_detect())
        layout.addWidget(nas_auto_chk)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton("?�??)
        btn_save.setStyleSheet(f"background: {config.ACCENT}; color: #000; font-weight: bold; padding: 6px;")
        
        # ?�� [?�여?�기 ?�벽 ?�정] ???�페?�스 ?�용 문제�??�결?�습?�다.
        def save_all():
            set_nas_path(nas_input.text())
            set_icloud_path(icloud_input.text())
            
            # 1. iCloud ?�정 ?�??�??�치독 ?�어
            icl_checked = icloud_auto_chk.isChecked()
            set_icloud_auto_detect(icl_checked)
            self._is_icloud_auto_mode = icl_checked
            
            if self._is_icloud_auto_mode:
                self._cloud_sync_manager.dropzone_path = icloud_input.text()
                self._cloud_sync_manager.start()
            else:
                self._cloud_sync_manager.stop()
                
            # 2. NAS ?�정 ?�??
            nas_checked = nas_auto_chk.isChecked()
            set_nas_auto_detect(nas_checked)
            self._is_nas_auto_mode = nas_checked
            
            get_logger().log(f"?�️ ?�정 변�?- iCloud ?�동: {icl_checked} / NAS ?�동: {nas_checked}")
            
            dlg.accept()
            self.show_home()
            
        btn_save.clicked.connect(save_all)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        
        dlg.exec()

    def _quick_exit(self):
        if self.backend: self.backend.stop()
        QApplication.quit()

    def _parse_srt_file(self, srt_path: str) -> list[dict]:
        import re
        segments = []
        if not os.path.exists(srt_path): return segments
        content = ""
        for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
            try:
                with open(srt_path, "r", encoding=enc) as f: content = f.read(); break
            except UnicodeDecodeError: continue
        if not content: return segments
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        pattern = re.compile(r'(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{2,3})\n(.*?)(?=\n(?:\s*\d+\s*\n)?\s*\d{2}:\d{2}:\d{2}[,.]|\Z)', re.DOTALL)
        for m in pattern.finditer(content):
            try:
                def srt_to_sec(ts): h, mn, s = ts.replace(',', '.').split(':'); return int(h)*3600 + int(mn)*60 + float(s)
                segments.append({"start": srt_to_sec(m.group(1)), "end": srt_to_sec(m.group(2)), "text": m.group(3).strip()})
            except Exception: continue
        return segments

    def _open_srt_in_editor(self, srt_path: str):
        segments = self._parse_srt_file(srt_path)
        from ui.editor_widget import EditorWidget
        self._remove_old_editor()
        base_path = os.path.splitext(srt_path)[0]
        media_extensions = ['.mp4', '.mov', '.MOV', '.MP4', '.wav', '.m4a', '.m2a', '.mp3', '.aac']
        media_path = next((base_path + ext for ext in media_extensions if os.path.exists(base_path + ext)), srt_path)

        editor = EditorWidget(video_name=os.path.basename(srt_path), segments=segments, media_path=media_path, parent=self)

        def _save_and_home(segs=None):
            if segs is not None: self._save_srt(srt_path, segs)
            QTimer.singleShot(0, self.show_home)

        def _on_manual_save(segs):
            self._save_srt(srt_path, segs)                          # ?�제 .srt ?�??
            self._backup_nums[srt_path] = self._backup_nums.get(srt_path, 1) + 1  # 번호 증�?
            self._backup_srt(srt_path, segs)                        # ??번호�?백업

        editor.sig_save.connect(lambda segs: self._save_srt(srt_path, segs))
        editor.sig_auto_save.connect(lambda segs: self._save_srt(srt_path, segs))
        editor.sig_next.connect(_save_and_home)
        # ?�� [?�정 ?? 복잡??로직??지?�고 깔끔?�게 창을 ?�도�??�도?�니??
        editor.sig_exit.connect(lambda _: self.close())
        
        self._editor_widget = editor
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        self.stack.insertWidget(1, editor); self.stack.setCurrentIndex(1)

    def _save_srt(self, srt_path: str, segments: list[dict]):
        try:
            # ?�� [?�기 ?�정] ?�날 ?�름??srt_writer�????�름?�로 바꿔주세??
            # ?�정 ?? from srt_writer import save_srt
            from core.subtitle_engine import save_srt
            save_srt(segments, srt_path, apply_offset=False)
            get_logger().log(f"??{os.path.basename(srt_path)} ?�???�료")
        except Exception as e: 
            get_logger().log(f"??SRT ?�???�패: {e}")

    def _backup_srt(self, srt_path: str, segments: list[dict]):
        """?�막백업 ?�더???�재 백업 ?�롯?�로 ?�??(??��?�기)."""
        try:
            from core.subtitle_engine import save_srt
            import datetime
            base = os.path.splitext(os.path.basename(srt_path))[0]
            date_str = datetime.date.today().strftime("%Y%m%d")
            num = self._backup_nums.get(srt_path, 1)
            backup_dir = os.path.join(os.path.dirname(srt_path), "?�막백업")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{base}_{date_str}_{num:03d}.srt")
            save_srt(segments, backup_path, apply_offset=False)
        except Exception as e:
            get_logger().log(f"?�️ 백업 ?�???�패: {e}")

    def closeEvent(self, event):
        # ?�디?��? ?�려 ?�을 ?�만 ?�???��? ?�인
        if hasattr(self, "_editor_widget") and self._editor_widget and self.stack.currentIndex() == 1:
            has_dirty = (hasattr(self._editor_widget, 'sm') and self._editor_widget.sm.is_dirty)

            if has_dirty:
                # [v01.00.04] editor_pipeline._on_prev/exit?� ?�일?????�니??취소 ?�이?�로�?
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("종료 ?�인")
                msg_box.setText("?�정???�용???�?�하?�겠?�니�?")
                msg_box.setStandardButtons(
                    QMessageBox.StandardButton.Yes |
                    QMessageBox.StandardButton.No  |
                    QMessageBox.StandardButton.Cancel
                )
                msg_box.button(QMessageBox.StandardButton.Yes).setText("??)
                msg_box.button(QMessageBox.StandardButton.No).setText("?�니??)
                msg_box.button(QMessageBox.StandardButton.Cancel).setText("취소")
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

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

        # 리소???�리 �?강제 종료
        get_logger().clear_ui_callback(); self.blockSignals(True)
        if self._editor_widget and hasattr(self._editor_widget, 'video_player'):
            try:
                vp = self._editor_widget.video_player
                if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                if hasattr(vp, '_worker') and vp._worker:
                    vp._worker.stop(); vp._worker.wait(200)
            except Exception: pass
        if self.backend: self.backend.stop()
        QTimer.singleShot(100, lambda: os._exit(0))
    def _remove_old_editor(self):
        old = self.stack.widget(1)
        if old:
            # 1. ?�디???��? ?�?�머 �??�레?�어 ?��?
            if hasattr(old, '_cleanup'):
                try: old._cleanup()
                except Exception: pass
                
            if hasattr(old, 'video_player'):
                try:
                    vp = old.video_player
                    if hasattr(vp, '_ui_timer'): vp._ui_timer.stop()
                    if hasattr(vp, 'audio_player'): vp.audio_player.stop()
                    if hasattr(vp, '_worker') and getattr(vp, '_worker', None): 
                        vp._worker.stop(); vp._worker.wait(200)
                except Exception: pass
            
            # 2. ?�면?�서 분리
            self.stack.removeWidget(old)
            old.hide()
            
            # 3. ?�� [?�전 ?��??? 즉시 ??��?��? ?�고 보�??�여 메모�??��? 방�?
            if not hasattr(self, '_trash_bin'):
                self._trash_bin = []
            self._trash_bin.append(old)
            
            if len(self._trash_bin) > 3:
                stale_widget = self._trash_bin.pop(0)
                stale_widget.deleteLater()

    def _init_editor(self, target_file: str, is_batch=False):
        """??��?�었???�디??초기???�수 복구"""
        from ui.editor_widget import EditorWidget
        vname = os.path.basename(target_file)
        self._remove_old_editor()
        
        editor = EditorWidget(video_name=vname, segments=[], media_path=target_file, parent=self)
        
        # ?�� [?�심] ?�이?�라?�에???�식?�도�?is_auto_start 변?��? ?�용?�니??
        editor.is_auto_start = is_batch 
        
        self._editor_widget = editor 
        
        if is_batch:
            if hasattr(editor, 'update_status'):
                editor.update_status("?? AI ?�진???�작?�었?�니?? (?�동 감�?)")

        # ?�그???�결
        def safe_home(*args): QTimer.singleShot(0, self.show_home)
        def force_exit_app(*args): self.close()
        def handle_prev(*args):
            if self._on_prev_cb: self._on_prev_cb()
            safe_home()

        if self._on_start_cb: editor.sig_start.connect(self._on_start_cb)
        editor.sig_prev.connect(handle_prev)
        editor.sig_exit.connect(force_exit_app)
        
        if self._on_save_cb: 
            editor.sig_next.connect(self._on_save_cb)
        else: 
            editor.sig_next.connect(safe_home)
            
        editor.sig_save.connect(lambda segs: self._save_srt(target_file, segs))
        editor.sig_auto_save.connect(lambda segs: self._save_srt(target_file, segs))

        if hasattr(editor, 'set_terminal_visible_layout'): 
            editor.set_terminal_visible_layout(self._log_visible)
        self.stack.insertWidget(1, editor)
        self.stack.setCurrentIndex(1)
        from ui.editor_widget import EditorWidget
        vname = os.path.basename(target_file)
        self._remove_old_editor()
        editor = EditorWidget(video_name=vname, segments=[], media_path=target_file, parent=self)
        
        # ?�� [교정] pipeline.py?�서 체크?�는 변?�명??is_auto_start�?변경합?�다.
        editor.is_auto_start = is_batch 
        
        self._editor_widget = editor
        
        if is_batch:
            if hasattr(editor, 'update_status'):
                editor.update_status("?? AI ?�진???�작?�었?�니?? (?�동 감�?)")

        def safe_home(*args): QTimer.singleShot(0, self.show_home)
        def force_exit_app(*args): self.close()
        def handle_prev(*args):
            if self._on_prev_cb: self._on_prev_cb()
            safe_home()

        if self._on_start_cb: editor.sig_start.connect(self._on_start_cb)
        editor.sig_prev.connect(handle_prev)
        editor.sig_exit.connect(force_exit_app)
        
        if self._on_save_cb: 
            editor.sig_next.connect(self._on_save_cb)
        else: 
            editor.sig_next.connect(safe_home)
            
        editor.sig_save.connect(lambda segs: self._save_srt(target_file, segs))
        editor.sig_auto_save.connect(lambda segs: self._save_srt(target_file, segs))

        self._editor_widget = editor
        if hasattr(editor, 'set_terminal_visible_layout'): editor.set_terminal_visible_layout(self._log_visible)
        self.stack.insertWidget(1, editor); self.stack.setCurrentIndex(1)
