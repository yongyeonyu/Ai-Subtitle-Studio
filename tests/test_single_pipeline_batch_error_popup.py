import unittest
from unittest import mock

from core.pipeline.single_pipeline import SinglePipelineMixin


class _Signal:
    def __init__(self):
        self.emissions = []

    def emit(self, *args):
        self.emissions.append(args)


class _Ui:
    def __init__(self):
        self._sig_update_queue_payload = _Signal()
        self._sig_update_queue_header_payload = _Signal()
        self._sig_finalize_generation_complete = _Signal()
        self._is_auto_pipeline = False
        self._auto_processing_active = False


class _DummyBackend(SinglePipelineMixin):
    def __init__(self, actions):
        self.ui = _Ui()
        self.files_to_process = ["clip_a.mp4", "clip_b.mp4"]
        self._active = True
        self._stop_requested = False
        self._scripted_actions = list(actions)
        self.calls = []

    def _send_ntfy_notification(self, **_kwargs):
        pass

    def _process_one(self, target_file, queue_index):
        self.calls.append((queue_index, target_file))
        action = self._scripted_actions[queue_index]
        if isinstance(action, BaseException):
            raise action
        if action == "fail":
            return False
        if action == "recorded_fail":
            self._record_deferred_batch_error(
                target_file,
                queue_index,
                stage="STT/자막 생성",
                message="샘플 자막 생성 실패",
            )
            return False
        return True


class SinglePipelineBatchErrorPopupTests(unittest.TestCase):
    def test_run_all_continues_after_file_exception_and_shows_popup_once(self):
        backend = _DummyBackend([RuntimeError("first clip exploded"), True])

        with mock.patch("ui.dialogs.runtime_error_popup.show_runtime_error_popup", return_value=True) as popup:
            backend._run_all()

        self.assertEqual(backend.calls, [(0, "clip_a.mp4"), (1, "clip_b.mp4")])
        popup.assert_called_once()
        title, text = popup.call_args.args
        self.assertEqual(title, "배치 자막 생성 일부 오류")
        self.assertIn("clip_a.mp4", text)
        self.assertIn("완료: 1개", text)
        self.assertIn("오류: 1개", text)
        self.assertIn("first clip exploded", text)

    def test_run_all_uses_generic_summary_when_file_returns_false(self):
        backend = _DummyBackend(["fail", True])

        with mock.patch("ui.dialogs.runtime_error_popup.show_runtime_error_popup", return_value=True) as popup:
            backend._run_all()

        self.assertEqual(backend.calls, [(0, "clip_a.mp4"), (1, "clip_b.mp4")])
        popup.assert_called_once()
        _title, text = popup.call_args.args
        self.assertIn("clip_a.mp4", text)
        self.assertIn("큐 상태와 로그를 확인해 주세요.", text)

    def test_run_all_does_not_show_popup_after_user_exit(self):
        backend = _DummyBackend([Exception("USER_EXIT"), True])

        with mock.patch("ui.dialogs.runtime_error_popup.show_runtime_error_popup", return_value=True) as popup:
            backend._run_all()

        self.assertEqual(backend.calls, [(0, "clip_a.mp4")])
        popup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
