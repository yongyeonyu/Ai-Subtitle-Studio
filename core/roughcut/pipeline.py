# Version: 03.01.30
# Phase: PHASE2
from __future__ import annotations

from typing import Iterable

from .chapter_segmenter import build_chapters
from .boundary_refiner import refine_major_boundaries
from .edit_decision_engine import build_edit_decisions, generate_cut_points
from .edl_generator import build_edl_segments
from .gap_detector import detect_subtitle_gaps
from .guide_writer import build_markdown_guide
from .major_segmenter import build_major_roughcut_segments
from .models import ChapterMetadata, RoughCutDraftState, RoughCutResult, RoughCutSegment, SubtitleSegment, subtitles_from_dicts
from .roughcut_llm import run_roughcut_llm_action
from .roughcut_settings import merge_roughcut_settings
from .semantic_chunker import build_semantic_chunks
from .story_mapper import map_story_roles
from .title_suggester import build_title_suggestions
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
                major_id=chapter.major_id or chapter.chapter_id,
                status="needs_review" if chapter.needs_review else "confirmed",
                safety="risky" if chapter.needs_review else "acceptable",
                importance=chapter.importance_score,
                llm_summary="",
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
    settings: dict | None = None,
    scene_changes: Iterable | None = None,
) -> RoughCutResult:
    """Single local entry point for the Phase2 roughcut MVP pipeline."""
    warnings: list[str] = []
    requested_llm = bool(use_llm)
    roughcut_settings = merge_roughcut_settings(settings)
    use_llm = bool(use_llm or roughcut_settings.get("roughcut_llm_enabled", False))
    if requested_llm and not roughcut_settings.get("roughcut_llm_enabled", False):
        warnings.append("use_llm=True requested, roughcut LLM is disabled; local heuristics fallback.")

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
    chapters = map_story_roles(build_chapters(chunks, min_chapter_duration=0.0))
    if use_llm:
        llm_result = run_roughcut_llm_action(
            "propose_major_segment",
            {
                "video_summary": f"자막 {len(subtitles)}개, chunk {len(chunks)}개",
                "chunks": [
                    {"chunk_id": chunk.chunk_id, "start": chunk.start, "end": chunk.end, "text": chunk.text}
                    for chunk in chunks
                ],
            },
            settings=roughcut_settings,
        )
        if not llm_result.ok:
            warnings.append(f"roughcut_llm_fallback:{llm_result.error}")
    duration = media_duration if media_duration is not None else max((item.end for item in subtitles), default=0.0)
    gaps = detect_subtitle_gaps(subtitles, media_duration=duration, min_gap=0.1, include_leading=False, include_trailing=False)
    if bool(roughcut_settings.get("roughcut_boundary_verification_enabled", True)):
        chapters = refine_major_boundaries(
            chapters,
            phrases=packed,
            gaps=gaps,
            scene_changes=scene_changes,
            search_window=float(roughcut_settings.get("roughcut_boundary_refine_window_sec", 1.5) or 1.5),
        )
    roughcut_segments, chapters = build_major_roughcut_segments(
        chapters,
        subtitles=subtitles,
        min_major_duration=float(roughcut_settings.get("roughcut_major_min_duration_sec", 0.0) or 0.0),
        max_major_duration=float(roughcut_settings.get("roughcut_major_max_duration_sec", 0.0) or 0.0),
        max_subtitle_count=int(roughcut_settings.get("roughcut_major_max_subtitle_count", 0) or 0),
    )
    decisions = build_edit_decisions(chapters, packed, gaps)
    cut_points = generate_cut_points(decisions, packed, gaps)
    edl = build_edl_segments(source_path, decisions, chapters)
    guide = build_markdown_guide(chapters, decisions, edl)
    summary = f"챕터 {len(chapters)}개, 편집 판단 {len(decisions)}개, 출력 구간 {len(edl)}개"
    interim = RoughCutResult(
        segments=roughcut_segments,
        chapters=tuple(chapters),
        edit_decisions=tuple(decisions),
        edl_segments=tuple(edl),
        guide_markdown=guide,
        warnings=tuple(warnings),
        video_summary=summary,
        packed_phrases=tuple(packed),
        chunks=tuple(chunks),
        cut_points=tuple(cut_points),
        draft_state=RoughCutDraftState(status="review" if any(chapter.needs_review for chapter in chapters) else "confirmed"),
        schema_version="roughcut_result.v2",
    )
    title_suggestions = build_title_suggestions(interim, settings=roughcut_settings)

    return RoughCutResult(
        segments=roughcut_segments,
        chapters=tuple(chapters),
        edit_decisions=tuple(decisions),
        edl_segments=tuple(edl),
        guide_markdown=guide,
        warnings=tuple(warnings),
        video_summary=summary,
        packed_phrases=tuple(packed),
        chunks=tuple(chunks),
        cut_points=tuple(cut_points),
        title_suggestions=title_suggestions,
        draft_state=RoughCutDraftState(status="review" if any(chapter.needs_review for chapter in chapters) else "confirmed"),
        schema_version="roughcut_result.v2",
    )
