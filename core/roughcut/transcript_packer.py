# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

from typing import Iterable

from .models import PackedPhrase, SubtitleSegment, subtitle_from_dict


def _normalize_segments(segments: Iterable[SubtitleSegment | dict]) -> list[SubtitleSegment]:
    normalized: list[SubtitleSegment] = []
    for index, segment in enumerate(segments):
        item = subtitle_from_dict(segment, fallback_id=index) if isinstance(segment, dict) else segment
        if item.text and item.end > item.start:
            normalized.append(item)
    return sorted(normalized, key=lambda seg: (seg.start, seg.end))


def _source_id(segment: SubtitleSegment, fallback: int) -> int:
    return segment.subtitle_id if segment.subtitle_id is not None else fallback


def pack_transcript(
    segments: Iterable[SubtitleSegment | dict],
    silence_gap_threshold: float = 0.5,
    max_phrase_duration: float = 12.0,
    max_chars: int = 280,
) -> list[PackedPhrase]:
    """Pack subtitle rows into larger phrase units for cheap roughcut analysis."""
    items = _normalize_segments(segments)
    if not items:
        return []

    gap_threshold = max(0.0, float(silence_gap_threshold))
    duration_limit = max(0.1, float(max_phrase_duration))
    char_limit = max(1, int(max_chars))

    phrases: list[PackedPhrase] = []
    current: list[SubtitleSegment] = []
    current_ids: list[int] = []

    def flush() -> None:
        if not current:
            return
        text = " ".join(seg.text for seg in current if seg.text).strip()
        if text:
            phrases.append(
                PackedPhrase(
                    phrase_id=f"phrase_{len(phrases) + 1:04d}",
                    start=current[0].start,
                    end=current[-1].end,
                    text=text,
                    speaker=current[0].speaker,
                    source_indices=tuple(current_ids),
                )
            )
        current.clear()
        current_ids.clear()

    for index, item in enumerate(items):
        if not current:
            current.append(item)
            current_ids.append(_source_id(item, index))
            continue

        previous = current[-1]
        gap = item.start - previous.end
        merged_text = " ".join([*(seg.text for seg in current), item.text]).strip()
        would_exceed_duration = item.end - current[0].start > duration_limit
        would_exceed_chars = len(merged_text) > char_limit
        speaker_changed = bool(previous.speaker and item.speaker and previous.speaker != item.speaker)
        long_silence = gap >= gap_threshold

        if long_silence or speaker_changed or would_exceed_duration or would_exceed_chars:
            flush()

        current.append(item)
        current_ids.append(_source_id(item, index))

    flush()
    return phrases


def format_packed_transcript(phrases: Iterable[PackedPhrase]) -> str:
    lines: list[str] = []
    for phrase in phrases:
        speaker = phrase.speaker or "S?"
        lines.append(f"[{phrase.start:08.2f}-{phrase.end:08.2f}] {speaker}: {phrase.text}")
    return "\n".join(lines)
