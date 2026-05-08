# Version: 03.01.25
# Phase: PHASE2
"""Non-destructive subtitle quality pipeline entry point."""

from __future__ import annotations

from typing import Any

from .candidate_generator import generate_quality_candidates
from .candidate_ranker import rank_quality_candidates
from .confidence_checker import evaluate_subtitle_confidence
from .hallucination_detector import annotate_segment_hallucination_risk
from .models import (
    QualityCandidate,
    QualityPipelineResult,
    SubtitleQualitySummary,
    attach_asr_metadata,
    metrics_to_dict,
    normalize_segment_quality,
)
from .recheck_engine import recheck_low_confidence_segments
from .vad_alignment_checker import annotate_segments_vad_alignment


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _duration(segment: dict[str, Any]) -> float:
    start = _as_float(segment.get("start"), 0.0)
    end = _as_float(segment.get("end"), start)
    return max(0.01, end - start)


def _summary_for_segments(
    segments: list[dict[str, Any]],
    *,
    warnings: tuple[str, ...] = (),
    before_score: float | None = None,
    after_score: float | None = None,
) -> SubtitleQualitySummary:
    if not segments:
        return SubtitleQualitySummary(warnings=warnings, before_score=before_score, after_score=after_score)

    counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0}
    weighted_score = 0.0
    total_duration = 0.0
    needs_review = 0
    auto_corrected = 0
    hallucination_risk = 0
    metadata_missing = 0

    for seg in segments:
        quality = dict(seg.get("quality") or {})
        label = str(quality.get("confidence_label") or "gray")
        if label not in counts:
            label = "gray"
        counts[label] += 1
        score = quality.get("confidence_score")
        duration = _duration(seg)
        if isinstance(score, (int, float)):
            weighted_score += float(score) * duration
            total_duration += duration
        flags = tuple(quality.get("flags") or ())
        if (
            label in ("red", "gray")
            or "non_speech_hallucination_risk" in flags
            or "high_no_speech_prob" in flags
            or "llm_uncertain_rewrite" in flags
        ):
            needs_review += 1
        if "auto_corrected" in flags:
            auto_corrected += 1
        if any(flag in flags for flag in ("non_speech_hallucination_risk", "known_hallucination_phrase", "high_no_speech_prob")):
            hallucination_risk += 1
        if "metadata_missing" in flags:
            metadata_missing += 1

    if total_duration <= 0.0:
        overall = None
    else:
        base = weighted_score / total_duration
        red_gray_ratio = (counts["red"] + counts["gray"]) / max(1, len(segments))
        halluc_ratio = hallucination_risk / max(1, len(segments))
        missing_ratio = metadata_missing / max(1, len(segments))
        penalty = red_gray_ratio * 8.0 + halluc_ratio * 10.0 + missing_ratio * 8.0
        overall = round(max(0.0, min(100.0, base - penalty)), 6)

    return SubtitleQualitySummary(
        overall_score=overall,
        green_count=counts["green"],
        yellow_count=counts["yellow"],
        red_count=counts["red"],
        gray_count=counts["gray"],
        needs_review_count=needs_review,
        auto_corrected_count=auto_corrected,
        before_score=before_score,
        after_score=after_score,
        warnings=warnings,
    )


def _quality_score(segment: dict[str, Any]) -> float | None:
    score = dict(segment.get("quality") or {}).get("confidence_score")
    if isinstance(score, (int, float)):
        return float(score)
    return None


