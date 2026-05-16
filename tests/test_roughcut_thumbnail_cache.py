# Version: 03.01.31
# Phase: PHASE2
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.roughcut import default_thumbnail_cache_dir, ensure_thumbnail, thumbnail_cache_path
from core.roughcut.thumbnail_cache import _cache_key


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

    def test_thumbnail_cache_key_reuses_cached_digest_for_repeat_requests(self):
        _cache_key.cache_clear()
        first = _cache_key("/tmp/source with space.mp4", 1.234, 320)
        second = _cache_key("/tmp/source with space.mp4", 1.234, 320)

        self.assertEqual(first, second)
        self.assertGreaterEqual(_cache_key.cache_info().hits, 1)

    def test_ensure_thumbnail_prunes_older_cache_files_after_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "thumbs"
            cache_dir.mkdir()
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"media")
            old_a = cache_dir / "old_a.jpg"
            old_b = cache_dir / "old_b.jpg"
            old_a.write_bytes(b"a" * 180)
            old_b.write_bytes(b"b" * 180)
            old_target = thumbnail_cache_path(str(source), 1.5, cache_dir, width=320)
            old_a.touch()
            old_b.touch()
            Path(old_a).stat()
            Path(old_b).stat()

            import os
            os.utime(old_a, (100, 100))
            os.utime(old_b, (200, 200))

            def _fake_run(cmd, check, stdout, stderr, **_kwargs):
                Path(cmd[-1]).write_bytes(b"n" * 120)
                return None

            with patch("subprocess.run", side_effect=_fake_run):
                result = ensure_thumbnail(
                    str(source),
                    1.5,
                    cache_dir=cache_dir,
                    cache_target_total_bytes=300,
                )

            self.assertEqual(result.status, "created")
            self.assertTrue(old_target.exists())
            self.assertFalse(old_a.exists())
            self.assertTrue(old_b.exists())


if __name__ == "__main__":
    unittest.main()
