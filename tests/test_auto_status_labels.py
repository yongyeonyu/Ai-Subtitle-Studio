# Version: 03.02.05
# Phase: PHASE2
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.auto_tracker import AutoTracker
from ui.cloud_ui import CloudUIMixin


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
