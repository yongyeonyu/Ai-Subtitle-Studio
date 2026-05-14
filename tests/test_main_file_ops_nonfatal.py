import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtWidgets import QApplication

from ui.main.main_file_ops import FileOpsMixin


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
