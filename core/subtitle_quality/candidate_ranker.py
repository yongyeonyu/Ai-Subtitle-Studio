# Version: 03.01.25
# Phase: PHASE2
"""Candidate ranking surface for subtitle quality review."""

from __future__ import annotations

import re
from typing import Any

from core.engine.llm_correction_guard import validate_llm_chunks
from core.subtitle_quality.hallucination_detector import estimate_hallucination_risk
from core.subtitle_quality.vad_alignment_checker import annotate_segments_vad_alignment, vad_overlap_ratio


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metadata_score(segment: dict[str, Any]) -> float:
    metadata = dict(segment.get("asr_metadata") or {})
    score = 70.0
    no_speech = metadata.get("no_speech_prob")
    avg_logprob = metadata.get("avg_logprob")
    compression = metadata.get("compression_ratio")
    word_conf = metadata.get("word_confidence")
    if isinstance(word_conf, (int, float)):
        score += (float(word_conf) - 0.5) * 35.0
    if isinstance(no_speech, (int, float)):
        score -= max(0.0, float(no_speech) - 0.2) * 45.0
    if isinstance(avg_logprob, (int, float)):
        score += max(-30.0, min(12.0, (float(avg_logprob) + 1.0) * 18.0))
    if isinstance(compression, (int, float)) and float(compression) > 2.4:
        score -= min(25.0, (float(compression) - 2.4) * 18.0)
    return score


def _precomputed_vad_ratio(segment: dict[str, Any]) -> float | None:
    metadata = dict(segment.get("asr_metadata") or {})
    vad = dict(metadata.get("vad_alignment") or {})
    value = vad.get("vad_overlap_ratio")
    if value is None:
        quality = dict(segment.get("quality") or {})
        score = quality.get("vad_alignment_score")
        if score is not None:
            value = _as_float(score) / 100.0
    if value is None:
        return None
    return max(0.0, min(1.0, _as_float(value)))


def score_quality_candidate(
    candidate: dict[str, Any],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    previous_end: float | None = None,
) -> float:
    segment = dict(candidate.get("segment") or candidate)
    score = _metadata_score(segment)
    ratio = _precomputed_vad_ratio(segment)
    if ratio is None:
        ratio = vad_overlap_ratio(segment, vad_segments or ())
    if ratio is not None:
        score += (float(ratio) - 0.5) * 30.0
    risk = estimate_hallucination_risk(segment, vad_segments=vad_segments or ()).get("risk", 0.0)
    score -= float(risk or 0.0) * 40.0

    words = segment.get("words") or []
    if words:
        score += min(8.0, len(words) * 0.6)

    if previous_end is not None:
        start = _as_float(segment.get("start"), 0.0)
        end = _as_float(segment.get("end"), start)
        overlap = max(0.0, min(end, float(previous_end)) - start)
        duration = max(0.01, end - start)
        score -= min(30.0, (overlap / duration) * 35.0)

    score += _as_float(candidate.get("score_bonus"), 0.0)
    return round(max(0.0, min(100.0, score)), 6)


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:[,.]\d+)?", str(text or ""))


def is_candidate_safe_to_apply(
    candidate: dict[str, Any],
    *,
    original_segment: dict[str, Any] | None = None,
    original_score: float | None = None,
    apply_threshold: float = 92.0,
    min_improvement: float = 10.0,
) -> tuple[bool, str]:
    score = _as_float(candidate.get("score"), 0.0)
    if score < float(apply_threshold or 0.0):
        return False, "below_apply_threshold"
    if original_score is not None and score - float(original_score or 0.0) < float(min_improvement or 0.0):
        return False, "insufficient_improvement"
    segment = dict(candidate.get("segment") or candidate)
    source_text = str((original_segment or {}).get("text", "") or "")
    candidate_text = str(segment.get("text", candidate.get("text", "")) or "")
    if not candidate_text.strip():
        return False, "empty_candidate"
    if _numbers(source_text) != _numbers(candidate_text):
        return False, "number_changed"
    if source_text and candidate_text != source_text:
        ok, reason = validate_llm_chunks(source_text, [candidate_text])
        if not ok:
            return False, f"guard_failed:{reason}"
    return True, "safe"


def rank_overlap_candidates(
    candidates: list[dict[str, Any]],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    previous_end: float | None = None,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    clean_candidates = [dict(candidate) for candidate in candidates or () if isinstance(candidate, dict)]
    segments = [dict(candidate.get("segment") or candidate) for candidate in clean_candidates]
    annotated_segments = (
        annotate_segments_vad_alignment(segments, vad_segments or ())
        if vad_segments and segments
        else segments
    )
    for candidate, segment in zip(clean_candidates, annotated_segments):
        item = dict(candidate)
        if "segment" in item:
            item["segment"] = segment
        else:
            item.update(segment)
        item["score"] = score_quality_candidate(item, vad_segments=vad_segments, previous_end=previous_end)
        ranked.append(item)
    return sorted(ranked, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)


def rank_quality_candidates(
    candidates: list[dict[str, Any]],
    *,
    original_segment: dict[str, Any] | None = None,
    original_score: float | None = None,
    apply_threshold: float = 92.0,
    min_improvement: float = 10.0,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        if item.get("score") is None:
            item["score"] = score_quality_candidate(item)
        safe, reason = is_candidate_safe_to_apply(
            item,
            original_segment=original_segment,
            original_score=original_score,
            apply_threshold=apply_threshold,
            min_improvement=min_improvement,
        )
        item["safe_to_apply"] = safe
        item["safety_reason"] = reason
        enriched.append(item)
    return sorted(enriched, key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)


__all__ = [
    "is_candidate_safe_to_apply",
    "rank_overlap_candidates",
    "rank_quality_candidates",
    "score_quality_candidate",
]
