import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.dialogs import runtime_error_popup


class RuntimeErrorPopupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        runtime_error_popup._reset_runtime_error_popup_state_for_tests()

    def test_build_runtime_error_message_explains_file_missing_in_korean(self):
        try:
            raise FileNotFoundError("missing_subtitle.srt")
        except FileNotFoundError as exc:
            title, text = runtime_error_popup.build_runtime_error_message(
                FileNotFoundError,
                exc,
                exc.__traceback__,
                log_path="/tmp/qt_slot_exceptions.log",
            )

        self.assertEqual(title, "앱 오류 안내")
        self.assertIn("필요한 파일이나 폴더를 찾지 못했습니다.", text)
        self.assertIn("오류 유형: FileNotFoundError", text)
        self.assertIn("오류 메시지: missing_subtitle.srt", text)
        self.assertIn("로그 파일: /tmp/qt_slot_exceptions.log", text)

    def test_build_runtime_error_message_marks_background_thread_context(self):
        try:
            raise RuntimeError("worker exploded")
        except RuntimeError as exc:
            title, text = runtime_error_popup.build_runtime_error_message(
                RuntimeError,
                exc,
                exc.__traceback__,
                source="thread",
                thread_name="stt-worker",
            )

        self.assertEqual(title, "백그라운드 작업 오류")
        self.assertIn("백그라운드 작업(stt-worker) 중 문제가 발생했습니다.", text)
        self.assertIn("오류 유형: RuntimeError", text)

    def test_show_runtime_error_popup_skips_unsafe_platform(self):
        with mock.patch.object(runtime_error_popup, "_runtime_popup_available", return_value=False):
            with mock.patch.object(
                runtime_error_popup,
                "_show_popup_message",
                side_effect=AssertionError("popup should not be shown"),
            ):
                shown = runtime_error_popup.show_runtime_error_popup("오류", "내용")

        self.assertFalse(shown)

    def test_show_runtime_error_popup_deduplicates_same_message(self):
        with mock.patch.object(runtime_error_popup, "_runtime_popup_available", return_value=True):
            with mock.patch.object(runtime_error_popup, "_show_popup_message") as popup:
                first = runtime_error_popup.show_runtime_error_popup("오류", "같은 문제")
                second = runtime_error_popup.show_runtime_error_popup("오류", "같은 문제")

        self.assertTrue(first)
        self.assertFalse(second)
        popup.assert_called_once_with("오류", "같은 문제")


if __name__ == "__main__":
    unittest.main()
