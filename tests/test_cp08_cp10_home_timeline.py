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
from PyQt6.QtWidgets import QApplication

from core.project.project_phase1b import apply_project_ui_state
from ui.main.main_window import MainWindow


class Cp08Cp10HomeTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _cleanup_window(self, window):
        window.close()
        window.deleteLater()
        self.app.processEvents()

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
            with patch("ui.home_ui.load_settings", return_value={"auto_start_enabled": True}), \
                 patch("ui.home_ui.save_settings"), \
                 patch.object(window, "_start_configured_watchers"):
                window._toggle_auto_start_enabled()
            self.assertIs(window.stack.currentWidget(), before)
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
            apply_project_ui_state(owner, editor, project_path)
            self.assertEqual(timeline.fit_called, 1)
            self.assertEqual(timeline.canvas.pps, 123.0)
            self.assertEqual(timeline.scroll.bar.set_calls, [])
        finally:
            os.remove(project_path)


if __name__ == "__main__":
    unittest.main()
