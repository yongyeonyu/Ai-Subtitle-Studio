"""Shared timeline display-time helpers."""

from __future__ import annotations

from typing import Any

from core.frame_time import frame_to_sec, normalize_fps


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(round(float(value)))
    except Exception:
        return None


def _first_float(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key), None)
        if value is not None:
            return value
    return None


def _row_fps(row: dict[str, Any]) -> float | None:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    for key in ("timeline_frame_rate", "frame_rate", "fps", "source_frame_rate"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return normalize_fps(value)
            except Exception:
                continue
    value = frame_range.get("timeline_frame_rate")
    if value not in (None, ""):
        try:
            return normalize_fps(value)
        except Exception:
            return None
    return None


def _frame_time(
    row: dict[str, Any],
    keys: tuple[str, ...],
    fps: float | None,
    *,
    frame_range_key: str,
) -> float | None:
    if fps is None:
        return None
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    for key in keys:
        value = _safe_int(row.get(key))
        if value is not None:
            return frame_to_sec(max(0, value), fps)
    value = _safe_int(frame_range.get(frame_range_key))
    if value is not None:
        return frame_to_sec(max(0, value), fps)
    return None


def _is_stt_preview_row(row: dict[str, Any]) -> bool:
    if bool(row.get("stt_pending") or row.get("_live_stt_preview")):
        return True
    source = str(row.get("stt_preview_source") or "").strip().upper()
    return source in {"STT", "STT1", "STT2"}


def _word_time_span(row: dict[str, Any], raw_start: float | None, raw_end: float | None) -> tuple[float, float] | None:
    if not _is_stt_preview_row(row):
        return None
    starts: list[float] = []
    ends: list[float] = []
    for word in list(row.get("words") or []):
        if not isinstance(word, dict):
            continue
        start = _safe_float(word.get("start"), None)
        end = _safe_float(word.get("end"), None)
        if start is None or end is None or end <= start:
            continue
        starts.append(max(0.0, start))
        ends.append(max(0.0, end))
    if not starts or not ends:
        return None
    word_start = min(starts)
    word_end = max(ends)
    if word_end <= word_start:
        return None
    if raw_start is not None and raw_end is not None:
        # Reject clearly local word timestamps, e.g. a chunk-local 0.2s word on a
        # 60s timeline segment. Later absolute word spans are intentional: they
        # correct rolling-window lead-in that otherwise makes STT draw too early.
        if word_start < raw_start - 0.35:
            return None
        if word_start > max(raw_end, raw_start) + 12.0:
            return None
    return word_start, word_end


def segment_display_time_bounds(row: Any) -> tuple[float, float]:
    """Return the time span that should be used for timeline display/hit tests.

    STT rows often preserve the recognizer window as ``start/end`` while also
    carrying a corrected timeline frame/span or word timestamps. Rendering must
    follow the corrected display span so STT candidates do not appear ahead of
    the audible waveform.
    """

    if not isinstance(row, dict):
        value = _safe_float(row, 0.0) or 0.0
        return value, value

    raw_start = _first_float(row, ("start", "timeline_sec", "time"))
    raw_end = _first_float(row, ("end",))
    if raw_end is None:
        raw_end = raw_start

    start = _first_float(row, ("timeline_start", "display_start"))
    end = _first_float(row, ("timeline_end", "display_end"))

    word_span = _word_time_span(row, raw_start, raw_end)
    if word_span is not None:
        timeline_is_corrected = bool(
            row.get("stt_preview_display_aligned_to_subtitle_segments")
            or row.get("preview_aligned_to_subtitle_segments")
            or row.get("stt_aligned_to_subtitle_segments")
        )
        if start is not None and raw_start is not None and abs(start - raw_start) > 0.12:
            timeline_is_corrected = True
        if not timeline_is_corrected:
            start, end = word_span
    if start is None and end is None and word_span is not None:
        start, end = word_span

    fps = _row_fps(row)
    if start is None:
        start = _frame_time(row, ("timeline_start_frame", "start_frame"), fps, frame_range_key="start")
    if end is None:
        end = _frame_time(row, ("timeline_end_frame", "end_frame"), fps, frame_range_key="end")

    if start is None:
        start = raw_start if raw_start is not None else 0.0
    if end is None:
        end = raw_end if raw_end is not None else start

    start = max(0.0, float(start or 0.0))
    end = max(0.0, float(end if end is not None else start))
    if end < start:
        start, end = end, start
    return start, end
