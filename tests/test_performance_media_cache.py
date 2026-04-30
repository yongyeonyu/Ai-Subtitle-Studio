# Version: 03.01.37
# Phase: PHASE2
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import media_info
from core.performance import bounded_worker_count, ffprobe_worker_count


class PerformanceMediaCacheTest(unittest.TestCase):
    def setUp(self):
        media_info.clear_media_probe_cache_memory()

    def tearDown(self):
        media_info.clear_media_probe_cache_memory()

    def test_probe_media_reuses_memory_and_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "sample.mp4"
            media.write_bytes(b"media")
            cache_dir = Path(tmp) / "cache"
            payload = {
                "format": {"duration": "12.5"},
                "streams": [{"width": 1920, "height": 1080, "r_frame_rate": "30000/1001"}],
            }

            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.ffprobe_binary", return_value="ffprobe"), \
                 patch("core.media_info.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(payload))) as run_mock:
                first = media_info.probe_media(str(media))
                second = media_info.probe_media(str(media))

            self.assertEqual(first["duration"], 12.5)
            self.assertEqual(first["width"], 1920)
            self.assertEqual(second, first)
            self.assertEqual(run_mock.call_count, 1)

            media_info.clear_media_probe_cache_memory()
            with patch("core.media_info.media_probe_cache_dir", return_value=cache_dir), \
                 patch("core.media_info.subprocess.run") as run_mock:
                third = media_info.probe_media(str(media))

            self.assertEqual(third, first)
            run_mock.assert_not_called()

    def test_probe_media_many_preserves_order(self):
        with patch("core.media_info.probe_media", side_effect=lambda path: {"duration": float(path[-1])}):
            result = media_info.probe_media_many(["clip1", "clip2", "clip3"], max_workers=3)

        self.assertEqual([item["duration"] for item in result], [1.0, 2.0, 3.0])

    def test_worker_bounds_are_conservative(self):
        self.assertGreaterEqual(bounded_worker_count(kind="io"), 1)
        self.assertLessEqual(ffprobe_worker_count(99), 8)
        self.assertEqual(ffprobe_worker_count(0), 1)


if __name__ == "__main__":
    unittest.main()
