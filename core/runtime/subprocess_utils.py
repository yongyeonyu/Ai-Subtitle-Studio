# Version: 01.00.00
# Phase: PHASE2
"""Shared subprocess capture helpers with optional retry/backoff."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterable

from core.platform_compat import hidden_subprocess_kwargs


def run_subprocess_capture(
    cmd: Iterable[object],
    *,
    timeout: float | None = None,
    env: dict | None = None,
    cwd: str | None = None,
    input_text: str | None = None,
    strip_qt: bool = False,
    retries: int = 0,
    retry_backoff_sec: float = 0.0,
    retry_backoff_multiplier: float = 2.0,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with common encoding/env flags and optional retry/backoff."""
    argv = [str(item) for item in cmd]
    retry_limit = max(0, int(retries or 0))
    backoff = max(0.0, float(retry_backoff_sec or 0.0))
    multiplier = max(1.0, float(retry_backoff_multiplier or 1.0))

    attempt = 0
    while True:
        try:
            kwargs = hidden_subprocess_kwargs(strip_qt=strip_qt, extra_env=env)
            return subprocess.run(
                argv,
                capture_output=capture_output,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                cwd=cwd,
                input=input_text,
                shell=False,
                **kwargs,
            )
        except (OSError, subprocess.TimeoutExpired):
            if attempt >= retry_limit:
                raise
            attempt += 1
            if backoff > 0.0:
                time.sleep(backoff)
                backoff *= multiplier


def run_subprocess_capture_cancelable(
    cmd: Iterable[object],
    *,
    timeout: float | None = None,
    env: dict | None = None,
    cwd: str | None = None,
    strip_qt: bool = False,
    cancel_callback=None,
    poll_interval_sec: float = 0.05,
    capture_output: bool = True,
) -> tuple[subprocess.CompletedProcess[str] | None, bool]:
    """Run a subprocess and allow cooperative cancellation while it is active."""
    argv = [str(item) for item in cmd]
    kwargs = hidden_subprocess_kwargs(strip_qt=strip_qt, extra_env=env)
    poll_sec = max(0.02, float(poll_interval_sec or 0.05))
    deadline = None
    if timeout is not None:
        deadline = time.monotonic() + max(0.0, float(timeout or 0.0))

    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        shell=False,
        **kwargs,
    )
    while True:
        if callable(cancel_callback):
            try:
                if cancel_callback():
                    try:
                        process.terminate()
                    except Exception:
                        pass
                    try:
                        process.communicate(timeout=max(0.05, poll_sec))
                    except subprocess.TimeoutExpired:
                        try:
                            process.kill()
                        except Exception:
                            pass
                        process.communicate()
                    return None, True
            except Exception:
                pass
        wait_timeout = poll_sec
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                try:
                    process.kill()
                except Exception:
                    pass
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
            wait_timeout = min(wait_timeout, remaining)
        try:
            stdout, stderr = process.communicate(timeout=wait_timeout)
            return (
                subprocess.CompletedProcess(
                    argv,
                    int(process.returncode or 0),
                    stdout,
                    stderr,
                ),
                False,
            )
        except subprocess.TimeoutExpired:
            continue
