import os
import tempfile
import unittest
from unittest.mock import patch

from core.video_preview_proxy import (
    cut_boundary_scan_source,
    existing_preview_proxy_for,
    preview_proxy_path_for,
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


if __name__ == "__main__":
    unittest.main()
