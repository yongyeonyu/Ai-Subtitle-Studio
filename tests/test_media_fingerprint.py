import os
import tempfile
import unittest

from core.media_fingerprint import media_file_fingerprint


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


if __name__ == "__main__":
    unittest.main()
