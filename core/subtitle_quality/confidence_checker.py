# Version: 03.01.24
# Phase: PHASE2
"""Segment-level subtitle confidence scoring."""

from __future__ import annotations

import difflib
import re
from typing import Any

from .models import SubtitleQualityMetrics
from .hallucination_detector import estimate_hallucination_risk

_TIMECODE_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{1,3})?")


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _duration(segment: dict[str, Any]) -> float:
    start = _as_float(segment.get("start"), 0.0) or 0.0
    end = _as_float(segment.get("end"), start) or start
    return max(0.0, end - start)


def _compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


def _label_for_score(score: float | None) -> str:
    if score is None:
        return "gray"
    if score >= 85:
        return "green"
    if score >= 65:
        return "yellow"
    if score >= 35:
        return "red"
    return "gray"


def _clip_score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 6)


def _add_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _asr_metadata_score(metadata: dict[str, Any], flags: list[str]) -> float:
    if not metadata:
        _add_flag(flags, "metadata_missing")
        return 30.0

    score = 78.0
    no_speech = _as_float(metadata.get("no_speech_prob"))
    avg_logprob = _as_float(metadata.get("avg_logprob"))
    compression = _as_float(metadata.get("compression_ratio"))
    word_conf = _as_float(metadata.get("word_confidence"))
    language_probability = _as_float(metadata.get("language_probability"))

    if no_speech is None:
        _add_flag(flags, "no_speech_prob_missing")
    else:
        score -= max(0.0, no_speech - 0.2) * 55.0
        if no_speech >= 0.6:
            _add_flag(flags, "high_no_speech_prob")

    if avg_logprob is None:
        _add_flag(flags, "avg_logprob_missing")
    else:
        score += max(-22.0, min(12.0, (avg_logprob + 0.8) * 18.0))
        if avg_logprob <= -1.0:
            _add_flag(flags, "low_avg_logprob")

    if compression is not None and compression > 2.4:
        score -= min(24.0, (compression - 2.4) * 18.0)
        _add_flag(flags, "high_compression_ratio")

    if word_conf is not None:
        score += (word_conf - 0.5) * 24.0
        if word_conf < 0.45:
            _add_flag(flags, "low_word_confidence")

    if language_probability is not None and language_probability < 0.45:
        score -= 12.0
        _add_flag(flags, "low_language_probability")

    return _clip_score(score)


def _vad_score(segment: dict[str, Any], flags: list[str]) -> float | None:
    quality = dict(segment.get("quality") or {})
    score = _as_float(quality.get("vad_alignment_score"))
    if score is not None:
        if score < 20:
            _add_flag(flags, "outside_vad_speech")
        return _clip_score(score)
    metadata = dict(segment.get("asr_metadata") or {})
    vad = dict(metadata.get("vad_alignment") or {})
    ratio = _as_float(vad.get("vad_overlap_ratio"))
    if ratio is None:
        return None
    score = ratio * 100.0
    if score < 20:
        _add_flag(flags, "outside_vad_speech")
    return _clip_score(score)


def _word_timestamp_score(segment: dict[str, Any], flags: list[str]) -> float:
    words = [dict(item) for item in (segment.get("words") or []) if isinstance(item, dict)]
    if not words:
        metadata_words = (dict(segment.get("asr_metadata") or {}).get("words") or [])
        words = [dict(item) for item in metadata_words if isinstance(item, dict)]
    if not words:
        _add_flag(flags, "word_timestamps_missing")
        return 35.0

    valid = 0
    monotonic = 0
    previous_end: float | None = None
    for word in words:
        start = _as_float(word.get("start"))
        end = _as_float(word.get("end"))
        if start is None or end is None or end <= start:
            continue
        valid += 1
        if previous_end is None or start >= previous_end - 0.03:
            monotonic += 1
        previous_end = end

    valid_ratio = valid / max(1, len(words))
    monotonic_ratio = monotonic / max(1, valid)
    score = (valid_ratio * 60.0) + (monotonic_ratio * 40.0)
    if valid_ratio < 0.8:
        _add_flag(flags, "word_timestamp_invalid")
    if monotonic_ratio < 0.9:
        _add_flag(flags, "word_timestamp_overlap")
    return _clip_score(score)


