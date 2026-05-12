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


def _normalize_tags(value: Any, *, limit: int = 8) -> tuple[str, ...]:
    raw_items: list[str]
    if isinstance(value, str):
        raw_items = re.split(r"[,/|#\n\r]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item) for item in value]
    else:
        raw_items = []
    seen: set[str] = set()
    tags: list[str] = []
    for raw in raw_items:
        tag = _compact(raw).strip("#- ")
        if not tag:
            continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag[:32])
        if len(tags) >= max(1, int(limit or 8)):
            break
    return tuple(tags)


_TOPIC_PREFIX_RE = re.compile(
    r"^(?:주제|중분류|중분류\s*주제|토픽|topic|title|제목|라벨|label)\s*[:：\-]\s*",
    re.IGNORECASE,
)
_WEAK_TOPIC_WORDS = {
    "내용",
    "대화",
    "상황",
    "설명",
    "영상",
    "장면",
    "부분",
    "이야기",
    "주제",
    "일상",
    "소개",
    "정리",
    "확인",
    "리뷰",
}

_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("주행 보조 기능", ("크루즈", "차선", "유지", "보조", "반자율", "adas", "스마트"), "vehicle"),
    ("주행 연비 평가", ("연비", "전비", "효율", "주유", "충전", "리터", "km"), "vehicle"),
    ("승차감과 정숙성", ("승차감", "정숙", "소음", "진동", "서스", "노면", "방음"), "vehicle"),
    ("가속 제동 성능", ("가속", "브레이크", "제동", "출력", "토크", "엔진", "모터"), "vehicle"),
    ("실내 편의 사양", ("실내", "시트", "공간", "센터", "디스플레이", "인포", "수납", "편의"), "vehicle"),
    ("외관 디자인 특징", ("외관", "외장", "디자인", "전면", "후면", "그릴", "램프", "휠"), "vehicle"),
    ("차량 시승 평가", ("차량", "자동차", "시승", "운전", "주행", "핸들", "속도"), "vehicle"),
    ("촬영 장비 세팅", ("카메라", "렌즈", "조명", "촬영", "노이즈", "마이크"), "media"),
    ("편집 작업 흐름", ("편집", "컷", "타임라인", "자막", "렌더", "프리미어"), "media"),
    ("상품 비교 평가", ("가격", "비교", "성능", "장점", "단점", "구매", "추천"), "review"),
    ("캐릭터 장면 설명", ("캐릭터", "장난감", "놀이", "아이", "어린이", "티니핑"), "kids"),
)


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
    hinted = _candidate_topic_hint(rows, fallback=fallback)
    if hinted:
        return hinted
    keywords = extract_keywords(text, top_k=4)
    if keywords:
        phrase = " ".join(keywords[:3])
        if phrase:
            return f"{phrase} 핵심 내용"[:42]
    return _compact(fallback)[:42]


def _candidate_topic_hint(rows: list[SubtitleSegment], fallback: str = "") -> str:
    text = _compact(" ".join(row.text for row in rows if row.text))
    search = text.casefold()
    fallback_text = _compact(fallback)

    scored: list[tuple[int, int, str]] = []
    broad_fallback: list[tuple[int, int, str]] = []
    for order, (label, terms, domain) in enumerate(_CATEGORY_RULES):
        hits = sum(1 for term in terms if term.casefold() in search)
        if hits <= 0:
            continue
        domain_bonus = 0
        if domain == "vehicle" and any(token in search for token in ("차", "차량", "자동차", "시승", "주행")):
            domain_bonus = 2
        elif domain == "media" and any(token in search for token in ("촬영", "영상", "편집", "카메라")):
            domain_bonus = 1
        target = broad_fallback if label in {"차량 시승 평가", "상품 비교 평가"} else scored
        target.append((hits + domain_bonus, -order, label))
    if scored:
        scored.sort(reverse=True)
        return scored[0][2]
    if broad_fallback:
        broad_fallback.sort(reverse=True)
        return broad_fallback[0][2]

    keywords = extract_keywords(text, top_k=5)
    useful = [keyword for keyword in keywords if keyword not in _WEAK_TOPIC_WORDS]
    if len(useful) >= 2:
        return f"{useful[0]} {useful[1]} 핵심 흐름"[:42]
    if useful:
        return f"{useful[0]} 주요 내용"[:42]
    return fallback_text[:42]


