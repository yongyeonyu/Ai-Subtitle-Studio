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
_TOPIC_PARTICLE_RE = re.compile(r"(?:에서|으로|에게|이랑|랑|과|와|은|는|이|가|을|를|도|만|에|로)$")
_TOPIC_FILLER_PREFIX_RE = re.compile(
    r"^(?:오늘은|이번에는|올해도|작년에도|이제|그러면|여기서|여기는|여기|그리고|그래서|일단|먼저)\s+"
)
_TOPIC_DEMONSTRATIVE_PREFIX_RE = re.compile(r"^(?:이|그|저)\s+")
_TOPIC_TRAILING_CLAUSE_RE = re.compile(
    r"(?:것\s*같(?:아|아요|습니다)|같더라고요|하네요|했네요|있네요|있는데|했는데|거든요|인데요)\s*$"
)
_TOPIC_TRAILING_ADVERB_RE = re.compile(r"(?:자세히|함께|먼저|직접|바로|다시|계속)\s*$")
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
_ACTION_TERMS = {
    "공개",
    "소개",
    "확인",
    "점검",
    "비교",
    "체험",
    "관람",
    "시승",
    "분석",
    "평가",
    "정리",
    "탐방",
    "방문",
}
_TOPIC_ENDING_ACTIONS: tuple[tuple[str, str], ...] = (
    ("살펴보겠습니다", "점검"),
    ("살펴봅니다", "점검"),
    ("살펴볼게요", "점검"),
    ("확인해보겠습니다", "확인"),
    ("확인해봅니다", "확인"),
    ("확인하겠습니다", "확인"),
    ("확인합니다", "확인"),
    ("정리해보겠습니다", "정리"),
    ("정리합니다", "정리"),
    ("소개해드리겠습니다", "소개"),
    ("소개하겠습니다", "소개"),
    ("소개합니다", "소개"),
    ("공개하겠습니다", "공개"),
    ("공개합니다", "공개"),
    ("비교해보겠습니다", "비교"),
    ("비교합니다", "비교"),
    ("체험해보겠습니다", "체험"),
    ("체험합니다", "체험"),
    ("시승해보겠습니다", "시승"),
    ("시승합니다", "시승"),
    ("둘러보겠습니다", "관람"),
    ("구경해보겠습니다", "관람"),
    ("가보도록 하겠습니다", "관람"),
    ("나왔습니다", "방문"),
    ("나왔는데", "방문"),
    ("왔습니다", "방문"),
)
_INLINE_ACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*구경"), "관람"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*관람"), "관람"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*공개"), "공개"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*소개"), "소개"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*비교"), "비교"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*체험"), "체험"),
    (re.compile(r"(.{2,32}?)(?:을|를)?\s*시승"), "시승"),
)
_VERBISH_TOKEN_SUFFIXES = (
    "합니다",
    "했습니다",
    "하겠습니다",
    "보겠습니다",
    "봅니다",
    "했는데",
    "거든요",
    "같아요",
    "같습니다",
    "나왔는데",
    "왔거든요",
)

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
_BROAD_TOPIC_LABELS = {label for label, _terms, _domain in _CATEGORY_RULES}


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


def _trim_topic_particle(text: str) -> str:
    compact = _compact(text)
    if not compact:
        return ""
    while True:
        updated = _TOPIC_PARTICLE_RE.sub("", compact).strip()
        if updated == compact:
            return compact
        compact = updated


def _normalize_keyword_token(token: Any) -> str:
    text = _compact(token)
    if not text:
        return ""
    text = _TOPIC_FILLER_PREFIX_RE.sub("", text).strip()
    text = _trim_topic_particle(text)
    if not text:
        return ""
    if any(text.endswith(suffix) for suffix in _VERBISH_TOKEN_SUFFIXES):
        return ""
    if text.casefold() in {word.casefold() for word in _WEAK_TOPIC_WORDS}:
        return ""
    return text[:32]


