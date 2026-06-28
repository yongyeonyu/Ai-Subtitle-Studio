from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.appctl import _finalize_appctl_result, _parser, _payload_from_args


class AppCtlTests(unittest.TestCase):
    def test_active_worker_control_commands_build_plain_payloads(self):
        for command in ("cancel-current-pipeline", "app-close-request", "app-quit-request"):
            args = _parser().parse_args([command])
            payload = _payload_from_args(args)
            self.assertEqual(payload["command"], command)
            self.assertEqual(payload.get("path", ""), "")
            self.assertEqual(payload.get("options", {}), {})

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
        self.assertEqual(payload["options"]["reuse_existing"], "no")

    def test_start_multiclip_can_still_request_confirmation_policy(self):
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
                    "--reuse-existing",
                    "ask",
                ]
            )
            payload = _payload_from_args(args)

        self.assertEqual(payload["options"]["reuse_existing"], "ask")

    def test_capture_snapshot_queued_result_reports_ready_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot.png"
            target.write_bytes(b"png")
            payload = {"command": "capture-snapshot", "path": str(target)}
            result = {
                "ok": True,
                "queued": True,
                "message": "snapshot_queued",
                "data": {"path": str(target)},
            }

            finalized = _finalize_appctl_result(payload, result, timeout_sec=0.1)

        self.assertTrue(finalized["ok"])
        self.assertTrue(finalized["queued"])
        self.assertTrue(finalized["data"]["artifact_ready"])
        self.assertTrue(finalized["data"]["artifact"]["path_exists"])
        self.assertGreater(finalized["data"]["artifact"]["path_size"], 0)

    def test_capture_snapshot_queued_result_keeps_missing_artifact_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "missing.png"
            payload = {"command": "capture-snapshot", "path": str(target)}
            result = {
                "ok": True,
                "queued": True,
                "message": "snapshot_queued",
                "data": {"path": str(target)},
            }

            finalized = _finalize_appctl_result(payload, result, timeout_sec=0.1)

        self.assertTrue(finalized["ok"])
        self.assertTrue(finalized["queued"])
        self.assertFalse(finalized["data"]["artifact_ready"])
        self.assertFalse(finalized["data"]["artifact"]["path_exists"])
        self.assertEqual(finalized["data"]["artifact"]["path_size"], 0)

    def test_guided_subtitle_run_timeout_reports_follow_up_status_evidence(self):
        media_path = "/tmp/demo.mp4"
        payload = {"command": "guided-subtitle-run", "path": media_path}
        result = {
            "ok": False,
            "accepted": False,
            "queued": False,
            "error": "command_timeout",
            "data": {},
        }

        def _fake_sender(status_payload, *, timeout_sec):
            self.assertEqual(status_payload["command"], "guided-subtitle-status")
            self.assertGreaterEqual(timeout_sec, 0.5)
            return {
                "ok": True,
                "data": {
                    "editor_media_path": media_path,
                    "editor_state": "ST_PROC",
                    "backend_active": True,
                    "guided_snapshot_run": {"active": True},
                },
            }

        finalized = _finalize_appctl_result(payload, result, timeout_sec=0.1, sender=_fake_sender)

        self.assertFalse(finalized["ok"])
        self.assertEqual(finalized["error"], "command_timeout")
        self.assertTrue(finalized["data"]["post_timeout_status"]["ok"])
        evidence = finalized["data"]["post_timeout_evidence"]
        self.assertTrue(evidence["matched_path"])
        self.assertTrue(evidence["work_may_have_started"])


if __name__ == "__main__":
    unittest.main()
