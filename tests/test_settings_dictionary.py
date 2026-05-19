# Version: 01.00.00
# Phase: PHASE2
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from core.correction_dictionary_db import load_corrections, save_corrections
from core.runtime import config
from ui.settings.settings_dictionary import CorrectionDictionaryDialog


class CorrectionDictionaryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_lists_entries_in_ganada_order_and_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "dataset_correction.json")
            save_corrections(
                {
                    "다람쥐": "D",
                    "가방": "B",
                    "나비": "N",
                },
                path,
            )
            previous_path = config.CORRECTIONS_FILE
            try:
                config.CORRECTIONS_FILE = path
                dlg = CorrectionDictionaryDialog()
                try:
                    self.assertEqual(
                        [
                            str(dlg.list_widget.item(index).data(Qt.ItemDataRole.UserRole))
                            for index in range(dlg.list_widget.count())
                        ],
                        ["가방", "나비", "다람쥐"],
                    )
                    dlg.search_edit.setText("나")
                    self.assertEqual(dlg.list_widget.count(), 1)
                    self.assertEqual(
                        str(dlg.list_widget.item(0).data(Qt.ItemDataRole.UserRole)),
                        "나비",
                    )
                finally:
                    dlg.close()
            finally:
                config.CORRECTIONS_FILE = previous_path

    def test_dialog_saves_new_entry_to_runtime_dictionary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "dataset_correction.json")
            save_corrections({"티니핀": "티니핑"}, path)
            previous_path = config.CORRECTIONS_FILE
            try:
                config.CORRECTIONS_FILE = path
                dlg = CorrectionDictionaryDialog()
                try:
                    dlg._prepare_new_entry()
                    dlg.original_edit.setText("사품핑")
                    dlg.corrected_edit.setText("사뿐핑")
                    dlg._save_current_entry()
                    dlg._commit_and_accept()
                finally:
                    dlg.close()
                saved = load_corrections(path)
            finally:
                config.CORRECTIONS_FILE = previous_path

            self.assertEqual(saved.get("사품핑"), "사뿐핑")


if __name__ == "__main__":
    unittest.main()
