import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog

from ui.main.main_file_ops import FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS, FileOpsMixin
from ui.main.main_window import MainWindow


class _FileOpsWindow(FileOpsMixin):
    def __init__(self):
        self._editor_widget = None
        self._quick_exit_requested = False
        self.backend = None

    def close(self):
        self.closed = True


class _BadEditor:
    def __init__(self):
        self._segment_queue = [{"text": "temp"}]
        self._live_editor_preview_queue = [{"text": "temp"}]
        self._live_editor_preview_segments = [{"text": "temp"}]
        self._live_editor_preview_keys = {("STT1", 0.0, 1.0, "temp")}
        self.text_edit = SimpleNamespace(clear=mock.Mock())
        self.timeline = SimpleNamespace(
            canvas=SimpleNamespace(total_duration=1.0),
            update_segments=mock.Mock(),
            set_playhead=mock.Mock(),
        )
        self.video_player = SimpleNamespace(
            set_context_segments=mock.Mock(),
            seek=mock.Mock(),
        )
        self._cached_segs = [{"text": "x"}]
        self._active_seg_start = 2.0

        class _BadTimer:
            def isActive(self):
                return True

            def stop(self):
                raise RuntimeError("stop boom")

        self._queue_timer = _BadTimer()


class MainFileOpsNonfatalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_prepare_dialog_state_ignores_nonfatal_focus_and_cursor_errors(self):
        window = _FileOpsWindow()
        with (
            mock.patch.object(QApplication, "focusWidget", side_effect=RuntimeError("focus gone")),
            mock.patch.object(QApplication, "processEvents") as process_events,
            mock.patch.object(window, "unsetCursor", side_effect=RuntimeError("cursor gone"), create=True),
            mock.patch.object(window, "update", side_effect=RuntimeError("update gone"), create=True),
        ):
            window._prepare_dialog_state()

        process_events.assert_called_once()

    def test_file_dialog_replays_deferred_home_rebuild_after_cancel(self):
        window = _FileOpsWindow()
        window._pending_home_auto_source_rebuild = True
        window._build_home_content = mock.Mock()

        def _open(_parent, _title, folder, _filter):
            self.assertTrue(window._file_dialog_active)
            self.assertTrue(folder)
            return ([], "")

        with mock.patch.object(QFileDialog, "getOpenFileNames", side_effect=_open):
            paths, _ = window._safe_open_file_names("파일 선택", "/missing/folder", "Media")

        self.assertEqual(paths, [])
        self.assertFalse(window._file_dialog_active)
        self.assertFalse(window._pending_home_auto_source_rebuild)
        self.app.processEvents()
        window._build_home_content.assert_called_once()

    def test_file_dialog_marks_active_before_startup_events_are_processed(self):
        window = _FileOpsWindow()
        seen = []

        def _process_events():
            seen.append(bool(getattr(window, "_file_dialog_active", False)))

        with (
            mock.patch.object(QApplication, "processEvents", side_effect=_process_events),
            mock.patch.object(QFileDialog, "getOpenFileNames", return_value=([], "")),
        ):
            window._safe_open_file_names("파일 선택", "/tmp", "Media")

        self.assertEqual(seen, [True])
        self.assertFalse(window._file_dialog_active)

    def test_file_dialog_keeps_foreground_priority_until_selection_dispatches(self):
        window = _FileOpsWindow()
        callbacks = []
        window._resume_deferred_editor_ai_release_after_file_open = mock.Mock()

        def _single_shot(delay_ms, callback):
            callbacks.append((int(delay_ms), callback))

        with (
            mock.patch.object(QTimer, "singleShot", side_effect=_single_shot),
            mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(["/tmp/clip.mp4"], "")),
        ):
            paths, _ = window._safe_open_file_names("파일 선택", "/tmp", "Media")

        self.assertEqual(paths, ["/tmp/clip.mp4"])
        self.assertFalse(window._file_dialog_active)
        self.assertTrue(window._foreground_file_open_requested)
        found = [c for c in callbacks if c[0] == FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS]
        self.assertTrue(bool(found))
        found[0][1]()
        self.assertFalse(window._foreground_file_open_requested)
        window._resume_deferred_editor_ai_release_after_file_open.assert_called_once()

    def test_file_dialog_suspends_startup_background_before_native_dialog(self):
        window = _FileOpsWindow()
        window._suspend_startup_background_for_foreground_action = mock.Mock()

        def _open(_parent, _title, _folder, _filter):
            window._suspend_startup_background_for_foreground_action.assert_called_once()
            self.assertTrue(window._foreground_file_open_requested)
            self.assertTrue(window._file_dialog_active)
            return ([], "")

        with mock.patch.object(QFileDialog, "getOpenFileNames", side_effect=_open):
            window._safe_open_file_names("파일 선택", "/tmp", "Media")

        window._suspend_startup_background_for_foreground_action.assert_called_once_with(
            "file_dialog",
            hold_ms=FILE_DIALOG_SELECTED_PRIORITY_HOLD_MS,
        )

    def test_file_dialog_selection_skips_stale_home_rebuild(self):
        window = _FileOpsWindow()
        window._pending_home_auto_source_rebuild = True
        window._build_home_content = mock.Mock()

        with mock.patch.object(QFileDialog, "getOpenFileNames", return_value=(["/tmp/clip.mp4"], "")):
            paths, _ = window._safe_open_file_names("파일 선택", "/tmp", "Media")

        self.assertEqual(paths, ["/tmp/clip.mp4"])
        self.assertFalse(window._file_dialog_active)
        self.assertFalse(window._pending_home_auto_source_rebuild)
        self.app.processEvents()
        window._build_home_content.assert_not_called()

    def test_optional_startup_waits_while_file_dialog_is_active(self):
        owner = SimpleNamespace(_offscreen_test=False, _file_dialog_active=True)

        self.assertFalse(MainWindow._optional_startup_home_ready(owner))

    def test_quick_exit_continues_when_schedule_and_backup_raise(self):
        window = _FileOpsWindow()
        window._confirm_save_dirty_editor_before_exit = mock.Mock(return_value=True)
        window._schedule_forced_process_exit = mock.Mock(side_effect=RuntimeError("schedule boom"))
        window._has_active_runtime_work_for_exit = mock.Mock(return_value=False)
        window._pause_all_runtime_work_for_exit = mock.Mock(side_effect=RuntimeError("pause boom"))
        window._start_runtime_cleanup_for_app_exit_async = mock.Mock(side_effect=RuntimeError("cleanup boom"))
        window._backup_before_quick_exit = mock.Mock(side_effect=RuntimeError("backup boom"))

        with mock.patch.object(QApplication, "quit") as quit_app:
            window._quick_exit()

        self.assertTrue(window._quick_exit_requested)
        self.assertTrue(getattr(window, "closed", False))
        quit_app.assert_called_once()


if __name__ == "__main__":
    unittest.main()
