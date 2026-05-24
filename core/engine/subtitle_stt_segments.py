from __future__ import annotations

"""Pure-Python STT1/STT2 candidate segment facade for timeline feed rows."""

from dataclasses import dataclass
from typing import Any


SUBTITLE_STT_SEGMENTS_FACADE_SCHEMA = "ai_subtitle_studio.subtitle_stt_segments.facade.v1"


@dataclass(frozen=True)
class PreparedSttPreviewRows:
    schema: str
    source_label: str
    rows: list[dict[str, Any]]


def normalize_stt_source_label(source_label: str | None, *, default: str = "STT1") -> str:
    label = str(source_label or default or "STT1").strip().upper()
    return label or "STT1"


def prepare_stt_preview_timeline_rows(
    segments: list[dict[str, Any]],
    *,
    source_label: str = "STT1",
    clip_offset: float = 0.0,
    clip_idx: int | None = None,
    clip_path: str | None = None,
    optimized: bool = False,
    optimizer_name: str | None = None,
) -> PreparedSttPreviewRows:
    label = normalize_stt_source_label(source_label)
    offset = float(clip_offset or 0.0)
    optimizer = str(
        optimizer_name
        or ("subtitle_split_gap_rules" if optimized else "raw_realtime")
    )
    rows: list[dict[str, Any]] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg.get("start", 0.0) or 0.0) + offset
            end = float(seg.get("end", start) or start) + offset
        except Exception:
            continue
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        row = dict(seg)
        row["start"] = start
        row["end"] = max(start + 0.05, end)
        row["text"] = text
        row["stt_preview_source"] = label
        row["stt_pending"] = True
        row["_live_stt_preview"] = True
        row["stt_preview_optimized"] = bool(optimized)
        row["stt_preview_optimizer"] = optimizer
        if clip_idx is not None:
            row["_clip_idx"] = clip_idx
        if clip_path:
            row["_clip_file"] = clip_path
        rows.append(row)
    return PreparedSttPreviewRows(
        schema=SUBTITLE_STT_SEGMENTS_FACADE_SCHEMA,
        source_label=label,
        rows=rows,
    )


__all__ = [
    "PreparedSttPreviewRows",
    "SUBTITLE_STT_SEGMENTS_FACADE_SCHEMA",
    "normalize_stt_source_label",
    "prepare_stt_preview_timeline_rows",
]
