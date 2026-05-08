import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from ui.dialogs.popup_dismiss import install_outside_click_dismiss, uninstall_outside_click_dismiss


def _mouse_press_at(x: int, y: int) -> QMouseEvent:
    pos = QPointF(float(x), float(y))
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


class PopupDismissTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_outside_click_dismisses_transient_popup(self):
        popup = QWidget()
        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        popup.resize(120, 80)
        popup.move(100, 100)
        popup.show()
        self.app.processEvents()
        closed = []

        event_filter = install_outside_click_dismiss(
            popup,
            lambda: (closed.append(True), popup.hide()),
            consume=True,
        )

        self.assertFalse(event_filter.eventFilter(self.app, _mouse_press_at(130, 130)))
        self.app.processEvents()
        self.assertEqual(closed, [])

        self.assertTrue(event_filter.eventFilter(self.app, _mouse_press_at(20, 20)))
        self.app.processEvents()
        self.assertEqual(closed, [True])
        self.assertFalse(popup.isVisible())

        uninstall_outside_click_dismiss(popup)
        popup.deleteLater()

    def test_uninstall_clears_popup_filter(self):
        popup = QWidget()
        event_filter = install_outside_click_dismiss(popup, lambda: None)

        uninstall_outside_click_dismiss(popup)

        self.assertFalse(event_filter._installed)
        self.assertIsNone(getattr(popup, "_outside_click_dismiss_filter", None))
        popup.deleteLater()


if __name__ == "__main__":
    unittest.main()
