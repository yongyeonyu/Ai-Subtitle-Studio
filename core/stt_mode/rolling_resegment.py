# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Rolling-window STT resegmentation helpers."""
from __future__ import annotations

from typing import Any

from core.frame_time import normalize_fps
from core.stt_mode.finalizer import resegment_raw_dictation_window
from core.stt_mode.settings import setting_int


def _frame_value(row: dict[str, Any], key: str, fallback: int = 0) -> int:
    try:
        return int(row.get(key, fallback) or fallback)
    except (TypeError, ValueError):
        return fallback


def build_rolling_window(
    raw_segments: list[dict[str, Any]],
    *,
    current_raw_id: str | None = None,
    window_size: int = 2,
) -> dict[str, Any]:
    rows = [dict(row) for row in raw_segments or [] if isinstance(row, dict)]
    rows.sort(key=lambda row: (row.get("timeline_start_frame", row.get("start_frame", 0)), row.get("index", 0)))
    if not rows:
        return {}
    current_idx = len(rows) - 1
    if current_raw_id:
        for idx, row in enumerate(rows):
            if str(row.get("id") or "") == str(current_raw_id):
                current_idx = idx
                break
    size = max(1, int(window_size or 1))
    start_idx = max(0, current_idx - size + 1)
    window_rows = rows[start_idx:current_idx + 1]
    start_frame = min(_frame_value(row, "timeline_start_frame", _frame_value(row, "start_frame")) for row in window_rows)
    end_frame = max(_frame_value(row, "timeline_end_frame", _frame_value(row, "end_frame")) for row in window_rows)
    fps = normalize_fps(
        next((row.get("timeline_frame_rate") or row.get("frame_rate") for row in window_rows if row.get("timeline_frame_rate") or row.get("frame_rate")), 30.0)
    )
    return {
        "id": f"stt_window_{start_idx + 1:04d}_{current_idx + 1:04d}",
        "window_size": len(window_rows),
        "raw_dictation_ids": [str(row.get("id") or "") for row in window_rows if row.get("id")],
        "start_frame": start_frame,
        "end_frame": end_frame,
        "timeline_start_frame": start_frame,
        "timeline_end_frame": end_frame,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "frame_range": {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        },
        "text": " ".join(str(row.get("text") or row.get("raw_text") or "").strip() for row in window_rows).strip(),
        "raw_segments": window_rows,
    }


def _overlaps_window(segment: dict[str, Any], window: dict[str, Any]) -> bool:
    start = _frame_value(segment, "timeline_start_frame", _frame_value(segment, "start_frame"))
    end = _frame_value(segment, "timeline_end_frame", _frame_value(segment, "end_frame"))
    win_start = _frame_value(window, "timeline_start_frame", _frame_value(window, "start_frame"))
    win_end = _frame_value(window, "timeline_end_frame", _frame_value(window, "end_frame"))
    return max(start, win_start) < min(end, win_end)


def apply_rolling_resegmentation(
    *,
    raw_segments: list[dict[str, Any]],
    final_segments: list[dict[str, Any]] | None = None,
    current_raw_id: str | None = None,
    fps: float | int | str | None = None,
    settings: dict[str, Any] | None = None,
    stt_lora_policy: dict[str, Any] | None = None,
    subtitle_style_policy: dict[str, Any] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    window = build_rolling_window(
        raw_segments,
        current_raw_id=current_raw_id,
        window_size=setting_int(settings, "stt_mode_rolling_window_size", 2),
    )
    if not window:
        return {"rolling_window": {}, "final_segments": list(final_segments or []), "generated_segments": []}
    timeline_fps = normalize_fps(fps or window.get("timeline_frame_rate") or 30.0)
    generated = resegment_raw_dictation_window(
        rolling_window=window,
        raw_segments=list(window.get("raw_segments") or []),
        fps=timeline_fps,
        settings=settings,
        stt_lora_policy=stt_lora_policy,
        subtitle_style_policy=subtitle_style_policy,
        cut_boundaries=cut_boundaries,
    )
    preserved: list[dict[str, Any]] = []
    for row in final_segments or []:
        if not isinstance(row, dict):
            continue
        if _overlaps_window(row, window) and not (row.get("manual_edited") or row.get("locked")):
            continue
        preserved.append(dict(row))
    merged = preserved + generated
    merged.sort(key=lambda row: (row.get("timeline_start_frame", row.get("start_frame", 0)), row.get("index", 0)))
    for idx, row in enumerate(merged, start=1):
        row["index"] = idx
        row["line"] = idx - 1
    return {
        "rolling_window": window,
        "final_segments": merged,
        "generated_segments": generated,
    }


__all__ = [
    "apply_rolling_resegmentation",
    "build_rolling_window",
]
