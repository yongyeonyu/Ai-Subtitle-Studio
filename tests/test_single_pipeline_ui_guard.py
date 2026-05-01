# Version: 03.02.18
# Phase: PHASE2
import unittest

from PyQt6 import sip
from PyQt6.QtCore import QObject

from core.pipeline.single_pipeline import SinglePipelineMixin, _is_deleted_qt_error


class _DummyBackend(SinglePipelineMixin):
    def __init__(self, ui):
        self.ui = ui
        self._active = True


class _Signal:
    def __init__(self):
        self.args = None

    def emit(self, *args):
        self.args = args


class _LiveUi(QObject):
    def __init__(self):
        super().__init__()
        self.sig = _Signal()
        self.called = False

    def open_editor_for_file(self):
        self.called = True


class SinglePipelineUiGuardTests(unittest.TestCase):
    def test_ui_call_treats_none_return_as_success(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)

        self.assertTrue(backend._ui_call("open_editor_for_file"))
        self.assertTrue(ui.called)
        self.assertTrue(backend._active)

    def test_deleted_qobject_disables_backend_without_runtime_error(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)
        sip.delete(ui)

        self.assertFalse(backend._ui_emit("sig", 1, 2, 3))
        self.assertFalse(backend._active)

    def test_deleted_qt_runtime_error_is_recognized_as_shutdown(self):
        exc = RuntimeError("wrapped C/C++ object of type MainWindow has been deleted")

        self.assertTrue(_is_deleted_qt_error(exc))


if __name__ == "__main__":
    unittest.main()
