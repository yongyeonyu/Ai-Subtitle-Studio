# Version: 03.02.05
# Phase: PHASE2
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.auto_tracker import AutoTracker
from ui.cloud_ui import CloudUIMixin


class _CloudStarter(CloudUIMixin):
    def __init__(self):
        self.started = []
        self.scopes = []
        self._auto_processing_active = False

    def _set_runtime_quality_override_for_scope(self, scope):
        self.scopes.append(scope)

    def _start_queue_mode(self, files, folder=None, source=None):
        self.started.append((list(files or []), folder, source))


class AutoStatusLabelsTests(unittest.TestCase):
    def _touch(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    def test_icloud_status_uses_waiting_and_completed_video_audio_counts_without_emoji(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as data:
            root = Path(tmp)
            pending_video = root / "pending.mov"
            done_audio = root / "done.m4a"
            self._touch(pending_video)
            self._touch(done_audio)

            tracker_path = os.path.join(data, "auto_tracker.json")
            with patch("core.auto_tracker.TRACKER_FILE", tracker_path), patch("ui.cloud_ui.get_icloud_path", return_value=str(root)):
                AutoTracker().mark_completed(str(done_audio))
                files, pending, completed = CloudUIMixin()._get_icloud_files()

        self.assertEqual(pending, "대기 : 영상 01개 / 음성 00개")
        self.assertEqual(completed, "완료 : 영상 00개 / 음성 01개")
        self.assertNotIn("✅", completed)
        self.assertNotIn("작업완료", completed)
        self.assertEqual([name for name, _ in files], ["pending.mov"])

    def test_icloud_files_include_nested_media_in_queue_order(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as data:
            root = Path(tmp)
            self._touch(root / "01_아이폰" / "a.mov")
            self._touch(root / "02_액션6" / "b.m4a")
            self._touch(root / "03_오즈모포켓3" / "c.srt")
            self._touch(root / "root.mp4")

            tracker_path = os.path.join(data, "auto_tracker.json")
            with patch("core.auto_tracker.TRACKER_FILE", tracker_path), patch("ui.cloud_ui.get_icloud_path", return_value=str(root)):
                files, pending, completed = CloudUIMixin()._get_icloud_files()

        self.assertEqual(
            [name for name, _ in files],
            [
                "01_아이폰/a.mov",
                "02_액션6/b.m4a",
                "03_오즈모포켓3/c.srt",
                "root.mp4",
            ],
        )
        self.assertEqual(pending, "대기 : 영상 02개 / 음성 01개")
        self.assertEqual(completed, "완료 : 영상 00개 / 음성 00개")

    def test_start_icloud_sync_starts_ordered_queue_and_omits_srt_files(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as data:
            root = Path(tmp)
            self._touch(root / "01_아이폰" / "a.mov")
            self._touch(root / "02_액션6" / "b.m4a")
            self._touch(root / "03_오즈모포켓3" / "c.srt")
            self._touch(root / "root.mp4")

            starter = _CloudStarter()
            tracker_path = os.path.join(data, "auto_tracker.json")
            with patch("core.auto_tracker.TRACKER_FILE", tracker_path), patch("ui.cloud_ui.get_icloud_path", return_value=str(root)):
                starter.start_icloud_sync()

        started_files, folder, source = starter.started[0]
        self.assertEqual(
            [os.path.relpath(path, root).replace(os.sep, "/") for path in started_files],
            [
                "01_아이폰/a.mov",
                "02_액션6/b.m4a",
                "root.mp4",
            ],
        )
        self.assertEqual(folder, str(root))
        self.assertEqual(source, "icloud")
        self.assertEqual(starter.scopes, ["icloud"])
        self.assertTrue(starter._auto_processing_active)

    def test_nas_status_uses_same_video_audio_count_format(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as data:
            root = Path(tmp)
            pending_folder = root / "pending"
            done_folder = root / "done"
            pending_video = pending_folder / "clip.mp4"
            pending_audio = pending_folder / "voice.wav"
            done_video = done_folder / "clip.mov"
            self._touch(pending_video)
            self._touch(pending_audio)
            self._touch(done_video)

            tracker_path = os.path.join(data, "auto_tracker.json")
            with (
                patch("core.auto_tracker.TRACKER_FILE", tracker_path),
                patch("ui.cloud_ui.get_nas_path", return_value=str(root)),
                patch("ui.cloud_ui.get_local_path", return_value=str(root)),
                patch("ui.cloud_ui.get_nas_excluded_folders", return_value=[]),
            ):
                AutoTracker().mark_completed(str(done_folder))
                _, pending, completed = CloudUIMixin()._get_nas_folders()

        self.assertEqual(pending, "대기 : 영상 01개 / 음성 01개")
        self.assertEqual(completed, "완료 : 영상 01개 / 음성 00개")
        self.assertNotIn("✅", completed)
        self.assertNotIn("작업완료", completed)


if __name__ == "__main__":
    unittest.main()
