# Version: 03.01.22
# Phase: PHASE2
"""Non-destructive hallucination risk helpers."""

from __future__ import annotations

import difflib
import re
from typing import Any

from core.subtitle_quality.vad_alignment_checker import vad_overlap_ratio

HALLUCINATION_PHRASES: tuple[str, ...] = (
    "한국어 대화",
    "자막 생성",
    "번역 중",
    "처리 중",
    "대화 내용",
    "Korean conversation",
    "subtitle",
    "transcription",
    "Thank you for watching",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _append_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def repeated_text_risk(text: str, previous_texts: list[str] | tuple[str, ...] | None = None) -> bool:
    compact = _compact_text(text)
    if len(compact) < 5:
        return False
    for prev in reversed(list(previous_texts or ())[-40:]):
        prev_compact = _compact_text(prev)
        if len(prev_compact) < 5:
            continue
        if compact in prev_compact or prev_compact in compact:
            return True
        match = difflib.SequenceMatcher(None, prev_compact, compact).find_longest_match(
            0, len(prev_compact), 0, len(compact)
        )
        if match.size >= 8 and (match.size / max(1, len(compact))) >= 0.7:
            return True
    return False


def estimate_hallucination_risk(
    segment: dict[str, Any],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    previous_texts: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    metadata = dict(segment.get("asr_metadata") or {})
    no_speech = metadata.get("no_speech_prob")
    avg_logprob = metadata.get("avg_logprob")
    risk = 0.0
    flags: list[str] = []
    if isinstance(no_speech, (int, float)) and no_speech >= 0.6:
        risk += 0.45
        _append_flag(flags, "high_no_speech_prob")
    if isinstance(avg_logprob, (int, float)) and avg_logprob <= -1.0:
        risk += 0.25
        _append_flag(flags, "low_avg_logprob")
    text = str(segment.get("text", "") or "").strip()
    duration = _as_float(segment.get("end"), 0.0) - _as_float(segment.get("start"), 0.0)
    if duration > 0 and len(text.replace(" ", "")) / max(duration, 0.01) > 18:
        risk += 0.2
        _append_flag(flags, "high_cps")
    if duration > 0 and duration < 0.8 and len(text.replace(" ", "")) > 10:
        risk += 0.25
        _append_flag(flags, "short_duration_long_text")
    lowered = text.lower()
    for phrase in HALLUCINATION_PHRASES:
        if phrase.lower() in lowered:
            risk += 0.45
            _append_flag(flags, "known_hallucination_phrase")
            break
    ratio = vad_overlap_ratio(segment, vad_segments or ())
    if ratio is not None and ratio < 0.2:
        risk += 0.35
        _append_flag(flags, "non_speech_hallucination_risk")
    if repeated_text_risk(text, previous_texts):
        risk += 0.3
        _append_flag(flags, "repeated_phrase_risk")
    return {"risk": round(max(0.0, min(1.0, risk)), 6), "flags": tuple(flags)}


def annotate_segment_hallucination_risk(
    segment: dict[str, Any],
    *,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    previous_texts: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    out = dict(segment or {})
    result = estimate_hallucination_risk(out, vad_segments=vad_segments, previous_texts=previous_texts)
    quality = dict(out.get("quality") or {})
    flags = list(quality.get("flags") or ())
    for flag in result.get("flags") or ():
        _append_flag(flags, str(flag))
    quality["hallucination_penalty"] = round(float(result.get("risk", 0.0) or 0.0) * 100.0, 3)
    if flags:
        quality["flags"] = tuple(flags)
    out["quality"] = quality
    asr_metadata = dict(out.get("asr_metadata") or {})
    asr_metadata["hallucination_risk"] = result
    out["asr_metadata"] = asr_metadata
    return out
