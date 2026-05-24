# Version: 03.02.18
# Phase: PHASE2
import unittest

from PyQt6 import sip
from PyQt6.QtCore import QObject

from core.pipeline.single_pipeline import SinglePipelineMixin, _is_deleted_qt_error
from ui.queue.queue_formatting import (
    normalize_queue_header_payload,
    normalize_queue_status_payload,
)


class _DummyBackend(SinglePipelineMixin):
    def __init__(self, ui):
        self.ui = ui
        self._active = True
        self._stop_requested = False


class _Signal:
    def __init__(self, owner=None, name: str = ""):
        self.owner = owner
        self.name = name
        self.args = None
        self.emissions = []

    def emit(self, *args):
        self.args = args
        self.emissions.append(args)
        if self.owner is not None and self.name:
            self.owner.events.append(self.name)


class _LiveUi(QObject):
    def __init__(self):
        super().__init__()
        self.events = []
        self.sig = _Signal(self, "sig")
        self._sig_preview_processing_segments = _Signal(self, "preview_processing_segments")
        self._sig_finalize_generation_complete = _Signal(self, "finalize_generation_complete")
        self._sig_update_queue = _Signal(self, "update_queue")
        self._sig_update_queue_payload = _Signal(self, "update_queue_payload")
        self._sig_update_queue_header = _Signal(self, "update_queue_header")
        self._sig_update_queue_header_payload = _Signal(self, "update_queue_header_payload")
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

    def test_ui_emit_routes_queue_status_to_payload_signal_when_available(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)

        self.assertTrue(backend._ui_emit("_sig_update_queue", 2, "대기 중", "15:54", "1920x1080", "24:10"))
        self.assertEqual(ui._sig_update_queue.args, None)
        payload = normalize_queue_status_payload(ui._sig_update_queue_payload.emissions[-1][0])
        self.assertEqual(payload["idx"], 2)
        self.assertEqual(payload["status"], "대기 중")
        self.assertEqual(payload["time_txt"], "15:54")

    def test_ui_emit_routes_queue_header_to_payload_signal_when_available(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)

        self.assertTrue(backend._ui_emit("_sig_update_queue_header", 1, 3, 20, "2분 10초"))
        self.assertEqual(ui._sig_update_queue_header.args, None)
        payload = normalize_queue_header_payload(ui._sig_update_queue_header_payload.emissions[-1][0])
        self.assertEqual(payload["current"], 1)
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["pct"], 20)

    def test_ui_emit_routes_processing_preview_payload_to_object_signal(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)

        payload = {"stage": "context_review", "stage_label": "문맥 보정", "segments": [{"start": 1.0, "end": 2.0, "text": "초안"}]}
        self.assertTrue(backend._ui_emit("_sig_preview_processing_segments", payload))
        self.assertEqual(ui._sig_preview_processing_segments.args[0]["stage"], "context_review")
        self.assertEqual(ui._sig_preview_processing_segments.args[0]["segments"][0]["text"], "초안")

    def test_emit_generation_completion_ready_emits_finalize_and_queue_update(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)

        self.assertTrue(backend._emit_generation_completion_ready(0, reason="stt_optimizer_threads_done"))
        self.assertEqual(ui._sig_finalize_generation_complete.args, ("stt_optimizer_threads_done",))
        payload = normalize_queue_status_payload(ui._sig_update_queue_payload.emissions[-1][0])
        self.assertEqual(payload["status"], "저장 준비 중")
        self.assertLess(
            ui.events.index("update_queue_payload"),
            ui.events.index("finalize_generation_complete"),
        )

    def test_emit_generation_completion_ready_allows_inactive_fallback_when_not_stopped(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)
        backend._active = False

        self.assertTrue(
            backend._emit_generation_completion_ready(
                1,
                reason="stt_optimizer_threads_done",
                allow_inactive_fallback=True,
            )
        )
        self.assertEqual(ui._sig_finalize_generation_complete.args, ("stt_optimizer_threads_done",))

    def test_emit_generation_completion_ready_skips_when_stopped(self):
        ui = _LiveUi()
        backend = _DummyBackend(ui)
        backend._active = False
        backend._stop_requested = True

        self.assertFalse(
            backend._emit_generation_completion_ready(
                1,
                reason="stt_optimizer_threads_done",
                allow_inactive_fallback=True,
            )
        )
        self.assertIsNone(ui._sig_finalize_generation_complete.args)


if __name__ == "__main__":
    unittest.main()
