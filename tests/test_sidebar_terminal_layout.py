# Version: 03.02.14
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.main.main_window import MainWindow


class SidebarTerminalLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_terminal_log_lives_in_sidebar_and_menu_toggles_sidebar(self):
        window = MainWindow()
        try:
            window.show_home()
            window.show_home()
            self.assertIs(window.log_text, window.sidebar_terminal_panel.log_text)
            self.assertIs(window.sidebar_terminal_panel.parent(), window.home_page)
            self.assertFalse(window.bottom_work_panel.log_content.isHidden())

            window._apply_log_visible(False, persist=False)
            self.assertTrue(window.home_page.isHidden())
            self.assertTrue(window.sidebar_terminal_panel.isHidden())
            self.assertFalse(window.bottom_work_panel.log_content.isHidden())

            window._apply_log_visible(True, persist=False)
            self.assertFalse(window.home_page.isHidden())
            self.assertFalse(window.sidebar_terminal_panel.isHidden())
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_global_menu_uses_sidebar_button_label(self):
        window = MainWindow()
        try:
            self.assertEqual(window.global_menu_bar.btn_log.text(), "사이드바")
            self.assertIs(window.global_menu_bar.parent(), window.right_workspace)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
