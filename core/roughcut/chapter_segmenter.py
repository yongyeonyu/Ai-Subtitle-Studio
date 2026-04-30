# Version: 03.01.27
# Phase: PHASE2
from __future__ import annotations

import math
from collections.abc import Iterable

from .models import ChapterMetadata, SemanticChunk
from .topic_detector import detect_topic_shift, extract_keywords, keyword_entropy

_STORY_HINTS = ("핵심", "결론", "추천", "문제", "전환", "결과", "중요", "요약", "마지막")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _duration(chunk: SemanticChunk) -> float:
    return max(0.0, float(chunk.end) - float(chunk.start))


def _chunk_text(chunks: list[SemanticChunk]) -> str:
    return " ".join(chunk.text for chunk in chunks if chunk.text).strip()


def _snippet(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def _importance_score(chunks: list[SemanticChunk], duration: float, maximum: float) -> float:
    text = _chunk_text(chunks)
    entropy = min(1.0, keyword_entropy(text) / 4.0)
    shift = max((chunk.topic_shift_score for chunk in chunks), default=0.0)
    hint_text = " ".join(
        [text, " ".join(keyword for chunk in chunks for keyword in chunk.keywords)]
    )
    hint_score = 0.18 if any(hint in hint_text for hint in _STORY_HINTS) else 0.0
    duration_score = min(0.26, duration / max(maximum, 1.0) * 0.26)
    score = 0.26 + duration_score + (entropy * 0.22) + (shift * 0.18) + hint_score
    return round(_clamp(score), 4)


def _make_chapter(
    index: int,
    chunks: list[SemanticChunk],
    *,
    start: float | None = None,
    end: float | None = None,
    title_suffix: str = "",
    reason: str = "",
    needs_review: bool = False,
    maximum: float = 180.0,
) -> ChapterMetadata:
    text = _chunk_text(chunks)
    keywords = extract_keywords(text, top_k=8)
    title = " / ".join(keywords[:3]) if keywords else (chunks[0].title if chunks else f"Chapter {index}")
    if title_suffix:
        title = f"{title} {title_suffix}".strip()
    chapter_start = float(chunks[0].start if start is None else start)
    chapter_end = float(chunks[-1].end if end is None else end)
    duration = max(0.0, chapter_end - chapter_start)
    segment_ids = tuple(chunk.chunk_id for chunk in chunks)
    summary = _snippet(text, limit=120)
    if reason:
        summary = f"{summary} ({reason})" if summary else reason
    return ChapterMetadata(
        chapter_id=f"chapter_{index:04d}",
        title=title or f"Chapter {index}",
        start=chapter_start,
        end=max(chapter_start, chapter_end),
        summary=summary,
        tags=tuple(keywords),
        segment_ids=segment_ids,
        importance_score=_importance_score(chunks, duration, maximum),
        narrative_function="roughcut_seed",
        story_reason=reason,
        needs_review=needs_review or any(chunk.topic_shift_score < 0.25 for chunk in chunks),
    )


def _merge_short_chunks(chunks: list[SemanticChunk], minimum: float) -> list[tuple[list[SemanticChunk], str]]:
    if minimum <= 0.0 or len(chunks) <= 1:
        return [([chunk], "") for chunk in chunks]
    groups: list[tuple[list[SemanticChunk], str]] = []
    carry: list[SemanticChunk] = []

    def flush(reason: str) -> None:
        nonlocal carry
        if carry:
            groups.append((carry, reason))
            carry = []

    for chunk in chunks:
        carry.append(chunk)
        if sum(_duration(item) for item in carry) >= minimum:
            reason = "short_chunk_merged" if len(carry) > 1 else ""
            flush(reason)

    if carry:
        if groups:
            previous, previous_reason = groups.pop()
            merged = previous + carry
            reason = "; ".join(part for part in (previous_reason, "short_tail_merged") if part)
            groups.append((merged, reason))
        else:
            flush("short_single_chunk")
    return groups


def _split_long_group(
    chunks: list[SemanticChunk],
    maximum: float,
) -> list[tuple[float, float, str]]:
    start = float(chunks[0].start)
    end = float(chunks[-1].end)
    duration = max(0.0, end - start)
    if maximum <= 0.0 or duration <= maximum:
        return [(start, end, "")]
    parts = max(1, int(math.ceil(duration / maximum)))
    part_duration = duration / parts
    ranges: list[tuple[float, float, str]] = []
    for index in range(parts):
        part_start = start + (part_duration * index)
        part_end = end if index == parts - 1 else min(end, start + (part_duration * (index + 1)))
        ranges.append((part_start, part_end, f"split_long_chapter:{index + 1}/{parts}"))
    return ranges


def build_chapters(
    chunks: Iterable[SemanticChunk],
    min_chapter_duration: float = 15.0,
    max_chapter_duration: float = 180.0,
) -> list[ChapterMetadata]:
    """Compatibility wrapper for the roughcut chapter segmentation contract."""
    ordered = sorted(list(chunks or ()), key=lambda chunk: (chunk.start, chunk.end))
    if not ordered:
        return []
    minimum = max(0.0, float(min_chapter_duration))
    maximum = max(minimum or 1.0, float(max_chapter_duration))
    chapters: list[ChapterMetadata] = []
    for group, merge_reason in _merge_short_chunks(ordered, minimum):
        split_ranges = _split_long_group(group, maximum)
        for split_start, split_end, split_reason in split_ranges:
            reason = "; ".join(part for part in (merge_reason, split_reason) if part)
            chapters.append(
                _make_chapter(
                    len(chapters) + 1,
                    group,
                    start=split_start,
                    end=split_end,
                    title_suffix=f"({len(chapters) + 1})" if split_reason else "",
                    reason=reason,
                    needs_review=bool(reason),
                    maximum=maximum,
                )
            )
    return chapters


__all__ = ["build_chapters", "detect_topic_shift"]
