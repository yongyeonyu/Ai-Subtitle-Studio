from __future__ import annotations

"""Deterministic STT lattice helpers kept separate from artifact persistence."""

from dataclasses import dataclass
from typing import Any, Callable

from core.coerce import safe_float as _safe_float
from core.native_stt_lattice import best_word_match as _native_best_word_match


@dataclass(frozen=True)
class STTLatticeThresholds:
    min_match_score: float
    replace_margin: float
    min_confidence: float


def lattice_selection_thresholds(settings: dict[str, Any] | None = None) -> STTLatticeThresholds:
    settings = dict(settings or {})
    return STTLatticeThresholds(
        min_match_score=max(0.1, min(0.95, _safe_float(settings.get("stt_lattice_min_match_score"), 0.42))),
        replace_margin=max(0.0, min(0.75, _safe_float(settings.get("stt_lattice_replace_margin"), 0.14))),
        min_confidence=max(0.0, min(1.0, _safe_float(settings.get("stt_lattice_min_confidence"), 0.62))),
    )


def candidate_score_100(
    candidate: dict[str, Any],
    *,
    score_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> float:
    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        if candidate.get(key) is None:
            continue
        score = _safe_float(candidate.get(key), 0.0)
        if score <= 1.0:
            score *= 100.0
        return max(0.0, min(100.0, score))
    return float(score_fn(candidate).get("score", 0.0) or 0.0)


def word_time_score(left: dict[str, Any], right: dict[str, Any]) -> float:
    start = max(_safe_float(left.get("start")), _safe_float(right.get("start")))
    end = min(_safe_float(left.get("end")), _safe_float(right.get("end")))
    overlap = max(0.0, end - start)
    span = max(
        _safe_float(left.get("end")) - _safe_float(left.get("start")),
        _safe_float(right.get("end")) - _safe_float(right.get("start")),
        0.05,
    )
    overlap_score = overlap / span
    left_mid = (_safe_float(left.get("start")) + _safe_float(left.get("end"))) / 2.0
    right_mid = (_safe_float(right.get("start")) + _safe_float(right.get("end"))) / 2.0
    midpoint_score = max(0.0, 1.0 - abs(left_mid - right_mid) / 0.75)
    return max(overlap_score, midpoint_score * 0.75)


def find_best_word_match(
    anchor: dict[str, Any],
    words: list[dict[str, Any]],
    used: set[int],
    *,
    min_match_score: float,
    similarity_scores: list[float],
) -> tuple[int | None, float]:
    native = _native_best_word_match(
        anchor_start=_safe_float(anchor.get("start"), 0.0),
        anchor_end=_safe_float(anchor.get("end"), 0.0),
        word_starts=[_safe_float(word.get("start"), 0.0) for word in list(words or [])],
        word_ends=[_safe_float(word.get("end"), 0.0) for word in list(words or [])],
        textual_scores=[float(score or 0.0) for score in list(similarity_scores or [])],
        used_indices=used,
        min_match_score=float(min_match_score),
    )
    if native is not None:
        index, score = native
        if index is None:
            return None, float(score or 0.0)
        return int(index), float(score or 0.0)

    best_idx = None
    best_score = 0.0
    for idx, word in enumerate(words):
        if idx in used:
            continue
        temporal = word_time_score(anchor, word)
        textual = float(similarity_scores[idx] or 0.0) if idx < len(similarity_scores) else 0.0
        score = temporal * 0.62 + textual * 0.38
        if score > best_score:
            best_idx = idx
            best_score = score
    if best_score < min_match_score:
        return None, best_score
    return best_idx, best_score


__all__ = [
    "STTLatticeThresholds",
    "candidate_score_100",
    "find_best_word_match",
    "lattice_selection_thresholds",
    "word_time_score",
]
