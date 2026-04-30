# Version: 03.01.29
# Phase: PHASE2
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .models import ChapterMetadata, RoughCutMinorGroup, RoughCutSegment, SubtitleSegment

_MAJOR_CODES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _duration(start: float, end: float) -> float:
    return max(0.0, float(end) - float(start))


def _major_code(index: int) -> str:
    if index < len(_MAJOR_CODES):
        return _MAJOR_CODES[index]
    return f"M{index + 1}"


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
    min_major_duration: float = 0.0,
    max_major_duration: float = 0.0,
    max_subtitle_count: int = 0,
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

    major_segments: list[RoughCutSegment] = []
    minor_chapters: list[ChapterMetadata] = []

    for major_index, group in enumerate(groups):
        if not group:
            continue
        major_id = _major_code(major_index)
        minors: list[RoughCutMinorGroup] = []
        major_start = min(chapter.start for chapter in group)
        major_end = max(chapter.end for chapter in group)
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


__all__ = ["build_major_roughcut_segments"]
