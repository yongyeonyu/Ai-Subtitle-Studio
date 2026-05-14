import unittest
from unittest import mock

from PyQt6.QtWidgets import QApplication

from ui.main.main_runtime_cleanup import (
    _is_deleted_qt_runtime_error,
    _run_cleanup_step,
)
from ui.main.main_window import MainWindow


class MainRuntimeCleanupHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_run_cleanup_step_logs_failure_and_returns_default(self):
        fake_logger = mock.Mock()
        with mock.patch("ui.main.main_runtime_cleanup.get_logger", return_value=fake_logger):
            result = _run_cleanup_step("sample-step", lambda: (_ for _ in ()).throw(RuntimeError("boom")), default="fallback")

        self.assertEqual(result, "fallback")
        fake_logger.log.assert_called_once()
        self.assertIn("sample-step", fake_logger.log.call_args[0][0])

    def test_run_cleanup_step_ignores_deleted_qt_runtime_error(self):
        fake_logger = mock.Mock()
        deleted_error = RuntimeError("wrapped C/C++ object of type QLabel has been deleted")
        with mock.patch("ui.main.main_runtime_cleanup.get_logger", return_value=fake_logger):
            result = _run_cleanup_step("deleted-widget-step", lambda: (_ for _ in ()).throw(deleted_error), default="ok")

        self.assertEqual(result, "ok")
        fake_logger.log.assert_not_called()
        self.assertTrue(_is_deleted_qt_runtime_error(deleted_error))

    def test_shutdown_runtime_memory_manager_logs_stop_failures(self):
        window = MainWindow()

        class _BadTimer:
            def stop(self):
                raise RuntimeError("timer stop boom")

        class _BadManager:
            def stop(self):
                raise RuntimeError("manager stop boom")

        fake_logger = mock.Mock()
        try:
            window._runtime_memory_timer = _BadTimer()
            window._runtime_memory_manager = _BadManager()
            with mock.patch("ui.main.main_runtime_cleanup.get_logger", return_value=fake_logger):
                window._shutdown_runtime_memory_manager()

            self.assertGreaterEqual(fake_logger.log.call_count, 2)
            logged = "\n".join(call.args[0] for call in fake_logger.log.call_args_list)
            self.assertIn("runtime memory timer stop", logged)
            self.assertIn("runtime memory manager stop", logged)
        finally:
            window.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