def _timing_score(segment: dict[str, Any], flags: list[str], settings: dict[str, Any]) -> float:
    duration = _duration(segment)
    text_len = len(_compact_text(segment.get("text")))
    if duration <= 0.0:
        _add_flag(flags, "invalid_timing")
        return 0.0

    min_duration = float(settings.get("sub_min_duration", 0.2) or 0.2)
    max_duration = float(settings.get("sub_max_duration", 6.0) or 6.0)
    max_cps = float(settings.get("sub_max_cps", 12) or 12)
    cps = text_len / max(duration, 0.01)
    score = 100.0
    if duration < min_duration:
        score -= min(50.0, (min_duration - duration) * 120.0)
        _add_flag(flags, "too_short_duration")
    if duration > max_duration:
        score -= min(45.0, (duration - max_duration) * 8.0)
        _add_flag(flags, "too_long_duration")
    if cps > max_cps:
        score -= min(55.0, (cps - max_cps) * 5.0)
        _add_flag(flags, "high_cps")
    if text_len == 0:
        score = 0.0
        _add_flag(flags, "empty_text")
    return _clip_score(score)


def _repetition_score(segment: dict[str, Any], previous_texts: list[str] | tuple[str, ...] | None, flags: list[str]) -> float:
    text = _compact_text(segment.get("text"))
    if len(text) < 5:
        return 80.0
    for previous in reversed(list(previous_texts or ())[-40:]):
        prev = _compact_text(previous)
        if len(prev) < 5:
            continue
        if text in prev or prev in text:
            _add_flag(flags, "repeated_phrase_risk")
            return 35.0
        match = difflib.SequenceMatcher(None, prev, text).find_longest_match(0, len(prev), 0, len(text))
        if match.size >= 8 and (match.size / max(1, len(text))) >= 0.7:
            _add_flag(flags, "repeated_phrase_risk")
            return 45.0
    return 100.0


def _context_score(segment: dict[str, Any], flags: list[str]) -> float:
    text = str(segment.get("text", "") or "").strip()
    if not text:
        _add_flag(flags, "empty_text")
        return 0.0
    score = 92.0
    if _TIMECODE_RE.search(text):
        score -= 50.0
        _add_flag(flags, "timecode_in_text")
    if not re.search(r"[가-힣a-zA-Z]", text):
        score -= 45.0
        _add_flag(flags, "text_has_no_language_chars")
    if len(text) <= 1:
        score -= 20.0
        _add_flag(flags, "very_short_text")
    return _clip_score(score)


def _memory_score(segment: dict[str, Any], flags: list[str]) -> float:
    quality = dict(segment.get("quality") or {})
    if "wrong_answer_memory_hit" in (quality.get("flags") or ()):
        _add_flag(flags, "wrong_answer_memory_hit")
        return 35.0
    return 75.0


def _apply_llm_rewrite_penalty(
    segment: dict[str, Any],
    score: float | None,
    flags: list[str],
) -> tuple[float | None, str | None]:
    policy = dict(segment.get("_llm_rewrite_policy") or {})
    if not policy.get("changed"):
        return score, None
    confidence = str(policy.get("confidence") or "").strip().lower()
    if confidence == "high":
        _add_flag(flags, "llm_confident_rewrite")
        return score, None

    _add_flag(flags, "llm_uncertain_rewrite")
    penalty = _as_float(policy.get("score_penalty"), 18.0) or 18.0
    adjusted = _clip_score((score if score is not None else 72.0) - penalty)
    return adjusted, confidence or "low"


