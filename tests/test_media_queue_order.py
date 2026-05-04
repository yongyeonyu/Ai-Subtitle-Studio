# Version: 03.14.24
# Phase: PHASE1-B
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.cloud_sync import CloudSyncManager
from core.media_queue_order import ordered_media_files


def _touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


def _relpaths(paths, root: Path):
    return [os.path.relpath(path, root).replace(os.sep, "/") for path in paths]


class MediaQueueOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_ordered_media_files_expands_subfolders_first_and_respects_exclusions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            excluded_folder = root / "04_skip"
            excluded_file = root / "03_오즈모포켓3" / "drop.mp4"
            _touch(root / "01_아이폰" / "clip2.mp4")
            _touch(root / "01_아이폰" / "clip10.mp4")
            _touch(root / "02_액션6" / "a.mov")
            _touch(root / "03_오즈모포켓3" / "z.wav")
            _touch(excluded_file)
            _touch(excluded_folder / "skip.mov")
            _touch(root / "root.mp4")
            _touch(root / ".hidden.mp4")
            _touch(root / "skip_자막소스.mov")

            ordered = ordered_media_files(
                str(root),
                excluded_paths=[str(excluded_folder), str(excluded_file)],
            )

        self.assertEqual(
            _relpaths(ordered, root),
            [
                "01_아이폰/clip2.mp4",
                "01_아이폰/clip10.mp4",
                "02_액션6/a.mov",
                "03_오즈모포켓3/z.wav",
                "root.mp4",
            ],
        )

    def test_folder_dialog_collects_queue_files_in_tree_order(self):
        from ui.dialogs.folder_dialog import FolderDialog, NasFolderDialog

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "01_아이폰" / "a.wav")
            _touch(root / "02_액션6" / "b.wav")
            _touch(root / "03_오즈모포켓3" / "c.wav")
            _touch(root / "root.wav")

            regular = FolderDialog(str(root))
            nas = NasFolderDialog(str(root), excluded_folders=[str(root / "02_액션6")])
            try:
                regular._collect_state()
                nas._collect_state()
                regular_files = list(regular.selected_files)
                nas_files = list(nas.selected_files)
            finally:
                regular.close()
                nas.close()
                regular.deleteLater()
                nas.deleteLater()
                self.app.processEvents()

        self.assertEqual(
            _relpaths(regular_files, root),
            [
                "01_아이폰/a.wav",
                "02_액션6/b.wav",
                "03_오즈모포켓3/c.wav",
                "root.wav",
            ],
        )
        self.assertEqual(
            _relpaths(nas_files, root),
            [
                "01_아이폰/a.wav",
                "03_오즈모포켓3/c.wav",
                "root.wav",
            ],
        )

    def test_cloud_sync_uses_same_recursive_order_for_icloud_and_nas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "01_아이폰" / "a.mp4")
            _touch(root / "02_액션6" / "b.mov")
            _touch(root / "03_오즈모포켓3" / "c.m4a")
            _touch(root / "root.wav")

            icloud = CloudSyncManager(str(root), lambda files: None)
            nas = CloudSyncManager(
                str(root),
                lambda files: None,
                mode="nas",
                exclude_callback=lambda: [str(root / "02_액션6")],
            )

            icloud_files = icloud._get_valid_files()
            nas_files = nas._get_valid_files()

        self.assertEqual(
            _relpaths(icloud_files, root),
            [
                "01_아이폰/a.mp4",
                "02_액션6/b.mov",
                "03_오즈모포켓3/c.m4a",
                "root.wav",
            ],
        )
        self.assertEqual(
            _relpaths(nas_files, root),
            [
                "01_아이폰/a.mp4",
                "03_오즈모포켓3/c.m4a",
                "root.wav",
            ],
        )


if __name__ == "__main__":
    unittest.main()
