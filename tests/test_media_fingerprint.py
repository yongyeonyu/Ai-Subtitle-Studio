import os
import tempfile
import unittest
from unittest.mock import patch

from core.media_fingerprint import _sample_digest_for_stat, media_file_fingerprint, media_fingerprint_digest


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


if __name__ == "__main__":
    unittest.main()
