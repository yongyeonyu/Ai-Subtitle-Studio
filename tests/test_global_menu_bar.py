import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from ui.menu_bar import GlobalMenuBar


class GlobalMenuBarSubtitleOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _make_bar(self):
        main = QWidget()
        main._current_work_mode = "editor"
        editor = QWidget(main)
        editor.export_calls = []

        def show_export_dialog(output_mode=None, initial_tab=None):
            editor.export_calls.append(
                {"output_mode": output_mode, "initial_tab": initial_tab}
            )

        editor._show_export_dialog = show_export_dialog
        main._editor_widget = editor
        with patch("ui.menu_bar.scenegraph_enabled", return_value=False):
            bar = GlobalMenuBar(main)
        bar.bind_editor(editor)
        return main, editor, bar

    def test_subtitle_output_opens_settings_dialog_directly(self):
        _, editor, bar = self._make_bar()
        bar._open_export()
        self.assertEqual(
            editor.export_calls,
            [{"output_mode": None, "initial_tab": None}],
        )


if __name__ == "__main__":
    unittest.main()
