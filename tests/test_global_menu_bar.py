import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtWidgets import QApplication, QWidget

from ui.menu_bar import GlobalMenuBar, MENU_PRECISION_COMPLETE_ACCENT


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

    def test_precision_button_lives_next_to_voice_and_waits_until_available(self):
        _, editor, bar = self._make_bar()
        editor._precision_available = False
        editor._precision_refine_available = lambda: bool(editor._precision_available)

        bar.refresh()
        left_texts = [button.text() for button in bar._left_qml_buttons]
        self.assertEqual(left_texts[left_texts.index("음성") + 1], "정밀")
        self.assertFalse(bar.btn_precision_refine.isEnabled())

        editor._precision_available = True
        bar.refresh()
        self.assertTrue(bar.btn_precision_refine.isEnabled())

    def test_precision_button_shows_completed_green_state(self):
        _, editor, bar = self._make_bar()
        editor._precision_refine_available = lambda: True
        editor._precision_refine_completed = True

        bar.refresh()

        self.assertTrue(bar.btn_precision_refine.isEnabled())
        self.assertEqual(bar.btn_precision_refine.property("qmlAccent"), MENU_PRECISION_COMPLETE_ACCENT)
        self.assertEqual(bar.btn_precision_refine.toolTip(), "정밀 자막 작업 완료")

    def test_precision_button_confirms_before_starting_editor_refine(self):
        _, editor, bar = self._make_bar()
        editor._precision_refine_available = lambda: True
        editor.start_precision_subtitle_refinement = Mock()
        bar.refresh()

        with patch("ui.menu_bar.ask_yes_no", return_value=True):
            bar._run_precision_refine()

        editor.start_precision_subtitle_refinement.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
