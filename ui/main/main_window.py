# Version: 03.01.18
# Phase: PHASE2
"""
ui/main/main_window.py
MainWindow — 메인 윈도우 클래스 (시그널 정의 · UI 빌드 · 시그널 연결)
Mixin 상속: HomeUI · EditorLifecycle · Workspace · Queue · Project · Cloud · FileOps · Signals
"""
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSplitter, QPushButton,
)
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon

from ui.queue_widget import QueueMixin
from ui.cloud_ui import CloudUIMixin
from ui.home_ui import HomeUIMixin
from ui.menu_bar import GlobalMenuBar, StatusRail
from ui.editor.editor_lifecycle import EditorLifecycleMixin
from ui.main.bottom_work_panel import BottomWorkPanel
from ui.main.workspace_stack import MainWorkspaceStack
from ui.sidebar.project_sidebar_widget import ProjectSidebarWidget
from ui.style import button_style, label_style, line_icon

from ui.project.project_panel import ProjectUIMixin
from ui.project.workspace_restore import WorkspaceMixin

from ui.main.main_file_ops import FileOpsMixin
from ui.main.main_signals import SignalHandlersMixin

import config
from logger import get_logger
from core.cloud_sync import CloudSyncManager
from core.path_manager import (
    get_icloud_path, get_nas_path, get_local_path, ensure_nas_mounted,
    get_icloud_auto_detect, get_nas_auto_detect, get_nas_excluded_folders,
)
from core.settings import load_settings, save_settings


