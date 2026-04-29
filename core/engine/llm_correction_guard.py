# Version: 03.00.21
# Phase: PHASE2
from __future__ import annotations

import difflib
import re
from typing import Iterable


_TIME_CODE_PATTERN = re.compile(
    r"(\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]|\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{1,3})?)"
)
_NOISE_PATTERN = re.compile(r"[^\w가-힣]+", re.UNICODE)


def normalized_text(value: str) -> str:
    return _NOISE_PATTERN.sub("", str(value or "")).lower()


def contains_timecode(value: str) -> bool:
    return bool(_TIME_CODE_PATTERN.search(str(value or "")))


def validate_llm_chunks(
    source_text: str,
    chunks: Iterable[str],
    *,
    min_similarity: float = 0.82,
    max_length_delta_ratio: float = 0.18,
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

    similarity = difflib.SequenceMatcher(None, source_norm, candidate_norm).ratio()
    if similarity < min_similarity:
        return False, f"similarity:{similarity:.2f}"

    return True, "ok"


def safe_llm_chunks(source_text: str, chunks: Iterable[str] | None) -> list[str] | None:
    if chunks is None:
        return None
    cleaned = [str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()]
    ok, _reason = validate_llm_chunks(source_text, cleaned)
    return cleaned if ok else None
