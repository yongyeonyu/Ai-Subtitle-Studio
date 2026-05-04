# Version: 03.14.10
# Phase: PHASE2
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox

from ui.main.main_file_ops import FileOpsMixin
from ui.project.multiclip_panel import MultiClipEditor


class _DummyBackend:
    def __init__(self):
        self.calls = []
        self.pipeline_calls = []

    def start_multiclip_pipeline(self, files, folder=None):
        self.calls.append((list(files or []), folder))

    def start_pipeline(self, files, folder=None, is_icloud=False, is_auto_start=False):
        self.pipeline_calls.append((list(files or []), folder, bool(is_auto_start)))


class _DummyWindow(FileOpsMixin):
    def __init__(self):
        self.backend = _DummyBackend()
        self._multiclip_files = []


class _AcceptedDialog:
    def __init__(self, files, parent=None, show_multiclip=True):
        self.sorted_files = list(files or [])

    def exec(self):
        return True


class _AcceptedFolderDialog:
    def __init__(self, _folder, _parent=None):
        self.saved_only = False
        self.selected_files = ["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"]
        self.processing_mode = "individual"
        self.export_subtitle_video = True

    def exec(self):
        return True

    def result(self):
        return True


class _DummyFolderWindow(FileOpsMixin):
    def __init__(self):
        self.backend = _DummyBackend()
        self.batch_calls = []
        self._multiclip_files = []
        self._project_boundary_times = []
        self._current_project_path = None

    def _safe_open_directory(self, _title, _folder):
        return "/tmp"

    def _add_recent_folder(self, _folder_path):
        pass

    def _start_batch(self, files, folder=None):
        self.batch_calls.append((list(files or []), folder))


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
            self.assertIn("자막품질", dlg.current_settings_lbl.text())
            self.assertIn("오토 오디오", dlg.current_settings_lbl.text())
            quality_combos = [
                combo for combo in dlg.findChildren(QComboBox)
                if [combo.itemText(i) for i in range(combo.count())] == ["빠름", "보통", "높음"]
            ]
            self.assertTrue(quality_combos)
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

    def test_folder_dialog_individual_mode_opens_editor_pipeline_and_preserves_export_flag(self):
        owner = _DummyFolderWindow()
        owner._multiclip_files = ["/tmp/stale_a.mp4", "/tmp/stale_b.mp4"]
        owner._multiclip_boundaries = [{"file": "/tmp/stale_a.mp4"}]
        with (
            patch("ui.main.main_file_ops.set_last_folder"),
            patch("ui.main.main_file_ops.get_last_folder", return_value="/tmp"),
            patch("ui.dialogs.folder_dialog.FolderDialog", _AcceptedFolderDialog),
        ):
            owner.select_folder()

        self.assertEqual(owner.batch_calls, [])
        self.assertEqual(owner.backend.calls, [])
        self.assertEqual(owner.backend.pipeline_calls, [(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"], "/tmp", True)])
        self.assertEqual(owner._multiclip_files, [])
        self.assertEqual(owner._multiclip_boundaries, [])
        self.assertTrue(owner._is_queue_mode)
        self.assertTrue(owner._auto_export_subtitle_video)

    def test_folder_dialog_ignores_multiclip_mode_and_runs_individual_pipeline(self):
        class _MulticlipFolderDialog(_AcceptedFolderDialog):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.processing_mode = "multiclip"

        owner = _DummyFolderWindow()
        with (
            patch("ui.main.main_file_ops.set_last_folder"),
            patch("ui.main.main_file_ops.get_last_folder", return_value="/tmp"),
            patch("ui.dialogs.folder_dialog.FolderDialog", _MulticlipFolderDialog),
            patch("ui.project.multiclip_panel.MultiClipEditor", _AcceptedDialog),
        ):
            owner.select_folder()

        self.assertEqual(owner.batch_calls, [])
        self.assertEqual(owner.backend.calls, [])
        self.assertEqual(owner.backend.pipeline_calls, [(["/tmp/clip_a.mp4", "/tmp/clip_b.mp4"], "/tmp", True)])
        self.assertTrue(owner._is_queue_mode)
        self.assertTrue(owner._auto_export_subtitle_video)

    def test_regular_folder_dialog_hides_auto_detect_and_uses_confirm(self):
        from ui.dialogs.folder_dialog import FolderDialog, NasFolderDialog

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "voice.wav"), "wb").close()
            regular = FolderDialog(tmp)
            nas = NasFolderDialog(tmp, excluded_folders=[tmp])
            try:
                regular_headers = [
                    regular.tree.headerItem().text(i)
                    for i in range(regular.tree.columnCount())
                ]
                nas_headers = [
                    nas.tree.headerItem().text(i)
                    for i in range(nas.tree.columnCount())
                ]
                regular_buttons = [btn.text() for btn in regular.findChildren(QPushButton)]

                self.assertNotIn("자동감지 제외", regular_headers)
                self.assertIn("자동감지 제외", nas_headers)
                self.assertIn("선택", regular_headers)
                self.assertIn("미리보기", regular_headers)
                self.assertIn("확인", regular_buttons)
                self.assertNotIn("저장", regular_buttons)
                self.assertNotIn("멀티클립 처리", [btn.text() for btn in regular.findChildren(QPushButton)])
                self.assertNotIn("멀티클립 처리", [label.text() for label in regular.findChildren(QLabel)])
                self.assertEqual(regular.tree.treePosition(), regular.name_col)
                self.assertEqual(nas.tree.treePosition(), nas.name_col)
                regular_quality = getattr(regular, "combo_subtitle_quality", None)
                nas_quality = getattr(nas, "combo_subtitle_quality", None)
                self.assertIsNotNone(regular_quality)
                self.assertIsNotNone(nas_quality)
                self.assertEqual(
                    [regular_quality.itemText(i) for i in range(regular_quality.count())],
                    ["빠름", "보통", "높음"],
                )
            finally:
                regular.close()
                nas.close()
                regular.deleteLater()
                nas.deleteLater()
                self.app.processEvents()

    def test_regular_folder_dialog_deselect_all_clears_selected_files(self):
        from PyQt6.QtCore import Qt
        from ui.dialogs.folder_dialog import FolderDialog

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "voice_a.wav"), "wb").close()
            open(os.path.join(tmp, "voice_b.wav"), "wb").close()
            dialog = FolderDialog(tmp)
            try:
                dialog._select_all()
                dialog._collect_state()
                self.assertEqual(len(dialog.selected_files), 2)

                root = dialog.tree.invisibleRootItem().child(0)
                first_file = root.child(0)
                first_file.setCheckState(dialog.select_col, Qt.CheckState.Unchecked)
                dialog._collect_state()
                self.assertEqual(len(dialog.selected_files), 1)
                self.assertEqual(root.checkState(dialog.select_col), Qt.CheckState.PartiallyChecked)

                dialog._deselect_all()
                dialog._collect_state()
                self.assertEqual(dialog.selected_files, [])

                self.assertEqual(root.checkState(dialog.select_col), Qt.CheckState.Unchecked)
            finally:
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()

    def test_folder_dialog_defaults_to_all_selected_and_respects_excluded_nas_root(self):
        from PyQt6.QtCore import Qt
        from ui.dialogs.folder_dialog import FolderDialog, NasFolderDialog

        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "voice_a.wav"), "wb").close()
            open(os.path.join(tmp, "voice_b.wav"), "wb").close()

            regular = FolderDialog(tmp)
            nas = NasFolderDialog(tmp, excluded_folders=[tmp])
            try:
                regular._collect_state()
                self.assertEqual(len(regular.selected_files), 2)

                regular_root = regular.tree.invisibleRootItem().child(0)
                self.assertEqual(regular_root.checkState(regular.select_col), Qt.CheckState.Checked)

                nas._collect_state()
                self.assertEqual(nas.selected_files, [])

                nas_root = nas.tree.invisibleRootItem().child(0)
                self.assertEqual(nas_root.checkState(nas.select_col), Qt.CheckState.Unchecked)
            finally:
                regular.close()
                nas.close()
                regular.deleteLater()
                nas.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
