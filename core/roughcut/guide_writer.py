# Version: 03.01.32
# Phase: PHASE2
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .models import ChapterMetadata, EDLSegment, EditDecision


def _fmt_time(sec: float | None) -> str:
    value = max(0.0, float(sec or 0.0))
    minutes, seconds = divmod(value, 60.0)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"


def _escape_cell(text: object) -> str:
    return str(text or "").replace("\n", " ").replace("|", "\\|").strip()


def _decision_lookup(decisions: Iterable[EditDecision]) -> dict[str, EditDecision]:
    return {decision.segment_id: decision for decision in decisions}


def _edl_lookup(edl_segments: Iterable[EDLSegment]) -> dict[str, EDLSegment]:
    return {segment.segment_id: segment for segment in edl_segments}


def _overall_summary(chapters: list[ChapterMetadata], decisions: list[EditDecision], edl: list[EDLSegment]) -> list[str]:
    total_duration = sum(max(0.0, chapter.end - chapter.start) for chapter in chapters)
    output_duration = edl[-1].output_end if edl else 0.0
    removed = sum(1 for decision in decisions if decision.action == "remove")
    risky = sum(1 for decision in decisions if decision.safety == "risky")
    highlights = sum(1 for decision in decisions if decision.action == "highlight")
    return [
        f"- 원본 분석 구간: {len(chapters)}개 / 약 {_fmt_time(total_duration)}",
        f"- 추천 출력 구간: {len(edl)}개 / 약 {_fmt_time(output_duration)}",
        f"- 제거 후보: {removed}개",
        f"- 하이라이트 후보: {highlights}개",
        f"- 컷 검토 필요: {risky}개",
    ]


def _story_flow(chapters: list[ChapterMetadata]) -> list[str]:
    lines = []
    for chapter in chapters:
        role = chapter.story_role or "-"
        title = chapter.title or chapter.chapter_id
        summary = chapter.summary or chapter.story_reason or ""
        move = "" if not chapter.move_recommendation or chapter.move_recommendation == "keep_order" else f" / 이동 검토: {chapter.move_recommendation}"
        lines.append(f"- **{role}** `{chapter.chapter_id}` {_escape_cell(title)}: {_escape_cell(summary)}{move}")
    return lines or ["- 챕터 정보 없음"]


def _chapter_table(chapters: list[ChapterMetadata], decisions: list[EditDecision], edl: list[EDLSegment]) -> list[str]:
    decision_by_id = _decision_lookup(decisions)
    edl_by_id = _edl_lookup(edl)
    lines = [
        "| 챕터 | 중분류 | 소분류 | 시간 | 역할 | 판단 | 안전도 | 출력 | 요약 |",
        "|---|---|---|---:|---|---|---|---:|---|",
    ]
    for chapter in chapters:
        decision = decision_by_id.get(chapter.chapter_id)
        edl_segment = edl_by_id.get(chapter.chapter_id)
        action = decision.action if decision else "-"
        safety = decision.safety if decision else "-"
        output = f"{_fmt_time(edl_segment.output_start)}-{_fmt_time(edl_segment.output_end)}" if edl_segment else "제외"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_escape_cell(chapter.chapter_id)}`",
                    _escape_cell(chapter.major_id or "-"),
                    _escape_cell(chapter.minor_code or "-"),
                    f"{_fmt_time(chapter.start)}-{_fmt_time(chapter.end)}",
                    _escape_cell(chapter.story_role or "-"),
                    _escape_cell(action),
                    _escape_cell(safety),
                    _escape_cell(output),
                    _escape_cell(chapter.summary or chapter.title),
                ]
            )
            + " |"
        )
    return lines


def _major_minor_table(chapters: list[ChapterMetadata]) -> list[str]:
    if not any(chapter.major_id or chapter.minor_code for chapter in chapters):
        return ["- 중분류/소분류 metadata 없음"]
    lines = [
        "| 중분류 | 소분류 | 챕터 | 시간 | 확신도 | 경계 상태 | 태그 | 주제 |",
        "|---|---|---|---:|---:|---|---|---|",
    ]
    for chapter in chapters:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(chapter.major_id or "-"),
                    _escape_cell(chapter.minor_code or "-"),
                    f"`{_escape_cell(chapter.chapter_id)}`",
                    f"{_fmt_time(chapter.start)}-{_fmt_time(chapter.end)}",
                    f"{float(chapter.confidence or 0.0):.2f}",
                    _escape_cell(chapter.boundary_status or "-"),
                    _escape_cell(", ".join(chapter.tags or ())),
                    _escape_cell(chapter.title),
                ]
            )
            + " |"
        )
    return lines


def _decision_table(decisions: list[EditDecision]) -> list[str]:
    lines = [
        "| 세그먼트 | 판단 | 소스 범위 | 안전도 | 이유 |",
        "|---|---|---:|---|---|",
    ]
    for decision in decisions:
        source = f"{_fmt_time(decision.source_start)}-{_fmt_time(decision.source_end)}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_escape_cell(decision.segment_id)}`",
                    _escape_cell(decision.action),
                    source,
                    _escape_cell(decision.safety),
                    _escape_cell(decision.reason),
                ]
            )
            + " |"
        )
    return lines


