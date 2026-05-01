# Version: 03.01.29
# Phase: PHASE2
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .models import ChapterMetadata, RoughCutMinorGroup, RoughCutSegment, SubtitleSegment

_MAJOR_CODES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_MAJOR_SEGMENTS = 26


def _duration(start: float, end: float) -> float:
    return max(0.0, float(end) - float(start))


def _major_code(index: int) -> str:
    index = max(0, min(int(index or 0), MAX_MAJOR_SEGMENTS - 1))
    return _MAJOR_CODES[index]


def _subtitle_ids_for_range(subtitles: list[SubtitleSegment], start: float, end: float) -> tuple[int, ...]:
    ids: list[int] = []
    for idx, subtitle in enumerate(subtitles):
        subtitle_id = subtitle.subtitle_id if subtitle.subtitle_id is not None else idx
        if subtitle.end > start and subtitle.start < end:
            ids.append(int(subtitle_id))
    return tuple(ids)


def _group_chapters(
    chapters: list[ChapterMetadata],
    *,
    min_major_duration: float,
    max_major_duration: float,
    max_subtitle_count: int,
    subtitles: list[SubtitleSegment],
) -> list[list[ChapterMetadata]]:
    if max_major_duration <= 0.0 and max_subtitle_count <= 0:
        return [[chapter] for chapter in chapters]

    groups: list[list[ChapterMetadata]] = []
    current: list[ChapterMetadata] = []

    def current_duration(items: list[ChapterMetadata]) -> float:
        if not items:
            return 0.0
        return _duration(items[0].start, items[-1].end)

    def current_subtitle_count(items: list[ChapterMetadata]) -> int:
        if not items:
            return 0
        return len(_subtitle_ids_for_range(subtitles, items[0].start, items[-1].end))

    for chapter in chapters:
        candidate = current + [chapter]
        too_long = max_major_duration > 0.0 and current and current_duration(candidate) > max_major_duration
        too_many_subtitles = max_subtitle_count > 0 and current and current_subtitle_count(candidate) > max_subtitle_count
        can_flush = current_duration(current) >= min_major_duration
        if (too_long or too_many_subtitles) and can_flush:
            groups.append(current)
            current = [chapter]
        else:
            current = candidate

    if current:
        groups.append(current)
    return groups


