import os
import tempfile
import unittest
from unittest.mock import patch

from core.video_preview_proxy import (
    cut_boundary_scan_source,
    existing_preview_proxy_for,
    preview_proxy_path_for,
    register_preview_proxy_created,
)


class VideoPreviewProxyTests(unittest.TestCase):
    def test_cut_boundary_scan_source_reuses_existing_preview_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "source movie.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"media")
            with patch("core.video_preview_proxy.config.DATASET_DIR", tmp):
                proxy_path = preview_proxy_path_for(media_path)
                os.makedirs(os.path.dirname(proxy_path), exist_ok=True)
                with open(proxy_path, "wb") as handle:
                    handle.write(b"proxy")

                self.assertEqual(existing_preview_proxy_for(media_path), proxy_path)
                self.assertEqual(cut_boundary_scan_source(media_path, {}), proxy_path)

    def test_cut_boundary_scan_source_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "source.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"media")
            with patch("core.video_preview_proxy.config.DATASET_DIR", tmp):
                proxy_path = preview_proxy_path_for(media_path)
                os.makedirs(os.path.dirname(proxy_path), exist_ok=True)
                with open(proxy_path, "wb") as handle:
                    handle.write(b"proxy")

                self.assertEqual(
                    cut_boundary_scan_source(media_path, {"scan_cut_use_preview_proxy_enabled": False}),
                    media_path,
                )

    def test_register_preview_proxy_created_prunes_older_proxy_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            media_path = os.path.join(tmp, "source.mp4")
            with open(media_path, "wb") as handle:
                handle.write(b"media")
            with patch("core.video_preview_proxy.config.DATASET_DIR", tmp):
                proxy_dir = os.path.join(tmp, "video_preview_cache")
                os.makedirs(proxy_dir, exist_ok=True)
                old_a = os.path.join(proxy_dir, "old_a_preview_720p_hevc.mp4")
                old_b = os.path.join(proxy_dir, "old_b_preview_720p_hevc.mp4")
                with open(old_a, "wb") as handle:
                    handle.write(b"a" * 180)
                with open(old_b, "wb") as handle:
                    handle.write(b"b" * 180)
                os.utime(old_a, (100, 100))
                os.utime(old_b, (200, 200))

                new_proxy = preview_proxy_path_for(media_path)
                with open(new_proxy, "wb") as handle:
                    handle.write(b"n" * 120)

                result = register_preview_proxy_created(new_proxy, target_total_bytes=300)

                self.assertGreaterEqual(result["removed_files"], 1)
                self.assertFalse(os.path.exists(old_a))
                self.assertTrue(os.path.exists(old_b))
                self.assertTrue(os.path.exists(new_proxy))


if __name__ == "__main__":
    unittest.main()
