import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSize
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

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

    def test_context_menu_center_pos_ignores_click_point(self):
        parent = QWidget()
        try:
            parent.resize(400, 300)
            parent.move(40, 50)
            popup_size = QSize(120, 80)

            first = qml_popup._centered_popup_pos(parent, popup_size, QPoint(1, 1))
            second = qml_popup._centered_popup_pos(parent, popup_size, QPoint(700, 500))

            self.assertEqual(first, second)
            center = qml_popup._popup_parent_center(parent, QPoint(1, 1))
            self.assertAlmostEqual(first.x() + popup_size.width() / 2, center.x(), delta=1)
            self.assertAlmostEqual(first.y() + popup_size.height() / 2, center.y(), delta=1)
        finally:
            parent.deleteLater()

    def test_popup_parent_center_uses_visible_top_level_window_not_bottom_child(self):
        window = QWidget()
        child = QWidget(window)
        try:
            window.resize(900, 700)
            window.move(80, 90)
            child.setGeometry(0, 640, 900, 48)
            window.show()
            self.app.processEvents()

            center = qml_popup._popup_parent_center(child, QPoint(1, 1))

            self.assertAlmostEqual(center.x(), window.frameGeometry().center().x(), delta=1)
            self.assertAlmostEqual(center.y(), window.frameGeometry().center().y(), delta=1)
        finally:
            window.close()
            window.deleteLater()

    def test_fallback_context_menu_execs_at_click_anchored_position(self):
        parent = QWidget()
        parent.resize(400, 300)
        expected_pos = QPoint(123, 234)
        captured = {}

        class _Action:
            def setEnabled(self, _enabled):
                pass

            def setCheckable(self, _checkable):
                pass

            def setChecked(self, _checked):
                pass

        class _Menu:
            def __init__(self, _parent):
                self.action = _Action()

            def setStyleSheet(self, _style):
                pass

            def addAction(self, _label):
                return self.action

            def addSeparator(self):
                pass

            def sizeHint(self):
                return QSize(180, 92)

            def setMaximumSize(self, _size):
                pass

            def setFixedWidth(self, _width):
                pass

            def exec(self, pos):
                captured["pos"] = QPoint(pos)
                return self.action

        try:
            with mock.patch.object(qml_popup, "QMenu", _Menu):
                with mock.patch.object(qml_popup, "_clamp_popup_pos", return_value=expected_pos) as clamped:
                    chosen = qml_popup._fallback_qmenu(
                        parent,
                        QPoint(700, 500),
                        [{"id": "open", "label": "열기"}],
                    )

            self.assertEqual(chosen, "open")
            self.assertEqual(captured["pos"], expected_pos)
            clamped.assert_called_once()
        finally:
            parent.deleteLater()

    def test_show_context_menu_quick_path_keeps_click_anchor(self):
        expected_pos = QPoint(210, 160)
        dialog_mock = mock.Mock()
        dialog_mock.selected_id.return_value = "open"
        loop_mock = mock.Mock()
        loop_mock.exec.return_value = None

        with mock.patch.object(qml_popup, "_quick_available", return_value=True):
            with mock.patch.object(qml_popup, "_QuickContextMenuDialog", return_value=dialog_mock):
                with mock.patch.object(qml_popup, "QEventLoop", return_value=loop_mock):
                    chosen = qml_popup.show_context_menu(
                        None,
                        expected_pos,
                        [{"id": "open", "label": "열기"}],
                    )

        self.assertEqual(chosen, "open")
        dialog_mock.fit_to_screen.assert_called_once()
        _, kwargs = dialog_mock.fit_to_screen.call_args
        self.assertEqual(kwargs.get("centered"), False)
        dialog_mock.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
