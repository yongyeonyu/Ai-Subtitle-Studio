# Version: 03.00.21
# Phase: PHASE2
from __future__ import annotations

import re
from typing import Iterable

from core.native_text_similarity import similarity_ratio


_TIME_CODE_PATTERN = re.compile(
    r"(\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]|\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{1,3})?)"
)
_NOISE_PATTERN = re.compile(r"[^\w가-힣]+", re.UNICODE)
_NUMBER_PATTERN = re.compile(r"\d+(?:[,.]\d+)?")


def normalized_text(value: str) -> str:
    return _NOISE_PATTERN.sub("", str(value or "")).lower()


def normalized_edit_distance(left: str, right: str, *, limit: int | None = None) -> int:
    a = normalized_text(left)
    b = normalized_text(right)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if limit is not None and abs(len(a) - len(b)) > int(limit):
        return int(limit) + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if limit is not None and row_min > int(limit):
            return int(limit) + 1
        previous = current
    return previous[-1]


def contains_timecode(value: str) -> bool:
    return bool(_TIME_CODE_PATTERN.search(str(value or "")))


def _number_tokens(value: str) -> list[str]:
    return _NUMBER_PATTERN.findall(str(value or ""))


def validate_llm_chunks(
    source_text: str,
    chunks: Iterable[str],
    *,
    min_similarity: float = 0.82,
    max_length_delta_ratio: float = 0.18,
    max_edit_distance: int | None = None,
) -> tuple[bool, str]:
    """Check that LLM correction/splitting did not invent, delete, or time-shift content."""
    source_norm = normalized_text(source_text)
    cleaned_chunks = [str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()]
    if not source_norm:
        return False, "empty_source"
    if not cleaned_chunks:
        return False, "empty_chunks"
    if any(contains_timecode(chunk) for chunk in cleaned_chunks):
        return False, "timecode_in_output"

    candidate_norm = normalized_text("".join(cleaned_chunks))
    if not candidate_norm:
        return False, "empty_candidate"

    length_delta = abs(len(candidate_norm) - len(source_norm)) / max(1, len(source_norm))
    if length_delta > max_length_delta_ratio:
        return False, f"length_delta:{length_delta:.2f}"

    similarity = similarity_ratio(source_norm, candidate_norm)
    if similarity < min_similarity:
        allowed_edit_distance = max_edit_distance
        if allowed_edit_distance is None:
            allowed_edit_distance = max(1, min(2, int(round(len(source_norm) * 0.12))))
        edit_distance = normalized_edit_distance(source_norm, candidate_norm, limit=allowed_edit_distance)
        if edit_distance > allowed_edit_distance:
            return False, f"similarity:{similarity:.2f}"

    return True, "ok"


def safe_llm_chunks(source_text: str, chunks: Iterable[str] | None) -> list[str] | None:
    if chunks is None:
        return None
    cleaned = [str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()]
    ok, _reason = validate_llm_chunks(source_text, cleaned)
    return cleaned if ok else None


def assess_llm_rewrite_policy(source_text: str, chunks: Iterable[str] | None) -> dict:
    cleaned = [str(chunk or "").strip() for chunk in chunks or [] if str(chunk or "").strip()]
    source_norm = normalized_text(source_text)
    candidate_text = " ".join(cleaned).strip()
    candidate_norm = normalized_text("".join(cleaned))
    if not source_norm or not candidate_norm:
        return {"changed": False, "confidence": "none", "needs_review": False, "reason": "empty_candidate"}
    if source_norm == candidate_norm:
        return {
            "changed": False,
            "confidence": "same",
            "needs_review": False,
            "reason": "no_material_change",
            "similarity": 1.0,
            "length_delta_ratio": 0.0,
            "score_penalty": 0.0,
        }

    similarity = similarity_ratio(source_norm, candidate_norm)
    length_delta_ratio = abs(len(candidate_norm) - len(source_norm)) / max(1, len(source_norm))
    numbers_changed = _number_tokens(source_text) != _number_tokens(candidate_text)
    high_confidence = (not numbers_changed) and similarity >= 0.90 and length_delta_ratio <= 0.10
    medium_confidence = (not numbers_changed) and similarity >= 0.86 and length_delta_ratio <= 0.16
    confidence = "high" if high_confidence else ("medium" if medium_confidence else "low")
    needs_review = confidence != "high"
    score_penalty = 0.0 if confidence == "high" else (18.0 if confidence == "medium" else 32.0)
    if numbers_changed:
        reason = "number_changed"
    elif confidence == "high":
        reason = "obvious_stt_rewrite"
    elif confidence == "medium":
        reason = "uncertain_lexical_rewrite"
    else:
        reason = "low_similarity_rewrite"
    return {
        "changed": True,
        "confidence": confidence,
        "needs_review": needs_review,
        "reason": reason,
        "similarity": round(similarity, 6),
        "length_delta_ratio": round(length_delta_ratio, 6),
        "numbers_changed": numbers_changed,
        "score_penalty": score_penalty,
        "candidate_text": candidate_text,
    }
