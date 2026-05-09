import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.performance import configure_qt_application_font, qt_application_font_family


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
