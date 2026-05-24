from __future__ import annotations

"""Pure-Python facade for subtitle waveform render-feed data."""

from typing import Any

import numpy as np


SUBTITLE_WAVEFORM_FACADE_SCHEMA = "ai_subtitle_studio.subtitle_waveform.facade.v1"


def waveform_speech_ranges(
    waveform_len: int,
    total_duration: float,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> list[tuple[int, int]]:
    wf_len = max(0, int(waveform_len or 0))
    if wf_len <= 0:
        return []
    total = float(total_duration or 0.0)
    vad_scale = (wf_len / total) if total > 0 else 100.0
    ranges: list[tuple[int, int]] = []
    for item in list(vad_segments or []):
        if not isinstance(item, dict):
            continue
        try:
            start_idx = max(0, int(float(item["start"]) * vad_scale))
            end_idx = min(wf_len, int(float(item["end"]) * vad_scale) + 1)
        except Exception:
            continue
        if end_idx > start_idx:
            ranges.append((start_idx, end_idx))
    return ranges


def python_waveform_columns(
    waveform: Any,
    *,
    width: int,
    total_duration: float,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> list[tuple[int, bool]]:
    if waveform is None or int(width or 0) <= 0:
        return []
    values = np.asarray(waveform, dtype=np.float32)
    if values.size <= 0:
        return []
    wf_len = int(values.size)
    speech_ranges = waveform_speech_ranges(wf_len, total_duration, vad_segments)
    columns: list[tuple[int, bool]] = []
    range_idx = 0
    safe_width = max(1, int(width or 0))
    for x in range(safe_width):
        idx = min(wf_len - 1, int((x / safe_width) * wf_len))
        while range_idx < len(speech_ranges) and idx >= speech_ranges[range_idx][1]:
            range_idx += 1
        in_speech = range_idx < len(speech_ranges) and speech_ranges[range_idx][0] <= idx < speech_ranges[range_idx][1]
        columns.append((max(1, int(float(values[idx]) * 14)), in_speech))
    return columns


def build_waveform_columns(
    waveform: Any,
    *,
    width: int,
    total_duration: float,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    allow_native: bool = True,
) -> list[tuple[int, bool]]:
    if waveform is None or int(width or 0) <= 0:
        return []
    if allow_native:
        try:
            from core.native_swift_timeline import build_waveform_columns_via_swift

            native_columns = build_waveform_columns_via_swift(
                waveform,
                width=int(width),
                total_duration=float(total_duration or 0.0),
                vad_segments=list(vad_segments or []),
            )
            if native_columns is not None and len(native_columns) == int(width):
                return native_columns
        except Exception:
            pass
    return python_waveform_columns(
        waveform,
        width=int(width),
        total_duration=float(total_duration or 0.0),
        vad_segments=vad_segments,
    )


__all__ = [
    "SUBTITLE_WAVEFORM_FACADE_SCHEMA",
    "build_waveform_columns",
    "python_waveform_columns",
    "waveform_speech_ranges",
]
