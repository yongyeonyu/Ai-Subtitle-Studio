# Version: 03.00.26
# Phase: PHASE2
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .models import EDLSegment


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _segment_id(index: int, segment: dict[str, Any]) -> int:
    value = segment.get("id", segment.get("subtitle_id", index + 1))
    try:
        return int(value)
    except (TypeError, ValueError):
        return index + 1


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> tuple[float, float] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return None
    return start, end


def retime_subtitles_for_edl(
    subtitle_segments: Iterable[dict[str, Any]],
    edl_segments: Iterable[EDLSegment],
    min_duration: float = 0.03,
) -> list[dict[str, Any]]:
    """Clip subtitle segments to EDL ranges and remap them onto roughcut output time."""
    subtitles = [dict(segment) for segment in subtitle_segments if not segment.get("is_gap")]
    minimum = max(0.0, float(min_duration))
    retimed: list[dict[str, Any]] = []

    for edl in edl_segments:
        edl_timeline_start = _as_float(edl.timeline_start, edl.source_start)
        edl_timeline_end = _as_float(edl.timeline_end, edl.source_end)
        for index, subtitle in enumerate(subtitles):
            source_start = _as_float(subtitle.get("start"))
            source_end = _as_float(subtitle.get("end"), source_start)
            clipped = _overlap(source_start, source_end, edl_timeline_start, edl_timeline_end)
            if clipped is None:
                continue
            clip_start, clip_end = clipped
            output_start = edl.output_start + (clip_start - edl_timeline_start)
            output_end = edl.output_start + (clip_end - edl_timeline_start)
            if output_end - output_start < minimum:
                continue
            retimed.append(
                {
                    "id": len(retimed) + 1,
                    "source_id": _segment_id(index, subtitle),
                    "source_start": round(clip_start, 3),
                    "source_end": round(clip_end, 3),
                    "start": round(output_start, 3),
                    "end": round(output_end, 3),
                    "text": str(subtitle.get("text", "") or "").strip(),
                    "speaker": subtitle.get("speaker"),
                    "edl_segment_id": edl.segment_id,
                    "chapter_id": edl.chapter_id,
                }
            )

    return retimed


def _srt_timestamp(seconds: float) -> str:
    value = max(0.0, float(seconds or 0.0))
    total_ms = int(round(value * 1000.0))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_srt(subtitle_segments: Iterable[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(subtitle_segments, start=1):
        text = str(segment.get("text", "") or "").strip()
        if not text:
            continue
        start = _srt_timestamp(_as_float(segment.get("start")))
        end = _srt_timestamp(_as_float(segment.get("end")))
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def save_retimed_srt(path: str | Path, subtitle_segments: Iterable[dict[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(format_srt(subtitle_segments), encoding="utf-8")
    return target
