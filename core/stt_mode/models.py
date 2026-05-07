# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Stable STT Mode schema constants and frame-canonical timing helpers."""
from __future__ import annotations

from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame


STT_MODE_STATE_SCHEMA = "ai_subtitle_studio.stt_mode_state.v1"
STT_MODE_LEARNING_SCHEMA = "ai_subtitle_studio.stt_mode_learning.v1"
STT_LORA_BUNDLE_SCHEMA = "ai_subtitle_studio.stt_lora_bundle.v1"

STT_WORK_SEGMENT_SOURCE = "stt_vad_ensemble"
RAW_DICTATION_SOURCE = "human_dictation"
FINAL_SUBTITLE_SOURCE = "human_dictation_resegmented"

STT_WORK_STATUS = (
    "empty",
    "listened",
    "input_done",
    "resegmented",
    "needs_review",
    "skipped",
)

RAW_DICTATION_STATUS = (
    "empty",
    "input_done",
    "locked",
    "needs_review",
)

FINAL_SUBTITLE_STATUS = (
    "auto_generated",
    "manual_edited",
    "locked",
    "needs_review",
)


def build_frame_range(
    start_frame: int,
    end_frame: int,
    *,
    timeline_frame_rate: float | int | str | None = None,
) -> dict[str, Any]:
    fps = normalize_fps(timeline_frame_rate or 30.0)
    start = max(0, int(start_frame or 0))
    end = max(start, int(end_frame or start))
    return {
        "unit": "frame",
        "start": start,
        "end": end,
        "timeline_frame_rate": fps,
    }


def canonical_frame_timing(
    start_sec: float | int | str | None,
    end_sec: float | int | str | None,
    *,
    frame_rate: float | int | str | None = None,
    timeline_frame_rate: float | int | str | None = None,
    timeline_start_sec: float | int | str | None = None,
    timeline_end_sec: float | int | str | None = None,
) -> dict[str, Any]:
    """Return STT Mode timing fields with seconds derived from frame/fps values."""
    source_fps = normalize_fps(frame_rate or timeline_frame_rate or 30.0)
    timeline_fps = normalize_fps(timeline_frame_rate or source_fps)
    source_start_frame = sec_to_frame(start_sec, source_fps)
    source_end_frame = max(source_start_frame, sec_to_frame(end_sec, source_fps))
    timeline_start_frame = sec_to_frame(
        start_sec if timeline_start_sec is None else timeline_start_sec,
        timeline_fps,
    )
    timeline_end_frame = max(
        timeline_start_frame,
        sec_to_frame(end_sec if timeline_end_sec is None else timeline_end_sec, timeline_fps),
    )
    return {
        "start_frame": source_start_frame,
        "end_frame": source_end_frame,
        "timeline_start_frame": timeline_start_frame,
        "timeline_end_frame": timeline_end_frame,
        "frame_rate": source_fps,
        "timeline_frame_rate": timeline_fps,
        "frame_range": build_frame_range(
            timeline_start_frame,
            timeline_end_frame,
            timeline_frame_rate=timeline_fps,
        ),
        "start": frame_to_sec(source_start_frame, source_fps),
        "end": frame_to_sec(source_end_frame, source_fps),
        "timeline_start": frame_to_sec(timeline_start_frame, timeline_fps),
        "timeline_end": frame_to_sec(timeline_end_frame, timeline_fps),
    }


__all__ = [
    "FINAL_SUBTITLE_SOURCE",
    "FINAL_SUBTITLE_STATUS",
    "RAW_DICTATION_SOURCE",
    "RAW_DICTATION_STATUS",
    "STT_LORA_BUNDLE_SCHEMA",
    "STT_MODE_LEARNING_SCHEMA",
    "STT_MODE_STATE_SCHEMA",
    "STT_WORK_SEGMENT_SOURCE",
    "STT_WORK_STATUS",
    "build_frame_range",
    "canonical_frame_timing",
]
