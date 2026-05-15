import subprocess
import unittest
from unittest.mock import patch

from core.runtime.subprocess_utils import (
    run_subprocess_capture,
    run_subprocess_capture_cancelable,
)


class RuntimeSubprocessUtilsTests(unittest.TestCase):
    def test_run_subprocess_capture_cancelable_returns_completed_process(self):
        class _DoneProcess:
            def __init__(self, argv, **_kwargs):
                self.args = list(argv)
                self.returncode = 0

            def communicate(self, timeout=None):
                self.returncode = 0
                return ("stdout-ok", "")

            def terminate(self):
                raise AssertionError("terminate should not be called for a completed process")

            def kill(self):
                raise AssertionError("kill should not be called for a completed process")

        with patch("core.runtime.subprocess_utils.subprocess.Popen", side_effect=_DoneProcess):
            completed, cancelled = run_subprocess_capture_cancelable(["echo", "ok"], timeout=1.0)

        self.assertFalse(cancelled)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "stdout-ok")

    def test_run_subprocess_capture_cancelable_terminates_when_cancel_requested(self):
        calls = {"cancel": 0}

        class _BusyProcess:
            def __init__(self, argv, **_kwargs):
                self.args = list(argv)
                self.returncode = None
                self.terminated = False
                self.killed = False

            def communicate(self, timeout=None):
                if self.terminated or self.killed:
                    self.returncode = -15 if self.terminated else -9
                    return ("", "")
                raise subprocess.TimeoutExpired(self.args, timeout)

            def terminate(self):
                self.terminated = True

            def kill(self):
                self.killed = True

        def cancel_callback():
            calls["cancel"] += 1
            return calls["cancel"] >= 2

        process_box = {}

        def build_process(argv, **kwargs):
            proc = _BusyProcess(argv, **kwargs)
            process_box["proc"] = proc
            return proc

        with patch("core.runtime.subprocess_utils.subprocess.Popen", side_effect=build_process):
            completed, cancelled = run_subprocess_capture_cancelable(
                ["ffmpeg", "-i", "input.mp4", "out.wav"],
                timeout=5.0,
                cancel_callback=cancel_callback,
                poll_interval_sec=0.01,
            )

        self.assertTrue(cancelled)
        self.assertIsNone(completed)
        self.assertTrue(process_box["proc"].terminated)

    def test_run_subprocess_capture_preserves_existing_retry_behavior(self):
        attempts = {"count": 0}

        def fake_run(*_args, **_kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise subprocess.TimeoutExpired("cmd", 1.0)
            return subprocess.CompletedProcess(["cmd"], 0, "ok", "")

        with patch("core.runtime.subprocess_utils.hidden_subprocess_kwargs", return_value={}), \
             patch("core.runtime.subprocess_utils.subprocess.run", side_effect=fake_run):
            completed = run_subprocess_capture(["cmd"], timeout=1.0, retries=1, retry_backoff_sec=0.0)

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "ok")


if __name__ == "__main__":
    unittest.main()
