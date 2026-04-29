# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from .models import ChapterBoundaryCandidate, PackedPhrase


_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_STOPWORDS = {
    "그리고",
    "그래서",
    "근데",
    "그런데",
    "이제",
    "정말",
    "그냥",
    "약간",
    "저는",
    "제가",
    "우리",
    "여기",
    "저기",
    "이거",
    "그거",
    "뭐",
    "좀",
    "더",
    "다",
    "네",
    "아",
    "어",
    "음",
}
_SHIFT_PHRASES = (
    "다음은",
    "다음으로",
    "이번에는",
    "반대로",
    "한편",
    "결론적으로",
    "정리하면",
    "그러면",
    "이제부터",
    "마지막으로",
    "다시 말해서",
)


def tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in _TOKEN_RE.findall(text or "")]
    return [token for token in tokens if len(token) >= 2 and token not in _STOPWORDS]


def extract_keywords(text: str, top_k: int = 8) -> tuple[str, ...]:
    """Simple local keyword extraction for offline roughcut analysis."""
    counter = Counter(tokenize(text))
    if not counter:
        return tuple()
    ranked = sorted(counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return tuple(token for token, _ in ranked[: max(1, int(top_k))])


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _shift_phrase_boost(text: str) -> float:
    if not text:
        return 0.0
    return min(0.25, 0.08 * sum(1 for phrase in _SHIFT_PHRASES if phrase in text))


def topic_shift_score(previous_text: str, current_text: str) -> float:
    """Score local topic drift without network or heavy NLP dependencies."""
    previous = set(extract_keywords(previous_text, top_k=12))
    current = set(extract_keywords(current_text, top_k=12))
    novelty = 1.0 - _jaccard(previous, current)
    boost = _shift_phrase_boost(current_text)
    score = novelty + boost
    return round(max(0.0, min(1.0, score)), 4)


def detect_topic_shifts(
    phrases: Iterable[PackedPhrase],
    threshold: float = 0.55,
) -> list[ChapterBoundaryCandidate]:
    ordered = sorted(phrases, key=lambda phrase: (phrase.start, phrase.end))
    minimum = max(0.0, min(1.0, float(threshold)))
    boundaries: list[ChapterBoundaryCandidate] = []

    for previous, current in zip(ordered, ordered[1:]):
        score = topic_shift_score(previous.text, current.text)
        if score >= minimum:
            reasons = ["keyword_shift"]
            if any(phrase in current.text for phrase in _SHIFT_PHRASES):
                reasons.append("discourse_marker")
            boundaries.append(
                ChapterBoundaryCandidate(
                    start=previous.end,
                    end=current.start,
                    score=score,
                    reasons=tuple(reasons),
                )
            )
    return boundaries


def keyword_overlap_score(text_a: str, text_b: str) -> float:
    keywords_a = set(extract_keywords(text_a, top_k=12))
    keywords_b = set(extract_keywords(text_b, top_k=12))
    if not keywords_a and not keywords_b:
        return 1.0
    return round(_jaccard(keywords_a, keywords_b), 4)


def keyword_entropy(text: str) -> float:
    tokens = tokenize(text)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    return round(entropy, 4)
