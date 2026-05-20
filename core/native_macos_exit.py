from __future__ import annotations

import os
import subprocess
import sys

from core.native_swift_subtitle import find_native_cli_path, native_swift_runtime_enabled
from core.platform_compat import hidden_subprocess_kwargs


def schedule_native_forced_exit(
    *,
    pid: int | None = None,
    delay_ms: int = 20,
    term_grace_ms: int = 50,
) -> bool:
    """Start a detached Swift watchdog that can terminate this app if Python stalls."""

    if sys.platform != "darwin":
        return False
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_EXIT_WATCHDOG", default_on_macos=False):
        return False
    cli = find_native_cli_path()
    if cli is None:
        return False
    target_pid = int(pid or os.getpid())
    if target_pid <= 0:
        return False
    safe_delay = max(0, int(delay_ms or 0))
    safe_grace = max(0, int(term_grace_ms or 0))
    kwargs = hidden_subprocess_kwargs(strip_qt=True)
    kwargs.update(
        {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }
    )
    if os.name == "posix":
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [
                str(cli),
                "app-exit-watchdog",
                "--pid",
                str(target_pid),
                "--delay-ms",
                str(safe_delay),
                "--term-grace-ms",
                str(safe_grace),
            ],
            **kwargs,
        )
        return True
    except Exception:
        return False


__all__ = ["schedule_native_forced_exit"]
