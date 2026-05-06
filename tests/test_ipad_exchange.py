import tempfile
import unittest
from pathlib import Path

from core.project.ipad_exchange import (
    IPAD_EXCHANGE_SCHEMA,
    build_ipad_exchange_manifest,
    validate_ipad_exchange_manifest,
)


class IpadExchangeTests(unittest.TestCase):
    def test_manifest_preserves_korean_names_and_fingerprints_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "프로젝트.ai-subtitle.json"
            media = root / "티니핑_유스어드벤처.MP4"
            project.write_text("{}", encoding="utf-8")
            media.write_bytes(b"first media")

            manifest = build_ipad_exchange_manifest(
                project_path=str(project),
                media_paths=[str(media)],
                bundle_name="iPad 교환",
            )

            self.assertEqual(manifest["schema"], IPAD_EXCHANGE_SCHEMA)
            self.assertEqual(manifest["media_count"], 1)
            self.assertEqual(manifest["media"][0]["name"], "티니핑_유스어드벤처.MP4")
            self.assertTrue(manifest["media"][0]["fingerprint_digest"])
            self.assertTrue(validate_ipad_exchange_manifest(manifest)["valid"])

            media.write_bytes(b"replacement media")
            validation = validate_ipad_exchange_manifest(manifest)
            self.assertFalse(validation["valid"])
            self.assertEqual(validation["stale"][0]["name"], "티니핑_유스어드벤처.MP4")

    def test_validation_can_use_moved_bundle_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            moved = Path(tmp) / "moved"
            source.mkdir()
            moved.mkdir()
            project = source / "프로젝트.ai-subtitle.json"
            media = source / "clip.MP4"
            project.write_text("{}", encoding="utf-8")
            media.write_bytes(b"portable media")

            manifest = build_ipad_exchange_manifest(
                project_path=str(project),
                media_paths=[str(media)],
            )
            project.unlink()
            media.unlink()
            (moved / "프로젝트.ai-subtitle.json").write_text("{}", encoding="utf-8")
            (moved / "clip.MP4").write_bytes(b"portable media")

            validation = validate_ipad_exchange_manifest(manifest, bundle_root=str(moved))

            self.assertTrue(validation["valid"])
            self.assertEqual(validation["valid_count"], 2)


if __name__ == "__main__":
    unittest.main()
