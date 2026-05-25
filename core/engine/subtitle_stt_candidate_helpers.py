# Version: 03.14.29
# Phase: PHASE2
"""STT candidate scoring helpers shared by subtitle generation guards."""

from __future__ import annotations

import difflib
import re


def _stt_candidate_compact_text(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""), flags=re.UNICODE).lower()


def _stt_candidate_similarity(left: str, right: str) -> float:
    ltxt = _stt_candidate_compact_text(left)
    rtxt = _stt_candidate_compact_text(right)
    if not ltxt and not rtxt:
        return 1.0
    if not ltxt or not rtxt:
        return 0.0
    return difflib.SequenceMatcher(None, ltxt, rtxt).ratio()


def _stt_candidate_score100(candidate: dict | None) -> float:
    candidate = candidate or {}
    for key in ("stt_score", "score", "confidence", "probability", "avg_confidence"):
        if candidate.get(key) is None:
            continue
        try:
            value = float(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if value <= 1.0:
            value *= 100.0
        return max(0.0, min(100.0, value))
    return 0.0


def _selected_decision_word_span(decision: dict | None) -> tuple[float, float] | None:
    words = [word for word in list((decision or {}).get("words") or []) if isinstance(word, dict)]
    if not words:
        return None
    starts = []
    ends = []
    for word in words:
        try:
            starts.append(float(word.get("start")))
            ends.append(float(word.get("end")))
        except (TypeError, ValueError):
            continue
    if not starts or not ends:
        return None
    start = min(starts)
    end = max(ends)
    if end <= start:
        return None
    return start, end


def _looks_like_relative_word_span(word_span: tuple[float, float], selected_span: tuple[float, float] | None) -> bool:
    if selected_span is None:
        return False
    selected_start, selected_end = selected_span
    duration = max(0.05, selected_end - selected_start)
    word_start, word_end = word_span
    return bool(
        selected_start > 5.0
        and word_start < 2.0
        and word_end <= max(2.0, duration + 1.0)
        and abs(word_start - selected_start) > 2.0
    )


def _candidate_span_from_decision(decision: dict | None) -> tuple[float, float] | None:
    try:
        start = float((decision or {}).get("start"))
        end = float((decision or {}).get("end"))
    except (TypeError, ValueError):
        return None
    return (start, end) if end > start else None


def _stt_decision_timing_span(decision: dict | None) -> tuple[float, float] | None:
    selected_span = _candidate_span_from_decision(decision)
    word_span = _selected_decision_word_span(decision)
    if word_span is None or _looks_like_relative_word_span(word_span, selected_span):
        return selected_span
    if selected_span is None:
        return word_span
    selected_start, selected_end = selected_span
    word_start, word_end = word_span
    overlap = max(0.0, min(selected_end, word_end) - max(selected_start, word_start))
    word_dur = max(0.001, word_end - word_start)
    selected_dur = max(0.001, selected_end - selected_start)
    overlap_ratio = overlap / min(word_dur, selected_dur)
    if overlap_ratio < 0.25 and max(abs(word_start - selected_start), abs(word_end - selected_end)) > 0.35:
        return word_span
    return selected_span




def _stt_selection_metadata(seg: dict) -> dict:
    keys = (
        "stt_candidates",
        "stt_ensemble_source",
        "stt_ensemble_similarity",
        "stt_ensemble_needs_llm_review",
        "stt_ensemble_inserted_from_stt2",
        "stt_ensemble_primary_region",
        "stt_ensemble_primary_locked",
        "stt_ensemble_word_rover",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_llm_selected_label",
        "stt_ensemble_deep_selected_source",
        "stt_ensemble_deep_selected_label",
        "stt_ensemble_deep_selected_score",
        "stt_ensemble_deep_selected_margin",
        "stt_selected_source",
        "score",
        "stt_score",
        "score_color",
        "stt_score_color",
        "stt_score_label",
        "stt_score_flags",
        "stt_score_components",
        "speaker_list",
        "speaker2",
        "_stt_speaker_marker_preserved",
        "_stt_original_candidate_start",
        "_stt_original_candidate_end",
        "_stt_original_candidate_start_frame",
        "_stt_original_candidate_end_frame",
        "_stt_candidate_word_timing_anchor_policy",
        "_stt_word_match_timing_policy",
        "_llm_stt_text_guard_policy",
        "_stt_no_llm_raw_candidate_policy",
        "_stt_no_llm_raw_text",
        "original_start",
        "original_end",
        "_stt_lattice_policy",
        "_deep_candidate_selector_policy",
        "_llm_gate_policy",
        "_uncertainty_policy",
        "_uncertainty_bucket",
        "_uncertainty_risk_score",
        "_codex_native_fast_path_policy",
    )
    return {key: seg[key] for key in keys if key in seg}