def _sentence_topic_candidate(text: Any) -> str:
    value = _compact(text)
    if not value:
        return ""
    value = _TOPIC_FILLER_PREFIX_RE.sub("", value).strip()
    value = _TOPIC_DEMONSTRATIVE_PREFIX_RE.sub("", value).strip()
    value = _TOPIC_TRAILING_CLAUSE_RE.sub("", value).strip()
    action = ""
    for ending, noun in _TOPIC_ENDING_ACTIONS:
        if value.endswith(ending):
            value = value[: -len(ending)].strip()
            action = noun
            break
    if not action:
        for pattern, noun in _INLINE_ACTION_PATTERNS:
            match = pattern.search(value)
            if not match:
                continue
            value = match.group(1).strip()
            action = noun
            break
    if "해서" in value:
        value = value.split("해서", 1)[0].strip()
    value = re.split(r"\s+(?:근데|그런데|그리고|그래서)\s+", value, maxsplit=1)[0].strip()
    value = _TOPIC_TRAILING_ADVERB_RE.sub("", value).strip()
    value = _trim_topic_particle(value)
    value = _clean_topic(value)
    if not value:
        return ""
    if action and action not in value:
        value = f"{value} {action}".strip()
    return value[:42]


def _detail_terms(rows: list[SubtitleSegment], *, tags: Iterable[Any] = (), fallback: str = "") -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in list(tags or ()):
        token = _normalize_keyword_token(raw)
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)
        if len(ordered) >= 8:
            return tuple(ordered)

    joined = _compact(" ".join(row.text for row in rows if row.text))
    if fallback:
        joined = f"{joined} {fallback}".strip()
    for raw in extract_keywords(joined, top_k=12):
        token = _normalize_keyword_token(raw)
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(token)
        if len(ordered) >= 8:
            break
    return tuple(ordered)


def _topic_candidate_score(
    topic: str,
    rows: list[SubtitleSegment],
    *,
    tags: Iterable[Any] = (),
    fallback: str = "",
) -> int:
    text = _clean_topic(topic)
    if not text:
        return -10_000
    if _is_weak_topic(text, rows):
        return -10_000

    normalized_fallback = _clean_topic(fallback)
    detail_terms = _detail_terms(rows, tags=tags, fallback=fallback)
    topic_tokens = {
        token
        for token in (_normalize_keyword_token(raw) for raw in extract_keywords(text, top_k=8))
        if token
    }
    overlap = sum(1 for term in detail_terms if term and (term in text or term in topic_tokens))
    action_bonus = 4 if any(term in text for term in _ACTION_TERMS) else 0
    proper_bonus = 3 if re.search(r"[A-Za-z]{2,}|\d", text) else 0
    broad_penalty = 8 if text in _BROAD_TOPIC_LABELS else 0
    fallback_bonus = 3 if normalized_fallback and text == normalized_fallback else 0
    return min(len(text), 32) + (overlap * 6) + action_bonus + proper_bonus + fallback_bonus - broad_penalty


def _looks_broad_topic_phrase(topic: Any) -> bool:
    text = _clean_topic(topic)
    if not text:
        return True
    if text in _BROAD_TOPIC_LABELS:
        return True
    normalized_tokens = [
        token
        for token in (_normalize_keyword_token(raw) for raw in extract_keywords(text, top_k=6))
        if token
    ]
    generic_suffixes = ("소개", "리뷰", "설명", "정리", "점검", "확인", "내용", "흐름")
    if len(normalized_tokens) <= 2 and any(text.endswith(suffix) for suffix in generic_suffixes):
        has_specific_anchor = bool(re.search(r"[A-Za-z]{2,}|\d", text)) or len(text) >= 12
        if not has_specific_anchor:
            return True
    return False


def _best_topic_candidate(
    rows: list[SubtitleSegment],
    candidates: Iterable[Any],
    *,
    tags: Iterable[Any] = (),
    fallback: str = "",
) -> str:
    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, raw in enumerate(candidates):
        variants = (_clean_topic(raw), _sentence_topic_candidate(raw))
        for variant in variants:
            if not variant:
                continue
            key = variant.casefold()
            if key in seen:
                continue
            seen.add(key)
            score = _topic_candidate_score(variant, rows, tags=tags, fallback=fallback)
            ranked.append((score, -order, variant[:42]))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    return ranked[0][2]


