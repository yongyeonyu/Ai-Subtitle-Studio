import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication, QToolTip

from core.performance import (
    configure_qt_application_font,
    configure_qt_tooltip_theme,
    qt_application_font_family,
    qt_tooltip_stylesheet,
)


class QtRuntimeFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mac_runtime_font_uses_concrete_system_family(self):
        with patch("core.performance.platform.system", return_value="Darwin"), \
             patch("core.runtime.config.FONT", "Apple SD Gothic Neo"):
            self.assertEqual(qt_application_font_family(), "Apple SD Gothic Neo")

    def test_configure_qt_application_font_sets_qapplication_family(self):
        old_font = self.app.font()
        try:
            with patch("core.performance.platform.system", return_value="Darwin"), \
                 patch("core.runtime.config.FONT", "Apple SD Gothic Neo"):
                family = configure_qt_application_font()

            self.assertEqual(family, "Apple SD Gothic Neo")
            self.assertEqual(self.app.font().family(), "Apple SD Gothic Neo")
        finally:
            self.app.setFont(old_font)

    def test_configure_qt_tooltip_theme_sets_dark_palette_and_rule(self):
        old_style = self.app.styleSheet()
        old_palette = QToolTip.palette()
        try:
            rule = configure_qt_tooltip_theme(append_stylesheet=True)
            palette = QToolTip.palette()

            self.assertIn("QToolTip", rule)
            self.assertIn("QTipLabel", rule)
            self.assertIn("#202A31", qt_tooltip_stylesheet())
            self.assertIn("#202A31", self.app.styleSheet())
            self.assertEqual(
                palette.color(QPalette.ColorRole.ToolTipBase).name().lower(),
                "#202a31",
            )
            self.assertEqual(
                palette.color(QPalette.ColorRole.ToolTipText).name().lower(),
                "#f5f7fa",
            )
        finally:
            self.app.setStyleSheet(old_style)
            QToolTip.setPalette(old_palette)
