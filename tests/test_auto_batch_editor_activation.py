# Version: 03.15.00
# Phase: PHASE2
import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from core.state_manager import SubtitleStateManager
from ui.main.main_window import MainWindow


class _DummyEditor(QWidget):
    def __init__(self, media_path: str, parent=None):
        super().__init__(parent)
        self.media_path = media_path
        self.is_auto_start = False
        self.sm = SubtitleStateManager()
        self.sm.init_state()


class AutoBatchEditorActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_worker_can_activate_processing_editor_for_auto_batch(self):
        target_file = "/tmp/queue_auto_batch_sample.mp4"
        with patch("ui.main.main_window.load_settings", return_value={"auto_start_enabled": False}), \
             patch.object(MainWindow, "_warmup_local_llm_models", lambda self: None), \
             patch.object(MainWindow, "_preflight_selected_local_llm_models", lambda self: None), \
             patch.object(MainWindow, "_check_required_models_on_startup", lambda self: None):
            window = MainWindow()

        def fake_open_editor(target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
            editor = _DummyEditor(target_file, window.stack)
            old = getattr(window, "_editor_widget", None)
            if old is not None:
                try:
                    if window.stack.indexOf(old) >= 0:
                        window.stack.removeWidget(old)
                except Exception:
                    pass
            window._editor_widget = editor
            if window.stack.indexOf(editor) < 0:
                window.stack.insertWidget(1, editor)
            window.stack.setCurrentWidget(editor)

        result_box = {}

        def worker():
            result_box["ok"] = window.ensure_processing_editor(target_file, timeout_sec=1.5)

        try:
            with patch.object(window, "_do_open_editor", side_effect=fake_open_editor):
                thread = threading.Thread(target=worker, daemon=True)
                thread.start()

                deadline = time.monotonic() + 2.0
                while thread.is_alive() and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                thread.join(timeout=0.2)

            self.app.processEvents()

            self.assertTrue(result_box.get("ok"))
            self.assertIsNotNone(window._editor_widget)
            self.assertEqual(window._editor_widget.media_path, target_file)
            self.assertTrue(window._editor_widget.is_auto_start)
            self.assertEqual(window._editor_widget.sm.state, SubtitleStateManager.ST_PROC)
            self.assertIs(window.stack.currentWidget(), window._editor_widget)
        finally:
            try:
                window._cloud_sync_manager.stop()
            except Exception:
                pass
            try:
                window._nas_sync_manager.stop()
            except Exception:
                pass
            try:
                window.stack.setCurrentIndex(0)
            except Exception:
                pass
            try:
                if getattr(window, "_editor_widget", None) is not None:
                    window._editor_widget.sm.is_dirty = False
            except Exception:
                pass
            window.close()

    def test_worker_waits_until_editor_is_replaced_for_next_queue_file(self):
        target_file = "/tmp/queue_next_clip_sample.mp4"
        with patch("ui.main.main_window.load_settings", return_value={"auto_start_enabled": False}), \
             patch.object(MainWindow, "_warmup_local_llm_models", lambda self: None), \
             patch.object(MainWindow, "_preflight_selected_local_llm_models", lambda self: None), \
             patch.object(MainWindow, "_check_required_models_on_startup", lambda self: None):
            window = MainWindow()

        def fake_open_editor(target_file, on_save, on_start, on_prev, on_exit, is_batch=False):
            editor = _DummyEditor(target_file, window.stack)
            editor.is_auto_start = bool(is_batch)
            old = getattr(window, "_editor_widget", None)
            if old is not None:
                try:
                    if window.stack.indexOf(old) >= 0:
                        window.stack.removeWidget(old)
                except Exception:
                    pass
            window._editor_widget = editor
            if window.stack.indexOf(editor) < 0:
                window.stack.insertWidget(1, editor)
            window.stack.setCurrentWidget(editor)

        result_box = {}

        def worker():
            result_box["ok"] = window.open_editor_for_file_and_wait(
                target_file,
                lambda *_args: None,
                lambda *_args: None,
                lambda *_args: None,
                lambda *_args: None,
                is_batch=True,
                timeout_sec=1.5,
            )

        try:
            with patch.object(window, "_do_open_editor", side_effect=fake_open_editor):
                thread = threading.Thread(target=worker, daemon=True)
                thread.start()

                deadline = time.monotonic() + 2.0
                while thread.is_alive() and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                thread.join(timeout=0.2)

            self.app.processEvents()

            self.assertTrue(result_box.get("ok"))
            self.assertIsNotNone(window._editor_widget)
            self.assertEqual(window._editor_widget.media_path, target_file)
            self.assertTrue(window._editor_widget.is_auto_start)
            self.assertIs(window.stack.currentWidget(), window._editor_widget)
        finally:
            try:
                window._cloud_sync_manager.stop()
            except Exception:
                pass
            try:
                window._nas_sync_manager.stop()
            except Exception:
                pass
            try:
                window.stack.setCurrentIndex(0)
            except Exception:
                pass
            try:
                if getattr(window, "_editor_widget", None) is not None:
                    window._editor_widget.sm.is_dirty = False
            except Exception:
                pass
            window.close()


if __name__ == "__main__":
    unittest.main()
