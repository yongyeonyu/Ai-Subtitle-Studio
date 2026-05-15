# Version: 03.20.00
# Phase: PHASE4_iPad
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from ui.main.main_window import MainWindow
from ui.responsive_profile import (
    profile_name_for_size,
    responsive_profile_for_size,
    responsive_sidebar_width,
)
from ui.settings.tablet_dialog import apply_tablet_dialog_profile
from ui.style import settings_button_style


class ResponsiveProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_desktop_size_uses_compact_menu_defaults(self):
        profile = responsive_profile_for_size(1920, 1080)
        self.assertEqual(profile.name, "desktop")
        self.assertEqual(profile.menu_button_height, 38)
        self.assertEqual(profile.menu_bar_height, 48)

    def test_desktop_tablet_sized_window_does_not_auto_enable_ipad_profile(self):
        profile = responsive_profile_for_size(1180, 820)
        self.assertEqual(profile.name, "desktop")

    def test_ipad_landscape_size_uses_touch_safe_profile(self):
        profile = responsive_profile_for_size(1180, 820, platform="ipad")
        self.assertEqual(profile.name, "tablet_landscape")
        self.assertGreaterEqual(profile.touch_target, 48)
        self.assertGreater(profile.menu_icon_only_width, 760)
        self.assertGreaterEqual(responsive_sidebar_width(1180, profile), profile.sidebar_min_width)

    def test_ipad_portrait_size_uses_portrait_profile(self):
        self.assertEqual(profile_name_for_size(820, 1180, touch_capable=True), "tablet_portrait")

    def test_global_menu_respects_forced_tablet_profile(self):
        window = MainWindow()
        try:
            window.setProperty("responsive_profile_override", "tablet_landscape")
            window.resize(1180, 820)
            window.global_menu_bar.refresh()
            self.app.processEvents()

            self.assertEqual(window.global_menu_bar.height(), 58)
            for button in window.global_menu_bar._tool_buttons:
                self.assertGreaterEqual(button.height(), 48)
                self.assertGreaterEqual(button.width(), 48)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_tablet_workspace_layout_keeps_sidebar_bounded(self):
        window = MainWindow()
        try:
            window.setProperty("responsive_profile_override", "tablet_portrait")
            window.resize(820, 1180)
            window._apply_responsive_workspace_layout()
            self.app.processEvents()

            profile = responsive_profile_for_size(820, 1180, override="tablet_portrait")
            sizes = window.workspace_splitter.sizes()
            self.assertGreaterEqual(sizes[0], profile.sidebar_min_width)
            self.assertLessEqual(sizes[0], profile.sidebar_max_width)
            self.assertGreater(sizes[1], sizes[0])
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_desktop_workspace_layout_reapplies_responsive_sidebar_width(self):
        window = MainWindow()
        try:
            window.resize(1600, 900)
            window.show()
            self.app.processEvents()
            window.workspace_splitter.setSizes([210, 1390])
            self.app.processEvents()
            self.assertGreaterEqual(window.workspace_splitter.sizes()[0], 204)

            profile = responsive_profile_for_size(1600, 900)
            total = max(1, int(window.width() or 0) - 6)
            expected_width = responsive_sidebar_width(total, profile)

            window._apply_responsive_workspace_layout()
            self.app.processEvents()

            self.assertEqual(window.workspace_splitter.sizes()[0], expected_width)
            locked = window._lock_workspace_sidebar_width()
            self.assertEqual(locked, expected_width)

            window.workspace_splitter.setSizes([204, 1396])
            window._apply_responsive_workspace_layout()
            self.app.processEvents()

            self.assertEqual(window.workspace_splitter.sizes()[0], expected_width)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_tablet_settings_dialog_clamps_oversized_min_width(self):
        parent = QWidget()
        dialog = QDialog(parent)
        try:
            parent.setProperty("responsive_profile_override", "tablet_portrait")
            parent.resize(820, 1180)
            dialog.setMinimumWidth(1180)

            profile = apply_tablet_dialog_profile(dialog)

            self.assertEqual(profile.name, "tablet_portrait")
            self.assertLessEqual(dialog.minimumWidth(), 820 - 32)
            self.assertEqual(getattr(dialog, "_settings_control_height"), 44)
        finally:
            dialog.deleteLater()
            parent.deleteLater()
            self.app.processEvents()

    def test_settings_button_style_keeps_desktop_default_height(self):
        style = settings_button_style("toolbar")

        self.assertIn("min-height: 40px", style)
        self.assertIn("max-height: 40px", style)

    def test_settings_button_style_can_use_touch_safe_height(self):
        style = settings_button_style("toolbar", min_height=44)

        self.assertIn("min-height: 44px", style)
        self.assertIn("max-height: 44px", style)


if __name__ == "__main__":
    unittest.main()
