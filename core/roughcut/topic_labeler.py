# Version: 03.24.01
# Phase: PHASE2
"""LLM-backed one-line topic labels for finalized roughcut major segments."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Iterable

from .models import RoughCutSegment, SubtitleSegment
from .roughcut_llm import run_roughcut_llm_action
from .topic_detector import extract_keywords


def _compact(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _major_id(segment: RoughCutSegment) -> str:
    return str(segment.major_id or segment.segment_id or "").strip()


def _subtitle_id(subtitle: SubtitleSegment, fallback: int) -> int:
    try:
        return int(subtitle.subtitle_id if subtitle.subtitle_id is not None else fallback)
    except Exception:
        return int(fallback)


def _subtitles_for_segment(segment: RoughCutSegment, subtitles: list[SubtitleSegment]) -> list[SubtitleSegment]:
    ids = {int(value) for value in tuple(segment.subtitle_ids or ())}
    if ids:
        selected = [
            item
            for idx, item in enumerate(subtitles)
            if _subtitle_id(item, idx) in ids
        ]
        if selected:
            return selected
    return [
        item
        for item in subtitles
        if float(item.end) > float(segment.start) and float(item.start) < float(segment.end)
    ]


def _topic_from_subtitles(rows: list[SubtitleSegment], fallback: str = "") -> str:
    text = _compact(" ".join(row.text for row in rows if row.text))
    keywords = extract_keywords(text, top_k=4)
    if keywords:
        return " / ".join(keywords[:3])[:42]
    return _compact(fallback)[:42]


def _looks_like_raw_subtitle_copy(topic: str, rows: list[SubtitleSegment]) -> bool:
    candidate = _compact(topic).casefold()
    if not candidate:
        return True
    for row in rows:
        text = _compact(row.text).casefold()
        if not text:
            continue
        if candidate == text:
            return True
        copy_ratio = len(candidate) / max(1, len(text))
        if len(candidate) >= 18 and copy_ratio >= 0.55 and (candidate in text or text.startswith(candidate)):
            return True
    return False


def _clean_topic(topic: Any) -> str:
    text = _compact(topic)
    text = text.strip("`'\"[](){} ")
    text = re.sub(r"^[\-•*#\d.\s]+", "", text).strip()
    return text[:42]


def _subtitle_rows_payload(rows: list[SubtitleSegment], *, max_rows: int = 80, max_chars: int = 6000) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    used_chars = 0
    for idx, item in enumerate(rows[:max_rows]):
        text = _compact(item.text)
        if not text:
            continue
        remaining = max(0, max_chars - used_chars)
        if remaining <= 0:
            break
        text = text[: min(280, remaining)]
        used_chars += len(text)
        payload.append(
            {
                "subtitle_id": _subtitle_id(item, idx),
                "start": round(float(item.start), 3),
                "end": round(float(item.end), 3),
                "text": text,
            }
        )
    return payload


def _topic_payload(segments: list[RoughCutSegment], subtitles: list[SubtitleSegment]) -> tuple[dict[str, Any], dict[str, list[SubtitleSegment]]]:
    rows_by_major: dict[str, list[SubtitleSegment]] = {}
    major_rows = []
    for segment in segments:
        major_id = _major_id(segment)
        if not major_id:
            continue
        rows = _subtitles_for_segment(segment, subtitles)
        rows_by_major[major_id] = rows
        major_rows.append(
            {
                "major_id": major_id,
                "current_title": segment.title,
                "current_summary": segment.summary or segment.llm_summary,
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "subtitle_count": len(rows),
                "subtitle_rows": _subtitle_rows_payload(rows),
            }
        )
    return (
        {
            "task_instruction": (
                "최종 확정된 각 중분류의 모든 subtitle_rows를 읽고, 첫 자막을 복사하지 말고 "
                "해당 묶음 전체의 핵심 주제를 한국어 한 줄 topic으로 작성한다. "
                "topic은 UI 중분류 라벨로 바로 표시되므로 12~24자 정도의 명사구가 좋다."
            ),
            "major_segments": major_rows,
        },
        rows_by_major,
    )


def _topic_map_from_llm(data: dict[str, Any], rows_by_major: dict[str, list[SubtitleSegment]]) -> dict[str, dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    raw_rows = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(raw_rows, list):
        return topics
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        major_id = str(row.get("major_id") or "").strip()
        if not major_id:
            continue
        rows = rows_by_major.get(major_id, [])
        topic = _clean_topic(row.get("topic") or row.get("title"))
        if _looks_like_raw_subtitle_copy(topic, rows):
            topic = _topic_from_subtitles(rows, row.get("summary") or "")
        if not topic:
            continue
        topics[major_id] = {
            "topic": topic,
            "summary": _compact(row.get("summary") or "")[:240],
            "tags": tuple(str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip())[:8]
            if isinstance(row.get("tags"), list)
            else (),
        }
    return topics


def apply_major_topic_labels(
    segments: Iterable[RoughCutSegment],
    subtitles: Iterable[SubtitleSegment],
    *,
    settings: dict[str, Any] | None = None,
    llm_client=None,
) -> tuple[RoughCutSegment, ...]:
    """Replace finalized major titles with one-line LLM topic labels when available."""
    segment_items = list(segments or ())
    subtitle_items = list(subtitles or ())
    if not segment_items or not subtitle_items:
        return tuple(segment_items)
    payload, rows_by_major = _topic_payload(segment_items, subtitle_items)
    if not payload["major_segments"]:
        return tuple(segment_items)

    result = run_roughcut_llm_action(
        "label_major_topics",
        payload,
        settings=settings,
        llm_client=llm_client,
    )
    if not result.ok:
        return tuple(segment_items)
    topic_map = _topic_map_from_llm(result.data, rows_by_major)
    if not topic_map:
        return tuple(segment_items)

    out: list[RoughCutSegment] = []
    for segment in segment_items:
        major_id = _major_id(segment)
        label = topic_map.get(major_id)
        if not label:
            out.append(segment)
            continue
        summary = label.get("summary") or segment.summary
        tags = label.get("tags") or segment.tags
        out.append(
            replace(
                segment,
                title=str(label["topic"]),
                summary=str(summary or "")[:240],
                tags=tuple(tags or ()),
                llm_summary=str(summary or segment.llm_summary or "")[:240],
            )
        )
    return tuple(out)


__all__ = ["apply_major_topic_labels"]
