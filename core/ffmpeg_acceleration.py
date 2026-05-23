from __future__ import annotations

import os

from core.runtime import config
from core.runtime.setting_utils import setting_bool


def macos_videotoolbox_enabled(settings: dict | None = None) -> bool:
    env_value = os.environ.get("AI_SUBTITLE_STUDIO_FFMPEG_VIDEOTOOLBOX")
    if env_value is not None:
        return setting_bool(env_value, True)
    if not getattr(config, "IS_MAC", False):
        return False
    data = dict(settings or {})
    if not setting_bool(data.get("runtime_hardware_acceleration_enabled"), True):
        return False
    return setting_bool(data.get("ffmpeg_videotoolbox_decode_enabled"), True)


def ffmpeg_video_decode_accel_args(settings: dict | None = None) -> list[str]:
    if not macos_videotoolbox_enabled(settings):
        return []
    # This is a decode hint only. Do not force a hardware output pixel format:
    # FFmpeg scene/audio filters still need software frames/samples.
    return ["-hwaccel", "videotoolbox"]


__all__ = ["ffmpeg_video_decode_accel_args", "macos_videotoolbox_enabled"]
