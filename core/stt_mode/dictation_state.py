# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Raw human dictation state for STT Mode."""
from __future__ import annotations

from typing import Any

from core.stt_mode.models import RAW_DICTATION_SOURCE
from core.stt_mode.quality import normalize_text
from core.stt_mode.settings import stt_settings


_TIMING_KEYS = (
    "start",
    "end",
    "timeline_start",
    "timeline_end",
    "start_frame",
    "end_frame",
    "timeline_start_frame",
    "timeline_end_frame",
    "frame_rate",
    "timeline_frame_rate",
    "frame_range",
)


def _copy_timing(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source.get(key) for key in _TIMING_KEYS if key in source}


def create_raw_dictation_segment(
    stt_work_segment: dict[str, Any],
    text: str,
    *,
    input_provider: str = "manual",
    whisper_used: bool = False,
    settings: dict[str, Any] | None = None,
    raw_index: int | None = None,
) -> dict[str, Any]:
    """Create a raw human-input segment while preserving STT work timing."""
    cfg = stt_settings(settings)
    raw_text = str(text or "").replace("\u2028", "\n")
    normalized = normalize_text(raw_text)
    empty_policy = str(cfg.get("stt_mode_empty_input_policy") or "needs_review")
    status = "input_done" if normalized else ("skipped" if empty_policy == "skip" else "needs_review")
    index = int(raw_index or 0)
    if index <= 0:
        try:
            index = int(stt_work_segment.get("index", 0) or 0)
        except (TypeError, ValueError):
            index = 0
    if index <= 0:
        index = 1
    segment_id = str(stt_work_segment.get("id") or f"stt_segment_{index:04d}")
    item = {
        "id": f"dictation_raw_{index:04d}",
        "index": index,
        "stt_segment_id": segment_id,
        "source": RAW_DICTATION_SOURCE,
        "input_provider": str(input_provider or cfg.get("stt_mode_text_input_provider") or "manual"),
        "text": normalized,
        "raw_text": raw_text,
        "whisper_used": bool(whisper_used),
        "llm_used": False,
        "dictation_environment": "quiet_indoor",
        "status": status,
    }
    item.update(_copy_timing(stt_work_segment))
    return item


def upsert_raw_dictation(
    raw_segments: list[dict[str, Any]] | None,
    raw_segment: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [dict(row) for row in raw_segments or [] if isinstance(row, dict)]
    raw_id = str(raw_segment.get("id") or "")
    stt_id = str(raw_segment.get("stt_segment_id") or "")
    replaced = False
    for idx, row in enumerate(rows):
        if (raw_id and row.get("id") == raw_id) or (stt_id and row.get("stt_segment_id") == stt_id):
            rows[idx] = dict(raw_segment)
            replaced = True
            break
    if not replaced:
        rows.append(dict(raw_segment))
    rows.sort(key=lambda row: (row.get("timeline_start_frame", row.get("start_frame", 0)), row.get("index", 0)))
    return rows


__all__ = [
    "create_raw_dictation_segment",
    "upsert_raw_dictation",
]
