# Version: 03.01.31
# Phase: PHASE2
import tempfile
import unittest
from pathlib import Path

from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail, thumbnail_cache_path


class RoughcutThumbnailCacheTests(unittest.TestCase):
    def test_default_cache_dir_does_not_use_dataset_preview_cache(self):
        cache_dir = default_thumbnail_cache_dir("")
        self.assertNotIn("dataset/video_preview_cache", str(cache_dir))
        self.assertIn("roughcut", str(cache_dir))

    def test_missing_source_returns_fallback_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ensure_thumbnail(str(Path(tmp) / "missing.mp4"), 1.2, cache_dir=tmp)
        self.assertEqual(result.status, "missing_source")
        self.assertEqual(result.timestamp, 1.2)

    def test_thumbnail_cache_path_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = thumbnail_cache_path("/tmp/source with space.mp4", 1.234, tmp, width=320)
            second = thumbnail_cache_path("/tmp/source with space.mp4", 1.234, tmp, width=320)
        self.assertEqual(first.name, second.name)
        self.assertTrue(first.name.endswith(".jpg"))


if __name__ == "__main__":
    unittest.main()