def _topic_from_subtitles(rows: list[SubtitleSegment], fallback: str = "") -> str:
    text = _compact(" ".join(row.text for row in rows if row.text))
    hinted = _candidate_topic_hint(rows, fallback=fallback)
    keywords = extract_keywords(text, top_k=4)
    keyword_phrase = " ".join(_normalize_keyword_token(token) for token in keywords[:3] if _normalize_keyword_token(token))
    candidates: list[str] = []
    if hinted:
        candidates.append(hinted)
    if fallback:
        candidates.append(str(fallback))
    if keyword_phrase:
        candidates.append(f"{keyword_phrase} 핵심 내용")
    if rows:
        candidates.append(rows[0].text)
        candidates.append(rows[len(rows) // 2].text)
        candidates.append(rows[-1].text)
    best = _best_topic_candidate(rows, candidates, fallback=fallback)
    if best:
        return best
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
    if any(marker in text for marker in sentence_markers):
        return True
    connective_markers = ("면서", "하며", "하고", "해서", "들고")
    if any(marker in text for marker in connective_markers):
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
                "topic은 첫 자막/마지막 자막/말문을 복사한 문장이 아니라, 묶음 전체를 대표하는 14~30자 한국어 명사구여야 한다. "
                "가능하면 장소/제품/인물/행동 중 최소 2가지 이상을 함께 드러내서, 중분류만 봐도 무슨 장면인지 바로 알 수 있게 쓴다. "
                "current_title이 이미 자막 근거가 분명한 구체적 제목이면 더 일반적인 표현으로 축약하지 말고, 더 정확한 방향으로만 다듬는다. "
                "각 중분류마다 tags도 반드시 함께 작성한다. "
                "tags는 나중에 프로젝트 파일과 러프컷 편집기에서 바로 사용할 핵심 키워드 목록이며, 2~6개의 짧은 명사형 단어/구로 만든다. "
                "예: topic='차량 실내 리뷰'이면 tags=['시트', '기능', '디자인 특징', '수납공간']처럼 자막 근거가 분명한 핵심어만 넣는다. "
                "candidate_topic_hint와 keywords는 참고만 하되, 자막 전체 근거가 더 정확하면 더 구체적인 중분류 주제로 바꾼다. "
                "금지: '내용', '대화', '상황', '설명', '영상', '리뷰'처럼 너무 넓은 단어만 쓰기. "
                "나쁜 예: '전시 소개', '차량 리뷰', '실내 설명'. "
                "좋은 예: '고속 주행 연비 비교', '주행 보조 기능 확인', '실내 버튼과 수납 공간 점검', '현대모토 스튜디오 넥소 전시 공개', '촬영 장비 세팅'."
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
        tags = _normalize_tags(row.get("tags"))
        topic = _best_topic_candidate(
            rows,
            (
                row.get("topic"),
                row.get("title"),
            ),
            tags=tags,
            fallback=str(row.get("topic") or row.get("title") or ""),
        )
        if _is_weak_topic(topic, rows):
            topic = _topic_from_subtitles(rows, row.get("summary") or "")
        if not topic:
            continue
        topics[major_id] = {
            "topic": topic,
            "summary": _compact(row.get("summary") or "")[:240],
            "tags": tags,
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
        rows = rows_by_major.get(major_id, [])
        if (
            not llm_topic_map_applied
            and str(segment.narrative_function or "") == "roughcut_llm_major_segment"
            and str(segment.title or "").strip()
        ):
            out.append(segment)
            continue
        summary = label.get("summary") or segment.summary
        tags = label.get("tags") or segment.tags
        proposed_topic = _best_topic_candidate(
            rows,
            (label.get("topic"),),
            tags=tags,
            fallback=str(segment.title or summary or ""),
        )
        fallback_topic = _best_topic_candidate(
            rows,
            (
                segment.title,
                _topic_from_subtitles(rows, fallback=str(segment.title or segment.summary or "")),
            ),
            tags=tags,
            fallback=str(segment.title or summary or ""),
        )
        proposed_score = _topic_candidate_score(
            proposed_topic,
            rows,
            tags=tags,
            fallback=str(segment.title or summary or ""),
        ) if proposed_topic else -10_000
        fallback_score = _topic_candidate_score(
            fallback_topic,
            rows,
            tags=tags,
            fallback=str(segment.title or summary or ""),
        ) if fallback_topic else -10_000

        if proposed_topic and not _looks_broad_topic_phrase(proposed_topic):
            chosen_topic = proposed_topic
        elif fallback_topic:
            chosen_topic = fallback_topic
        else:
            chosen_topic = str(label["topic"])
        out.append(
            replace(
                segment,
                title=chosen_topic,
                summary=str(summary or "")[:240],
                tags=tuple(tags or ()),
                llm_summary=str(summary or segment.llm_summary or "")[:240],
            )
        )
    return tuple(out)


__all__ = ["apply_major_topic_labels"]
