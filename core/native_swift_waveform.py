from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import numpy as np

from core.native_swift_subtitle import find_native_cli_path


def _enabled() -> bool:
    value = os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_WAVEFORM", "").lower()
    if value in {"0", "false", "off", "no"}:
        return False
    return value in {"1", "true", "on", "yes"} or bool(os.environ.get("AI_SUBTITLE_STUDIO_BUNDLE_RESOURCES"))


def downsample_f32le_via_swift(
    raw: bytes | bytearray | memoryview | None,
    *,
    sample_rate: int,
    points_per_second: int,
    duration: float | None = None,
) -> tuple[np.ndarray, float] | None:
    if not raw or not _enabled():
        return None
    cli = find_native_cli_path()
    if cli is None:
        return None
    args = [
        str(cli),
        "waveform-peaks-f32le",
        "--sample-rate",
        str(int(sample_rate)),
        "--points-per-second",
        str(int(points_per_second)),
    ]
    if duration is not None and float(duration or 0.0) > 0.0:
        args.extend(["--duration", str(float(duration or 0.0))])
    try:
        proc = subprocess.run(
            args,
            input=bytes(raw),
            check=True,
            capture_output=True,
            timeout=60,
        )
        payload: dict[str, Any] = json.loads(proc.stdout.decode("utf-8") or "{}")
        waveform = np.asarray(payload.get("waveform") or [], dtype=np.float32)
        dur = float(payload.get("duration") or 0.0)
    except Exception:
        return None
    if waveform.size <= 0 or dur <= 0:
        return None
    return waveform, dur


__all__ = ["downsample_f32le_via_swift"]
