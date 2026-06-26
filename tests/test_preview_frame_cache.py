import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runtime.preview_frame_cache import (
    ensure_preview_frame,
    nearest_cached_preview_frame,
    preview_frame_cache_path,
)


class PreviewFrameCacheTests(unittest.TestCase):
    def test_nearest_cached_preview_frame_uses_temp_workspace_frame_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"media")
            cached = preview_frame_cache_path(str(source), 1.0, width=320, root=tmp)
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(b"jpg")

            result = nearest_cached_preview_frame(str(source), 1.03, fps=30.0, width=320, tolerance_frames=2, root=tmp)

        self.assertEqual(result, str(cached))

    def test_ensure_preview_frame_writes_under_temp_preview_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"media")
            with patch("core.runtime.preview_frame_cache.ensure_thumbnail") as ensure:
                ensure.return_value = type("Result", (), {"status": "created", "path": str(Path(tmp) / "thumb.jpg")})()
                result = ensure_preview_frame(str(source), 1.02, fps=30.0, width=320, root=tmp)

            cache_dir = ensure.call_args.kwargs["cache_dir"]

        self.assertIn("Preview", str(cache_dir))
        self.assertEqual(result.status, "created")


if __name__ == "__main__":
    unittest.main()
