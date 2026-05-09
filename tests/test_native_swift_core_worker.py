from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.native_swift_subtitle as native_subtitle
from core.native_swift_project import read_project_via_swift, write_project_via_swift
from core.native_swift_subtitle import find_native_cli_path, parse_srt_via_swift, stop_native_core_worker


class NativeSwiftCoreWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        stop_native_core_worker()

    def tearDown(self) -> None:
        stop_native_core_worker()

    def test_core_worker_reuses_single_swift_process_across_srt_and_project_tasks(self):
        if find_native_cli_path() is None:
            self.skipTest("AIStudioNativeCLI release build is not available")

        with tempfile.TemporaryDirectory() as tmp:
            srt_path = Path(tmp) / "sample.srt"
            srt_path.write_text(
                "1\n00:00:00,000 --> 00:00:01,200\n안녕하세요\n\n"
                "2\n00:00:01,500 --> 00:00:02,700\n반갑습니다\n",
                encoding="utf-8",
            )
            project_path = Path(tmp) / "project.json"
            project_payload = {
                "project_name": "worker-test",
                "analysis": {
                    "stt_candidate_tracks": {
                        "STT1": [{"start": 0.0, "end": 1.0, "text": "안녕하세요"}],
                    }
                },
                "_project_file_path": str(project_path),
            }

            env = {
                "AI_SUBTITLE_STUDIO_SWIFT_CORE": "1",
                "AI_SUBTITLE_STUDIO_SWIFT_PROJECT_IO": "1",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                first_segments = parse_srt_via_swift(str(srt_path))
                first_worker = native_subtitle._CORE_WORKER
                second_segments = parse_srt_via_swift(str(srt_path))
                second_worker = native_subtitle._CORE_WORKER
                wrote = write_project_via_swift(str(project_path), project_payload)
                loaded = read_project_via_swift(str(project_path))
                final_worker = native_subtitle._CORE_WORKER

            self.assertIsNotNone(first_worker)
            self.assertIs(first_worker, second_worker)
            self.assertIs(first_worker, final_worker)
            self.assertIsNone(final_worker.poll())
            self.assertEqual(first_segments, second_segments)
            self.assertEqual(len(first_segments or []), 2)
            self.assertTrue(wrote)
            self.assertIsInstance(loaded, dict)
            self.assertEqual(loaded["project_name"], "worker-test")
            self.assertNotIn("_project_file_path", loaded)


if __name__ == "__main__":
    unittest.main()
