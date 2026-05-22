from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.appctl import _parser, _payload_from_args


class AppCtlTests(unittest.TestCase):
    def test_start_multiclip_folder_expands_local_media_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            first = folder / "a.mp4"
            second = folder / "b.mp4"
            ignored = folder / "notes.txt"
            first.write_bytes(b"video")
            second.write_bytes(b"video")
            ignored.write_text("skip", encoding="utf-8")

            args = _parser().parse_args(
                [
                    "start-multiclip",
                    "--folder",
                    str(folder),
                    "--mode",
                    "high",
                    "--reuse-existing",
                    "no",
                ]
            )
            payload = _payload_from_args(args)

        self.assertEqual(payload["command"], "start-multiclip")
        self.assertEqual(payload["folder"], str(folder))
        self.assertEqual(payload["paths"], [str(first), str(second)])
        self.assertEqual(payload["path"], str(first))
        self.assertEqual(payload["options"]["mode"], "high")
        self.assertEqual(payload["options"]["reuse_existing"], "no")

    def test_start_multiclip_keeps_explicit_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            first = folder / "a.mp4"
            second = folder / "b.mp4"
            first.write_bytes(b"video")
            second.write_bytes(b"video")

            args = _parser().parse_args(
                [
                    "start-multiclip",
                    str(first),
                    str(second),
                    "--folder",
                    str(folder),
                ]
            )
            payload = _payload_from_args(args)

        self.assertEqual(payload["paths"], [str(first), str(second)])
        self.assertEqual(payload["path"], str(first))


if __name__ == "__main__":
    unittest.main()