def _recalculate_segments(
    segments: list[dict[str, Any]],
    *,
    vad_segments: list[dict[str, Any]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    recalculated: list[dict[str, Any]] = []
    previous_texts: list[str] = []
    prepared = [attach_asr_metadata(dict(segment)) for segment in segments]
    if vad_segments:
        prepared = annotate_segments_vad_alignment(prepared, vad_segments)
    for item in prepared:
        item = annotate_segment_hallucination_risk(item, vad_segments=vad_segments, previous_texts=previous_texts)
        metrics = evaluate_subtitle_confidence(
            item,
            vad_segments=vad_segments,
            settings=settings,
            previous_texts=previous_texts,
        )
        item["quality"] = metrics_to_dict(metrics)
        history = list(item.get("quality_history") or [])
        if history:
            item["quality_history"] = history
        recalculated.append(normalize_segment_quality(item))
        previous_texts.append(str(item.get("text", "") or ""))
    return recalculated


def _candidate_to_model(candidate: dict[str, Any]) -> QualityCandidate:
    segment = dict(candidate.get("segment") or candidate)
    return QualityCandidate(
        candidate_id=str(candidate.get("candidate_id") or ""),
        segment_index=int(candidate.get("segment_index", segment.get("line", 0)) or 0),
        text=str(segment.get("text", candidate.get("text", "")) or ""),
        start=_as_float(segment.get("start", candidate.get("start", 0.0))),
        end=_as_float(segment.get("end", candidate.get("end", 0.0))),
        source=str(candidate.get("source", "existing") or "existing"),
        score=_as_float(candidate.get("score")) if candidate.get("score") is not None else None,
        reason=str(candidate.get("reason", "") or ""),
        safe_to_apply=bool(candidate.get("safe_to_apply", False)),
        metadata=dict(candidate.get("metadata") or {}),
    )


def _candidate_payload(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in candidates:
        segment = dict(item.get("segment") or item)
        payload.append(
            {
                "candidate_id": str(item.get("candidate_id") or ""),
                "source": str(item.get("source", "") or ""),
                "text": str(segment.get("text", item.get("text", "")) or ""),
                "score": item.get("score"),
                "reason": str(item.get("reason", "") or ""),
                "safe_to_apply": bool(item.get("safe_to_apply", False)),
                "safety_reason": str(item.get("safety_reason", "") or ""),
                "metadata": dict(item.get("metadata") or {}),
            }
        )
    return payload


def run_subtitle_quality_pipeline(
    segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    auto_correct: bool = False,
    context: dict[str, Any] | None = None,
) -> QualityPipelineResult:
    settings = dict(settings or {})
    context = dict(context or {})
    vad_segments = list(vad_segments or [])
    normalized = _recalculate_segments(list(segments or []), vad_segments=vad_segments, settings=settings)
    before_summary = _summary_for_segments(normalized)
    all_candidates: list[dict[str, Any]] = []

    warning_list: list[str] = []
    if settings and not (
        settings.get("subtitle_quality_enabled")
        or settings.get("subtitle_quality_auto_check_after_generate")
        or settings.get("subtitle_quality_auto_correct_enabled")
    ):
        warning_list.append("quality_settings_off_manual_pipeline")

    if auto_correct:
        threshold = _as_float(settings.get("review_auto_correct_apply_threshold"), 92.0)
        min_improvement = _as_float(settings.get("review_auto_correct_min_improvement"), 10.0)
        buffer_sec = _as_float(settings.get("review_recheck_buffer_sec"), 1.2)
        targets = recheck_low_confidence_segments(
            normalized,
            buffer_sec=buffer_sec,
            clip_boundaries=list(context.get("clip_boundaries") or []),
        )
        target_lines = {
            int(item["segment_index"] if item.get("segment_index") is not None else item.get("line", -1))
            for item in targets
        }
        next_segments: list[dict[str, Any]] = []
        for index, segment in enumerate(normalized):
            line = int(segment.get("line", index) if segment.get("line") is not None else index)
            if line not in target_lines:
                next_segments.append(segment)
                continue
            generated = generate_quality_candidates(segment, settings=settings, context=context)
            original_score = _quality_score(segment)
            ranked = rank_quality_candidates(
                generated,
                original_segment=segment,
                original_score=original_score,
                apply_threshold=threshold,
                min_improvement=min_improvement,
            )
            for candidate in ranked:
                candidate["segment_index"] = line
                all_candidates.append(candidate)
            best = next((item for item in ranked if item.get("safe_to_apply") and str(item.get("candidate_id")) != "existing"), None)
            if best is None:
                item = dict(segment)
                item["quality_candidates"] = _candidate_payload(ranked)
                next_segments.append(item)
                continue
            candidate_segment = dict(best.get("segment") or {})
            old_quality = dict(segment.get("quality") or {})
            history = list(segment.get("quality_history") or [])
            if old_quality:
                history.append(old_quality)
            quality = dict(candidate_segment.get("quality") or old_quality)
            flags = list(quality.get("flags") or [])
            if "auto_corrected" not in flags:
                flags.append("auto_corrected")
            quality["flags"] = flags
            quality["auto_corrected_from"] = str(segment.get("text", "") or "")
            quality["auto_corrected_reason"] = str(best.get("reason", "") or "")
            candidate_segment["quality"] = quality
            candidate_segment["quality_history"] = history
            candidate_segment["quality_candidates"] = _candidate_payload(ranked)
            next_segments.append(candidate_segment)
        normalized = _recalculate_segments(next_segments, vad_segments=vad_segments, settings=settings)
        # Preserve candidate/history metadata after recalculation.
        for dst, src in zip(normalized, next_segments):
            if src.get("quality_history"):
                dst["quality_history"] = src.get("quality_history")
            if src.get("quality_candidates"):
                dst["quality_candidates"] = src.get("quality_candidates")
            if "auto_corrected_from" in dict(src.get("quality") or {}):
                q = dict(dst.get("quality") or {})
                old_q = dict(src.get("quality") or {})
                flags = list(q.get("flags") or [])
                if "auto_corrected" not in flags:
                    flags.append("auto_corrected")
                q["flags"] = flags
                q["auto_corrected_from"] = old_q.get("auto_corrected_from")
                q["auto_corrected_reason"] = old_q.get("auto_corrected_reason", "")
                dst["quality"] = q
    warnings = tuple(warning_list)
    before_score = before_summary.overall_score
    after_score = _summary_for_segments(normalized).overall_score
    if context:
        if context.get("before_score") is not None:
            before_score = _as_float(context.get("before_score"))
        if context.get("after_score") is not None:
            after_score = _as_float(context.get("after_score"))

    return QualityPipelineResult(
        segments=tuple(normalized),
        summary=_summary_for_segments(normalized, warnings=warnings, before_score=before_score, after_score=after_score),
        candidates=tuple(_candidate_to_model(item) for item in all_candidates),
        warnings=warnings,
    )
