# Version: 03.14.00
# Phase: PHASE2
"""Frame-synced topicless placeholder installer for roughcut state."""

from __future__ import annotations

from datetime import datetime


def _middle_label(index: int) -> str:
    index = max(1, int(index or 1))
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _roughcut_topicless_frame_bounds(row: dict):
    """
    project placeholder row에서 frame 기준 start/end를 복원한다.
    seconds는 frame/fps에서만 계산한다.
    """
    from core.frame_time import normalize_fps, frame_to_sec, sec_to_frame

    fps = 30.0
    for key in ("fps", "frame_rate", "timeline_frame_rate"):
        try:
            value = float(row.get(key) or 0.0)
            if value > 1.0:
                fps = normalize_fps(value)
                break
        except Exception:
            pass

    start_frame = None
    end_frame = None

    for key in ("timeline_start_frame", "start_frame"):
        try:
            value = row.get(key)
            if value is not None:
                start_frame = int(value)
                break
        except Exception:
            pass

    for key in ("timeline_end_frame", "end_frame"):
        try:
            value = row.get(key)
            if value is not None:
                end_frame = int(value)
                break
        except Exception:
            pass

    if start_frame is None:
        try:
            start_frame = sec_to_frame(float(row.get("start", row.get("timeline_start", 0.0)) or 0.0), fps)
        except Exception:
            start_frame = 0

    if end_frame is None:
        try:
            end_frame = sec_to_frame(float(row.get("end", row.get("timeline_end", 0.0)) or 0.0), fps)
        except Exception:
            end_frame = start_frame

    start_frame = max(0, int(start_frame))
    end_frame = max(start_frame, int(end_frame))

    return start_frame, end_frame, frame_to_sec(start_frame, fps), frame_to_sec(end_frame, fps), fps


def _frame_synced_topicless_placeholder_result_from_project(self):
    project_path = self._project_path()
    try:
        from core.roughcut.cut_boundary_placeholder import extract_topicless_placeholders_from_project
    except Exception:
        return None

    rows = extract_topicless_placeholders_from_project(project_path)
    if not rows:
        return None

    from core.roughcut.models import (
        RoughCutResult,
        RoughCutSegment,
        RoughCutMinorGroup,
        ChapterMetadata,
        EditDecision,
        EDLSegment,
        RoughCutDraftState,
    )

    rough_segments = []
    chapters = []
    decisions = []
    edl_segments = []

    source_path = self._media_path()
    output_cursor = 0.0

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue

        start_frame, end_frame, start, end, fps = _roughcut_topicless_frame_bounds(row)
        if end_frame <= start_frame:
            continue

        major_id = str(row.get("major_id") or row.get("segment_id") or row.get("id") or "")
        if not major_id or major_id.startswith("cut_topicless_middle"):
            major_id = _middle_label(idx)

        segment_id = major_id
        chapter_id = major_id
        minor_id = f"{major_id}1"

        minor = RoughCutMinorGroup(
            minor_id=minor_id,
            major_id=major_id,
            code=f"{major_id}1",
            title="주제없음",
            start=start,
            end=end,
            subtitle_ids=tuple(),
            chapter_ids=(chapter_id,),
            summary="컷 경계 기반 임시 소분류입니다.",
            tags=("컷경계", "주제없음"),
            status="provisional",
            safety="acceptable",
            confidence=0.0,
            needs_review=True,
        )

        rough_segments.append(
            RoughCutSegment(
                segment_id=segment_id,
                start=start,
                end=end,
                subtitle_ids=tuple(),
                title="주제없음",
                summary="컷 경계 기반 임시 중분류입니다. LLM 분석 전 상태입니다.",
                tags=("컷경계", "주제없음", "임시"),
                story_role="topicless_placeholder",
                narrative_function="cut_boundary_placeholder",
                importance_score=0.0,
                can_move=True,
                can_trim=True,
                can_remove=True,
                move_risk="low",
                needs_review=True,
                boundary_confidence=1.0,
                major_id=major_id,
                minor_groups=(minor,),
                status="provisional",
                safety="acceptable",
                importance=0.0,
                llm_summary="주제없음",
            )
        )

        chapters.append(
            ChapterMetadata(
                chapter_id=chapter_id,
                title="주제없음",
                start=start,
                end=end,
                summary="컷 경계 기반 임시 챕터입니다. LLM 중분류 결과로 대체 예정입니다.",
                tags=("컷경계", "주제없음"),
                segment_ids=(segment_id,),
                importance_score=0.0,
                narrative_function="cut_boundary_placeholder",
                story_role="topicless_placeholder",
                needs_review=True,
                major_id=major_id,
                minor_code=f"{major_id}1",
                confidence=0.0,
                boundary_status="provisional",
            )
        )

        decisions.append(
            EditDecision(
                segment_id=segment_id,
                action="keep",
                reason="컷 경계 기반 주제없음 임시 중분류",
                source_start=start,
                source_end=end,
                output_order=idx,
                safety="acceptable",
                confidence=0.0,
            )
        )

        output_start = output_cursor
        output_end = output_start + (end - start)
        output_cursor = output_end

        edl_segments.append(
            EDLSegment(
                source_path=source_path,
                segment_id=segment_id,
                source_start=start,
                source_end=end,
                output_start=output_start,
                output_end=output_end,
                action="keep",
                chapter_id=chapter_id,
                story_role="topicless_placeholder",
                reason="컷 경계 기반 주제없음 임시 중분류",
                timeline_start=start,
                timeline_end=end,
                clip_index=None,
            )
        )

    if not rough_segments:
        return None

    return RoughCutResult(
        segments=tuple(rough_segments),
        chapters=tuple(chapters),
        edit_decisions=tuple(decisions),
        edl_segments=tuple(edl_segments),
        guide_markdown="컷 경계 기반 '주제없음' 임시 중분류입니다. LLM 분석 결과로 대체 예정입니다.",
        warnings=("cut_boundary_topicless_placeholder", "frame_synced"),
        video_summary=f"컷 경계 기반 주제없음 임시 중분류 {len(rough_segments)}개",
        draft_state=RoughCutDraftState(
            draft_id="cut_boundary_topicless",
            status="review",
            selected_major_id=rough_segments[0].major_id if rough_segments else "",
            selected_minor_code=f"{rough_segments[0].major_id}1" if rough_segments else "",
            autosave_enabled=True,
            last_saved_at=datetime.now().isoformat(timespec="seconds"),
            notes="컷 경계 기반 주제없음 placeholder · frame synced",
        ),
        schema_version="roughcut_result.cut_boundary_placeholder.frame_synced.v1",
    )




def install_frame_synced_topicless_placeholder(RoughcutStateMixin) -> None:
    RoughcutStateMixin._topicless_placeholder_result_from_project = (
        _frame_synced_topicless_placeholder_result_from_project
    )
