# Version: 03.01.30
# Phase: PHASE2
from __future__ import annotations

from typing import Iterable

from core.cut_boundary_fusion import build_roughcut_fusion_boundary_rows

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



def _extract_scene_change_time(item) -> float | None:
    if item is None:
        return None

    if isinstance(item, (int, float)):
        return float(item)

    if isinstance(item, dict):
        if item.get("hard_cut_allowed") is False or str(item.get("boundary_role") or "").lower() == "roughcut":
            return None
        if str(item.get("fusion_decision") or "").lower() in {"drop_hint", "roughcut_boundary"}:
            return None
        for key in ("time", "timeline_sec", "sec", "seconds", "timestamp", "start", "pos"):
            if key in item:
                try:
                    return float(item[key])
                except Exception:
                    return None
        for key in ("timeline_frame", "frame", "start_frame"):
            if key in item:
                try:
                    fps = float(item.get("fps") or item.get("frame_rate") or 30.0)
                    if fps > 0.0:
                        return float(item[key]) / fps
                except Exception:
                    return None

    for key in ("time", "sec", "seconds", "timestamp", "start", "pos"):
        if hasattr(item, key):
            try:
                return float(getattr(item, key))
            except Exception:
                return None

    return None



def _hard_cut_times_from_scene_changes(
    scene_changes: Iterable | None,
    media_duration: float | None = None,
) -> tuple[float, ...]:
    """Return sorted absolute hard cut times.

    These cuts are absolute boundaries:
    - STT/subtitle segments must not cross them.
    - roughcut/major/middle segments must not cross them.
    - LLM may rename/overwrite topics, but cannot merge across these cuts.
    """
    if not scene_changes:
        return ()

    duration = float(media_duration or 0.0)
    times: list[float] = []

    for item in scene_changes:
        sec = _extract_scene_change_time(item)
        if sec is None:
            continue
        sec = round(float(sec), 3)
        if sec <= 0.0:
            continue
        if duration > 0.0 and sec >= duration:
            continue
        times.append(sec)

    return tuple(sorted(set(times)))


def _split_subtitles_by_hard_cuts(
    subtitles: Iterable[SubtitleSegment],
    hard_cuts: Iterable[float],
) -> tuple[SubtitleSegment, ...]:
    """Split subtitle rows so no subtitle crosses a hard visual cut.

    Text is duplicated into the split pieces because the visual boundary is
    more important than preserving a single long subtitle row.
    """
    cuts = tuple(sorted(float(x) for x in (hard_cuts or ()) if float(x) > 0.0))
    if not cuts:
        return tuple(subtitles or ())

    out: list[SubtitleSegment] = []

    for item in subtitles or ():
        start = float(item.start)
        end = float(item.end)
        if end <= start:
            continue

        inner_cuts = [c for c in cuts if start < c < end]
        if not inner_cuts:
            out.append(item)
            continue

        points = [start] + inner_cuts + [end]
        for idx in range(len(points) - 1):
            part_start = points[idx]
            part_end = points[idx + 1]
            if part_end <= part_start:
                continue

            suffix = f"_cut{idx + 1}" if len(points) > 2 else ""
            out.append(
                SubtitleSegment(
                    start=part_start,
                    end=part_end,
                    text=item.text,
                    speaker=item.speaker,
                    subtitle_id=f"{item.subtitle_id}{suffix}",
                )
            )

    return tuple(out)


def _clamp_roughcut_segments_to_hard_cuts(
    segments: Iterable[RoughCutSegment],
    hard_cuts: Iterable[float],
) -> tuple[RoughCutSegment, ...]:
    """Guarantee roughcut segments never cross hard cuts.

    LLM or heuristic analysis may create more segments inside a cut range,
    but it must not produce one segment that crosses a visual cut.
    """
    cuts = tuple(sorted(float(x) for x in (hard_cuts or ()) if float(x) > 0.0))
    if not cuts:
        return tuple(segments or ())

    out: list[RoughCutSegment] = []

    for seg in segments or ():
        start = float(seg.start)
        end = float(seg.end)
        if end <= start:
            continue

        inner_cuts = [c for c in cuts if start < c < end]
        if not inner_cuts:
            out.append(seg)
            continue

        points = [start] + inner_cuts + [end]
        for idx in range(len(points) - 1):
            part_start = points[idx]
            part_end = points[idx + 1]
            if part_end <= part_start:
                continue

            part_id = f"{seg.segment_id}_hardcut_{idx + 1}"
            out.append(
                RoughCutSegment(
                    segment_id=part_id,
                    start=part_start,
                    end=part_end,
                    title=seg.title,
                    summary=seg.summary,
                    tags=tuple(sorted(set(tuple(seg.tags or ()) + ("컷경계",)))),
                    story_role=seg.story_role,
                    narrative_function=seg.narrative_function,
                    importance_score=seg.importance_score,
                    can_move=seg.can_move,
                    can_trim=seg.can_trim,
                    can_remove=seg.can_remove,
                    move_risk=seg.move_risk,
                    dependencies=seg.dependencies,
                    needs_review=True,
                    boundary_confidence=min(float(seg.boundary_confidence or 0.0), 1.0),
                    major_id=part_id,
                    status="needs_review",
                    safety=seg.safety,
                    importance=seg.importance,
                    llm_summary=seg.llm_summary,
                )
            )

    return tuple(out)


