# Version: 03.01.30
# Phase: PHASE2
from __future__ import annotations

import re
from typing import Any, Iterable

from .models import RoughCutResult, RoughCutTitleSuggestion
from .roughcut_llm import run_roughcut_llm_action
from .roughcut_settings import merge_roughcut_settings


_SPACE_RE = re.compile(r"\s+")


def _clean_title(text: str) -> str:
    title = _SPACE_RE.sub(" ", str(text or "")).strip(" -:|")
    return title[:90].strip()


def _unique_tags(items: Iterable[str], limit: int = 5) -> tuple[str, ...]:
    tags: list[str] = []
    seen = set()
    for raw in items:
        tag = _clean_title(str(raw)).strip("#, ")
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        tags.append(tag)
        seen.add(key)
        if len(tags) >= limit:
            break
    return tuple(tags)


def _result_payload(result: RoughCutResult) -> dict[str, Any]:
    chapters = [
        {
            "chapter_id": chapter.chapter_id,
            "title": chapter.title,
            "summary": chapter.summary,
            "tags": list(chapter.tags),
            "start": chapter.start,
            "end": chapter.end,
            "importance": chapter.importance_score,
            "major_id": chapter.major_id,
            "minor_code": chapter.minor_code,
        }
        for chapter in result.chapters[:24]
    ]
    segments = [
        {
            "major_id": segment.major_id or segment.segment_id,
            "title": segment.title,
            "summary": segment.summary or segment.llm_summary,
            "tags": list(segment.tags),
            "start": segment.start,
            "end": segment.end,
            "importance": max(segment.importance, segment.importance_score),
        }
        for segment in result.segments[:12]
    ]
    return {
        "video_summary": result.video_summary,
        "chapters": chapters,
        "major_segments": segments,
        "warnings": list(result.warnings),
    }


def _suggestion_from_dict(index: int, item: dict[str, Any], source: str) -> RoughCutTitleSuggestion | None:
    title = _clean_title(str(item.get("title") or ""))
    if not title:
        return None
    return RoughCutTitleSuggestion(
        title_id=str(item.get("title_id") or f"title_{index:03d}"),
        title=title,
        score=float(item.get("score") or item.get("expected_score") or 0.0),
        reason=str(item.get("reason") or item.get("rationale") or ""),
        source="llm" if source == "llm" else "local",
        tags=_unique_tags(item.get("tags") or ()),
        expected_reach=str(item.get("expected_reach") or item.get("reach") or ""),
        copied=bool(item.get("copied", False)),
        applied=bool(item.get("applied", False)),
    )


def _local_title_suggestions(result: RoughCutResult, limit: int) -> tuple[RoughCutTitleSuggestion, ...]:
    scored_chapters = sorted(
        result.chapters,
        key=lambda chapter: (chapter.importance_score, chapter.end - chapter.start),
        reverse=True,
    )
    scored_segments = sorted(
        result.segments,
        key=lambda segment: (max(segment.importance, segment.importance_score), segment.end - segment.start),
        reverse=True,
    )
    titles: list[str] = []
    tags: list[str] = []
    for segment in scored_segments[:3]:
        if segment.title:
            titles.append(segment.title)
        tags.extend(segment.tags)
    for chapter in scored_chapters[:5]:
        if chapter.title:
            titles.append(chapter.title)
        tags.extend(chapter.tags)
    tags_tuple = _unique_tags(tags, limit=6)
    primary = _clean_title(titles[0] if titles else result.video_summary or "러프컷 하이라이트")
    secondary = _clean_title(titles[1] if len(titles) > 1 else "")
    tag_tail = " ".join(f"#{tag}" for tag in tags_tuple[:3])
    candidates = [
        f"{primary} 핵심만 빠르게 보기",
        f"{primary} 리뷰 포인트 총정리",
        f"{primary}{' vs ' + secondary if secondary else ''} 하이라이트",
        f"{primary} 꼭 봐야 할 장면 {tag_tail}".strip(),
    ]
    suggestions = []
    seen = set()
    for index, title in enumerate(candidates, start=1):
        clean = _clean_title(title)
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        suggestions.append(
            RoughCutTitleSuggestion(
                title_id=f"title_{index:03d}",
                title=clean,
                score=max(0.52, 0.86 - (index - 1) * 0.08),
                reason="중분류 제목과 중요도 상위 챕터를 기반으로 생성",
                source="local",
                tags=tags_tuple[:4],
                expected_reach="중간" if index > 1 else "높음",
            )
        )
        if len(suggestions) >= limit:
            break
    return tuple(suggestions)


def build_title_suggestions(
    result: RoughCutResult,
    *,
    settings: dict[str, Any] | None = None,
    llm_client=None,
    limit: int = 4,
) -> tuple[RoughCutTitleSuggestion, ...]:
    """Build YouTube title suggestions for the PAGE 3-B roughcut panel."""
    roughcut_settings = merge_roughcut_settings(settings)
    limit = max(1, int(limit or 4))
    if not bool(roughcut_settings.get("roughcut_title_suggestions_enabled", True)):
        return ()

    llm_result = run_roughcut_llm_action(
        "title_suggestions",
        _result_payload(result),
        settings=settings,
        llm_client=llm_client,
    )
    if llm_result.ok:
        suggestions = []
        for index, item in enumerate(llm_result.data.get("titles", []) or [], start=1):
            if isinstance(item, dict):
                suggestion = _suggestion_from_dict(index, item, "llm")
                if suggestion is not None:
                    suggestions.append(suggestion)
            if len(suggestions) >= limit:
                break
        if suggestions:
            return tuple(suggestions)
    return _local_title_suggestions(result, limit)


__all__ = ["build_title_suggestions"]
