import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from ui.main.main_window import MainWindow


class MainWindowNonfatalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_window(self):
        patches = (
            mock.patch("ui.main.main_window.load_settings", return_value={"auto_start_enabled": False}),
            mock.patch("ui.main.main_window.get_icloud_auto_detect", return_value=False),
            mock.patch("ui.main.main_window.get_nas_auto_detect", return_value=False),
            mock.patch.object(MainWindow, "_warmup_local_llm_models", lambda self: None),
            mock.patch.object(MainWindow, "_preflight_selected_local_llm_models", lambda self: None),
            mock.patch.object(MainWindow, "_check_required_models_on_startup", lambda self: None),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            return MainWindow()

    def _cleanup_window(self, window):
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_post_show_startup_ignores_trainer_recovery_error(self):
        window = self._make_window()
        try:
            trainer = SimpleNamespace(
                recover_startup_jobs_async=mock.Mock(side_effect=RuntimeError("trainer boom"))
            )
            window._personalization_idle_trainer = trainer
            window._post_show_startup_started = False

            window._start_post_show_startup_tasks()

            self.assertTrue(window._post_show_startup_started)
            trainer.recover_startup_jobs_async.assert_called_once()
        finally:
            self._cleanup_window(window)

    def test_start_auto_watchers_after_launch_ignores_watcher_errors(self):
        window = self._make_window()
        try:
            cloud_manager = SimpleNamespace(start=mock.Mock(side_effect=RuntimeError("cloud boom")))
            window._auto_start_on = True
            window._is_icloud_auto_mode = True
            window._is_nas_auto_mode = False
            window._cloud_sync_manager = cloud_manager

            window._start_auto_watchers_after_launch()

            cloud_manager.start.assert_called_once()
        finally:
            self._cleanup_window(window)

    def test_optional_startup_tasks_defer_while_editor_is_active(self):
        window = self._make_window()
        try:
            window._offscreen_test = False
            window._editor_widget = object()
            window._startup_warmup_pending = True
            window._startup_required_model_check_pending = True
            window._startup_llm_preflight_pending = True
            window._startup_auto_watchers_pending = True
            window._pending_initial_home_auto_source_refresh = True
            window._start_initial_home_auto_source_refresh = mock.Mock()
            window._warmup_local_llm_models = mock.Mock()
            window._check_required_models_on_startup = mock.Mock()
            window._preflight_selected_local_llm_models = mock.Mock()
            window._start_auto_watchers_after_launch = mock.Mock()
            window._schedule_optional_startup_tasks = mock.Mock()

            window._run_optional_startup_tasks()

            window._schedule_optional_startup_tasks.assert_called_once()
            window._start_initial_home_auto_source_refresh.assert_not_called()
            window._warmup_local_llm_models.assert_not_called()
            window._check_required_models_on_startup.assert_not_called()
            window._preflight_selected_local_llm_models.assert_not_called()
            window._start_auto_watchers_after_launch.assert_not_called()
            self.assertTrue(window._startup_warmup_pending)
            self.assertTrue(window._pending_initial_home_auto_source_refresh)
        finally:
            self._cleanup_window(window)

    def test_optional_startup_tasks_run_when_home_is_ready(self):
        window = self._make_window()
        try:
            window._offscreen_test = False
            window._editor_widget = None
            window.stack.setCurrentIndex(0)
            window._auto_processing_active = False
            window._startup_warmup_pending = True
            window._startup_required_model_check_pending = True
            window._startup_llm_preflight_pending = True
            window._startup_auto_watchers_pending = True
            window._pending_initial_home_auto_source_refresh = True
            window._start_initial_home_auto_source_refresh = mock.Mock()
            window._warmup_local_llm_models = mock.Mock()
            window._check_required_models_on_startup = mock.Mock()
            window._preflight_selected_local_llm_models = mock.Mock()
            window._start_auto_watchers_after_launch = mock.Mock()

            window._run_optional_startup_tasks()

            window._start_initial_home_auto_source_refresh.assert_called_once_with(delay_ms=0)
            window._warmup_local_llm_models.assert_called_once()
            window._check_required_models_on_startup.assert_called_once()
            window._preflight_selected_local_llm_models.assert_called_once()
            window._start_auto_watchers_after_launch.assert_called_once()
            self.assertFalse(window._startup_warmup_pending)
            self.assertFalse(window._startup_required_model_check_pending)
            self.assertFalse(window._startup_llm_preflight_pending)
            self.assertFalse(window._startup_auto_watchers_pending)
            self.assertFalse(window._pending_initial_home_auto_source_refresh)
        finally:
            self._cleanup_window(window)

    def test_show_home_compacts_hidden_workspace_widgets_when_idle(self):
        window = self._make_window()
        try:
            editor = SimpleNamespace(enter_home_compact_mode=mock.Mock())
            roughcut = SimpleNamespace(compact_for_home_navigation=mock.Mock())
            window._editor_widget = editor
            window._roughcut_widget = roughcut
            window._is_editor_ai_busy = mock.Mock(return_value=False)
            window._is_backend_ai_busy = mock.Mock(return_value=False)
            window._cleanup_runtime_for_navigation = mock.Mock()
            window._build_home_content = mock.Mock()
            window._schedule_optional_startup_tasks = mock.Mock()
            window._stop_post_completion_idle_timer = mock.Mock()
            window._reset_transient_multiclip_state = mock.Mock()
            window._dock_global_menu_to_workspace = mock.Mock()
            window._show_bottom_queue_table = mock.Mock()

            window.show_home()

            editor.enter_home_compact_mode.assert_called_once()
            roughcut.compact_for_home_navigation.assert_called_once()
        finally:
            self._cleanup_window(window)

    def test_show_home_skips_compaction_while_active_work(self):
        window = self._make_window()
        try:
            editor = SimpleNamespace(enter_home_compact_mode=mock.Mock())
            roughcut = SimpleNamespace(compact_for_home_navigation=mock.Mock())
            window._editor_widget = editor
            window._roughcut_widget = roughcut
            window._is_editor_ai_busy = mock.Mock(return_value=True)
            window._is_backend_ai_busy = mock.Mock(return_value=False)
            window._cleanup_runtime_for_navigation = mock.Mock()
            window._build_home_content = mock.Mock()
            window._schedule_optional_startup_tasks = mock.Mock()
            window._stop_post_completion_idle_timer = mock.Mock()
            window._reset_transient_multiclip_state = mock.Mock()
            window._dock_global_menu_to_workspace = mock.Mock()
            window._show_bottom_queue_table = mock.Mock()

            window.show_home()

            editor.enter_home_compact_mode.assert_not_called()
            roughcut.compact_for_home_navigation.assert_not_called()
        finally:
            self._cleanup_window(window)

    def test_defer_home_action_does_not_reenter_qt_event_loop(self):
        window = self._make_window()
        try:
            widget = QWidget(window.home_page)
            widget.setObjectName("MenuButton")
            widget._normal_ss = "QWidget#MenuButton { background: #000; }"
            widget.setStyleSheet("QWidget#MenuButton { background: #fff; }")
            action = mock.Mock()

            with mock.patch("PyQt6.QtWidgets.QApplication.processEvents", side_effect=AssertionError("should not run")):
                with mock.patch("ui.home_ui.QTimer.singleShot") as single_shot:
                    window._defer_home_action(widget, action)

            single_shot.assert_called_once_with(100, action)
            self.assertIn("#000", widget.styleSheet())
        finally:
            self._cleanup_window(window)

    def test_restore_editor_video_after_navigation_prefers_editor_restore_hook(self):
        window = self._make_window()
        try:
            restore_editor = mock.Mock()
            restore_video = mock.Mock()
            editor = SimpleNamespace(
                leave_home_compact_mode=restore_editor,
                video_player=SimpleNamespace(restore_after_navigation=restore_video),
            )

            window._restore_editor_video_after_navigation(editor)

            restore_editor.assert_called_once()
            restore_video.assert_not_called()
        finally:
            self._cleanup_window(window)

    def test_initial_home_auto_source_refresh_defers_until_home_ready(self):
        window = self._make_window()
        try:
            window._offscreen_test = False
            window._initial_home_scan_deferred = True
            window._editor_widget = object()
            window._schedule_optional_startup_tasks = mock.Mock()

            window._start_initial_home_auto_source_refresh(delay_ms=123)

            self.assertTrue(window._pending_initial_home_auto_source_refresh)
            self.assertFalse(window._home_auto_source_refresh_inflight)
            window._schedule_optional_startup_tasks.assert_called_once_with(delay_ms=123)
        finally:
            self._cleanup_window(window)

    def test_home_auto_sources_ready_ignores_rebuild_error_and_keeps_cache(self):
        window = self._make_window()
        try:
            window._initial_home_scan_deferred = True
            window._home_auto_source_refresh_inflight = True
            window._home_auto_source_refresh_token = 3
            window._build_home_content = mock.Mock(side_effect=RuntimeError("rebuild boom"))
            window.stack.setCurrentIndex(0)

            payload = {
                "token": 3,
                "icloud": ([("sample.mp4", "/tmp/sample.mp4")], "대기", ""),
                "nas": ([("folder", "/tmp/folder")], "경로 없음", ""),
            }
            window._on_home_auto_sources_ready(payload)

            self.assertFalse(window._initial_home_scan_deferred)
            self.assertFalse(window._home_auto_source_refresh_inflight)
            self.assertEqual(window._home_auto_source_cache["icloud"][1], "대기")
            self.assertEqual(window._home_auto_source_cache["nas"][0][0][0], "folder")
            window._build_home_content.assert_called_once()
        finally:
            self._cleanup_window(window)

    def test_initialize_runtime_memory_manager_ignores_creation_error(self):
        window = self._make_window()
        try:
            with mock.patch("ui.main.main_window.RuntimeMemoryManager", side_effect=RuntimeError("memory boom")):
                window._initialize_runtime_memory_manager(settings={"interval_ms": 1234})

            self.assertIsNone(window._runtime_memory_manager)
            self.assertFalse(window._runtime_memory_timer.isActive())
        finally:
            self._cleanup_window(window)

    def test_poll_runtime_resource_coordinator_keeps_snapshot_when_refresh_fails(self):
        window = self._make_window()
        try:
            coordinator = SimpleNamespace(poll=mock.Mock(return_value={"stage": "normal"}))
            window._runtime_resource_coordinator = coordinator
            window._refresh_sidebar_runtime_monitor = mock.Mock(side_effect=RuntimeError("sidebar boom"))
            window._refresh_saved_status_label = mock.Mock(side_effect=RuntimeError("status boom"))
            window._last_saved_status_dirty = True

            window._poll_runtime_resource_coordinator()

            self.assertEqual(window._runtime_resource_snapshot, {"stage": "normal"})
            coordinator.poll.assert_called_once()
            window._refresh_sidebar_runtime_monitor.assert_called_once()
            window._refresh_saved_status_label.assert_called_once_with(is_dirty=True)
        finally:
            self._cleanup_window(window)

    def test_apply_responsive_workspace_layout_ignores_sidebar_and_splitter_errors(self):
        window = self._make_window()
        try:
            class _BadSidebar:
                def __init__(self):
                    self.min_calls = 0
                    self.max_calls = 0

                def setMinimumWidth(self, _value):
                    self.min_calls += 1

                def setMaximumWidth(self, _value):
                    self.max_calls += 1
                    raise RuntimeError("sidebar max boom")

            class _BadSplitter:
                def __init__(self):
                    self.set_calls = 0

                def setSizes(self, _sizes):
                    self.set_calls += 1
                    raise RuntimeError("splitter boom")

                def sizes(self):
                    return [220, 1200]

            sidebar = _BadSidebar()
            splitter = _BadSplitter()
            window.resize(1600, 900)
            window.home_page = sidebar
            window.workspace_splitter = splitter
            window._log_visible = True
            window._workspace_sidebar_locked_width = 320

            window._apply_responsive_workspace_layout()

            self.assertEqual(sidebar.min_calls, 2)
            self.assertEqual(sidebar.max_calls, 2)
            self.assertEqual(splitter.set_calls, 1)
        finally:
            self._cleanup_window(window)

    def test_ensure_sidebar_terminal_panel_recreates_panel_after_runtime_error(self):
        window = self._make_window()
        try:
            class _BadPanel:
                @property
                def log_text(self):
                    raise RuntimeError("panel gone")

            replacement = object()
            window.sidebar_terminal_panel = _BadPanel()
            with mock.patch.object(window, "_create_sidebar_terminal_panel", return_value=replacement) as rebuild:
                result = window._ensure_sidebar_terminal_panel()

            self.assertIs(result, replacement)
            rebuild.assert_called_once()
        finally:
            self._cleanup_window(window)


if __name__ == "__main__":
    unittest.main()
