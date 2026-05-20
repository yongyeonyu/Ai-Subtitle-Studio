import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.dialogs import qml_popup


class QmlPopupGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_exec_message_box_returns_default_when_widget_fallback_is_unsafe(self):
        with mock.patch.object(qml_popup, "_quick_available", return_value=False):
            with mock.patch.object(qml_popup, "_platform_name", return_value="cocoa"):
                with mock.patch.object(qml_popup, "_can_exec_fallback_message_box", return_value=False):
                    with mock.patch.object(
                        qml_popup.QMessageBox,
                        "__init__",
                        side_effect=AssertionError("QMessageBox should not be constructed"),
                    ):
                        reply = qml_popup.exec_message_box(
                            None,
                            "테스트",
                            "시작 중에는 modal을 만들지 않습니다.",
                            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            default=QMessageBox.StandardButton.No,
                        )

        self.assertEqual(reply, QMessageBox.StandardButton.No)


if __name__ == "__main__":
    unittest.main()