def _cut_point_table(decisions: list[EditDecision], edl: list[EDLSegment]) -> list[str]:
    edl_by_id = _edl_lookup(edl)
    lines = [
        "| 세그먼트 | 소스 컷 | 출력 | 판단 | 안전도 | 컷 근거 |",
        "|---|---:|---:|---|---|---|",
    ]
    for decision in decisions:
        edl_segment = edl_by_id.get(decision.segment_id)
        output = f"{_fmt_time(edl_segment.output_start)}-{_fmt_time(edl_segment.output_end)}" if edl_segment else "제외"
        source = f"{_fmt_time(decision.source_start)}-{_fmt_time(decision.source_end)}"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_escape_cell(decision.segment_id)}`",
                    source,
                    output,
                    _escape_cell(decision.action),
                    _escape_cell(decision.safety),
                    _escape_cell(decision.reason),
                ]
            )
            + " |"
        )
    return lines


def _review_points(decisions: list[EditDecision]) -> list[str]:
    risky = [decision for decision in decisions if decision.safety == "risky" or decision.action == "move"]
    if not risky:
        return ["- 위험 컷 없음. 최종 출력 전 전체 재생 검토만 진행하세요."]
    lines = []
    for decision in risky:
        lines.append(
            f"- `{decision.segment_id}` {_fmt_time(decision.source_start)}-{_fmt_time(decision.source_end)} "
            f"/ {decision.action} / {decision.safety}: {_escape_cell(decision.reason)}"
        )
    return lines


def _manual_review_points(decisions: list[EditDecision], edl: list[EDLSegment]) -> list[str]:
    edl_ids = {segment.segment_id for segment in edl}
    points: list[str] = []
    for decision in decisions:
        reasons: list[str] = []
        if decision.safety == "risky":
            reasons.append("위험 컷")
        if decision.action == "move":
            reasons.append("이동 검토")
        if decision.action == "remove":
            reasons.append("삭제 후보")
        if decision.segment_id not in edl_ids:
            reasons.append("출력 제외")
        if not reasons:
            continue
        points.append(
            f"- `{decision.segment_id}` {_fmt_time(decision.source_start)}-{_fmt_time(decision.source_end)} "
            f"/ {', '.join(reasons)} / {_escape_cell(decision.reason)}"
        )
    return points or ["- 수동 검토 우선순위 없음. 최종 출력 전 전체 재생 검토만 진행하세요."]


def build_markdown_guide(
    chapters: Iterable[ChapterMetadata],
    decisions: Iterable[EditDecision],
    edl_segments: Iterable[EDLSegment],
    title: str = "러프컷 편집 가이드",
) -> str:
    chapter_items = list(chapters)
    decision_items = list(decisions)
    edl_items = list(edl_segments)
    lines: list[str] = [
        f"# {title}",
        "",
        "## 전체 요약",
        *_overall_summary(chapter_items, decision_items, edl_items),
        "",
        "## 추천 스토리 흐름",
        *_story_flow(chapter_items),
        "",
        "## 챕터 표",
        *_chapter_table(chapter_items, decision_items, edl_items),
        "",
        "## 중분류 / 소분류",
        *_major_minor_table(chapter_items),
        "",
        "## 편집 판단",
        *_decision_table(decision_items),
        "",
        "## 컷 포인트",
        *_cut_point_table(decision_items, edl_items),
        "",
        "## 위험 컷 / 검토 필요 구간",
        *_review_points(decision_items),
        "",
        "## 수동 검토 추천 지점",
        *_manual_review_points(decision_items, edl_items),
        "",
        "## 검토 필요 컷",
        *_review_points(decision_items),
        "",
    ]
    return "\n".join(lines)


def save_markdown_guide(path: str | Path, markdown: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(markdown).rstrip() + "\n", encoding="utf-8")
    return target


def write_markdown_guide(
    chapters: Iterable[ChapterMetadata],
    decisions: Iterable[EditDecision],
    edl_segments: Iterable[EDLSegment],
    title: str = "러프컷 편집 가이드",
) -> str:
    """Compatibility wrapper for older action-item naming."""
    return build_markdown_guide(chapters, decisions, edl_segments, title=title)