def _build_cut_boundary_topicless_result(
    *,
    scene_changes: Iterable | None,
    media_duration: float | None,
    source_path: str = "",
    warnings: list[str] | None = None,
) -> RoughCutResult | None:
    """컷 경계가 있으면 LLM/주제 분석 없이 즉시 주제없음 세그먼트 생성."""
    if not scene_changes:
        return None

    duration = float(media_duration or 0.0)
    if duration <= 0:
        return None

    cut_times: list[float] = []
    for item in scene_changes:
        sec = _extract_scene_change_time(item)
        if sec is None:
            continue
        if 0.0 < sec < duration:
            cut_times.append(sec)

    cut_times = sorted(set(round(x, 3) for x in cut_times))
    if not cut_times:
        return None

    boundaries = [0.0] + cut_times + [duration]

    segments: list[RoughCutSegment] = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        if end <= start:
            continue

        seg_id = f"cut_topicless_{idx + 1:03d}"
        segments.append(
            RoughCutSegment(
                segment_id=seg_id,
                start=start,
                end=end,
                title="주제없음",
                summary="컷 경계 기반으로 자동 생성된 임시 세그먼트입니다.",
                tags=("컷경계",),
                story_role="topicless_placeholder",
                narrative_function="cut_boundary_placeholder",
                importance_score=0.0,
                can_move=True,
                can_trim=True,
                can_remove=True,
                move_risk="low",
                dependencies=(),
                needs_review=True,
                boundary_confidence=1.0,
                major_id=seg_id,
                status="needs_review",
                safety="acceptable",
                importance=0.0,
                llm_summary="",
            )
        )

    if not segments:
        return None

    return RoughCutResult(
        segments=tuple(segments),
        chapters=(),
        edit_decisions=(),
        edl_segments=(),
        guide_markdown="",
        warnings=tuple(warnings or ()),
        video_summary=f"컷 경계 기반 주제없음 세그먼트 {len(segments)}개",
        packed_phrases=(),
        chunks=(),
        cut_points=tuple(cut_times),
        title_suggestions=(),
        draft_state=RoughCutDraftState(status="review"),
        schema_version="roughcut_result.v2",
    )


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _overlap_text_for_range(chunks: Iterable, start: float, end: float) -> str:
    texts: list[str] = []
    for chunk in chunks or ():
        try:
            if float(chunk.end) > start and float(chunk.start) < end:
                text = str(getattr(chunk, "text", "") or "").strip()
                if text:
                    texts.append(text)
        except Exception:
            continue
    return " ".join(texts)[:240]


