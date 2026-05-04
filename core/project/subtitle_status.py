"""Shared subtitle status helpers for UI and project persistence."""
from __future__ import annotations

from typing import Any

from core.runtime import config

SUBTITLE_STATUS_COLORS = {
    "confirmed": "#34C759",
    "pending": "#FFCC00",
    "recheck": "#FF453A",
    "conflict": "#8E8E93",
}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_score_100(value: float | None) -> float | None:
    if value is None:
        return None
    score = float(value)
    if 0.0 <= score <= 1.0:
        score *= 100.0
    return max(0.0, min(100.0, score))


def _selected_stt_source(seg: dict) -> str:
    for key in ("stt_selected_source", "stt_ensemble_llm_selected_source", "stt_ensemble_source"):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    candidates = list(seg.get("stt_candidates") or [])
    if len(candidates) == 1:
        source = str(candidates[0].get("source", "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    return ""


def _stt_source_for_segment(seg: dict) -> str:
    for key in ("stt_preview_source", "stt_source", "stt_ensemble_source"):
        source = str(seg.get(key, "") or "").strip().upper()
        if source in {"STT1", "STT2"}:
            return source
    return ""


def subtitle_detection_score(seg: dict, source: str = "") -> float | None:
    quality = dict(seg.get("quality") or {})
    score = _as_float(quality.get("confidence_score"))
    if score is not None:
        return max(0.0, min(100.0, score))

    target_source = str(source or _selected_stt_source(seg) or _stt_source_for_segment(seg)).strip().upper()
    for candidate in list(seg.get("stt_candidates") or []):
        cand_source = str(candidate.get("source", "") or "").strip().upper()
        if target_source and cand_source != target_source:
            continue
        score = _as_float(candidate.get("stt_score", candidate.get("score")))
        if score is not None:
            return _normalize_score_100(score)

    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        score = _as_float(seg.get(key))
        if score is not None:
            return _normalize_score_100(score)

    similarity = _as_float(seg.get("stt_ensemble_similarity"))
    if similarity is not None:
        return _normalize_score_100(similarity)
    return None


def _stt_candidate_scores(seg: dict) -> list[float]:
    scores: list[float] = []
    for candidate in list(seg.get("stt_candidates") or []):
        if str(candidate.get("source", "") or "").strip().upper() not in {"STT1", "STT2"}:
            continue
        score = _as_float(candidate.get("stt_score", candidate.get("score")))
        if score is not None:
            normalized = _normalize_score_100(score)
            if normalized is not None:
                scores.append(normalized)
    return scores


def recheck_threshold() -> float:
    try:
        from core.settings import load_settings

        settings = load_settings() or {}
        value = settings.get(
            "stt_low_score_recheck_threshold",
            config.DEFAULT_ADV_SETTINGS.get("stt_low_score_recheck_threshold", 60),
        )
        return float(value or 60)
    except Exception:
        return 60.0


def subtitle_review_state(seg: dict, *, threshold: float | None = None) -> str:
    """Return one of confirmed, pending, recheck, conflict."""
    quality = dict(seg.get("quality") or {})
    flags = {str(flag) for flag in (quality.get("flags") or ())}
    if bool(quality.get("manual_confirmed")) or "manual_confirmed" in flags:
        return "confirmed"

    threshold = recheck_threshold() if threshold is None else float(threshold)
    selected_source = _selected_stt_source(seg)
    score = subtitle_detection_score(seg, selected_source)
    candidate_scores = _stt_candidate_scores(seg)
    label = str(quality.get("confidence_label") or "").strip().lower()

    if score is not None and score < threshold:
        return "recheck"
    if not selected_source and candidate_scores and max(candidate_scores) < threshold:
        return "recheck"
    if label == "red":
        return "recheck"

    candidates = [
        item for item in list(seg.get("stt_candidates") or [])
        if str(item.get("source", "") or "").strip().upper() in {"STT1", "STT2"}
    ]
    if (
        selected_source not in {"STT1", "STT2"}
        and (
            bool(seg.get("stt_ensemble_needs_llm_review"))
            or len(candidates) >= 2
            or label == "gray"
        )
    ):
        return "conflict"

    return "pending"


def subtitle_status_payload(seg: dict) -> dict[str, Any]:
    state = subtitle_review_state(seg)
    selected_source = _selected_stt_source(seg)
    return {
        "subtitle_review_state": state,
        "subtitle_status_color": SUBTITLE_STATUS_COLORS.get(state, ""),
        "subtitle_status_schema": "subtitle_status.v1",
        "subtitle_status_score": subtitle_detection_score(seg, selected_source),
        "subtitle_status_source": selected_source,
    }


__all__ = [
    "SUBTITLE_STATUS_COLORS",
    "subtitle_detection_score",
    "subtitle_review_state",
    "subtitle_status_payload",
]
