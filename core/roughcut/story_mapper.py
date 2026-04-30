# Version: 03.01.26
# Phase: PHASE2
from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .models import ChapterMetadata

STORY_ROLES = ("기", "승", "전", "결")

_ROLE_HINTS: dict[str, tuple[str, ...]] = {
    "기": (
        "시작",
        "소개",
        "오늘은",
        "먼저",
        "처음",
        "배경",
        "문제 제기",
        "목표",
        "오프닝",
    ),
    "승": (
        "이어서",
        "다음",
        "과정",
        "방법",
        "설명",
        "준비",
        "예시",
        "본론",
        "확장",
    ),
    "전": (
        "하지만",
        "반대로",
        "한편",
        "문제",
        "위기",
        "핵심",
        "반전",
        "실패",
        "전환",
        "다르게",
    ),
    "결": (
        "결론",
        "정리",
        "마지막",
        "마무리",
        "요약",
        "결과",
        "추천",
        "끝",
        "엔딩",
        "다음 영상",
    ),
}


def _chapter_text(chapter: ChapterMetadata) -> str:
    parts = [
        chapter.title,
        chapter.summary,
        " ".join(chapter.tags),
        chapter.narrative_function,
    ]
    return " ".join(part for part in parts if part).lower()


def _position_role(index: int, total: int) -> str:
    if total <= 1:
        return "기"
    ratio = (index + 0.5) / max(1, total)
    if ratio < 0.3:
        return "기"
    if ratio < 0.62:
        return "승"
    if ratio < 0.82:
        return "전"
    return "결"


def _hint_scores(text: str) -> dict[str, int]:
    return {
        role: sum(1 for hint in hints if hint.lower() in text)
        for role, hints in _ROLE_HINTS.items()
    }


def _score_roles(position_role: str, hint_scores: dict[str, int]) -> dict[str, float]:
    scores = {role: 0.0 for role in STORY_ROLES}
    scores[position_role] = 0.65
    for role, count in hint_scores.items():
        scores[role] += min(0.75, count * 0.3)
    return scores


def _classify_story_role(chapter: ChapterMetadata, index: int, total: int) -> tuple[str, str, str, float]:
    position_role = _position_role(index, total)
    text = _chapter_text(chapter)
    hints = _hint_scores(text)
    scores = _score_roles(position_role, hints)
    role = max(STORY_ROLES, key=lambda item: (scores[item], -STORY_ROLES.index(item)))

    matched_hints = [f"{hint}" for hint in _ROLE_HINTS[role] if hint.lower() in text]
    reason_parts = [f"position:{index + 1}/{total}->{position_role}"]
    if matched_hints:
        reason_parts.append(f"hints:{','.join(matched_hints[:4])}")
    else:
        reason_parts.append("hints:none")

    sorted_scores = sorted(scores.values(), reverse=True)
    margin = sorted_scores[0] - (sorted_scores[1] if len(sorted_scores) > 1 else 0.0)
    confidence = round(max(0.0, min(1.0, 0.45 + margin)), 4)

    move_recommendation = "keep_order"
    if role != position_role and hints.get(role, 0) > hints.get(position_role, 0):
        move_recommendation = f"review_move_toward_{role}"
        reason_parts.append(f"position_hint_conflict:{position_role}->{role}")

    return role, "; ".join(reason_parts), move_recommendation, confidence


def map_story_roles(chapters: Iterable[ChapterMetadata]) -> list[ChapterMetadata]:
    """Assign 기/승/전/결 metadata without changing the chapter order."""
    ordered = list(chapters)
    total = len(ordered)
    mapped: list[ChapterMetadata] = []

    for index, chapter in enumerate(ordered):
        role, reason, move_recommendation, confidence = _classify_story_role(chapter, index, total)
        narrative_function = chapter.narrative_function or f"story_{role}"
        mapped.append(
            replace(
                chapter,
                narrative_function=narrative_function,
                story_role=role,
                story_reason=reason,
                move_recommendation=move_recommendation,
                role_confidence=confidence,
            )
        )

    return mapped


def classify_story_role(chapter: ChapterMetadata, index: int = 0, total: int = 1) -> tuple[str, str, str, float]:
    """Public compatibility wrapper for story role classification."""
    return _classify_story_role(chapter, index, max(1, total))


def remap_story_flow(chapters: Iterable[ChapterMetadata]) -> list[ChapterMetadata]:
    """Compatibility alias; current policy assigns roles without reordering."""
    return map_story_roles(chapters)
