#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from core.engine.subtitle_text_policy import normalize_subtitle_text_lines, split_visible_len


def _segment_duration(row: dict[str, Any]) -> float:
    start = float(row.get("start", 0.0) or 0.0)
    end = float(row.get("end", start) or start)
    return max(0.001, end - start)


def _readability_line_lengths(text: Any) -> list[int]:
    normalized = normalize_subtitle_text_lines(str(text or ""))
    lengths = [split_visible_len(line) for line in normalized.split("\n") if str(line or "").strip()]
    return [int(length) for length in lengths if int(length) > 0]


def _readability_target_line_count(total_chars: int, settings: dict[str, Any]) -> int:
    target_chars = max(8, int(settings.get("subtitle_common_split_target_chars", 16) or 16))
    target_lines = settings.get("subtitle_target_line_count")
    try:
        explicit = int(target_lines)
    except (TypeError, ValueError):
        explicit = 0
    if explicit in (1, 2):
        if total_chars <= max(10, target_chars - 2):
            return 1
        return explicit
    if total_chars <= max(10, target_chars + 2):
        return 1
    return 2


def _readability_line_count_score(line_count: int, target_lines: int, max_line_chars: int, hard_max: int) -> float:
    if line_count <= 0:
        return 0.0
    if line_count > 2:
        return max(0.0, 20.0 - (line_count - 3) * 5.0)
    if target_lines == 1:
        if line_count == 1:
            return 100.0
        return 82.0 if max_line_chars <= hard_max else 56.0
    if line_count == 2:
        return 100.0
    return 84.0 if max_line_chars <= hard_max else 62.0


def _readability_line_length_score(lengths: list[int], *, target_chars: int, hard_max: int) -> float:
    if not lengths:
        return 0.0
    penalty = 0.0
    for length in lengths:
        penalty += max(0, length - hard_max) * 8.0
        penalty += max(0, length - target_chars) * 2.5
    return max(0.0, min(100.0, 100.0 - penalty))


def _readability_balance_score(lengths: list[int], target_lines: int) -> float:
    if not lengths:
        return 0.0
    if len(lengths) == 1:
        return 100.0 if target_lines == 1 else 72.0
    if len(lengths) != 2:
        return 25.0
    longest = max(lengths)
    shortest = min(lengths)
    if longest <= 0:
        return 0.0
    ratio = shortest / longest
    return max(0.0, min(100.0, 35.0 + ratio * 65.0))


def _readability_orphan_score(lengths: list[int], total_chars: int) -> float:
    if len(lengths) < 2 or total_chars < 10:
        return 100.0
    shortest = min(lengths)
    if shortest <= 2:
        return 15.0
    if shortest == 3:
        return 35.0
    if shortest == 4:
        return 60.0
    if shortest <= 5:
        return 82.0
    return 100.0


def _readability_cps_score(cps: float, max_cps: float) -> float:
    if max_cps <= 0.0:
        return 100.0
    if cps <= max_cps:
        return 100.0
    return max(0.0, min(100.0, 100.0 - (cps - max_cps) * 14.0))


def score_readability(rows: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = dict(settings or {})
    usable_rows = [dict(row) for row in rows if str(row.get("text", "") or "").strip()]
    if not usable_rows:
        return {
            "readability_score": 0.0,
            "avg_segment_readability": 0.0,
            "avg_lines_per_segment": 0.0,
            "avg_max_line_chars": 0.0,
            "avg_cps": 0.0,
            "two_line_segments": 0,
            "over_two_line_segments": 0,
            "hard_overflow_segments": 0,
            "orphan_line_segments": 0,
            "balanced_two_line_segments": 0,
            "packaging_changed_segments": 0,
        }

    target_chars = max(8, int(settings.get("subtitle_common_split_target_chars", 16) or 16))
    hard_max = max(target_chars, int(settings.get("subtitle_common_split_hard_max_chars", 24) or 24))
    max_cps = max(0.0, float(settings.get("sub_max_cps", 12.0) or 12.0))
    duration_weighted_score = 0.0
    duration_total = 0.0
    line_total = 0
    max_line_char_total = 0
    cps_total = 0.0
    two_line_segments = 0
    over_two_line_segments = 0
    hard_overflow_segments = 0
    orphan_line_segments = 0
    balanced_two_line_segments = 0
    packaging_changed_segments = 0

    for row in usable_rows:
        line_lengths = _readability_line_lengths(row.get("text"))
        if not line_lengths:
            continue
        line_count = len(line_lengths)
        total_chars = sum(line_lengths)
        max_line_chars = max(line_lengths)
        cps = total_chars / _segment_duration(row)
        target_lines = _readability_target_line_count(total_chars, settings)

        line_count_score = _readability_line_count_score(line_count, target_lines, max_line_chars, hard_max)
        line_length_score = _readability_line_length_score(line_lengths, target_chars=target_chars, hard_max=hard_max)
        balance_score = _readability_balance_score(line_lengths, target_lines)
        orphan_score = _readability_orphan_score(line_lengths, total_chars)
        cps_score = _readability_cps_score(cps, max_cps)

        segment_score = (
            line_count_score * 0.24
            + line_length_score * 0.28
            + balance_score * 0.18
            + orphan_score * 0.18
            + cps_score * 0.12
        )
        duration = _segment_duration(row)
        duration_weighted_score += segment_score * duration
        duration_total += duration
        line_total += line_count
        max_line_char_total += max_line_chars
        cps_total += cps
        if line_count == 2:
            two_line_segments += 1
            longest = max(line_lengths)
            shortest = min(line_lengths)
            if longest > 0 and shortest / longest >= 0.72:
                balanced_two_line_segments += 1
        elif line_count > 2:
            over_two_line_segments += 1
        if max_line_chars > hard_max:
            hard_overflow_segments += 1
        if line_count >= 2 and total_chars >= 10 and min(line_lengths) <= 4:
            orphan_line_segments += 1
        if row.get("_lora_packaging_policy"):
            packaging_changed_segments += 1

    avg_segment_readability = duration_weighted_score / max(0.001, duration_total)
    segment_count = max(1, len(usable_rows))
    return {
        "readability_score": round(avg_segment_readability, 3),
        "avg_segment_readability": round(avg_segment_readability, 3),
        "avg_lines_per_segment": round(line_total / segment_count, 3),
        "avg_max_line_chars": round(max_line_char_total / segment_count, 3),
        "avg_cps": round(cps_total / segment_count, 3),
        "two_line_segments": two_line_segments,
        "over_two_line_segments": over_two_line_segments,
        "hard_overflow_segments": hard_overflow_segments,
        "orphan_line_segments": orphan_line_segments,
        "balanced_two_line_segments": balanced_two_line_segments,
        "packaging_changed_segments": packaging_changed_segments,
    }
