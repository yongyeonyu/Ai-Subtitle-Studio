import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.main.main_window import MainWindow
from ui.timeline.timeline_widget import TimelineWidget


class TabletViewportSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_window_tablet_landscape_and_portrait_smoke(self):
        cases = [
            ("tablet_landscape", 1180, 820),
            ("tablet_portrait", 820, 1180),
        ]
        for profile, width, height in cases:
            with self.subTest(profile=profile):
                window = MainWindow()
                try:
                    window.setProperty("responsive_profile_override", profile)
                    window.resize(width, height)
                    window._apply_responsive_workspace_layout()
                    window.global_menu_bar.refresh()
                    self.app.processEvents()

                    self.assertEqual(window.global_menu_bar.visual_panel_height(), window._project_info_button_height())
                    self.assertEqual(window.global_menu_bar.visual_panel_height(), 48)
                    self.assertEqual(window.global_menu_bar.height(), window.global_menu_bar.visual_panel_height())
                    sizes = window.workspace_splitter.sizes()
                    self.assertGreater(sizes[0], 0)
                    self.assertGreater(sizes[1], sizes[0])
                    for button in window.global_menu_bar._tool_buttons:
                        self.assertGreaterEqual(button.height(), 48)
                        self.assertGreaterEqual(button.width(), 48)
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_timeline_tablet_touch_targets_smoke(self):
        timeline = TimelineWidget()
        try:
            timeline.setProperty("responsive_profile_override", "tablet_landscape")
            timeline.resize(1180, timeline.height())
            timeline._apply_responsive_touch_targets()
            self.app.processEvents()

            for button in timeline._zoom_buttons:
                self.assertGreaterEqual(button.width(), 48)
                self.assertGreaterEqual(button.height(), 44)
        finally:
            timeline.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