def build_major_roughcut_segments(
    chapters: Iterable[ChapterMetadata],
    subtitles: Iterable[SubtitleSegment] | None = None,
    *,
    media_duration: float | None = None,
    min_major_duration: float = 0.0,
    max_major_duration: float = 0.0,
    max_subtitle_count: int = 0,
    max_major_segment_count: int = MAX_MAJOR_SEGMENTS,
) -> tuple[tuple[RoughCutSegment, ...], tuple[ChapterMetadata, ...]]:
    """Assign PAGE 3-B major/minor IDs without removing the legacy chapter rows."""
    ordered = sorted(list(chapters or ()), key=lambda chapter: (chapter.start, chapter.end, chapter.chapter_id))
    subtitle_items = sorted(list(subtitles or ()), key=lambda subtitle: (subtitle.start, subtitle.end))
    groups = _group_chapters(
        ordered,
        min_major_duration=max(0.0, float(min_major_duration or 0.0)),
        max_major_duration=max(0.0, float(max_major_duration or 0.0)),
        max_subtitle_count=max(0, int(max_subtitle_count or 0)),
        subtitles=subtitle_items,
    )
    groups = _merge_groups_to_limit(
        groups,
        max_count=max(1, min(MAX_MAJOR_SEGMENTS, int(max_major_segment_count or MAX_MAJOR_SEGMENTS))),
    )

    major_segments: list[RoughCutSegment] = []
    minor_chapters: list[ChapterMetadata] = []
    major_ranges = _continuous_group_ranges(groups, media_duration=media_duration)

    for major_index, group in enumerate(groups):
        if not group:
            continue
        major_id = _major_code(major_index)
        minors: list[RoughCutMinorGroup] = []
        major_start, major_end = major_ranges[major_index] if major_index < len(major_ranges) else (
            min(chapter.start for chapter in group),
            max(chapter.end for chapter in group),
        )
        major_tags: list[str] = []
        needs_review = any(chapter.needs_review for chapter in group)
        confidence_values: list[float] = []

        for minor_index, chapter in enumerate(group, start=1):
            minor_code = f"{major_id}{minor_index}"
            subtitle_ids = _subtitle_ids_for_range(subtitle_items, chapter.start, chapter.end)
            confidence = chapter.confidence or chapter.role_confidence or chapter.importance_score
            confidence_values.append(max(0.0, min(1.0, float(confidence or 0.0))))
            status = chapter.boundary_status
            if status == "confirmed" and chapter.needs_review:
                status = "needs_review"
            minor = RoughCutMinorGroup(
                minor_id=minor_code,
                major_id=major_id,
                code=minor_code,
                title=chapter.title or minor_code,
                start=chapter.start,
                end=chapter.end,
                subtitle_ids=subtitle_ids,
                chapter_ids=(chapter.chapter_id,),
                summary=chapter.summary,
                tags=chapter.tags,
                status=status,
                safety="risky" if chapter.needs_review else "acceptable",
                confidence=confidence,
                needs_review=chapter.needs_review,
            )
            minors.append(minor)
            minor_chapters.append(
                replace(
                    chapter,
                    major_id=major_id,
                    minor_code=minor_code,
                    confidence=confidence,
                    boundary_status=status,
                )
            )
            for tag in chapter.tags:
                if tag and tag not in major_tags:
                    major_tags.append(tag)

        title = group[0].title or f"중분류 {major_id}"
        summary = " / ".join(chapter.summary or chapter.title for chapter in group if chapter.summary or chapter.title)
        confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
        major_segments.append(
            RoughCutSegment(
                segment_id=major_id,
                start=major_start,
                end=major_end,
                subtitle_ids=_subtitle_ids_for_range(subtitle_items, major_start, major_end),
                title=title,
                summary=summary[:240],
                tags=tuple(major_tags[:8]),
                story_role=group[0].story_role,
                narrative_function=group[0].narrative_function,
                importance_score=max((chapter.importance_score for chapter in group), default=0.0),
                can_move=all(not chapter.move_recommendation.startswith("keep_locked") for chapter in group),
                can_trim=True,
                can_remove=not needs_review,
                move_risk="medium" if any(chapter.move_recommendation.startswith("review_move") for chapter in group) else "low",
                dependencies=tuple(chapter.chapter_id for chapter in group),
                needs_review=needs_review,
                boundary_confidence=confidence,
                major_id=major_id,
                minor_groups=tuple(minors),
                status="needs_review" if needs_review else "confirmed",
                safety="risky" if needs_review else "acceptable",
                importance=max((chapter.importance_score for chapter in group), default=0.0),
                llm_summary=summary[:240],
            )
        )

    return tuple(major_segments), tuple(minor_chapters)


def _continuous_group_ranges(
    groups: list[list[ChapterMetadata]],
    *,
    media_duration: float | None,
) -> list[tuple[float, float]]:
    raw_ranges: list[tuple[float, float]] = []
    for group in groups:
        if not group:
            continue
        raw_ranges.append((min(chapter.start for chapter in group), max(chapter.end for chapter in group)))
    if not raw_ranges:
        return []

    fallback_end = raw_ranges[-1][1]
    try:
        duration = float(media_duration if media_duration is not None else fallback_end)
    except (TypeError, ValueError):
        duration = fallback_end
    duration = max(0.0, duration, fallback_end)
    if len(raw_ranges) == 1:
        return [(0.0, duration)]

    boundaries = [0.0]
    for idx in range(len(raw_ranges) - 1):
        current_start, current_end = raw_ranges[idx]
        next_start, next_end = raw_ranges[idx + 1]
        if next_start > current_end:
            boundary = (current_end + next_start) / 2.0
        else:
            boundary = next_start
        lower = boundaries[-1]
        upper = duration if idx + 1 == len(raw_ranges) - 1 else max(next_end, next_start, lower)
        boundaries.append(max(lower, min(float(boundary), upper)))
    boundaries.append(duration)
    return [
        (boundaries[idx], max(boundaries[idx], boundaries[idx + 1]))
        for idx in range(len(boundaries) - 1)
    ]


def _merge_groups_to_limit(groups: list[list[ChapterMetadata]], *, max_count: int) -> list[list[ChapterMetadata]]:
    if len(groups) <= max_count:
        return groups
    total = len(groups)
    merged: list[list[ChapterMetadata]] = []
    for bucket_index in range(max_count):
        start_idx = bucket_index * total // max_count
        end_idx = (bucket_index + 1) * total // max_count
        bucket: list[ChapterMetadata] = []
        for group in groups[start_idx:end_idx]:
            bucket.extend(group)
        if bucket:
            merged.append(bucket)
    return merged


__all__ = ["build_major_roughcut_segments"]
