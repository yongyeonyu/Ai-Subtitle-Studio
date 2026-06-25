# Version: 03.15.00
# Phase: PHASE2
"""Shared video codec options for ffmpeg decode/encode commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path


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


def roughcut_render_mode(mode: str | None = None) -> str:
    """Return roughcut export mode.

    `sync_safe` decodes kept ranges, resets timestamps, and writes CFR parts so
    output duration matches the EDL/SRT timeline.
    `copy` keeps original compressed packets when possible. It is the fastest and
    has zero generation loss, but cuts are constrained by codec/container rules.
    `lossless` decodes only the kept ranges and writes a lossless mezzanine.
    `preview_hevc` keeps the previous small-preview HEVC behavior.
    """
    value = str(mode or os.environ.get("AI_SUBTITLE_ROUGHCUT_RENDER_MODE", "sync_safe") or "sync_safe").strip().lower()
    if value in {"sync", "sync-safe", "sync_safe", "safe", "accurate", "precise"}:
        return "sync_safe"
    if value in {"copy", "stream_copy", "stream-copy", "remux", "passthrough"}:
        return "copy"
    if value in {"lossless", "ffv1", "x264_lossless", "mezzanine"}:
        return "lossless"
    if value in {"preview", "hevc", "preview_hevc"}:
        return "preview_hevc"
    return "sync_safe"


def lossless_video_encode_args(output_path: str | os.PathLike[str] | None = None) -> tuple[str, ...]:
    """Build lossless ffmpeg video/audio args suitable for roughcut mezzanines."""
    suffix = Path(str(output_path or "")).suffix.lower()
    if suffix in {".mkv", ".matroska", ""}:
        return (
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-g",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "flac",
        )
    if suffix in {".mov", ".mp4", ".m4v"}:
        return (
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "alac",
        )
    return (
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-g",
        "1",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "flac",
    )
