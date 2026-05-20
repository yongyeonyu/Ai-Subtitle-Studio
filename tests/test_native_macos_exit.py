import unittest
from pathlib import Path
from unittest import mock

from core.native_macos_exit import schedule_native_forced_exit


class NativeMacOSExitTests(unittest.TestCase):
    def test_schedule_native_forced_exit_launches_detached_watchdog(self):
        with mock.patch("core.native_macos_exit.sys.platform", "darwin"), \
             mock.patch("core.native_macos_exit.native_swift_runtime_enabled", return_value=True) as runtime_enabled, \
             mock.patch("core.native_macos_exit.find_native_cli_path", return_value=Path("/tmp/AIStudioNativeCLI")), \
             mock.patch("core.native_macos_exit.hidden_subprocess_kwargs", return_value={"env": {}}), \
             mock.patch("core.native_macos_exit.subprocess.Popen") as popen:

            scheduled = schedule_native_forced_exit(pid=1234, delay_ms=20, term_grace_ms=50)

        self.assertTrue(scheduled)
        runtime_enabled.assert_called_once_with(
            "AI_SUBTITLE_STUDIO_SWIFT_EXIT_WATCHDOG",
            default_on_macos=False,
        )
        args = popen.call_args.args[0]
        self.assertEqual(args[:3], ["/tmp/AIStudioNativeCLI", "app-exit-watchdog", "--pid"])
        self.assertIn("1234", args)
        self.assertIn("--delay-ms", args)
        self.assertIn("20", args)
        self.assertIn("--term-grace-ms", args)
        self.assertIn("50", args)
        self.assertTrue(popen.call_args.kwargs["close_fds"])
        self.assertEqual(popen.call_args.kwargs["stdout"], -3)

    def test_schedule_native_forced_exit_skips_non_macos(self):
        with mock.patch("core.native_macos_exit.sys.platform", "linux"), \
             mock.patch("core.native_macos_exit.subprocess.Popen") as popen:

            scheduled = schedule_native_forced_exit(pid=1234)

        self.assertFalse(scheduled)
        popen.assert_not_called()

    def test_schedule_native_forced_exit_is_opt_in_on_macos(self):
        with mock.patch("core.native_macos_exit.sys.platform", "darwin"), \
             mock.patch("core.native_macos_exit.native_swift_runtime_enabled", return_value=False), \
             mock.patch("core.native_macos_exit.subprocess.Popen") as popen:

            scheduled = schedule_native_forced_exit(pid=1234)

        self.assertFalse(scheduled)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
