# Version: 03.14.33
# Phase: PHASE2
"""
ui/main/main_window.py
MainWindow — 메인 윈도우 클래스 (시그널 정의 · UI 빌드 · 시그널 연결)
Mixin 상속: HomeUI · EditorLifecycle · Workspace · Queue · Project · Cloud · FileOps · Signals
"""
import os
import datetime
import time
import threading

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSplitter, QPushButton,
)
from PyQt6.QtCore import QDateTime, QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon

from ui.queue_widget import QueueMixin
from ui.cloud_ui import CloudUIMixin
from ui.home_ui import HomeUIMixin
from ui.menu_bar import GlobalMenuBar, StatusRail
from ui.editor.editor_lifecycle import EditorLifecycleMixin
from ui.main.bottom_work_panel import BottomWorkPanel
from ui.main.workspace_stack import MainWorkspaceStack
from ui.sidebar.project_sidebar_widget import ProjectSidebarWidget
from ui.log.terminal_log_widget import TerminalLogWidget
from ui.responsive_profile import responsive_profile_for_size, responsive_sidebar_width
from ui.style import button_style, label_style, line_icon

from ui.project.project_panel import ProjectUIMixin
from ui.project.project_session_runtime import detach_project_session, set_project_boundary_rows
from ui.project.workspace_restore import WorkspaceMixin
from ui.queue.queue_formatting import build_queue_header_payload

from ui.main.main_file_ops import FileOpsMixin
from ui.main.app_command_bridge import dispatch_app_command, handle_app_command_signal
from ui.main.main_nonfatal import call_nonfatal_ui_step, run_nonfatal_ui_step
from ui.main.main_runtime_cleanup import MainRuntimeCleanupMixin
from ui.main.main_signals import SignalHandlersMixin

from core.runtime.logger import get_logger
from core.runtime import config
from core.runtime.memory_manager import RuntimeMemoryManager
from core.runtime.multi_process import RuntimeResourceCoordinator
from core.personalization.idle_trainer import FOREGROUND_ACTIVITY_HOLD_MS, PersonalizationIdleTrainer
from core.cloud_sync import CloudSyncManager
from core.path_manager import (
    get_icloud_path, get_nas_path, get_local_path, ensure_nas_mounted,
    get_icloud_auto_detect, get_nas_auto_detect, get_nas_excluded_folders,
)
from core.settings import load_settings, save_settings

MAIN_PANEL_GAP = 3


