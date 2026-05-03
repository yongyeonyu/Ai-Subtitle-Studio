# Version: 03.13.02
# Phase: PHASE2
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from ui.main.main_file_ops import FileOpsMixin
from ui.project.multiclip_panel import MultiClipEditor


class _DummyBackend:
    def __init__(self):
        self.calls = []

    def start_multiclip_pipeline(self, files, folder=None):
        self.calls.append((list(files or []), folder))


class _DummyWindow(FileOpsMixin):
    def __init__(self):
        self.backend = _DummyBackend()
        self._multiclip_files = []


class _AcceptedDialog:
    def __init__(self, files, parent=None, show_multiclip=True):
        self.sorted_files = list(files or [])

    def exec(self):
        return True


class MulticlipPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_multiclip_editor_shows_single_edit_action_and_current_settings(self):
        dlg = MultiClipEditor(
            ["/tmp/b.mp4", "/tmp/a.mp4"],
            show_multiclip=True,
        )
        try:
            texts = [btn.text() for btn in dlg.findChildren(QPushButton)]
            self.assertIn("멀티클립 편집", texts)
            self.assertNotIn("빠른모드", texts)
            self.assertNotIn("품질모드", texts)
            self.assertTrue(hasattr(dlg, "current_settings_lbl"))
            label_texts = [label.text() for label in dlg.findChildren(QLabel)]
            self.assertIn("현재 적용될 설정", label_texts)
            self.assertIn("정밀인식", dlg.current_settings_lbl.text())
        finally:
            dlg.close()
            dlg.deleteLater()
            self.app.processEvents()

    def test_multiclip_dialog_accept_starts_multiclip_pipeline_only(self):
        owner = _DummyWindow()
        with patch("ui.project.multiclip_panel.MultiClipEditor", _AcceptedDialog):
            owner._show_multiclip_then_batch(
                ["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"],
                folder="/tmp/work",
                show_multiclip=True,
            )

        self.assertEqual(owner._multiclip_files, ["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"])
        self.assertEqual(owner.backend.calls, [(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"], "/tmp/work")])


if __name__ == "__main__":
    unittest.main()
