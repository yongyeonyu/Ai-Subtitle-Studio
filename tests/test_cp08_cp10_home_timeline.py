# Version: 03.09.28
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication, QLabel

from core.project.project_phase1b import apply_project_ui_state
import ui.main.main_window as main_window_module
from ui.main.main_window import MainWindow


class Cp08Cp10HomeTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _cleanup_window(self, window):
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_main_window_imports_runtime_config_for_gui_launch_timers(self):
        self.assertTrue(hasattr(main_window_module, "config"))
        self.assertTrue(hasattr(main_window_module.config, "IS_MAC"))

    def test_post_completion_idle_default_is_ten_minutes(self):
        window = MainWindow()
        try:
            self.assertEqual(window._post_completion_idle_ms, 600_000)
        finally:
            self._cleanup_window(window)

    def test_idle_countdown_keeps_header_compact(self):
        window = MainWindow()
        try:
            window._post_completion_idle_ms = 10_000
            window._start_post_completion_idle_timer()
            text = window.saved_status_label.text()
            self.assertNotIn("홈", text)
            self.assertIn("AI Subtitle Studio", text)
            self.assertIn("v", text)
            self.assertGreater(window._post_completion_idle_remaining_ms(), 0)
        finally:
            self._cleanup_window(window)

    def test_home_build_uses_loading_placeholder_when_initial_auto_scan_is_deferred(self):
        window = MainWindow()
        try:
            window._initial_home_scan_deferred = True
            window._home_auto_source_cache = {}
            with patch.object(window, "_start_initial_home_auto_source_refresh") as start_refresh, \
                 patch.object(window, "_get_icloud_files", side_effect=AssertionError("icloud sync scan should stay deferred")), \
                 patch.object(window, "_get_nas_folders", side_effect=AssertionError("nas sync scan should stay deferred")):
                window._build_home_content()
            texts = [label.text() for label in window.home_page.findChildren(QLabel)]
            self.assertGreaterEqual(texts.count("불러오는 중"), 2)
            start_refresh.assert_called()
        finally:
            self._cleanup_window(window)

    def test_home_auto_scan_ready_rebuilds_home_with_cached_results(self):
        window = MainWindow()
        try:
            window._initial_home_scan_deferred = True
            window._home_auto_source_refresh_token = 7
            with patch.object(window, "_build_home_content") as rebuild:
                window._on_home_auto_sources_ready(
                    {
                        "token": 7,
                        "icloud": ([("sample.mp4", "/tmp/sample.mp4")], "대기: 영상 1개", "완료: 영상 0개"),
                        "nas": ([("folder", "/tmp/folder")], "경로 없음", ""),
                    }
                )
            self.assertFalse(window._initial_home_scan_deferred)
            self.assertEqual(window._home_auto_source_cache["icloud"][1], "대기: 영상 1개")
            self.assertEqual(window._home_auto_source_cache["nas"][0][0][0], "folder")
            rebuild.assert_called_once()
        finally:
            self._cleanup_window(window)

    def test_idle_timeout_is_extended_while_editor_is_editing(self):
        window = MainWindow()
        try:
            window._post_completion_idle_ms = 10_000
            window._editor_widget = SimpleNamespace(sm=SimpleNamespace(state="ST_EDITING"))
            window._start_post_completion_idle_timer()
            window._on_post_completion_idle_timeout()
            self.assertTrue(window._post_completion_idle_enabled)
            self.assertGreater(window._post_completion_idle_remaining_ms(), 0)
        finally:
            self._cleanup_window(window)

    def test_idle_timeout_returns_home_and_allows_home_idle_learning(self):
        window = MainWindow()
        try:
            trainer = getattr(window, "_personalization_idle_trainer", None)
            self.assertIsNotNone(trainer)
            window._post_completion_idle_ms = 10_000
            window.stack.setCurrentWidget(window.editor_page)

            with patch.object(window, "show_home", wraps=window.show_home) as show_home, \
                 patch.object(trainer, "resume_for_home_idle", wraps=trainer.resume_for_home_idle) as resume_home:
                window._start_post_completion_idle_timer()
                window._on_post_completion_idle_timeout()

            show_home.assert_called_once_with(allow_home_idle_learning=True)
            resume_home.assert_called_once_with(preserve_idle_age=True, start_if_ready=True)
        finally:
            self._cleanup_window(window)

    def test_general_user_activity_refreshes_personalization_idle_timer_without_post_completion_mode(self):
        window = MainWindow()
        try:
            trainer = getattr(window, "_personalization_idle_trainer", None)
            self.assertIsNotNone(trainer)
            trainer.last_user_activity_ms = 0

            event = QEvent(QEvent.Type.MouseButtonPress)
            window.eventFilter(window, event)

            self.assertGreater(int(getattr(trainer, "last_user_activity_ms", 0) or 0), 0)
            self.assertFalse(window._post_completion_idle_enabled)
        finally:
            self._cleanup_window(window)

    def test_mouse_move_interrupts_busy_personalization_training_immediately(self):
        window = MainWindow()
        try:
            trainer = getattr(window, "_personalization_idle_trainer", None)
            self.assertIsNotNone(trainer)
            with patch.object(trainer, "request_immediate_stop", return_value={"suspended": True}) as request_stop:
                event = QEvent(QEvent.Type.MouseMove)
                window.eventFilter(window, event)

            request_stop.assert_called_once_with(
                reason="user_input_interrupt",
                hold_ms=0,
                join_timeout_sec=0.03,
            )
        finally:
            self._cleanup_window(window)

    def test_mouse_button_and_wheel_interrupt_personalization_training_immediately(self):
        window = MainWindow()
        try:
            trainer = getattr(window, "_personalization_idle_trainer", None)
            self.assertIsNotNone(trainer)
            with patch.object(trainer, "request_immediate_stop", return_value={"suspended": True}) as request_stop:
                for event_type in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.Wheel):
                    window.eventFilter(window, QEvent(event_type))

            self.assertEqual(request_stop.call_count, 3)
        finally:
            self._cleanup_window(window)

    def test_key_press_notifies_registered_personalization_stop_targets(self):
        window = MainWindow()
        try:
            class StopTarget:
                def __init__(self):
                    self.called = 0

                def _request_stop_for_user_input(self):
                    self.called += 1
                    return True

            target = StopTarget()
            window._register_personalization_learning_dialog(target)

            event = QEvent(QEvent.Type.KeyPress)
            window.eventFilter(window, event)

            self.assertEqual(target.called, 1)
        finally:
            self._cleanup_window(window)

    def test_personalization_dialog_defers_expensive_summary_until_visible(self):
        from ui.settings.settings_personalization import PersonalizationLearningDialog

        with patch("ui.settings.settings_personalization.initialize_lora_personalization_store") as init_store, \
             patch("ui.settings.settings_personalization.build_text_lora_dataset") as build_dataset, \
             patch("ui.settings.settings_personalization.refresh_lora_personalization_manifest") as refresh_manifest:
            dialog = PersonalizationLearningDialog(None)
            try:
                self.assertIn("불러오는 중", dialog.summary_label.text())
                init_store.assert_not_called()
                build_dataset.assert_not_called()
                refresh_manifest.assert_not_called()
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()

    def test_personalization_full_learning_enables_stop_during_prepare(self):
        from core.personalization.idle_trainer import clear_personalization_training_interrupt
        from ui.settings.settings_personalization import PersonalizationLearningDialog

        fake_threads = []

        class _FakeThread:
            def __init__(self, *, target, name=None, daemon=False):
                self.target = target
                self.name = name
                self.daemon = daemon
                self.started = False
                fake_threads.append(self)

            def start(self):
                self.started = True

            def is_alive(self):
                return self.started

        dialog = PersonalizationLearningDialog(None)
        try:
            dialog._trainer = lambda: SimpleNamespace(is_busy=lambda: False)
            dialog._resolve_pairs_for_import = lambda: {"pairs": [], "unresolved": []}
            dialog._current_editor_segments = lambda: ([], "")
            with patch("ui.settings.settings_personalization.threading.Thread", _FakeThread):
                dialog._start_full_learning()

            self.assertTrue(fake_threads)
            self.assertTrue(dialog.btn_stop_full_learning.isEnabled())
            self.assertFalse(dialog.btn_start_auto_learning.isEnabled())
            self.assertEqual(dialog.btn_start_auto_learning.text(), "준비 중...")

            dialog._stop_full_learning()
            self.assertTrue(dialog._pending_queue_batch_stop_requested)
        finally:
            clear_personalization_training_interrupt()
            dialog._full_learning_prepare_timer.stop()
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_lora_learning_info_dialog_defers_payload_build_until_event_loop(self):
        from ui.settings.personalization_learning_info import PersonalizationLearningInfoDialog

        with patch("ui.settings.personalization_learning_info.build_learning_info_payload") as build_payload:
            dialog = PersonalizationLearningInfoDialog(None)
            try:
                self.assertIn("불러오는 중", dialog.header_label.text())
                build_payload.assert_not_called()
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()

    def test_main_window_installs_app_event_filter_for_personalization_idle_tracking(self):
        window = MainWindow()
        try:
            self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))
        finally:
            self._cleanup_window(window)

    def test_main_window_detaches_app_event_filter_on_close(self):
        window = MainWindow()
        self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))

        window.close()

        self.assertFalse(bool(getattr(window, "_app_event_filter_installed", False)))
        self._cleanup_window(window)

    def test_stopping_post_completion_idle_timer_keeps_personalization_event_filter_installed(self):
        window = MainWindow()
        try:
            window._start_post_completion_idle_timer()
            self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))

            window._stop_post_completion_idle_timer()

            self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))
        finally:
            self._cleanup_window(window)

    def test_post_completion_idle_timeout_keeps_personalization_event_filter_installed(self):
        window = MainWindow()
        try:
            window._start_post_completion_idle_timer()
            self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))

            window._on_post_completion_idle_timeout()

            self.assertTrue(bool(getattr(window, "_app_event_filter_installed", False)))
        finally:
            self._cleanup_window(window)

    def test_auto_toggle_keeps_current_workspace_page(self):
        window = MainWindow()
        try:
            window.stack.setCurrentWidget(window.editor_page)
            before = window.stack.currentWidget()
            with patch(
                "ui.home_ui.load_path_settings",
                return_value={"icloud_auto_detect": True, "nas_auto_detect": True, "auto_start_enabled": True},
            ), \
                 patch("ui.home_ui.save_path_settings"), \
                 patch.object(window, "_start_configured_watchers"):
                window._toggle_auto_start_enabled()
            self.assertIs(window.stack.currentWidget(), before)
        finally:
            self._cleanup_window(window)

    def test_auto_toggle_button_turns_off_both_auto_scopes_together(self):
        saved = {}

        def _save_path_settings(settings):
            saved.update(settings)

        window = MainWindow()
        try:
            with patch(
                "ui.home_ui.load_path_settings",
                return_value={"icloud_auto_detect": True, "nas_auto_detect": True, "auto_start_enabled": True},
            ), \
                 patch("ui.home_ui.save_path_settings", side_effect=_save_path_settings), \
                 patch.object(window, "_refresh_after_auto_start_toggle"), \
                 patch.object(window, "_stop_auto_watchers"):
                window._toggle_auto_start_enabled()

            self.assertFalse(saved["icloud_auto_detect"])
            self.assertFalse(saved["nas_auto_detect"])
            self.assertFalse(saved["auto_start_enabled"])
        finally:
            self._cleanup_window(window)

    def test_saved_project_zoom_is_ignored_and_timeline_fits(self):
        class DummyScrollBar:
            def __init__(self):
                self.value = 0
                self.set_calls = []

            def setValue(self, value):
                self.value = int(value)
                self.set_calls.append(int(value))

        class DummyScroll:
            def __init__(self):
                self.bar = DummyScrollBar()

            def horizontalScrollBar(self):
                return self.bar

        class DummyTimeline:
            def __init__(self):
                self.canvas = SimpleNamespace(pps=123.0, update=lambda: None)
                self.scroll = DummyScroll()
                self.lock_chk = None
                self.fit_called = 0

            def fit_to_view(self):
                self.fit_called += 1

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump({"workspace": {"zoom_pps": 999.0, "scroll_x": 500}}, handle)
            project_path = handle.name
        try:
            timeline = DummyTimeline()
            editor = SimpleNamespace(timeline=timeline)
            owner = SimpleNamespace()
            with patch("core.project.project_phase1b.QTimer.singleShot", side_effect=lambda _delay, cb: cb()):
                apply_project_ui_state(owner, editor, project_path)
            self.assertEqual(timeline.fit_called, 1)
            self.assertEqual(timeline.canvas.pps, 123.0)
            self.assertEqual(timeline.scroll.bar.set_calls, [])
        finally:
            os.remove(project_path)


if __name__ == "__main__":
    unittest.main()