class MainWindow(
    HomeUIMixin,
    EditorLifecycleMixin,
    WorkspaceMixin,
    QueueMixin,
    ProjectUIMixin,
    CloudUIMixin,
    FileOpsMixin,
    SignalHandlersMixin,
    QMainWindow,
):
    _sig_show_home           = pyqtSignal()
    _sig_append_segments     = pyqtSignal(list)
    _sig_update_status       = pyqtSignal(int, int)
    _sig_open_editor         = pyqtSignal(str, object, object, object, object, bool)
    _sig_set_vad_segments    = pyqtSignal(list)
    _sig_update_queue        = pyqtSignal(int, str, str, str, str)
    _sig_update_queue_header = pyqtSignal(int, int, int, str)
    _sig_auto_start_pipeline = pyqtSignal(list)
    _sig_load_multiclip_waveform = pyqtSignal(list)
    _sig_set_recog_zone      = pyqtSignal(float, float)
    _sig_set_recog_progress  = pyqtSignal(float)
    _sig_clear_editor        = pyqtSignal()
    _sig_restart_multiclip   = pyqtSignal(list, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎬 AI Subtitle Studio")
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "icons", "app_icon.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(600, 500)
        self.recent_folders = []
        self.add_recent_folder_callback = None
        self._editor_widget = None
        self.backend = None
        self.backend_fast = None
        self._backup_nums = {}
        self._preview_containers = []
        self._expected_seconds = {}
        self._file_start_times = {}
        self._current_file_idx = 1
        self._total_files = 1
        self._is_auto_pipeline = False
        self._auto_processing_active = False
        self._current_project_path = None
        self._project_boundary_times = []
        self._dashboard_mode = "dashboard"
        self._current_work_mode = "editor"
        self._project_panel_visible = True
        self._unified_dashboard = True
        self._on_save_cb = None
        self._on_start_cb = None
        self._on_prev_cb = None
        self._on_exit_cb = None
        self._local_llm_models = []
        self._required_model_check_done = False
        self._post_completion_idle_enabled = False
        self._post_completion_idle_ms = 600_000

        settings = load_settings()
        self._auto_start_on = settings.get("auto_start_enabled", True)
        self._is_icloud_auto_mode = get_icloud_auto_detect()
        self._is_nas_auto_mode = get_nas_auto_detect()

        self._live_timer = QTimer()
        self._live_timer.timeout.connect(self._update_live_queue_header)
        self._post_completion_idle_timer = QTimer(self)
        self._post_completion_idle_timer.setSingleShot(True)
        self._post_completion_idle_timer.timeout.connect(self._on_post_completion_idle_timeout)

        self._build_ui()
        self._connect_signals()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        QTimer.singleShot(0, self._warmup_local_llm_models)
        QTimer.singleShot(900, self._check_required_models_on_startup)

        self._cloud_sync_manager = CloudSyncManager(
            get_icloud_path(), self._on_files_detected, self._is_app_busy
        )
        self._nas_sync_manager = CloudSyncManager(
            get_local_path(get_nas_path()), self._on_files_detected, self._is_app_busy,
            mode="nas", scan_interval=60, stable_seconds=300, exclude_callback=get_nas_excluded_folders
        )
        if self._auto_start_on and getattr(self, "_is_icloud_auto_mode", False):
            self._cloud_sync_manager.start()
        elif self._auto_start_on and getattr(self, "_is_nas_auto_mode", False):
            nas_path = get_nas_path()
            if ensure_nas_mounted(nas_path):
                self._nas_sync_manager.dropzone_path = get_local_path(nas_path)
                self._nas_sync_manager.start()

    # ── UI 빌드 ──────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)
        self.stack = MainWorkspaceStack()

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setHandleWidth(2)
        workspace_splitter.setStyleSheet("QSplitter::handle { background: #0F1518; width: 2px; }")
        main_layout.addWidget(workspace_splitter, stretch=1)

        self.home_page = ProjectSidebarWidget()
        workspace_splitter.addWidget(self.home_page)
        self.status_rail = StatusRail(self.home_page)
        self.saved_status_label = QLabel("", self.home_page)
        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.saved_status_label.setStyleSheet("color: #A9B0B7; font-size: 11px; background: transparent;")
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label(is_dirty=False)
        self.sidebar_settings_label = QLabel("", self.home_page)
        self.sidebar_settings_label.setWordWrap(True)
        self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()

        self.editor_page = QWidget()
        editor_placeholder = QVBoxLayout(self.editor_page)
        editor_placeholder.setContentsMargins(32, 32, 32, 32)
        editor_placeholder.setSpacing(10)
        title = QLabel("작업을 선택하세요")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(label_style("normal", 20, bold=True))
        subtitle = QLabel("새 작업은 파일, 폴더, 프로젝트 중 하나를 선택해서 시작합니다.")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(label_style("muted", 12))
        quick_row = QHBoxLayout()
        quick_row.setSpacing(10)
        btn_file = self._empty_quick_button("파일", "file", self.select_files)
        btn_folder = self._empty_quick_button("폴더", "folder", self.select_folder)
        btn_project = self._empty_quick_button("프로젝트", "project", self._open_project)
        quick_row.addStretch()
        quick_row.addWidget(btn_file)
        quick_row.addWidget(btn_folder)
        quick_row.addWidget(btn_project)
        quick_row.addStretch()
        editor_placeholder.addStretch()
        editor_placeholder.addWidget(title)
        editor_placeholder.addWidget(subtitle)
        editor_placeholder.addLayout(quick_row)
        editor_placeholder.addStretch()
        self.stack.addWidget(self.editor_page)
        workspace_splitter.addWidget(self.stack)
        workspace_splitter.setSizes([210, 1465])
        self.workspace_splitter = workspace_splitter

        self.global_menu_bar = GlobalMenuBar(self)
        self.global_menu_bar.set_status_rail(self.status_rail)
        main_layout.addWidget(self.global_menu_bar)

        self.bottom_work_panel = self._build_log_panel()
        main_layout.addWidget(self.bottom_work_panel)
        self.show_home()

    def _build_log_panel(self):
        panel = BottomWorkPanel(self)

        self._log_content = panel.log_content
        self._log_toggle_btn = panel.log_toggle_btn
        self.log_splitter = panel.log_splitter
        self.log_text = panel.log_text
        self.bottom_right_stack = panel.bottom_right_stack
        self.bottom_queue_page = panel.queue_panel
        self.bottom_roughcut_page = panel.roughcut_panel
        self.queue_header_lbl = panel.queue_header_lbl
        self.queue_table = panel.queue_table
        self.roughcut_bottom_header_lbl = panel.roughcut_bottom_header_lbl
        self.roughcut_bottom_host = panel.roughcut_bottom_host
        self.roughcut_bottom_host_layout = panel.roughcut_bottom_host_layout

        self._log_visible = panel.log_visible

        # 큐 애니메이션
        self._queue_anim_frames = ["📑", "📄", "📃", "📝"]
        self._queue_anim_idx = 0
        self._queue_anim_timer = QTimer(self)
        self._queue_anim_timer.setInterval(250)
        self._queue_anim_timer.timeout.connect(self._animate_queue_status)
        self._queue_anim_timer.start()

        return panel

    def _set_roughcut_bottom_widget(self, widget: QWidget):
        panel = getattr(self, "bottom_work_panel", None)
        if widget is None or panel is None:
            return
        panel.set_roughcut_widget(widget)

    def _show_bottom_queue_table(self):
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.show_queue_table()

    def _show_bottom_roughcut_table(self):
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.show_roughcut_table()

    def _empty_quick_button(self, text, icon_name, slot):
        btn = QPushButton(text)
        btn.setIcon(line_icon(icon_name, "#A9B0B7", 24))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(button_style("toolbar", font_size="12px", padding="8px 16px"))
        btn.clicked.connect(slot)
        return btn

    # ── 시그널 연결 ──────────────────────────────────────
    def _connect_signals(self):
        self._sig_show_home.connect(self.show_home)
        self._sig_append_segments.connect(self._do_append_segments)
        self._sig_update_status.connect(self._do_update_status)
        self._sig_open_editor.connect(self._do_open_editor)
        self._sig_set_vad_segments.connect(self._on_vad_segments)
        self._sig_update_queue.connect(self.update_queue_status)
        self._sig_update_queue_header.connect(self.update_queue_header)
        self._sig_auto_start_pipeline.connect(self._do_auto_start_pipeline)
        self._sig_load_multiclip_waveform.connect(self._do_load_multiclip_waveform)
        self._sig_set_recog_zone.connect(self._on_recog_zone)
        self._sig_set_recog_progress.connect(self._on_recog_progress)
        self._sig_clear_editor.connect(self._do_clear_editor)
        self._sig_restart_multiclip.connect(self._do_restart_multiclip)

    # ── 홈 / 에디터 전환 ────────────────────────────────
    def show_home(self):
        self._stop_post_completion_idle_timer()
        self._reset_transient_multiclip_state()
        self.stack.setCurrentIndex(0)
        if hasattr(self, "_show_bottom_queue_table"):
            self._show_bottom_queue_table()
        if self._editor_widget and not getattr(self, "_unified_dashboard", False):
            self._trash_bin = getattr(self, "_trash_bin", [])
            self._trash_bin.append(self._editor_widget)
            if len(self._trash_bin) > 3:
                self._trash_bin.pop(0)
            self._editor_widget = None
        self._build_home_content()

    def _reset_transient_multiclip_state(self):
        for attr, value in (
            ("_multiclip_files", []),
            ("_multiclip_boundaries", []),
            ("_accumulated_vad", []),
            ("_project_boundary_times", []),
            ("_reuse_clip_indices", set()),
        ):
            try:
                setattr(self, attr, value.copy() if hasattr(value, "copy") else value)
            except Exception:
                pass

    def eventFilter(self, obj, event):
        try:
            if self._is_user_activity_event(event):
                self._reset_post_completion_idle_timer()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _is_user_activity_event(self, event) -> bool:
        if not getattr(self, "_post_completion_idle_enabled", False):
            return False
        return event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.TouchBegin,
            QEvent.Type.TouchUpdate,
            QEvent.Type.TouchEnd,
        }

    def _start_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = True
        self._post_completion_idle_timer.start(self._post_completion_idle_ms)

    def _reset_post_completion_idle_timer(self):
        if getattr(self, "_post_completion_idle_enabled", False):
            self._post_completion_idle_timer.start(self._post_completion_idle_ms)

    def _stop_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = False
        try:
            self._post_completion_idle_timer.stop()
        except Exception:
            pass

    def _on_post_completion_idle_timeout(self):
        self._post_completion_idle_enabled = False
        backend = getattr(self, "backend", None)
        if backend is not None and hasattr(backend, "_action_state") and hasattr(backend, "_edit_event"):
            try:
                backend._action_state[0] = "exit"
                backend._edit_event.set()
                return
            except Exception:
                pass
        self.show_home()

    # ── 로그 토글 ────────────────────────────────────────
    def _apply_log_visible(self, visible: bool):
        self._log_visible = bool(visible)
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.set_log_visible(self._log_visible)
        if self._editor_widget and hasattr(self._editor_widget, "set_terminal_visible_layout"):
            self._editor_widget.set_terminal_visible_layout(self._log_visible)
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()

    def _toggle_log(self):
        self._apply_log_visible(not self._log_visible)
        if hasattr(self, "show_home") and self.stack.currentWidget() is self.home_page:
            self.show_home()
        for c in getattr(self, "_preview_containers", []):
            try:
                c.setVisible(not self._log_visible)
            except Exception:
                pass
        for i, btn in enumerate(getattr(self, "_recent_buttons", [])):
            try:
                btn.setVisible(i == 0 if self._log_visible else True)
            except Exception:
                pass
        try:
            settings = load_settings()
            settings["show_terminal_log"] = self._log_visible
            save_settings(settings)
        except Exception as e:
            get_logger().log(f"⚠️ 터미널 로그 표시 설정 저장 실패: {e}")
        QTimer.singleShot(10, self._refresh_video)

    def sync_menu_from_editor(self, editor=None):
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.sync_from_editor(editor)

    def open_help_dialog(self):
        from ui.help.help_dialog import HelpDialog

        dialog = HelpDialog(self)
        dialog.exec()

    def _refresh_video(self):
        if self._editor_widget and hasattr(self._editor_widget, "video_player"):
            self._editor_widget.video_player.resizeEvent(None)