def _weights(settings: dict[str, Any] | None) -> dict[str, float]:
    settings = settings or {}
    return {
        "asr_metadata_score": float(settings.get("score_weight_asr_metadata", 0.25) or 0.25),
        "vad_alignment_score": float(settings.get("score_weight_vad_alignment", 0.20) or 0.20),
        "word_timestamp_score": float(settings.get("score_weight_word_timestamp", 0.15) or 0.15),
        "timing_score": float(settings.get("score_weight_timing", 0.10) or 0.10),
        "repetition_score": float(settings.get("score_weight_repetition", 0.10) or 0.10),
        "context_score": float(settings.get("score_weight_context", 0.10) or 0.10),
        "correction_memory_score": float(settings.get("score_weight_memory", 0.05) or 0.05),
        "hallucination_penalty": float(settings.get("score_weight_hallucination_penalty", 0.30) or 0.30),
    }


def evaluate_subtitle_confidence(
    segment: dict[str, Any],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    settings: dict[str, Any] | None = None,
    previous_texts: list[str] | tuple[str, ...] | None = None,
) -> SubtitleQualityMetrics:
    metadata = dict(segment.get("asr_metadata") or {})
    settings = settings or {}
    flags = list((dict(segment.get("quality") or {}).get("flags") or ()))

    asr_score = _asr_metadata_score(metadata, flags)
    vad_score = _vad_score(segment, flags)
    word_score = _word_timestamp_score(segment, flags)
    timing_score = _timing_score(segment, flags, settings)
    repetition_score = _repetition_score(segment, previous_texts, flags)
    context_score = _context_score(segment, flags)
    memory_score = _memory_score(segment, flags)

    hallucination = dict(metadata.get("hallucination_risk") or {})
    if not hallucination:
        hallucination = estimate_hallucination_risk(segment, vad_segments=vad_segments or (), previous_texts=previous_texts or ())
    hallucination_penalty = _clip_score(float(hallucination.get("risk", 0.0) or 0.0) * 100.0)
    for flag in hallucination.get("flags") or ():
        _add_flag(flags, str(flag))

    weights = _weights(settings)
    components = {
        "asr_metadata_score": asr_score,
        "vad_alignment_score": vad_score,
        "word_timestamp_score": word_score,
        "timing_score": timing_score,
        "repetition_score": repetition_score,
        "context_score": context_score,
        "correction_memory_score": memory_score,
    }
    available = {
        key: value
        for key, value in components.items()
        if value is not None
    }
    if not available:
        score = None
    else:
        weight_sum = sum(max(0.0, weights[key]) for key in available)
        raw = sum(float(value) * max(0.0, weights[key]) for key, value in available.items()) / max(weight_sum, 0.001)
        score = _clip_score(raw - hallucination_penalty * max(0.0, weights["hallucination_penalty"]))

    score, rewrite_confidence = _apply_llm_rewrite_penalty(segment, score, flags)
    label = _label_for_score(score)
    if score is None or "metadata_missing" in flags and word_score <= 35.0:
        label = "gray"
    elif rewrite_confidence == "medium":
        score = _clip_score(min(float(score if score is not None else 72.0), 72.0))
        label = "yellow"
    elif rewrite_confidence == "low":
        score = _clip_score(min(float(score if score is not None else 58.0), 58.0))
        label = "red"
    reasons = [flag for flag in flags if flag]
    if not reasons:
        reasons = ["ok"]

    return SubtitleQualityMetrics(
        confidence_score=score,
        confidence_label=label,
        confidence_reason=", ".join(reasons[:4]),
        flags=tuple(flags),
        asr_metadata_score=asr_score,
        vad_alignment_score=vad_score,
        word_timestamp_score=word_score,
        timing_score=timing_score,
        repetition_score=repetition_score,
        context_score=context_score,
        correction_memory_score=memory_score,
        hallucination_penalty=hallucination_penalty,
    )