class MainWindow(
    HomeUIMixin,
    EditorLifecycleMixin,
    WorkspaceMixin,
    QueueMixin,
    ProjectUIMixin,
    CloudUIMixin,
    FileOpsMixin,
    MainRuntimeCleanupMixin,
    SignalHandlersMixin,
    QMainWindow,
):
    _sig_show_home           = pyqtSignal()
    _sig_append_segments     = pyqtSignal(list)
    _sig_append_segments_ready = pyqtSignal(list, object)
    _sig_update_status       = pyqtSignal(int, int)
    _sig_open_editor         = pyqtSignal(str, object, object, object, object, bool)
    _sig_open_editor_ready   = pyqtSignal(str, object, object, object, object, bool, object)
    _sig_set_vad_segments    = pyqtSignal(list)
    _sig_update_queue_payload = pyqtSignal(object)
    _sig_update_queue_header_payload = pyqtSignal(object)
    _sig_auto_start_pipeline = pyqtSignal(list)
    _sig_prepare_processing_editor = pyqtSignal(str, object)
    _sig_load_multiclip_waveform = pyqtSignal(list)
    _sig_set_recog_zone      = pyqtSignal(float, float)
    _sig_set_recog_progress  = pyqtSignal(float)
    _sig_preview_stt_segments = pyqtSignal(list)
    _sig_preview_processing_segments = pyqtSignal(object)
    _sig_clear_editor        = pyqtSignal()
    _sig_restart_multiclip   = pyqtSignal(list, object)
    _sig_refresh_cut_boundary_placeholder = pyqtSignal()
    _sig_preview_cut_boundary_topicless_segments = pyqtSignal(list)
    _sig_set_cut_boundary_scan_active = pyqtSignal(bool)
    _sig_preview_cut_boundary_scan = pyqtSignal(float, float)
    _sig_preview_cut_boundary_scan_lines = pyqtSignal(list)
    _sig_update_project_boundary_times = pyqtSignal(list)
    _sig_set_llm_review_segment = pyqtSignal(dict)
    _sig_editor_processing_stage = pyqtSignal(str)
    _sig_finalize_generation_complete = pyqtSignal(str)
    _sig_runtime_audio_tune = pyqtSignal(str, object)
    _sig_home_auto_sources_ready = pyqtSignal(object)
    _sig_external_app_command = pyqtSignal(object, object)

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
        self._auto_processing_active = False
        detach_project_session(
            self,
            auto_pipeline=False,
            clear_multiclip=True,
            emit_boundary_signal=False,
        )
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
        self._personalization_learning_dialogs = []
        self._post_completion_idle_enabled = False
        self._post_completion_idle_ms = 600_000
        self._app_event_filter_installed = False
        self._lora_foreground_busy_until_ms = 0
        self._lora_foreground_busy_reason = ""
        self._fast_exit_requested = False
        self._fast_exit_pause_logged = False
        self._exit_runtime_cleanup_done = False
        self._exit_runtime_cleanup_thread = None
        self._workspace_sidebar_locked_width = 0
        self._runtime_auto_audio_file = ""
        self._runtime_auto_audio_tune = {}
        self._runtime_auto_audio_decision = {}
        self._guided_snapshot_run = None

        settings = load_settings()
        self._auto_start_on = settings.get("auto_start_enabled", True)
        self._is_icloud_auto_mode = get_icloud_auto_detect()
        self._is_nas_auto_mode = get_nas_auto_detect()
        self._offscreen_test = str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen"
        self._initial_home_built = False

        self._live_timer = QTimer()
        self._live_timer.timeout.connect(self._update_live_queue_header)
        self._post_completion_idle_timer = QTimer(self)
        self._post_completion_idle_timer.setSingleShot(True)
        self._post_completion_idle_timer.timeout.connect(self._on_post_completion_idle_timeout)
        self._post_completion_idle_deadline_ms = 0
        self._post_completion_idle_countdown_timer = QTimer(self)
        self._post_completion_idle_countdown_timer.setInterval(1000)
        self._post_completion_idle_countdown_timer.timeout.connect(self._refresh_post_completion_idle_status)
        self._runtime_memory_timer = QTimer(self)
        self._runtime_memory_timer.timeout.connect(self._poll_runtime_memory_manager)
        self._runtime_memory_manager = None
        self._runtime_resource_timer = QTimer(self)
        self._runtime_resource_timer.timeout.connect(self._poll_runtime_resource_coordinator)
        self._runtime_resource_coordinator = None
        self._runtime_resource_snapshot = {}
        self._post_show_startup_started = False
        self._initial_home_build_requested = False
        self._initial_home_scan_deferred = not self._offscreen_test
        self._home_auto_source_cache = {}
        self._home_auto_source_refresh_token = 0
        self._home_auto_source_refresh_inflight = False

        self._build_ui()
        self._connect_signals()
        self._personalization_idle_trainer = PersonalizationIdleTrainer(self, recover_on_init=False)
        self._attach_app_event_filter()
        self._initialize_runtime_memory_manager(settings)
        self._initialize_runtime_resource_coordinator(settings)
        if not self._offscreen_test:
            QTimer.singleShot(450 if getattr(config, "IS_MAC", False) else 0, self._warmup_local_llm_models)
            QTimer.singleShot(1400 if getattr(config, "IS_MAC", False) else 900, self._check_required_models_on_startup)
            QTimer.singleShot(1800 if getattr(config, "IS_MAC", False) else 1200, self._preflight_selected_local_llm_models)

        self._cloud_sync_manager = CloudSyncManager(
            get_icloud_path(), self._on_files_detected, self._is_app_busy
        )
        self._nas_sync_manager = CloudSyncManager(
            get_local_path(get_nas_path()), self._on_files_detected, self._is_app_busy,
            mode="nas", scan_interval=60, stable_seconds=300, exclude_callback=get_nas_excluded_folders
        )
        if self._auto_start_on and (getattr(self, "_is_icloud_auto_mode", False) or getattr(self, "_is_nas_auto_mode", False)):
            if self._offscreen_test:
                self._start_auto_watchers_after_launch()
            else:
                QTimer.singleShot(1600 if getattr(config, "IS_MAC", False) else 0, self._start_auto_watchers_after_launch)

    def showEvent(self, event):  # noqa: N802 - Qt override
        super().showEvent(event)
        if self._offscreen_test:
            self._ensure_initial_home_ready()
        else:
            self._schedule_initial_home_ready()
        self._start_post_show_startup_tasks()

    def _schedule_initial_home_ready(self):
        if bool(getattr(self, "_initial_home_built", False)) or bool(getattr(self, "_initial_home_build_requested", False)):
            return
        self._initial_home_build_requested = True
        QTimer.singleShot(0, self._ensure_initial_home_ready)

    def _ensure_initial_home_ready(self):
        if bool(getattr(self, "_initial_home_built", False)):
            return
        self._initial_home_build_requested = False
        self._initial_home_built = True
        self.show_home()
        self._start_initial_home_auto_source_refresh(
            delay_ms=120 if getattr(config, "IS_MAC", False) else 0,
        )

    def _start_post_show_startup_tasks(self):
        if bool(getattr(self, "_post_show_startup_started", False)):
            return
        self._post_show_startup_started = True
        trainer = getattr(self, "_personalization_idle_trainer", None)
        call_nonfatal_ui_step(
            "메인윈도우 시작",
            trainer,
            "recover_startup_jobs_async",
            reason="trainer_startup",
            delay_ms=500 if getattr(config, "IS_MAC", False) else 0,
            step="recover_startup_jobs_async",
        )

    def _start_auto_watchers_after_launch(self):
        if self._auto_start_on and getattr(self, "_is_icloud_auto_mode", False):
            call_nonfatal_ui_step(
                "자동 감시 시작",
                getattr(self, "_cloud_sync_manager", None),
                "start",
                step="icloud watcher start",
            )
        elif self._auto_start_on and getattr(self, "_is_nas_auto_mode", False):
            nas_path = run_nonfatal_ui_step(
                "자동 감시 시작",
                "get_nas_path",
                get_nas_path,
                default="",
            )
            if not nas_path:
                return
            mounted = run_nonfatal_ui_step(
                "자동 감시 시작",
                "ensure_nas_mounted",
                lambda: ensure_nas_mounted(nas_path),
                default=False,
            )
            if not mounted:
                return
            local_path = run_nonfatal_ui_step(
                "자동 감시 시작",
                "get_local_path",
                lambda: get_local_path(nas_path),
                default="",
            )
            if not local_path:
                return
            manager = getattr(self, "_nas_sync_manager", None)
            run_nonfatal_ui_step(
                "자동 감시 시작",
                "nas dropzone_path",
                lambda: setattr(manager, "dropzone_path", local_path),
            )
            call_nonfatal_ui_step(
                "자동 감시 시작",
                manager,
                "start",
                step="nas watcher start",
            )

    # ── UI 빌드 ──────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(MAIN_PANEL_GAP, MAIN_PANEL_GAP, MAIN_PANEL_GAP, MAIN_PANEL_GAP)
        main_layout.setSpacing(MAIN_PANEL_GAP)
        self.stack = MainWorkspaceStack()

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setHandleWidth(MAIN_PANEL_GAP)
        workspace_splitter.setStyleSheet(
            f"QSplitter::handle {{ background: #0F1518; width: {MAIN_PANEL_GAP}px; }}"
        )
        main_layout.addWidget(workspace_splitter, stretch=1)

        self.home_page = ProjectSidebarWidget()
        workspace_splitter.addWidget(self.home_page)
        self._create_sidebar_terminal_panel()
        if bool(getattr(self, "_unified_dashboard", False)):
            self.status_rail = None
        else:
            self.status_rail = StatusRail(self.home_page)
        self.saved_status_label = QLabel("", self.home_page)
        self.saved_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.saved_status_label.setStyleSheet("color: #A9B0B7; font-size: 11px; background: transparent;")
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label(is_dirty=False)
        self.sidebar_settings_label = QLabel("", self.home_page)
        self.sidebar_settings_label.setWordWrap(True)
        self.sidebar_settings_label.setStyleSheet("color: #A9B0B7; font-size: 9px; font-weight: bold; background: transparent; border: none;")
        self.sidebar_runtime_label = QLabel("", self.home_page)
        self.sidebar_runtime_label.setWordWrap(True)
        self.sidebar_runtime_label.setTextFormat(Qt.TextFormat.RichText)
        self.sidebar_runtime_label.setStyleSheet("color: #A9B0B7; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        if hasattr(self, "_refresh_sidebar_engine_info"):
            self._refresh_sidebar_engine_info()
        if hasattr(self, "_refresh_sidebar_runtime_monitor"):
            self._refresh_sidebar_runtime_monitor()

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

        right_workspace = QWidget()
        right_workspace.setObjectName("RightWorkspace")
        right_workspace.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        right_workspace.setStyleSheet("QWidget#RightWorkspace { background: transparent; border: none; }")
        right_layout = QVBoxLayout(right_workspace)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(MAIN_PANEL_GAP)
        self.right_layout = right_layout
        right_layout.addWidget(self.stack, stretch=1)

        self.global_menu_bar = GlobalMenuBar(self)
        self.global_menu_bar.set_status_rail(self.status_rail)

        self.bottom_work_panel = self._build_log_panel()
        right_layout.addWidget(self.bottom_work_panel)
        right_layout.addWidget(self.global_menu_bar)
        workspace_splitter.addWidget(right_workspace)
        workspace_splitter.setSizes([210, 1465])
        self.workspace_splitter = workspace_splitter
        self.right_workspace = right_workspace
        self._configure_workspace_splitter_handle()
        self._apply_log_visible(self._log_visible, persist=False)
        self._apply_responsive_workspace_layout()
        if self._offscreen_test:
            self._ensure_initial_home_ready()
        else:
            self.stack.setCurrentIndex(0)

    def _configure_workspace_splitter_handle(self) -> None:
        splitter = getattr(self, "workspace_splitter", None)
        if splitter is None:
            return
        for index in range(1, int(splitter.count())):
            handle = splitter.handle(index)
            if handle is None:
                continue
            try:
                handle.setEnabled(False)
                handle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                handle.setCursor(Qt.CursorShape.ArrowCursor)
            except Exception:
                pass

    def _start_initial_home_auto_source_refresh(self, *, delay_ms: int = 0) -> None:
        if not bool(getattr(self, "_initial_home_scan_deferred", False)):
            return
        if bool(getattr(self, "_home_auto_source_refresh_inflight", False)):
            return
        self._home_auto_source_refresh_inflight = True
        token = int(getattr(self, "_home_auto_source_refresh_token", 0) or 0) + 1
        self._home_auto_source_refresh_token = token

        def launch() -> None:
            def worker() -> None:
                payload = {"token": token}
                payload["icloud"] = run_nonfatal_ui_step(
                    "홈 자동 소스 갱신",
                    "get_icloud_files",
                    self._get_icloud_files,
                    default=([], "오류", ""),
                )
                payload["nas"] = run_nonfatal_ui_step(
                    "홈 자동 소스 갱신",
                    "get_nas_folders",
                    self._get_nas_folders,
                    default=([], "오류", ""),
                )
                run_nonfatal_ui_step(
                    "홈 자동 소스 갱신",
                    "emit home_auto_sources_ready",
                    lambda: self._sig_home_auto_sources_ready.emit(payload),
                )

            threading.Thread(
                target=worker,
                name="home-auto-source-refresh",
                daemon=True,
            ).start()

        QTimer.singleShot(max(0, int(delay_ms or 0)), launch)

    def _on_home_auto_sources_ready(self, payload) -> None:
        current_token = int(getattr(self, "_home_auto_source_refresh_token", 0) or 0)
        payload_token = 0
        if isinstance(payload, dict):
            try:
                payload_token = int(payload.get("token", 0) or 0)
            except (TypeError, ValueError):
                payload_token = 0
        if payload_token and payload_token != current_token:
            return
        cache = {}
        if isinstance(payload, dict):
            cache["icloud"] = payload.get("icloud", ([], "오류", ""))
            cache["nas"] = payload.get("nas", ([], "오류", ""))
        self._home_auto_source_cache = cache
        self._initial_home_scan_deferred = False
        self._home_auto_source_refresh_inflight = False
        if int(getattr(self, "stack", None).currentIndex() if getattr(self, "stack", None) is not None else -1) == 0:
            run_nonfatal_ui_step(
                "홈 자동 소스 갱신",
                "rebuild_home_content",
                self._build_home_content,
            )

    def _initialize_runtime_memory_manager(self, settings=None):
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
            return
        manager = run_nonfatal_ui_step(
            "메모리 관리자 시작",
            "create runtime memory manager",
            lambda: RuntimeMemoryManager(settings=dict(settings or {}), logger=get_logger()),
            default=None,
        )
        if manager is None:
            return
        self._runtime_memory_manager = manager
        run_nonfatal_ui_step(
            "메모리 관리자 시작",
            "register trim callback",
            lambda: manager.register_trim_callback("mainwindow", self._handle_runtime_memory_pressure),
        )
        run_nonfatal_ui_step(
            "메모리 관리자 시작",
            "configure memory timer",
            lambda: self._runtime_memory_timer.setInterval(int(manager.interval_ms)),
        )
        run_nonfatal_ui_step(
            "메모리 관리자 시작",
            "start memory timer",
            self._runtime_memory_timer.start,
        )

    def _initialize_runtime_resource_coordinator(self, settings=None):
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
            return
        coordinator = run_nonfatal_ui_step(
            "런타임 코디네이터 시작",
            "create runtime resource coordinator",
            lambda: RuntimeResourceCoordinator(settings=dict(settings or {}), logger=get_logger()),
            default=None,
        )
        if coordinator is None:
            return
        self._runtime_resource_coordinator = coordinator
        run_nonfatal_ui_step(
            "런타임 코디네이터 시작",
            "configure resource timer",
            lambda: self._runtime_resource_timer.setInterval(2500),
        )
        run_nonfatal_ui_step(
            "런타임 코디네이터 시작",
            "start resource timer",
            self._runtime_resource_timer.start,
        )
        run_nonfatal_ui_step(
            "런타임 코디네이터 시작",
            "initial resource poll",
            self._poll_runtime_resource_coordinator,
        )

    def _poll_runtime_memory_manager(self):
        manager = getattr(self, "_runtime_memory_manager", None)
        if manager is None:
            return
        run_nonfatal_ui_step(
            "메모리 관리자 폴링",
            "manager.poll",
            manager.poll,
        )

    def _poll_runtime_resource_coordinator(self):
        coordinator = getattr(self, "_runtime_resource_coordinator", None)
        if coordinator is None:
            return
        _missing = object()
        snapshot = run_nonfatal_ui_step(
            "런타임 코디네이터 폴링",
            "coordinator.poll",
            lambda: coordinator.poll(window=self),
            default=_missing,
        )
        if snapshot is _missing:
            return
        self._runtime_resource_snapshot = snapshot
        if hasattr(self, "_refresh_sidebar_runtime_monitor"):
            run_nonfatal_ui_step(
                "런타임 코디네이터 폴링",
                "refresh_sidebar_runtime_monitor",
                self._refresh_sidebar_runtime_monitor,
            )
        if hasattr(self, "_refresh_saved_status_label"):
            run_nonfatal_ui_step(
                "런타임 코디네이터 폴링",
                "refresh_saved_status_label",
                lambda: self._refresh_saved_status_label(is_dirty=getattr(self, "_last_saved_status_dirty", None)),
            )

    def _current_responsive_profile(self):
        override = run_nonfatal_ui_step(
            "반응형 레이아웃",
            "responsive_profile_override",
            lambda: str(self.property("responsive_profile_override") or ""),
            default="",
        )
        return responsive_profile_for_size(self.width(), self.height(), override=override)

    def _apply_responsive_workspace_layout(self):
        splitter = getattr(self, "workspace_splitter", None)
        sidebar = getattr(self, "home_page", None)
        if splitter is None or sidebar is None:
            return
        profile = self._current_responsive_profile()
        total = max(1, int(self.width() or 0) - (MAIN_PANEL_GAP * 2))
        if not bool(getattr(self, "_log_visible", True)):
            run_nonfatal_ui_step(
                "반응형 레이아웃",
                "hide sidebar sizes",
                lambda: splitter.setSizes([0, total]),
            )
            return
        run_nonfatal_ui_step(
            "반응형 레이아웃",
            "set sidebar width bounds",
            lambda: (
                sidebar.setMinimumWidth(profile.sidebar_min_width),
                sidebar.setMaximumWidth(profile.sidebar_max_width),
            ),
        )
        locked_w = int(getattr(self, "_workspace_sidebar_locked_width", 0) or 0)
        if locked_w > 0:
            sidebar_w = max(profile.sidebar_min_width, min(profile.sidebar_max_width, locked_w))
            run_nonfatal_ui_step(
                "반응형 레이아웃",
                "lock sidebar width bounds",
                lambda: (
                    sidebar.setMinimumWidth(sidebar_w),
                    sidebar.setMaximumWidth(sidebar_w),
                ),
            )
            run_nonfatal_ui_step(
                "반응형 레이아웃",
                "apply locked splitter sizes",
                lambda: splitter.setSizes([sidebar_w, max(1, total - sidebar_w)]),
            )
            return
        sidebar_w = responsive_sidebar_width(total, profile)
        run_nonfatal_ui_step(
            "반응형 레이아웃",
            f"apply {profile.name} splitter sizes",
            lambda: splitter.setSizes([sidebar_w, max(1, total - sidebar_w)]),
        )

    def _lock_workspace_sidebar_width(self, width: int | None = None) -> int:
        splitter = getattr(self, "workspace_splitter", None)
        sidebar = getattr(self, "home_page", None)
        if splitter is None or sidebar is None or not bool(getattr(self, "_log_visible", True)):
            self._workspace_sidebar_locked_width = 0
            return 0
        profile = self._current_responsive_profile()
        sizes = run_nonfatal_ui_step(
            "반응형 레이아웃",
            "read splitter sizes",
            lambda: list(splitter.sizes()),
            default=[],
        )
        current_w = int(sizes[0]) if len(sizes) >= 2 and int(sizes[0]) > 0 else 0
        total = max(1, sum(sizes) if sizes else int(self.width() or 0) - (MAIN_PANEL_GAP * 2))
        target = int(width or current_w or responsive_sidebar_width(total, profile))
        target = max(profile.sidebar_min_width, min(profile.sidebar_max_width, target))
        self._workspace_sidebar_locked_width = target
        run_nonfatal_ui_step(
            "반응형 레이아웃",
            "lock sidebar width",
            lambda: (
                sidebar.setMinimumWidth(target),
                sidebar.setMaximumWidth(target),
            ),
        )
        run_nonfatal_ui_step(
            "반응형 레이아웃",
            "lock splitter sizes",
            lambda: splitter.setSizes([target, max(1, total - target)]),
        )
        return target

    def _unlock_workspace_sidebar_width(self) -> None:
        self._workspace_sidebar_locked_width = 0
        sidebar = getattr(self, "home_page", None)
        if sidebar is not None:
            profile = self._current_responsive_profile()
            run_nonfatal_ui_step(
                "반응형 레이아웃",
                "unlock sidebar width bounds",
                lambda: (
                    sidebar.setMinimumWidth(profile.sidebar_min_width),
                    sidebar.setMaximumWidth(profile.sidebar_max_width),
                ),
            )
        self._apply_responsive_workspace_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._apply_responsive_workspace_layout)
        menu = getattr(self, "global_menu_bar", None)
        if menu is not None:
            QTimer.singleShot(0, menu.refresh)

    def _create_sidebar_terminal_panel(self):
        panel = TerminalLogWidget(self.home_page)
        panel.setMinimumHeight(116)
        panel.setMaximumHeight(190)
        panel.setStyleSheet(
            "QWidget#TerminalLogPanel { background: #11181C; border: 1px solid #2D3942; border-radius: 7px; }"
        )
        self.sidebar_terminal_panel = panel
        self.log_text = panel.log_text
        return panel

    def _ensure_sidebar_terminal_panel(self):
        panel = getattr(self, "sidebar_terminal_panel", None)
        if panel is not None:
            log_text = run_nonfatal_ui_step(
                "사이드바 터미널 패널",
                "panel.log_text",
                lambda: panel.log_text,
                default=None,
            )
            if log_text is not None:
                parent = run_nonfatal_ui_step(
                    "사이드바 터미널 패널",
                    "panel.parent",
                    panel.parent,
                    default=self.home_page,
                )
                if parent is None:
                    run_nonfatal_ui_step(
                        "사이드바 터미널 패널",
                        "panel.setParent",
                        lambda: panel.setParent(self.home_page),
                    )
                return panel
        return self._create_sidebar_terminal_panel()

    def _build_log_panel(self):
        panel = BottomWorkPanel(self)

        self._log_content = panel.log_content
        self._log_toggle_btn = panel.log_toggle_btn
        self.log_splitter = panel.log_splitter
        self.bottom_right_stack = panel.bottom_right_stack
        self.bottom_queue_page = panel.queue_panel
        self.bottom_roughcut_page = panel.roughcut_panel
        self.queue_header_lbl = panel.queue_header_lbl
        self.queue_table = panel.queue_table
        self.roughcut_bottom_header_lbl = panel.roughcut_bottom_header_lbl
        self.roughcut_bottom_host = panel.roughcut_bottom_host
        self.roughcut_bottom_host_layout = panel.roughcut_bottom_host_layout

        self._log_visible = True
        self._project_panel_visible = self._log_visible

        # 큐 애니메이션
        self._queue_anim_frames = ["", "", "", ""]
        self._queue_anim_idx = 0
        self._queue_anim_timer = QTimer(self)
        self._queue_anim_timer.setInterval(250)
        self._queue_anim_timer.timeout.connect(self._animate_queue_status)
        self._queue_anim_timer.start()

        return panel

    def _set_roughcut_bottom_widget(self, widget: QWidget):
        self._dock_global_menu_to_workspace()
        panel = getattr(self, "bottom_work_panel", None)
        if widget is None or panel is None:
            return
        panel.set_roughcut_widget(widget)
        panel.setVisible(True)
        panel.setMaximumHeight(190)

    def _show_bottom_queue_table(self):
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.show_queue_table()
            if self._should_preserve_editor_processing_layout():
                return
            panel.setVisible(False)
            panel.setMaximumHeight(0)

    def _should_preserve_editor_processing_layout(self) -> bool:
        """Keep the editor/video geometry stable while the start pipeline is running."""
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return False
        try:
            stack = getattr(self, "stack", None)
            if stack is not None and stack.currentWidget() is not editor:
                return False
        except RuntimeError:
            return False
        except Exception:
            pass
        state_manager = getattr(editor, "sm", None)
        state = str(getattr(state_manager, "state", "") or "")
        return state == "ST_PROC" or bool(getattr(editor, "_is_ai_processing", False))

    def _show_bottom_roughcut_table(self):
        self._dock_global_menu_to_workspace()
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.show_roughcut_table()
            panel.setVisible(True)
            panel.setMaximumHeight(190)

    def _backup_editor_segments_for_restart(self, editor, files=None) -> bool:
        if editor is None or not hasattr(editor, "_get_current_segments"):
            return False
        try:
            segs = [
                dict(seg)
                for seg in (editor._get_current_segments() or [])
                if not seg.get("is_gap") and str(seg.get("text", "") or "").strip()
            ]
        except Exception:
            segs = []
        if not segs:
            return False
        try:
            from core.utils import seconds_to_srt_time

            files = list(files or [])
            target = str(getattr(editor, "media_path", "") or (files[0] if files else "") or "")
            if not target:
                return False
            backup_dir = os.path.join(os.path.dirname(target), "자막백업")
            os.makedirs(backup_dir, exist_ok=True)
            base = os.path.splitext(os.path.basename(target))[0]
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"{base}_restart_segments_{stamp}.srt")
            lines = []
            for idx, seg in enumerate(segs, 1):
                start = max(0.0, float(seg.get("start", 0.0) or 0.0))
                end = float(seg.get("end", start + 0.1) or start + 0.1)
                if end <= start:
                    end = start + 0.1
                text = str(seg.get("text", "") or "").strip().replace("\u2028", "\n")
                lines.extend([
                    str(idx),
                    f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                    text,
                    "",
                ])
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            get_logger().log(f"📦 재시작 전 현재 세그먼트 백업 완료: {os.path.basename(backup_path)}")
            return True
        except Exception as e:
            get_logger().log(f"⚠️ 재시작 전 세그먼트 백업 실패: {e}")
            return False

    def _clear_editor_for_full_restart(self, editor=None):
        editor = editor or getattr(self, "_editor_widget", None)
        if editor is None:
            return
        def _clear_canvas(canvas, *, keep_duration=True):
            if canvas is None:
                return
            try:
                if keep_duration:
                    canvas.total_duration = float(getattr(canvas, "total_duration", 0.0) or 0.0)
                else:
                    canvas.total_duration = 0.0
                canvas.segments = []
                canvas.gap_segments = []
                canvas.vad_segments = []
                if hasattr(canvas, "voice_activity_segments"):
                    canvas.voice_activity_segments = []
                if hasattr(canvas, "_voice_activity_segments"):
                    canvas._voice_activity_segments = []
                if hasattr(canvas, "_multiclip_boxes"):
                    canvas._multiclip_boxes = []
                if hasattr(canvas, "_active_clip_idx"):
                    canvas._active_clip_idx = 0
                if hasattr(canvas, "_selected_candidate"):
                    canvas._selected_candidate = None
                if hasattr(canvas, "_selected_candidate_source"):
                    canvas._selected_candidate_source = ""
                canvas.active_seg_start = None
                canvas.playhead_sec = 0.0
                canvas._last_playhead_px = None
                canvas.re_recog_zone = None
                canvas.re_recog_progress = None
                canvas._hover_line = None
                canvas._hover_handle = None
                canvas._drag_seg = None
                canvas._drag_edge = None
                canvas._drag_adj_l = None
                canvas._drag_adj_r = None
                canvas._snap_lines = []
                if hasattr(canvas, "boundary_times"):
                    canvas.boundary_times = []
                if hasattr(canvas, "scan_boundary_times"):
                    canvas.scan_boundary_times = []
                for attr in (
                    "_preliminary_middle_segments",
                    "preliminary_middle_segments",
                    "_cut_boundary_topicless_middle_segments",
                    "_roughcut_segments",
                    "roughcut_segments",
                    "_middle_segments",
                    "middle_segments",
                    "_chapter_segments",
                    "chapter_segments",
                    "_roughcut_draft_segments",
                    "_roughcut_result",
                    "roughcut_result",
                    "_roughcut_draft_result",
                ):
                    if hasattr(canvas, attr):
                        setattr(canvas, attr, [] if "result" not in attr else None)
                canvas._edit_active = False
                canvas._edit_line = -1
                canvas._edit_text = ""
                canvas._edit_orig = ""
                canvas._speech_mask = None
                if hasattr(canvas, "_invalidate_marker_caches"):
                    canvas._invalidate_marker_caches()
                if hasattr(canvas, "_invalidate_static_cache"):
                    canvas._invalidate_static_cache()
                canvas.update()
            except Exception:
                pass
        try:
            for timer_name in ("_queue_timer", "_roughcut_draft_timer"):
                timer = getattr(editor, timer_name, None)
                if timer is not None and hasattr(timer, "isActive") and timer.isActive():
                    timer.stop()
        except Exception:
            pass
        try:
            if hasattr(editor, "text_edit"):
                blocked = editor.text_edit.blockSignals(True)
                try:
                    editor.text_edit.clear()
                    try:
                        editor.text_edit.document().clearUndoRedoStacks()
                    except Exception:
                        pass
                finally:
                    editor.text_edit.blockSignals(blocked)
                if hasattr(editor.text_edit, "update_margins"):
                    editor.text_edit.update_margins()
        except Exception:
            pass
        try:
            if hasattr(editor, "_segment_queue"):
                editor._segment_queue.clear()
            editor._cached_segs = []
            if hasattr(editor, "_live_stt_preview_segments"):
                editor._live_stt_preview_segments = []
            if hasattr(editor, "_accumulated_vad"):
                editor._accumulated_vad = []
            editor._active_seg_start = 0.0
            editor._completion_handled = False
            editor._roughcut_draft_pending = False
            editor._is_dirty = False
            for attr in ("_partial_insert_pos", "_pending_roughcut_draft", "_last_draft_segments_signature"):
                if hasattr(editor, attr):
                    try:
                        delattr(editor, attr)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            timeline = getattr(editor, "timeline", None)
            if timeline is not None:
                total = float(getattr(getattr(timeline, "canvas", None), "total_duration", 0.0) or 0.0)
                timeline.update_segments([], 0.0, total)
                timeline.set_playhead(0.0)
                if hasattr(timeline, "set_vad_segments"):
                    timeline.set_vad_segments([])
                if hasattr(timeline, "set_voice_activity_segments"):
                    timeline.set_voice_activity_segments([])
                _clear_canvas(getattr(timeline, "canvas", None), keep_duration=True)
                _clear_canvas(getattr(timeline, "global_canvas", None), keep_duration=True)
        except Exception:
            pass
        try:
            video_player = getattr(editor, "video_player", None)
            if video_player is not None:
                video_player.set_context_segments([])
                video_player.segments = []
                video_player._pending_segments = []
                video_player._subtitle_starts = []
                video_player._subtitle_ends = []
                video_player._subtitle_texts = []
                video_player._subtitle_count = 0
                video_player._last_segments_signature = ""
                video_player.seek(0.0)
        except Exception:
            pass
        try:
            if hasattr(editor, "_remember_saved_segments"):
                editor._remember_saved_segments([])
        except Exception:
            pass

    def _clear_roughcut_for_full_restart(self, files=None):
        try:
            self._editor_roughcut_result = None
            self._stored_roughcut_result = None
        except Exception:
            pass
        roughcut = getattr(self, "_roughcut_widget", None)
        if roughcut is not None:
            try:
                roughcut._result = None
                roughcut._stored_roughcut_result = None
                roughcut._source_signature = ""
                roughcut._selected_candidate_id = ""
                roughcut._roughcut_candidates = []
                roughcut._user_edits = {}
                if hasattr(roughcut, "_refresh_candidate_combo"):
                    roughcut._refresh_candidate_combo()
                if hasattr(roughcut, "_set_empty_state"):
                    roughcut._set_empty_state()
            except RuntimeError:
                pass
            except Exception:
                pass

        project_path = str(getattr(self, "_current_project_path", "") or "")
        if project_path and os.path.exists(project_path):
            try:
                from core.cut_boundary import sync_project_cut_boundaries
                from core.project.project_io import read_project_file, write_project_file
                from core.project.project_manager import save_project
                from core.work_mode import EDITOR_MODE

                save_project(
                    project_path,
                    segments=[],
                    roughcut_state={},
                    active_work_mode=EDITOR_MODE,
                    stt_preview_segments=[],
                    provisional_cut_boundaries=[],
                )
                project = read_project_file(project_path)
                analysis = project.setdefault("analysis", {})
                analysis["cut_boundaries"] = []
                analysis["cut_boundary_provisional_boundaries"] = []
                sync_project_cut_boundaries(
                    project,
                    settings=project.get("user_settings", {}),
                    provisional_boundaries=[],
                )
                write_project_file(project_path, project)
                get_logger().log("🧹 재시작: 프로젝트 러프컷 상태와 세그먼트를 초기화했습니다.")
            except Exception as exc:
                get_logger().log(f"⚠️ 재시작 러프컷 상태 초기화 실패: {exc}")

    def _clear_cut_boundary_state_for_full_restart(self, editor=None):
        editor = editor or getattr(self, "_editor_widget", None)
        set_project_boundary_rows(self, [], emit_boundary_signal=True)

        if editor is None:
            return

        for attr in (
            "_preliminary_middle_segments",
            "preliminary_middle_segments",
            "_project_boundary_times",
            "_auto_cut_boundary_scan_lines",
            "_cut_boundary_topicless_middle_segments",
            "_middle_segments",
            "middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
            "_roughcut_result",
            "roughcut_result",
            "_roughcut_draft_result",
        ):
            try:
                setattr(editor, attr, [] if "result" not in attr else None)
            except Exception:
                pass
        try:
            editor._scan_cut_state = None
        except Exception:
            pass
        try:
            if hasattr(editor, "_set_auto_cut_boundary_scan_active"):
                editor._set_auto_cut_boundary_scan_active(False)
        except Exception:
            pass
        try:
            if hasattr(editor, "_set_auto_cut_boundary_scan_lines"):
                editor._set_auto_cut_boundary_scan_lines([])
        except Exception:
            pass
        try:
            timeline = getattr(editor, "timeline", None)
            if timeline is not None:
                if hasattr(timeline, "set_boundary_times"):
                    timeline.set_boundary_times([])
                if hasattr(timeline, "set_scan_boundary_times"):
                    timeline.set_scan_boundary_times([])
                for obj in (timeline, getattr(timeline, "canvas", None), getattr(timeline, "global_canvas", None)):
                    if obj is None:
                        continue
                    for attr in (
                        "_preliminary_middle_segments",
                        "preliminary_middle_segments",
                        "_cut_boundary_topicless_middle_segments",
                        "_roughcut_segments",
                        "roughcut_segments",
                        "_middle_segments",
                        "middle_segments",
                        "_chapter_segments",
                        "chapter_segments",
                        "_roughcut_draft_segments",
                        "_roughcut_result",
                        "roughcut_result",
                        "_roughcut_draft_result",
                    ):
                        try:
                            setattr(obj, attr, [] if "result" not in attr else None)
                        except Exception:
                            pass
                    if hasattr(obj, "_invalidate_marker_caches"):
                        obj._invalidate_marker_caches()
                    if hasattr(obj, "_invalidate_static_cache"):
                        obj._invalidate_static_cache()
                    if hasattr(obj, "update"):
                        obj.update()
        except Exception:
            pass

    def _restart_current_pipeline_from_beginning(self, editor=None) -> bool:
        editor = editor or getattr(self, "_editor_widget", None)
        backend = getattr(self, "backend", None)
        if editor is None or backend is None:
            return False
        files = list(getattr(backend, "files_to_process", []) or [])
        if not files:
            media_path = str(getattr(editor, "media_path", "") or "")
            files = [media_path] if media_path else []
        if not files:
            return False

        get_logger().log("\n🔄 재시작: 백업 후 처음부터 다시 생성합니다.")
        if hasattr(self, "_stop_post_completion_idle_timer"):
            self._stop_post_completion_idle_timer()
        self._backup_editor_segments_for_restart(editor, files)
        self._clear_editor_for_full_restart(editor)
        self._clear_roughcut_for_full_restart(files)
        self._clear_cut_boundary_state_for_full_restart(editor)
        self._prepare_cut_boundary_prescan_for_restart(backend, files)
        try:
            state_manager = getattr(editor, "sm", None)
            if state_manager is not None and hasattr(state_manager, "start_processing"):
                state_manager.start_processing()
        except Exception:
            pass
        try:
            self._reuse_existing_multiclip_subtitles = False
            self._reuse_clip_indices = set()
            backend._reuse_existing_single_subtitle = False
            backend._reuse_existing_multiclip_subtitles = False
            backend._reuse_clip_indices = set()
            backend._force_no_reuse_once = True
            backend._force_cut_boundary_rescan_once = True
            backend._speaker_map = []
            backend.pipeline_start_time = time.time()
            backend.is_first_start = False
        except Exception:
            pass
        if hasattr(self, "init_queue_list"):
            self.init_queue_list(files)
        self._restart_queue_eta_metadata(backend, files)
        try:
            if hasattr(self, "_live_timer"):
                self._live_timer.start(1000)
        except Exception:
            pass
        if hasattr(self, "_sig_update_queue_header_payload"):
            self._sig_update_queue_header_payload.emit(
                build_queue_header_payload(1, len(files), 0, "")
            )
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label(is_dirty=False, touch_saved_time=False)
        if hasattr(self, "sync_menu_from_editor"):
            self.sync_menu_from_editor(editor)

        if len(files) > 1:
            if hasattr(self, "_sig_restart_multiclip"):
                self._sig_restart_multiclip.emit(files, getattr(backend, "current_folder", None))
            else:
                backend.start_multiclip_pipeline(files, folder=getattr(backend, "current_folder", None))
            return True

        pipeline_thread = getattr(backend, "_pipeline_thread", None)
        pipeline_thread_alive = bool(
            pipeline_thread is not None
            and callable(getattr(pipeline_thread, "is_alive", None))
            and pipeline_thread.is_alive()
        )
        if pipeline_thread_alive:
            backend._active = True
            backend.restart_current_file()
            return True

        starter = getattr(backend, "start_pipeline", None)
        if callable(starter):
            starter(
                list(files),
                folder=getattr(backend, "current_folder", None),
                is_icloud=bool(getattr(backend, "is_icloud", False)),
                is_auto_start=True,
            )
            return True

        backend._active = True
        backend.restart_current_file()
        return True

    def _restart_queue_eta_metadata(self, backend, files) -> None:
        """Refresh queue ETA/video-duration metadata after a completed-state restart."""
        files = list(files or [])
        if backend is None or not files:
            return
        precalculate = getattr(backend, "_precalculate_etas", None)
        if not callable(precalculate):
            return
        try:
            backend.files_to_process = list(files)
            backend._show_queue_for_current_run = True
            backend._video_durations = {}
            thread = threading.Thread(
                target=precalculate,
                daemon=True,
                name="eta-calculator-restart",
            )
            backend._eta_thread = thread
            thread.start()
        except Exception as exc:
            get_logger().log(f"⚠️ 재시작 큐 시간 계산 준비 실패: {exc}")

    def _prepare_cut_boundary_prescan_for_restart(self, backend, files) -> None:
        """Re-arm cut-boundary prescan when restarting from a completed editor state."""
        files = list(files or [])
        if backend is None or not files:
            return
        scan = getattr(backend, "_auto_scan_cut_boundaries_for_start", None)
        if not callable(scan):
            return
        try:
            settings = load_settings()
        except Exception:
            settings = {}
        project_path = str(getattr(self, "_current_project_path", "") or "")
        if project_path and os.path.exists(project_path):
            try:
                from core.project.project_io import read_project_file, write_project_file

                project = read_project_file(project_path)
                project["user_settings"] = dict(settings or {})
                analysis = project.setdefault("analysis", {})
                for key in (
                    "cut_boundary_prescan_done",
                    "cut_boundary_cache_path",
                    "cut_boundary_cache_type",
                ):
                    analysis.pop(key, None)
                write_project_file(project_path, project)
            except Exception as exc:
                get_logger().log(f"⚠️ 재시작 컷 경계 설정 갱신 실패: {exc}")
        try:
            backend._force_cut_boundary_rescan_once = True
        except Exception:
            pass
        try:
            scan(project_path, files)
        except Exception as exc:
            get_logger().log(f"⚠️ 재시작 컷 경계 사전 분석 시작 실패: {exc}")

    def _dock_global_menu_to_workspace(self):
        menu = getattr(self, "global_menu_bar", None)
        layout = getattr(self, "right_layout", None)
        workspace = getattr(self, "right_workspace", None)
        if menu is None or layout is None or workspace is None:
            return
        try:
            target_index = layout.count() - 1
            if menu.parentWidget() is workspace and layout.indexOf(menu) == target_index:
                menu.show()
                return
            menu.setParent(workspace)
            layout.addWidget(menu)
            menu.show()
        except RuntimeError:
            return

    def _attach_global_menu_to_editor(self, editor):
        if editor is not None:
            detach = getattr(editor, "detach_external_menu_bar", None)
            if callable(detach):
                detach()
        self._dock_global_menu_to_workspace()

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
        self._sig_append_segments_ready.connect(self._do_append_segments_ready)
        self._sig_update_status.connect(self._do_update_status)
        self._sig_open_editor.connect(self._do_open_editor)
        self._sig_open_editor_ready.connect(self._do_open_editor_ready)
        self._sig_set_vad_segments.connect(self._on_vad_segments)
        self._sig_update_queue_payload.connect(self.update_queue_status)
        self._sig_update_queue_header_payload.connect(self.update_queue_header)
        self._sig_auto_start_pipeline.connect(self._do_auto_start_pipeline)
        self._sig_prepare_processing_editor.connect(self._do_prepare_processing_editor)
        self._sig_load_multiclip_waveform.connect(self._do_load_multiclip_waveform)
        self._sig_set_recog_zone.connect(self._on_recog_zone)
        self._sig_set_recog_progress.connect(self._on_recog_progress)
        self._sig_preview_stt_segments.connect(self._do_preview_stt_segments)
        self._sig_preview_processing_segments.connect(self._do_preview_processing_segments)
        self._sig_clear_editor.connect(self._do_clear_editor)
        self._sig_restart_multiclip.connect(self._do_restart_multiclip)
        self._sig_refresh_cut_boundary_placeholder.connect(self._do_refresh_cut_boundary_placeholder)
        self._sig_preview_cut_boundary_topicless_segments.connect(self._on_cut_boundary_topicless_segments)
        self._sig_set_cut_boundary_scan_active.connect(self._on_cut_boundary_scan_active)
        self._sig_preview_cut_boundary_scan.connect(self._on_cut_boundary_scan_preview)
        self._sig_preview_cut_boundary_scan_lines.connect(self._on_cut_boundary_scan_lines)
        self._sig_update_project_boundary_times.connect(self._on_project_boundary_times_updated)
        self._sig_set_llm_review_segment.connect(self._do_set_llm_review_segment)
        self._sig_editor_processing_stage.connect(self._do_editor_processing_stage)
        self._sig_finalize_generation_complete.connect(self._do_finalize_generation_complete)
        self._sig_runtime_audio_tune.connect(self._set_runtime_audio_tune_display)
        self._sig_home_auto_sources_ready.connect(self._on_home_auto_sources_ready)
        self._sig_external_app_command.connect(self._do_execute_external_app_command)
        self._pending_async_snapshots = []
        self._last_async_snapshot_result = {}

    def dispatch_external_app_command(self, payload, *, timeout_sec: float = 12.0):
        return dispatch_app_command(self, payload, timeout_sec=timeout_sec)

    def _do_execute_external_app_command(self, payload, reply_state=None):
        handle_app_command_signal(self, payload, reply_state)

    def _automation_guided_snapshot_state_payload(self):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict):
            state = {}
        snapshots = []
        for item in list(state.get("snapshots", []) or []):
            if isinstance(item, dict):
                snapshots.append(
                    {
                        "label": str(item.get("label", "") or ""),
                        "stage_text": str(item.get("stage_text", "") or ""),
                        "path": str(item.get("path", "") or ""),
                        "sequence": int(item.get("sequence", 0) or 0),
                    }
                )
        stage_events = []
        for item in list(state.get("stage_events", []) or []):
            if isinstance(item, dict):
                stage_events.append(
                    {
                        "key": str(item.get("key", "") or ""),
                        "label": str(item.get("label", "") or ""),
                        "text": str(item.get("text", "") or ""),
                        "sequence": int(item.get("sequence", 0) or 0),
                    }
                )
        last_async = dict(getattr(self, "_last_async_snapshot_result", {}) or {})
        pending_async = []
        for item in list(getattr(self, "_pending_async_snapshots", []) or []):
            if isinstance(item, dict):
                pending_async.append(
                    {
                        "path": str(item.get("path", "") or ""),
                        "requested_at": float(item.get("requested_at", 0.0) or 0.0),
                    }
                )
        return {
            "active": bool(state.get("active", False)),
            "media_path": str(state.get("media_path", "") or ""),
            "snapshot_dir": str(state.get("snapshot_dir", "") or ""),
            "last_stage": str(state.get("last_stage", "") or ""),
            "last_stage_key": str(state.get("last_stage_key", "") or ""),
            "last_stage_label": str(state.get("last_stage_label", "") or ""),
            "snapshot_count": len(snapshots),
            "snapshots": snapshots,
            "stage_event_count": len(stage_events),
            "stage_events": stage_events,
            "latest_snapshot_path": str((snapshots[-1].get("path", "") if snapshots else "") or ""),
            "pending_async_snapshot_count": len(pending_async),
            "pending_async_snapshots": pending_async,
            "last_async_snapshot": last_async,
        }

    def _automation_begin_guided_subtitle_run(self, media_path: str, snapshot_dir: str = ""):
        base_name = os.path.splitext(os.path.basename(str(media_path or "").strip()))[0] or "media"
        stamp = time.strftime("%Y%m%d_%H%M%S")
        target_dir = str(snapshot_dir or "").strip() or os.path.join(str(config.OUTPUT_DIR or ""), "guided_runs", f"{base_name}_{stamp}")
        os.makedirs(target_dir, exist_ok=True)
        self._guided_snapshot_run = {
            "active": True,
            "media_path": str(media_path or ""),
            "snapshot_dir": target_dir,
            "snapshots": [],
            "captured_labels": set(),
            "captured_stage_keys": set(),
            "stage_events": [],
            "stage_event_keys": set(),
            "last_stage": "",
            "last_stage_key": "",
            "last_stage_label": "",
            "sequence": 0,
        }
        return self._automation_guided_snapshot_state_payload()

    def _automation_classify_guided_stage(self, text: str):
        raw = str(text or "").strip()
        if not raw:
            return "", ""
        lowered = raw.lower()
        if "자막 생성 완료" in raw or "backend_done" in lowered:
            return "completed", "자막 생성 완료"
        if "저장 준비 중" in raw or ("저장" in raw and "실패" not in raw):
            return "save", "저장"
        if "러프컷" in raw and ("llm" in lowered or "초안" in raw or "running" in lowered or "queued" in lowered):
            return "roughcut-llm", "러프컷 LLM"
        if "컷 경계" in raw:
            return "cut-boundary", "컷 경계"
        if any(token in raw for token in ("오디오 추출", "오토 오디오", "음성 향상", "ClearVoice")) or "[음성]" in raw:
            return "audio-filter", "음성 필터"
        if any(token in lowered for token in ("stt", "whisper")) or "자막 llm" in lowered or "단어 타임태그" in raw or "자막 생성 중" in raw:
            return "subtitle-generation", "자막 생성"
        return "", ""

    def _automation_record_guided_stage(self, key: str, label: str, text: str, *, capture: bool = False):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return {}
        normalized_key = str(key or "").strip()
        normalized_label = str(label or "").strip()
        normalized_text = str(text or "").strip()
        if not normalized_key:
            return {}
        state["last_stage"] = normalized_text or normalized_label or normalized_key
        state["last_stage_key"] = normalized_key
        state["last_stage_label"] = normalized_label
        event_keys = state.setdefault("stage_event_keys", set())
        if normalized_key in event_keys:
            return {}
        event_keys.add(normalized_key)
        events = state.setdefault("stage_events", [])
        event = {
            "key": normalized_key,
            "label": normalized_label,
            "text": normalized_text,
            "sequence": len(events) + 1,
        }
        events.append(event)
        if capture:
            return self._automation_capture_guided_snapshot(normalized_key, stage_text=normalized_text, force=True)
        return event

    def _automation_capture_guided_snapshot(self, label: str, *, stage_text: str = "", force: bool = False):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not state:
            return {}
        label_text = str(label or "").strip().lower() or "snapshot"
        slug_chars = []
        previous_dash = False
        for ch in label_text:
            if ch.isascii() and ch.isalnum():
                slug_chars.append(ch)
                previous_dash = False
            elif not previous_dash:
                slug_chars.append("-")
                previous_dash = True
        slug = "".join(slug_chars).strip("-") or "snapshot"
        captured_labels = state.setdefault("captured_labels", set())
        if not force and slug in captured_labels:
            return {}
        sequence = int(state.get("sequence", 0) or 0) + 1
        state["sequence"] = sequence
        snapshot_dir = str(state.get("snapshot_dir", "") or "")
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_path = os.path.join(snapshot_dir, f"{sequence:02d}_{slug}.png")
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        pixmap = self.grab()
        if pixmap is None or getattr(pixmap, "isNull", lambda: True)():
            return {}
        if not bool(pixmap.save(snapshot_path, "PNG")):
            return {}
        captured_labels.add(slug)
        snapshot = {
            "label": str(label or ""),
            "stage_text": str(stage_text or ""),
            "path": snapshot_path,
            "sequence": sequence,
        }
        state.setdefault("snapshots", []).append(snapshot)
        state["last_stage"] = str(stage_text or label or "")
        return snapshot

    def _automation_request_async_snapshot_capture(self, snapshot_path: str):
        path = str(snapshot_path or "").strip()
        if not path:
            return {}
        request = {
            "path": path,
            "requested_at": time.time(),
        }
        self._pending_async_snapshots.append(request)
        QTimer.singleShot(0, self._automation_flush_async_snapshot_queue)
        return request

    def _automation_flush_async_snapshot_queue(self):
        pending = list(getattr(self, "_pending_async_snapshots", []) or [])
        if not pending:
            return
        request = pending[0]
        path = str(request.get("path", "") or "")
        result = {"ok": False, "path": path}
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            try:
                app.processEvents()
            except Exception:
                pass
        try:
            pixmap = self.grab()
            if pixmap is not None and not getattr(pixmap, "isNull", lambda: True)():
                saved = bool(pixmap.save(path, "PNG"))
                result = {
                    "ok": saved,
                    "path": path,
                    "width": int(getattr(pixmap, "width", lambda: 0)() or 0),
                    "height": int(getattr(pixmap, "height", lambda: 0)() or 0),
                    "bytes": int(os.path.getsize(path)) if saved and os.path.isfile(path) else 0,
                }
        except Exception:
            result = {"ok": False, "path": path}
        self._last_async_snapshot_result = dict(result)
        try:
            self._pending_async_snapshots = self._pending_async_snapshots[1:]
        except Exception:
            self._pending_async_snapshots = []
        if self._pending_async_snapshots:
            QTimer.singleShot(50, self._automation_flush_async_snapshot_queue)

    def _automation_capture_processing_stage(self, stage_text: str):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        text = str(stage_text or "").strip()
        if not text:
            return
        key, label = self._automation_classify_guided_stage(text)
        if not key:
            state["last_stage"] = text
            return
        self._automation_record_guided_stage(key, label, text, capture=True)

    def _automation_track_log_line(self, line: str):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        text = str(line or "").strip()
        if not text:
            return
        key, label = self._automation_classify_guided_stage(text)
        if not key:
            return
        self._automation_record_guided_stage(key, label, text, capture=True)

    def _automation_finalize_guided_snapshot(self, reason: str = "backend_done"):
        state = getattr(self, "_guided_snapshot_run", None)
        if not isinstance(state, dict) or not bool(state.get("active", False)):
            return
        self._automation_record_guided_stage("completed", "자막 생성 완료", str(reason or "backend_done"), capture=True)
        state["active"] = False

    # ── 홈 / 에디터 전환 ────────────────────────────────
    def show_home(self, allow_home_idle_learning: bool = False):
        active_work = self._is_editor_ai_busy(getattr(self, "_editor_widget", None)) or self._is_backend_ai_busy()
        self._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.5, stop_active=False)
        self._stop_post_completion_idle_timer()
        if not active_work:
            self._reset_transient_multiclip_state()
        self._dock_global_menu_to_workspace()
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
        trainer = getattr(self, "_personalization_idle_trainer", None)
        resume_for_home_idle = getattr(trainer, "resume_for_home_idle", None) if trainer is not None else None
        if callable(resume_for_home_idle):
            try:
                resume_for_home_idle(
                    preserve_idle_age=bool(allow_home_idle_learning),
                    start_if_ready=bool(allow_home_idle_learning),
                )
            except Exception:
                pass

    def _activate_editor_idle_mode(self, *, reason: str = "editor_open") -> None:
        self._start_post_completion_idle_timer()
        pause_lora = getattr(self, "_pause_personalization_for_foreground_activity", None)
        if callable(pause_lora):
            try:
                pause_lora(str(reason or "editor_open"), hold_ms=int(self._post_completion_idle_ms))
            except Exception:
                pause_lora(str(reason or "editor_open"))

    def _stop_active_ai_for_home(self):
        self._cleanup_runtime_for_navigation(context="홈 이동", timeout_sec=0.5, stop_active=True)

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

    def _attach_app_event_filter(self):
        if getattr(self, "_app_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            app.installEventFilter(self)
            self._app_event_filter_installed = True
        except RuntimeError:
            self._app_event_filter_installed = False

    def _detach_app_event_filter(self):
        if not getattr(self, "_app_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            self._app_event_filter_installed = False
            return
        try:
            app.removeEventFilter(self)
        except RuntimeError:
            pass
        self._app_event_filter_installed = False

    def eventFilter(self, obj, event):
        try:
            if self._is_general_user_activity_event(event):
                immediate_stop = self._is_immediate_personalization_stop_event(event)
                trainer = getattr(self, "_personalization_idle_trainer", None)
                if trainer is not None:
                    try:
                        if immediate_stop:
                            request_stop = getattr(trainer, "request_immediate_stop", None)
                            if callable(request_stop):
                                request_stop(
                                    reason="user_input_interrupt",
                                    hold_ms=0,
                                    join_timeout_sec=0.03,
                                )
                            else:
                                trainer.note_user_activity()
                                trainer.suspend_for_foreground_activity(
                                    reason="user_input_interrupt",
                                    hold_ms=0,
                                )
                        else:
                            trainer.note_user_activity()
                    except Exception:
                        pass
                if immediate_stop:
                    self._request_personalization_stop_for_user_input()
                if getattr(self, "_post_completion_idle_enabled", False):
                    self._reset_post_completion_idle_timer()
        except Exception:
            pass
        return False

    def _is_general_user_activity_event(self, event) -> bool:
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

    def _is_immediate_personalization_stop_event(self, event) -> bool:
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

    def _register_personalization_learning_dialog(self, dialog) -> None:
        dialogs = [
            item
            for item in list(getattr(self, "_personalization_learning_dialogs", []) or [])
            if item is not None
        ]
        if dialog not in dialogs:
            dialogs.append(dialog)
        self._personalization_learning_dialogs = dialogs

    def _unregister_personalization_learning_dialog(self, dialog) -> None:
        self._personalization_learning_dialogs = [
            item
            for item in list(getattr(self, "_personalization_learning_dialogs", []) or [])
            if item is not None and item is not dialog
        ]

    def _request_personalization_stop_for_user_input(self) -> None:
        for widget in list(getattr(self, "_personalization_learning_dialogs", []) or []):
            request_stop = getattr(widget, "_request_stop_for_user_input", None)
            if not callable(request_stop):
                continue
            try:
                request_stop()
            except Exception:
                continue

    def _run_personalization_idle_jobs_now(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {"started": False, "reason": "trainer_unavailable"}
        return trainer.run_pending_now()

    def _pause_personalization_for_foreground_activity(
        self,
        reason: str = "foreground_activity",
        *,
        hold_ms: int = FOREGROUND_ACTIVITY_HOLD_MS,
    ):
        """Stop launching LoRA learning while the user/app starts foreground work."""
        now = QDateTime.currentMSecsSinceEpoch()
        try:
            hold = max(0, int(hold_ms))
        except Exception:
            hold = FOREGROUND_ACTIVITY_HOLD_MS
        self._lora_foreground_busy_until_ms = max(
            int(getattr(self, "_lora_foreground_busy_until_ms", 0) or 0),
            now + hold,
        )
        self._lora_foreground_busy_reason = str(reason or "foreground_activity")
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {"suspended": False, "reason": "trainer_unavailable"}
        try:
            return trainer.suspend_for_foreground_activity(
                reason=self._lora_foreground_busy_reason,
                hold_ms=hold,
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 개인화 학습 일시중지 실패: {exc}")
            return {"suspended": False, "reason": str(exc)}

    def _pause_personalization_idle_jobs(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.pause_pending_jobs()

    def _resume_personalization_idle_jobs(self):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.resume_pending_jobs()

    def _clear_personalization_idle_jobs(self, *, keep_completed: bool = True):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {}
        return trainer.clear_pending_jobs(keep_completed=keep_completed)

    def _post_generation_resource_cleanup(self, *, reason: str = "generation_complete", editor=None):
        """Return the UI to an interactive state and detach clip-owned work."""
        for backend_name in ("backend", "backend_fast"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            try:
                lock = getattr(backend, "_prefetch_lock", None)
                if lock is not None:
                    with lock:
                        backend._prefetch_generation = int(getattr(backend, "_prefetch_generation", 0) or 0) + 1
                        getattr(backend, "_prefetch_cache", {}).clear()
                        getattr(backend, "_prefetch_threads", {}).clear()
            except Exception:
                pass
            vp = getattr(backend, "video_processor", None)
            if vp is not None:
                for method_name in ("clear_fast_mode_overrides", "clear_auto_audio_tune_overrides"):
                    method = getattr(vp, method_name, None)
                    if callable(method):
                        try:
                            method()
                        except Exception:
                            pass
                try:
                    vp.stage_callback = None
                except Exception:
                    pass
        target_editor = editor if editor is not None else getattr(self, "_editor_widget", None)
        if target_editor is not None:
            for method_name in ("_abort_pending_editor_processing_ui_work", "_clear_processing_indicators", "_safe_enable_start_btn"):
                method = getattr(target_editor, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
            try:
                target_editor._subtitle_generation_completed = True
            except Exception:
                pass
            try:
                target_editor._is_ai_processing = False
            except Exception:
                pass
            try:
                target_editor._post_generation_models_release_requested = True
                target_editor._post_generation_models_released = False
            except Exception:
                pass
            try:
                state_manager = getattr(target_editor, "sm", None)
                if state_manager is not None and (
                    bool(getattr(state_manager, "is_locked", False))
                    or str(getattr(state_manager, "state", "") or "") == "ST_PROC"
                ):
                    state_manager.complete_ai()
            except Exception:
                pass
            for attr_name, empty_value in (
                ("_live_editor_preview_queue", []),
                ("_live_editor_preview_segments", []),
                ("_subtitle_context_window_index_cache", {}),
            ):
                try:
                    current = getattr(target_editor, attr_name, None)
                    if isinstance(current, list):
                        current.clear()
                    elif isinstance(current, dict):
                        current.clear()
                    else:
                        setattr(target_editor, attr_name, empty_value.copy() if hasattr(empty_value, "copy") else empty_value)
                except Exception:
                    pass
            try:
                target_editor._segment_cache_valid = False
            except Exception:
                pass
        for backend_name in ("backend", "backend_fast"):
            backend = getattr(self, backend_name, None)
            if backend is None:
                continue
            for thread_name in ("_pipeline_thread", "_eta_thread", "_cut_boundary_prescan_thread", "_cut_boundary_follower_thread"):
                thread = getattr(backend, thread_name, None)
                try:
                    if thread is not None and getattr(thread, "is_alive", lambda: False)():
                        thread.join(timeout=0.05)
                    if thread is not None and not getattr(thread, "is_alive", lambda: False)():
                        setattr(backend, thread_name, None)
                except Exception:
                    pass
        try:
            self._auto_processing_active = False
        except Exception:
            pass
        try:
            self._force_editor_idle_after_generation(target_editor, reason=reason)
        except Exception:
            self._restore_normal_cursor(self, target_editor)
        try:
            self._editor_ai_runtime_release_requested_for_editor_mode = True
            self._release_ai_models_for_editor_mode(
                force=True,
                preserve_roughcut_status=True,
                ollama_timeout_sec=1.2,
            )
        except Exception as exc:
            get_logger().log(f"⚠️ 생성 완료 직후 모델 즉시 종료 실패: {exc}")
        self._schedule_post_generation_gc(editor=target_editor, delay_ms=450)
        get_logger().log(f"🧹 후처리 정리 완료: {reason}")
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label()
        return {"cleaned": True, "reason": reason}

    def _is_user_activity_event(self, event) -> bool:
        if not getattr(self, "_post_completion_idle_enabled", False):
            return False
        return self._is_general_user_activity_event(event)

    def _start_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = True
        self._attach_app_event_filter()
        self._post_completion_idle_deadline_ms = QDateTime.currentMSecsSinceEpoch() + int(self._post_completion_idle_ms)
        self._post_completion_idle_timer.start(self._post_completion_idle_ms)
        self._post_completion_idle_countdown_timer.start()
        self._refresh_post_completion_idle_status()

    def _reset_post_completion_idle_timer(self):
        if getattr(self, "_post_completion_idle_enabled", False):
            self._post_completion_idle_deadline_ms = QDateTime.currentMSecsSinceEpoch() + int(self._post_completion_idle_ms)
            self._post_completion_idle_timer.start(self._post_completion_idle_ms)
            self._refresh_post_completion_idle_status()

    def _stop_post_completion_idle_timer(self):
        self._post_completion_idle_enabled = False
        self._post_completion_idle_deadline_ms = 0
        try:
            self._post_completion_idle_timer.stop()
        except Exception:
            pass
        try:
            self._post_completion_idle_countdown_timer.stop()
        except Exception:
            pass
        self._refresh_post_completion_idle_status()

    def _post_completion_idle_remaining_ms(self) -> int:
        if not getattr(self, "_post_completion_idle_enabled", False):
            return 0
        deadline = int(getattr(self, "_post_completion_idle_deadline_ms", 0) or 0)
        if deadline <= 0:
            return 0
        return max(0, deadline - QDateTime.currentMSecsSinceEpoch())

    def _refresh_post_completion_idle_status(self):
        if hasattr(self, "_refresh_saved_status_label"):
            self._refresh_saved_status_label()

    def _is_editor_actively_editing(self) -> bool:
        editor = getattr(self, "_editor_widget", None)
        if editor is None:
            return False
        state_manager = getattr(editor, "sm", None)
        if state_manager is not None:
            state = str(getattr(state_manager, "state", "") or "")
            if state in {"ST_EDITING", "ST_AUTOSAVE"}:
                return True
        timeline = getattr(editor, "timeline", None)
        canvas = getattr(timeline, "canvas", None) if timeline is not None else None
        if canvas is not None:
            if bool(getattr(canvas, "_edit_active", False)):
                return True
            if getattr(canvas, "_drag_seg", None) is not None:
                return True
        return False

    def _on_post_completion_idle_timeout(self):
        if self._is_editor_actively_editing():
            self._reset_post_completion_idle_timer()
            return
        self._post_completion_idle_enabled = False
        self._post_completion_idle_deadline_ms = 0
        try:
            self._post_completion_idle_countdown_timer.stop()
        except Exception:
            pass
        backend = getattr(self, "backend", None)
        if backend is not None and hasattr(backend, "_action_state") and hasattr(backend, "_edit_event"):
            try:
                backend._action_state[0] = "exit"
                backend._edit_event.set()
                return
            except Exception:
                pass
        self.show_home(allow_home_idle_learning=True)

    # ── 로그 토글 ────────────────────────────────────────
    def _apply_log_visible(self, visible: bool, *, persist: bool = True):
        visible = True
        previous_visible = bool(getattr(self, "_log_visible", True))
        self._log_visible = bool(visible)
        self._project_panel_visible = self._log_visible
        sidebar = getattr(self, "home_page", None)
        splitter = getattr(self, "workspace_splitter", None)
        prev_sizes = []
        if splitter is not None:
            try:
                prev_sizes = list(splitter.sizes())
            except Exception:
                prev_sizes = []
        if sidebar is not None:
            sidebar.setVisible(self._log_visible)
        if splitter is not None and previous_visible != self._log_visible:
            total = max(1, sum(splitter.sizes()) or splitter.width() or 1600)
            if self._log_visible:
                current_sidebar_w = int(prev_sizes[0]) if len(prev_sizes) >= 2 else 0
                if current_sidebar_w > 0:
                    sidebar_w = current_sidebar_w
                else:
                    sidebar_w = min(218, max(204, int(total * 0.14)))
                splitter.setSizes([sidebar_w, max(1, total - sidebar_w)])
            else:
                splitter.setSizes([0, total])
        panel = getattr(self, "bottom_work_panel", None)
        if panel is not None:
            panel.set_log_visible(True)
        terminal = self._ensure_sidebar_terminal_panel() if hasattr(self, "_ensure_sidebar_terminal_panel") else getattr(self, "sidebar_terminal_panel", None)
        if terminal is not None:
            terminal.setVisible(self._log_visible)
        if hasattr(self, "global_menu_bar"):
            self.global_menu_bar.refresh()
        self._apply_responsive_workspace_layout()

    def _toggle_log(self):
        self._apply_log_visible(not self._log_visible)
        if hasattr(self, "show_home") and self.stack.currentWidget() is self.home_page:
            self.show_home()
        for c in getattr(self, "_preview_containers", []):
            try:
                c.setVisible(not self._log_visible)
            except Exception:
                pass
        try:
            settings = load_settings()
            settings["show_terminal_log"] = self._log_visible
            settings["sidebar_visible"] = self._log_visible
            save_settings(settings)
        except Exception as e:
            get_logger().log(f"⚠️ 사이드바 표시 설정 저장 실패: {e}")
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

    def _shutdown_personalization_idle_trainer(
        self,
        *,
        timeout_sec: float = 3.0,
        cleanup: bool = True,
        recover: bool = True,
    ):
        trainer = getattr(self, "_personalization_idle_trainer", None)
        if trainer is None:
            return {"stopped": True, "busy": False}
        try:
            try:
                import inspect

                params = inspect.signature(trainer.shutdown).parameters
                kwargs = {}
                if "timeout_sec" in params:
                    kwargs["timeout_sec"] = timeout_sec
                if "cleanup" in params:
                    kwargs["cleanup"] = cleanup
                if "recover" in params:
                    kwargs["recover"] = recover
                result = trainer.shutdown(**kwargs)
            except (TypeError, ValueError):
                try:
                    result = trainer.shutdown(timeout_sec=timeout_sec)
                except TypeError:
                    result = trainer.shutdown()
        except Exception as exc:
            get_logger().log(f"⚠️ 개인화 학습 종료 처리 실패: {exc}")
            return {"stopped": False, "busy": True}
        if bool(result.get("busy")):
            get_logger().log("⚠️ 개인화 학습 작업이 아직 종료 중입니다. 현재 클립 처리가 끝나면 대기 상태로 복구됩니다.")
        return result

    def closeEvent(self, event):
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() == "offscreen":
            try:
                self._detach_app_event_filter()
            except Exception:
                pass
            event.accept()
            return
        if bool(getattr(self, "_quick_exit_requested", False)):
            try:
                get_logger().clear_ui_callback()
            except Exception:
                pass
            try:
                self.blockSignals(True)
            except Exception:
                pass
            try:
                QApplication.quit()
            except Exception:
                pass
            event.accept()
            return
        confirm_exit = getattr(self, "_confirm_save_dirty_editor_before_exit", None)
        if callable(confirm_exit) and not confirm_exit():
            event.ignore()
            return
        try:
            self._schedule_forced_process_exit(delay_ms=30 if getattr(config, "IS_MAC", False) else 60)
        except Exception:
            pass
        busy_before_exit = False
        try:
            busy_before_exit = bool(self._has_active_runtime_work_for_exit())
        except Exception:
            pass
        try:
            self._pause_all_runtime_work_for_exit(context="앱 종료")
        except Exception as exc:
            try:
                get_logger().log(f"⚠️ 종료 중 작업 일시정지 실패: {exc}")
            except Exception:
                pass
        if str(os.environ.get("QT_QPA_PLATFORM", "")).lower() != "offscreen":
            try:
                async_cleanup = getattr(self, "_start_runtime_cleanup_for_app_exit_async", None)
                if callable(async_cleanup):
                    async_cleanup(timeout_sec=0.08 if getattr(config, "IS_MAC", False) else 0.15)
                else:
                    self._cleanup_runtime_for_app_exit(timeout_sec=0.08 if getattr(config, "IS_MAC", False) else 0.15)
            except Exception:
                pass
        if not busy_before_exit:
            try:
                self._backup_before_quick_exit(include_project_backup=False)
            except Exception:
                pass
        try:
            get_logger().clear_ui_callback()
        except Exception:
            pass
        try:
            self.blockSignals(True)
        except Exception:
            pass
        event.accept()
