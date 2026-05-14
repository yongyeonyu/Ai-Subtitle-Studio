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
