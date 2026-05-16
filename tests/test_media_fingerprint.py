import os
import tempfile
import unittest
import hashlib
from unittest.mock import patch

from core.media_fingerprint import (
    _media_fingerprint_digest_for_stat,
    _sample_digest_for_stat,
    media_file_fingerprint,
    media_fingerprint_digest,
    media_fingerprint_snapshot,
)


class MediaFingerprintTests(unittest.TestCase):
    def test_same_name_same_size_same_mtime_changes_when_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "same_name.mp4")
            with open(path, "wb") as handle:
                handle.write(b"A" * 4096)
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
            first = media_file_fingerprint(path, sample_bytes=1024, include_samples=True)

            with open(path, "wb") as handle:
                handle.write(b"B" * 4096)
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
            second = media_file_fingerprint(path, sample_bytes=1024, include_samples=True)

            self.assertNotEqual(first, second)

    def test_sample_digest_is_reused_for_same_file_stat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "same_name.mp4")
            with open(path, "wb") as handle:
                handle.write(b"A" * 4096)
            _sample_digest_for_stat.cache_clear()

            with patch("builtins.open", wraps=open) as open_spy:
                first = media_file_fingerprint(path, sample_bytes=1024, include_samples=True)
                digest = media_fingerprint_digest(path, sample_bytes=1024, include_samples=True)

            self.assertTrue(first)
            self.assertTrue(digest)
            self.assertEqual(open_spy.call_count, 1)

    def test_fingerprint_digest_is_reused_for_same_file_stat(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "same_name.mp4")
            with open(path, "wb") as handle:
                handle.write(b"A" * 4096)
            _sample_digest_for_stat.cache_clear()
            _media_fingerprint_digest_for_stat.cache_clear()

            with patch("core.media_fingerprint.hashlib.sha1", wraps=hashlib.sha1) as sha1_spy:
                first = media_fingerprint_digest(path, sample_bytes=1024, include_samples=True)
                second = media_fingerprint_digest(path, sample_bytes=1024, include_samples=True)

            self.assertEqual(first, second)
            self.assertEqual(sha1_spy.call_count, 2)

    def test_fingerprint_snapshot_matches_individual_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.mp4")
            with open(path, "wb") as handle:
                handle.write(b"sample payload" * 64)

            snapshot = media_fingerprint_snapshot(path, sample_bytes=1024, include_samples=True)

            self.assertTrue(snapshot["exists"])
            self.assertEqual(snapshot["path"], os.path.abspath(path))
            self.assertEqual(snapshot["fingerprint"], media_file_fingerprint(path, sample_bytes=1024, include_samples=True))
            self.assertEqual(
                snapshot["fingerprint_digest"],
                media_fingerprint_digest(path, sample_bytes=1024, include_samples=True),
            )

    def test_fingerprint_snapshot_allows_missing_digest_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "missing.mp4")

            snapshot = media_fingerprint_snapshot(path, missing_digest="")

            self.assertFalse(snapshot["exists"])
            self.assertEqual(snapshot["path"], os.path.abspath(path))
            self.assertEqual(snapshot["fingerprint"], os.path.abspath(path))
            self.assertEqual(snapshot["fingerprint_digest"], "")


if __name__ == "__main__":
    unittest.main()
