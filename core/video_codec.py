# Version: 03.15.00
# Phase: PHASE2
"""Shared video codec options for ffmpeg decode/encode commands."""

from __future__ import annotations

import os
import sys


def ffmpeg_hwdecode_args() -> tuple[str, ...]:
    """Prefer hardware decoding when ffmpeg is doing actual video decode work."""
    if sys.platform == "darwin":
        return ("-hwaccel", "videotoolbox")
    return ("-hwaccel", "auto")


def hevc_encoder_name() -> str:
    """Return the preferred HEVC encoder name, overridable for local setups."""
    override = str(os.environ.get("AI_SUBTITLE_HEVC_ENCODER", "") or "").strip()
    if override:
        return override
    if sys.platform == "darwin":
        return "hevc_videotoolbox"
    return "libx265"


def hevc_encode_args(*, quality: str = "balanced") -> tuple[str, ...]:
    """Build compatible H.265/HEVC video encode arguments."""
    encoder = hevc_encoder_name()
    args: list[str] = ["-c:v", encoder, "-pix_fmt", "yuv420p"]
    if encoder == "hevc_videotoolbox":
        args.extend(["-tag:v", "hvc1"])
        if quality == "fast":
            args.extend(["-b:v", "8M"])
        else:
            args.extend(["-b:v", "12M"])
    elif encoder == "libx265":
        args.extend(["-preset", "medium", "-crf", "23"])
    else:
        args.extend(["-crf", "23"])
    return tuple(args)
