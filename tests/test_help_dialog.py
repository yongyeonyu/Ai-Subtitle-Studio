# Version: 03.00.27
# Phase: PHASE2
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.help.help_content import HELP_TABS
from ui.help.help_dialog import HelpDialog


class HelpDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_help_content_has_required_sections(self):
        self.assertGreaterEqual(len(HELP_TABS), 8)
        for tab in HELP_TABS:
            self.assertTrue(tab.get("title"))
            self.assertTrue(tab.get("summary"))
            self.assertTrue(tab.get("steps"))
            self.assertTrue(tab.get("examples"))
            self.assertTrue(tab.get("shortcuts"))

    def test_dialog_builds_all_tabs(self):
        dialog = HelpDialog()
        try:
            self.assertEqual(dialog.tabs.count(), len(HELP_TABS))
            self.assertEqual(dialog.windowTitle(), "도움말")
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