def _representative_excerpt(rows: list[SubtitleSegment], *, max_rows: int = 3) -> str:
    texts = [_compact(row.text) for row in rows if _compact(row.text)]
    if not texts:
        return ""
    if len(texts) <= max_rows:
        return " / ".join(texts)[:360]
    middle = texts[len(texts) // 2]
    return " / ".join([texts[0], middle, texts[-1]])[:360]


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


def _is_weak_topic(topic: str, rows: list[SubtitleSegment]) -> bool:
    text = _compact(topic)
    if not text:
        return True
    if _looks_like_raw_subtitle_copy(text, rows):
        return True
    normalized = re.sub(r"[\s/·,._\-]+", "", text).casefold()
    if normalized in {word.casefold() for word in _WEAK_TOPIC_WORDS}:
        return True
    tokens = extract_keywords(text, top_k=5)
    if len(text) <= 3 or (len(tokens) <= 1 and len(text) <= 6):
        return True
    sentence_markers = ("합니다", "했습니다", "됩니다", "보겠습니다", "같습니다", "있습니다", "입니다")
    if len(text) >= 18 and any(marker in text for marker in sentence_markers):
        return True
    if len(text) > 34 and len(tokens) >= 7:
        return True
    return False


def _clean_topic(topic: Any) -> str:
    text = _compact(topic)
    text = text.strip("`'\"[](){} ")
    text = _TOPIC_PREFIX_RE.sub("", text).strip()
    text = re.sub(r"^[\-•*#\d.\s]+", "", text).strip()
    text = re.split(r"[\n\r]", text, maxsplit=1)[0].strip()
    text = re.sub(r"\s*[.!?。！？]+$", "", text).strip()
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
        text = _compact(" ".join(row.text for row in rows if row.text))
        major_rows.append(
            {
                "major_id": major_id,
                "current_title": segment.title,
                "current_summary": segment.summary or segment.llm_summary,
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "subtitle_count": len(rows),
                "topic_level": "middle_category",
                "candidate_topic_hint": _candidate_topic_hint(rows, fallback=segment.title or segment.summary or ""),
                "keywords": list(extract_keywords(text, top_k=8)),
                "representative_excerpt": _representative_excerpt(rows),
                "subtitle_rows": _subtitle_rows_payload(rows),
            }
        )
    return (
        {
            "task_instruction": (
                "최종 확정된 각 중분류의 모든 subtitle_rows를 읽고 중분류 주제(topic_level=middle_category)를 작성한다. "
                "topic은 첫 자막/마지막 자막/말문을 복사한 문장이 아니라, 묶음 전체를 대표하는 10~22자 한국어 명사구여야 한다. "
                "각 중분류마다 tags도 반드시 함께 작성한다. "
                "tags는 나중에 프로젝트 파일과 러프컷 편집기에서 바로 사용할 핵심 키워드 목록이며, 2~6개의 짧은 명사형 단어/구로 만든다. "
                "예: topic='차량 실내 리뷰'이면 tags=['시트', '기능', '디자인 특징', '수납공간']처럼 자막 근거가 분명한 핵심어만 넣는다. "
                "candidate_topic_hint와 keywords는 참고만 하되, 자막 전체 근거가 더 정확하면 더 구체적인 중분류 주제로 바꾼다. "
                "금지: '내용', '대화', '상황', '설명', '영상', '리뷰'처럼 너무 넓은 단어만 쓰기. "
                "좋은 예: '고속 주행 연비 평가', '주행 보조 기능 확인', '실내 편의 사양 점검', '외관 디자인 특징', '촬영 장비 세팅'."
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
        if _is_weak_topic(topic, rows):
            topic = _topic_from_subtitles(rows, row.get("summary") or "")
        if not topic:
            continue
        topics[major_id] = {
            "topic": topic,
            "summary": _compact(row.get("summary") or "")[:240],
            "tags": _normalize_tags(row.get("tags")),
        }
    return topics


def _heuristic_topic_map(
    segments: list[RoughCutSegment],
    rows_by_major: dict[str, list[SubtitleSegment]],
) -> dict[str, dict[str, Any]]:
    topics: dict[str, dict[str, Any]] = {}
    for segment in list(segments or []):
        major_id = _major_id(segment)
        if not major_id:
            continue
        rows = rows_by_major.get(major_id, [])
        if not rows:
            continue
        fallback = segment.title or segment.summary or segment.llm_summary or major_id
        topic = _topic_from_subtitles(rows, fallback=fallback)
        if not topic:
            continue
        topics[major_id] = {
            "topic": topic,
            "summary": _representative_excerpt(rows)[:240],
            "tags": tuple(extract_keywords(_compact(" ".join(row.text for row in rows if row.text)), top_k=4)),
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
    topic_map = _topic_map_from_llm(result.data, rows_by_major) if result.ok else {}
    llm_topic_map_applied = bool(topic_map)
    if not topic_map:
        topic_map = _heuristic_topic_map(segment_items, rows_by_major)
    if not topic_map:
        return tuple(segment_items)

    out: list[RoughCutSegment] = []
    for segment in segment_items:
        major_id = _major_id(segment)
        label = topic_map.get(major_id)
        if not label:
            out.append(segment)
            continue
        if (
            not llm_topic_map_applied
            and str(segment.narrative_function or "") == "roughcut_llm_major_segment"
            and str(segment.title or "").strip()
        ):
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
