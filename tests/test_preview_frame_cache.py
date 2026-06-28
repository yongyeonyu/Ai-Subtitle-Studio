import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.runtime.preview_frame_cache import (
    PREVIEW_FRAME_CACHE_PURPOSE,
    PREVIEW_FRAME_CACHE_SCHEMA,
    ensure_preview_frame,
    nearest_cached_preview_frame,
    preview_frame_manifest_path,
    preview_frame_cache_path,
    read_preview_frame_manifest,
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

    def test_ensure_preview_frame_writes_user_preview_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.mp4"
            source.write_bytes(b"media")
            thumb_path = Path(tmp) / "Preview" / "FrameThumbnails" / "frame.jpg"
            with patch("core.runtime.preview_frame_cache.ensure_thumbnail") as ensure:
                ensure.return_value = type("Result", (), {"status": "created", "path": str(thumb_path)})()
                ensure_preview_frame(str(source), 1.02, fps=60000 / 1001, width=320, root=tmp)

            manifest_path = preview_frame_manifest_path(thumb_path)
            manifest = read_preview_frame_manifest(thumb_path)

        self.assertTrue(manifest_path.name.endswith(".jpg.json"))
        self.assertEqual(manifest["schema"], PREVIEW_FRAME_CACHE_SCHEMA)
        self.assertEqual(manifest["purpose"], PREVIEW_FRAME_CACHE_PURPOSE)
        self.assertEqual(manifest["cache_kind"], "nle_preview_skimming_frame")
        self.assertEqual(manifest["evidence_role"], "user_preview_only")
        self.assertIs(manifest["cut_boundary_evidence"], False)
        self.assertIs(manifest["ui_thread_decode_allowed"], False)
        self.assertEqual(manifest["frame"], 61)
        self.assertAlmostEqual(manifest["snapped_sec"], 61 / (60000 / 1001), places=6)


if __name__ == "__main__":
    unittest.main()
