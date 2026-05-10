# Version: 04.00.01
# Phase: MAC_NATIVE_REFACTOR
"""C++ backed word split planning for subtitle generation.

The heavy loop is delegated to ``core.native_cut_boundary.word_split_groups``
when the extension is available. Python keeps only policy preparation and
validation so the large subtitle engine does not own native bridge details.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from core.native_cut_boundary import word_split_groups as _native_word_split_groups
except Exception:  # pragma: no cover - native extension may be unavailable.
    _native_word_split_groups = None


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def native_builtin_word_groups(
    words: list[dict[str, Any]],
    *,
    rules: dict[str, Any],
    threshold: int,
    gap_break_sec: float,
    default_gap_break_sec: float,
    natural_break_func: Callable[[str, str, dict[str, Any]], bool],
    visible_len_func: Callable[[str], int],
) -> list[tuple[int, int]] | None:
    if not callable(_native_word_split_groups) or len(words) < 2:
        return None

    starts: list[float] = []
    ends: list[float] = []
    char_counts: list[int] = []
    natural_breaks: list[int] = []
    vad_indexes: list[int] = []
    for index, word in enumerate(words):
        start = _float_value(word.get("start"), 0.0)
        end = max(start + 0.001, _float_value(word.get("end"), start + 0.001))
        starts.append(start)
        ends.append(end)
        char_counts.append(visible_len_func(str(word.get("word", "") or "")))
        if index + 1 < len(words):
            current = str(word.get("word", "") or "")
            nxt = str(words[index + 1].get("word", "") or "")
            natural_breaks.append(1 if natural_break_func(current, nxt, rules) else 0)
        else:
            natural_breaks.append(0)
        vad_indexes.append(-1)

    groups = _native_word_split_groups(
        starts,
        ends,
        char_counts,
        natural_breaks,
        vad_indexes,
        max_chars=max(2, int(threshold or 10)),
        max_duration=999999.0,
        max_cps=999999.0,
        min_duration=0.0,
        gap_break_sec=max(0.01, float(gap_break_sec or default_gap_break_sec)),
        word_gap_break_sec=max(0.01, float(gap_break_sec or default_gap_break_sec)),
    )
    if not groups:
        return None

    cleaned: list[tuple[int, int]] = []
    cursor = 0
    word_count = len(words)
    for begin, end in groups:
        begin = int(begin)
        end = int(end)
        if begin != cursor or end <= begin or end > word_count:
            return None
        cleaned.append((begin, end))
        cursor = end
    return cleaned if cursor == word_count else None


__all__ = ["native_builtin_word_groups"]
