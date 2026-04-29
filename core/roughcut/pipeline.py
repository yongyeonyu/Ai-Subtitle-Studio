# Version: 03.00.14
# Phase: PHASE2
from __future__ import annotations

from typing import Iterable

from .edit_decision_engine import build_edit_decisions
from .edl_generator import build_edl_segments
from .gap_detector import detect_subtitle_gaps
from .guide_writer import build_markdown_guide
from .models import ChapterMetadata, RoughCutResult, RoughCutSegment, SubtitleSegment, subtitles_from_dicts
from .semantic_chunker import build_semantic_chunks, chunks_to_chapters
from .story_mapper import map_story_roles
from .transcript_packer import pack_transcript


def _normalize_subtitles(items: Iterable[dict] | Iterable[SubtitleSegment]) -> tuple[SubtitleSegment, ...]:
    source = list(items or ())
    if not source:
        return ()
    first = source[0]
    if isinstance(first, SubtitleSegment):
        return tuple(item for item in source if isinstance(item, SubtitleSegment) and item.end > item.start)
    return subtitles_from_dicts(tuple(item for item in source if isinstance(item, dict)))


def _segments_from_chapters(chapters: Iterable[ChapterMetadata]) -> tuple[RoughCutSegment, ...]:
    segments = []
    for chapter in chapters:
        segments.append(
            RoughCutSegment(
                segment_id=chapter.chapter_id,
                start=chapter.start,
                end=chapter.end,
                title=chapter.title,
                summary=chapter.summary,
                tags=chapter.tags,
                story_role=chapter.story_role,
                narrative_function=chapter.narrative_function,
                importance_score=chapter.importance_score,
                can_move=not chapter.move_recommendation.startswith("keep_locked"),
                can_trim=True,
                can_remove=not chapter.needs_review,
                move_risk="medium" if chapter.move_recommendation.startswith("review_move") else "low",
                dependencies=(),
                needs_review=chapter.needs_review,
                boundary_confidence=chapter.role_confidence,
            )
        )
    return tuple(segments)


def run_roughcut_pipeline(
    subtitle_segments: Iterable[dict] | Iterable[SubtitleSegment],
    media_duration: float | None = None,
    source_path: str = "",
    use_llm: bool = False,
    silence_gap_threshold: float = 1.0,
    topic_shift_threshold: float = 0.55,
) -> RoughCutResult:
    """Single local entry point for the Phase2 roughcut MVP pipeline."""
    warnings: list[str] = []
    if use_llm:
        warnings.append("use_llm=True requested, but v03.00.14 pipeline uses local heuristics only.")

    subtitles = _normalize_subtitles(subtitle_segments)
    if not subtitles:
        return RoughCutResult(warnings=tuple(warnings + ["no_subtitle_segments"]))

    packed = pack_transcript(
        [
            {
                "start": item.start,
                "end": item.end,
                "text": item.text,
                "speaker": item.speaker,
                "subtitle_id": item.subtitle_id,
            }
            for item in subtitles
        ],
        silence_gap_threshold=silence_gap_threshold,
    )
    chunks = build_semantic_chunks(
        packed,
        topic_shift_threshold=topic_shift_threshold,
        min_chunk_duration=0.0,
    )
    chapters = map_story_roles(chunks_to_chapters(chunks))
    roughcut_segments = _segments_from_chapters(chapters)
    duration = media_duration if media_duration is not None else max((item.end for item in subtitles), default=0.0)
    gaps = detect_subtitle_gaps(subtitles, media_duration=duration, min_gap=0.1, include_leading=False, include_trailing=False)
    decisions = build_edit_decisions(chapters, packed, gaps)
    edl = build_edl_segments(source_path, decisions, chapters)
    guide = build_markdown_guide(chapters, decisions, edl)

    return RoughCutResult(
        segments=roughcut_segments,
        chapters=tuple(chapters),
        edit_decisions=tuple(decisions),
        edl_segments=tuple(edl),
        guide_markdown=guide,
        warnings=tuple(warnings),
    )
