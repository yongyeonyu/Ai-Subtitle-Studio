from __future__ import annotations

"""Optional native text similarity helpers.

RapidFuzz is a C++ extension. When it is installed we use it for hot
ratio-only checks; otherwise difflib keeps the same pure-Python fallback.
"""

from difflib import SequenceMatcher
import os
from typing import Any

try:
    from rapidfuzz import fuzz as _rapidfuzz_fuzz  # type: ignore
    from rapidfuzz.distance import Levenshtein as _rapidfuzz_levenshtein  # type: ignore
except Exception:  # pragma: no cover - exercised in fallback environments.
    _rapidfuzz_fuzz = None  # type: ignore
    _rapidfuzz_levenshtein = None  # type: ignore


HAS_NATIVE_TEXT_SIMILARITY = _rapidfuzz_fuzz is not None


def native_text_similarity_enabled() -> bool:
    if _rapidfuzz_fuzz is None:
        return False
    value = str(os.environ.get("AI_SUBTITLE_NATIVE_TEXT_SIMILARITY", "1") or "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def text_similarity_backend() -> str:
    return "rapidfuzz" if native_text_similarity_enabled() else "difflib"


def similarity_ratio(left: Any, right: Any) -> float:
    left_text = str(left or "")
    right_text = str(right or "")
    if native_text_similarity_enabled():
        return max(0.0, min(1.0, float(_rapidfuzz_fuzz.ratio(left_text, right_text)) / 100.0))
    return float(SequenceMatcher(None, left_text, right_text).ratio())


def _sequence(value: Any) -> list[Any] | str:
    if value is None:
        return []
    if isinstance(value, str):
        return value
    try:
        return list(value)
    except TypeError:
        return [value]


def edit_distance(left: Any, right: Any) -> int:
    left_seq = _sequence(left)
    right_seq = _sequence(right)
    if native_text_similarity_enabled() and _rapidfuzz_levenshtein is not None:
        try:
            return int(_rapidfuzz_levenshtein.distance(left_seq, right_seq))
        except Exception:
            pass
    if not left_seq:
        return len(right_seq)
    if not right_seq:
        return len(left_seq)
    previous = list(range(len(right_seq) + 1))
    for index_left, item_left in enumerate(left_seq, start=1):
        current = [index_left]
        for index_right, item_right in enumerate(right_seq, start=1):
            insert_cost = current[index_right - 1] + 1
            delete_cost = previous[index_right] + 1
            replace_cost = previous[index_right - 1] + (0 if item_left == item_right else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return int(previous[-1])


def character_error_rate(reference: Any, hypothesis: Any) -> float:
    ref_seq = _sequence(reference)
    hyp_seq = _sequence(hypothesis)
    if not ref_seq and not hyp_seq:
        return 0.0
    if not ref_seq or not hyp_seq:
        return 1.0
    return min(1.0, edit_distance(ref_seq, hyp_seq) / max(1, len(ref_seq)))