def _chapters_from_llm_major_segments(
    llm_data: dict,
    *,
    chunks: Iterable,
    subtitles: Iterable[SubtitleSegment],
    media_duration: float | None,
) -> list[ChapterMetadata]:
    rows = llm_data.get("major_segments") if isinstance(llm_data, dict) else None
    if not isinstance(rows, list):
        return []
    subtitle_items = list(subtitles or ())
    fallback_end = max((item.end for item in subtitle_items), default=0.0)
    duration = max(_as_float(media_duration, fallback_end), fallback_end)
    out: list[ChapterMetadata] = []
    allowed_status = {"provisional", "reading", "confirmed", "needs_review"}

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        start = max(0.0, _as_float(row.get("start"), 0.0))
        end = _as_float(row.get("end"), start)
        if duration > 0.0:
            end = min(duration, end)
        if end <= start:
            continue
        major_id = str(row.get("major_id") or chr(ord("A") + min(idx, 25))).strip() or f"M{idx + 1}"
        title = str(row.get("title") or f"중분류 {major_id}").strip()
        summary = str(row.get("summary") or _overlap_text_for_range(chunks, start, end) or title).strip()
        raw_tags = row.get("tags") or row.get("keywords") or ()
        tags = tuple(str(tag).strip() for tag in raw_tags if str(tag).strip())[:8] if isinstance(raw_tags, (list, tuple)) else ()
        confidence = max(0.0, min(1.0, _as_float(row.get("confidence"), 0.72)))
        status = str(row.get("status") or ("confirmed" if confidence >= 0.72 else "needs_review")).strip()
        if status not in allowed_status:
            status = "needs_review"
        out.append(
            ChapterMetadata(
                chapter_id=f"llm_major_{idx + 1:03d}_{major_id}",
                title=title,
                start=start,
                end=end,
                summary=summary[:240],
                tags=tags,
                importance_score=confidence,
                narrative_function="roughcut_llm_major_segment",
                story_role="llm_major",
                story_reason="roughcut_llm",
                move_recommendation="review_move" if status != "confirmed" else "",
                role_confidence=confidence,
                needs_review=status != "confirmed" or confidence < 0.65,
                major_id=major_id,
                confidence=confidence,
                boundary_status=status,
            )
        )
    return sorted(out, key=lambda item: (item.start, item.end))


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
    boundary_rows = build_roughcut_fusion_boundary_rows(
        subtitles,
        scene_changes,
        media_duration=media_duration,
        settings=roughcut_settings,
    )
    boundary_source = boundary_rows if boundary_rows else scene_changes

    # ✅ 컷 경계는 이제 절대 경계다.
    # 1) 자막이 아직 없으면 00:00~첫 컷 placeholder를 먼저 반환한다.
    # 2) 자막이 있으면 모든 자막을 hard cut 기준으로 먼저 분할한다.
    # 3) 이후 LLM/휴리스틱 주제 분석은 이 경계를 넘어갈 수 없다.
    hard_cuts = _hard_cut_times_from_scene_changes(boundary_source, media_duration)

    if not subtitles:
        if bool(roughcut_settings.get("roughcut_cut_boundary_topicless_first", True)):
            topicless_result = _build_cut_boundary_topicless_result(
                scene_changes=boundary_source,
                media_duration=media_duration,
                source_path=source_path,
                warnings=warnings,
            )
            if topicless_result is not None:
                return topicless_result
        return RoughCutResult(warnings=tuple(warnings + ["no_subtitle_segments"]))

    subtitles = _split_subtitles_by_hard_cuts(subtitles, hard_cuts)

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
        if llm_result.ok:
            llm_chapters = _chapters_from_llm_major_segments(
                llm_result.data,
                chunks=chunks,
                subtitles=subtitles,
                media_duration=media_duration,
            )
            if llm_chapters:
                chapters = map_story_roles(llm_chapters)
                warnings.append(f"roughcut_llm_applied:{len(llm_chapters)}")
            else:
                warnings.append("roughcut_llm_fallback:empty_major_segments")
        else:
            warnings.append(f"roughcut_llm_fallback:{llm_result.error}")
    duration = media_duration if media_duration is not None else max((item.end for item in subtitles), default=0.0)
    gaps = detect_subtitle_gaps(subtitles, media_duration=duration, min_gap=0.1, include_leading=False, include_trailing=False)
    if bool(roughcut_settings.get("roughcut_boundary_verification_enabled", True)):
        chapters = refine_major_boundaries(
            chapters,
            phrases=packed,
            gaps=gaps,
            scene_changes=boundary_source,
            search_window=float(roughcut_settings.get("roughcut_boundary_refine_window_sec", 1.5) or 1.5),
        )
    roughcut_segments, chapters = build_major_roughcut_segments(
        chapters,
        subtitles=subtitles,
        media_duration=duration,
        min_major_duration=float(roughcut_settings.get("roughcut_major_min_duration_sec", 0.0) or 0.0),
        max_major_duration=float(roughcut_settings.get("roughcut_major_max_duration_sec", 0.0) or 0.0),
        max_subtitle_count=int(roughcut_settings.get("roughcut_major_max_subtitle_count", 0) or 0),
        max_major_segment_count=int(roughcut_settings.get("roughcut_major_max_segment_count", 10) or 10),
    )

    # ✅ LLM/휴리스틱 결과가 컷 경계를 넘어가면 여기서 다시 강제 분할한다.
    # LLM은 주제없음 placeholder를 overwrite할 수 있지만,
    # hard cut 자체를 병합하거나 무시할 수는 없다.
    roughcut_segments = _clamp_roughcut_segments_to_hard_cuts(roughcut_segments, hard_cuts)
    decisions = build_edit_decisions(chapters, packed, gaps)
    cut_points = generate_cut_points(decisions, packed, gaps)
    edl = build_edl_segments(source_path, decisions, chapters)
    guide = build_markdown_guide(chapters, decisions, edl)
    if hard_cuts:
        warnings.append(f"hard_cut_boundaries_enforced:{len(hard_cuts)}")

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
