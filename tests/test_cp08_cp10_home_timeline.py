# Version: 03.01.35
# Phase: PHASE2
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.project.project_phase1b import apply_project_ui_state
from ui.main.main_window import MainWindow


class Cp08Cp10HomeTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_idle_countdown_is_shown_next_to_version(self):
        window = MainWindow()
        try:
            window._post_completion_idle_ms = 10_000
            window._start_post_completion_idle_timer()
            text = window.saved_status_label.text()
            self.assertIn("홈", text)
            self.assertIn("v", text)
            self.assertGreater(window._post_completion_idle_remaining_ms(), 0)
        finally:
            window.close()

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
            window.close()

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
            window.close()

    def test_missing_project_zoom_fits_timeline_once(self):
        class DummyTimeline:
            def __init__(self):
                self.canvas = SimpleNamespace(pps=123.0, update=lambda: None)
                self.scroll = None
                self.lock_chk = None
                self.fit_called = 0

            def fit_to_view(self):
                self.fit_called += 1

        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump({"workspace": {}}, handle)
            project_path = handle.name
        try:
            timeline = DummyTimeline()
            editor = SimpleNamespace(timeline=timeline)
            owner = SimpleNamespace()
            apply_project_ui_state(owner, editor, project_path)
            self.assertEqual(timeline.fit_called, 1)
        finally:
            os.remove(project_path)


if __name__ == "__main__":
    unittest.main()
