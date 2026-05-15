from __future__ import annotations

import re
from typing import Any

from core.coerce import safe_float as _safe_float, safe_int as _safe_int
from core.native_text_similarity import edit_distance, similarity_ratio
from core.personalization.lora_models import line_break_pattern_for_text, stable_hash
from core.text_utils import clean_text as _clean_text, compact_text as _compact, line_count as _line_count


USER_EDIT_METRICS_SCHEMA = "ai_subtitle_studio.user_edit_metrics.v1"

_SOURCE_TEXT_KEYS = (
    "source_before_edit",
    "original_text",
    "dictated_text",
    "generated_text",
    "stt_text",
    "text_before_edit",
    "raw_text_before_edit",
)

_TIMING_KEY_PAIRS = (
    ("original_start", "original_end"),
    ("original_start_sec", "original_end_sec"),
    ("generated_start", "generated_end"),
    ("generated_start_sec", "generated_end_sec"),
    ("source_start", "source_end"),
    ("source_start_sec", "source_end_sec"),
    ("stt_start", "stt_end"),
    ("before_edit_start", "before_edit_end"),
    ("start_before_edit", "end_before_edit"),
    ("start_original", "end_original"),
)

def _punctuation_pattern(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch in ".,!?~…")


def _parenthetical_count(value: Any) -> int:
    return len(re.findall(r"\([^)]*\)|\[[^\]]*\]|【[^】]*】|（[^）]*）", str(value or "")))


def _levenshtein_distance(source: str, target: str) -> int:
    return edit_distance(source, target)


def source_text_for_edit_metrics(segment: dict[str, Any] | None) -> str:
    seg = dict(segment or {})
    for key in _SOURCE_TEXT_KEYS:
        text = _clean_text(seg.get(key))
        if text:
            return text
    snapshot = seg.get("stt_candidate_snapshot") if isinstance(seg.get("stt_candidate_snapshot"), dict) else {}
    if not snapshot:
        extra = seg.get("extra") if isinstance(seg.get("extra"), dict) else {}
        snapshot = extra.get("stt_candidate_snapshot") if isinstance(extra.get("stt_candidate_snapshot"), dict) else {}
    selected = str(snapshot.get("selected_source") or snapshot.get("llm_selected_source") or snapshot.get("ensemble_source") or "").strip().upper()
    candidates = [item for item in list(snapshot.get("candidates") or []) if isinstance(item, dict)]
    if selected:
        for candidate in candidates:
            if str(candidate.get("source") or "").strip().upper() == selected:
                text = _clean_text(candidate.get("text"))
                if text:
                    return text
    for candidate in candidates:
        text = _clean_text(candidate.get("text"))
        if text:
            return text
    for item in list(seg.get("stt_candidates") or [])[:8]:
        if isinstance(item, dict):
            text = _clean_text(item.get("text") or item.get("output"))
            if text:
                return text
    return ""


def _timing_reference(segment: dict[str, Any]) -> tuple[float | None, float | None, str]:
    for start_key, end_key in _TIMING_KEY_PAIRS:
        if segment.get(start_key) is None or segment.get(end_key) is None:
            continue
        start = _safe_float(segment.get(start_key), 0.0)
        end = _safe_float(segment.get(end_key), start)
        if end > start:
            return start, end, f"{start_key}/{end_key}"
    return None, None, ""


def _source_segment_count(segment: dict[str, Any]) -> int:
    for key in ("source_segment_count", "original_segment_count", "generated_segment_count", "stt_segment_count", "merged_segment_count"):
        value = _safe_int(segment.get(key), 0)
        if value > 0:
            return value
    for key in ("source_segment_ids", "_source_segment_ids", "merged_from_segments", "original_segment_ids"):
        value = segment.get(key)
        if isinstance(value, (list, tuple, set)) and value:
            return len(value)
    return 1


def measure_user_edit_metrics(
    segment: dict[str, Any] | None,
    *,
    final_text: str | None = None,
    final_speech_text: str | None = None,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> dict[str, Any]:
    seg = dict(segment or {})
    source_text = source_text_for_edit_metrics(seg)
    final_raw = str(final_text if final_text is not None else seg.get("text") or "")
    final_speech = str(final_speech_text if final_speech_text is not None else final_raw)
    source_compact = _compact(source_text)
    final_compact = _compact(final_speech)
    distance = _levenshtein_distance(source_compact, final_compact) if source_compact or final_compact else 0
    base_chars = max(1, len(source_compact), len(final_compact))
    edit_ratio = distance / base_chars
    similarity = similarity_ratio(source_compact, final_compact) if source_compact or final_compact else 1.0

    final_start = _safe_float(start_sec if start_sec is not None else seg.get("start"), 0.0)
    final_end = _safe_float(end_sec if end_sec is not None else seg.get("end"), final_start)
    ref_start, ref_end, ref_source = _timing_reference(seg)
    if ref_start is None or ref_end is None:
        start_shift = 0.0
        end_shift = 0.0
        duration_delta = 0.0
        move_distance = 0.0
    else:
        start_shift = final_start - ref_start
        end_shift = final_end - ref_end
        duration_delta = (final_end - final_start) - (ref_end - ref_start)
        move_distance = abs(start_shift) + abs(end_shift)

    source_lines = _line_count(source_text)
    final_lines = _line_count(final_raw)
    source_segments = _source_segment_count(seg)
    final_segments = max(1, _safe_int(seg.get("final_segment_count"), 1))
    source_line_pattern = line_break_pattern_for_text(source_text)
    final_line_pattern = line_break_pattern_for_text(final_speech)
    source_punctuation = _punctuation_pattern(source_text)
    final_punctuation = _punctuation_pattern(final_raw)
    source_parentheticals = _parenthetical_count(source_text)
    final_parentheticals = _parenthetical_count(final_raw)
    line_break_changed = bool(source_text and source_line_pattern != final_line_pattern)
    punctuation_changed = bool(source_text and source_punctuation != final_punctuation)
    parenthetical_changed = source_parentheticals != final_parentheticals
    whitespace_normalized = bool(source_text and source_text != final_speech and source_compact == final_compact)
    style_correction_count = sum(
        1
        for flag in (
            line_break_changed,
            punctuation_changed,
            parenthetical_changed,
            whitespace_normalized,
        )
        if flag
    )

    split_added = final_lines > max(1, source_lines)
    merge_likely = source_segments > final_segments or (source_lines > final_lines and source_lines > 1)
    text_score = min(100.0, edit_ratio * 100.0)
    timing_score = min(100.0, move_distance * 100.0)
    structure_score = 18.0 if split_added or merge_likely or source_segments != final_segments else 0.0
    style_score = min(20.0, style_correction_count * 5.0)
    burden = min(100.0, text_score * 0.58 + timing_score * 0.22 + structure_score + style_score)
    if burden >= 45.0:
        severity = "large"
    elif burden >= 18.0:
        severity = "medium"
    elif burden > 0.0:
        severity = "small"
    else:
        severity = "none"

    changed = bool(distance or move_distance or split_added or merge_likely or style_correction_count)
    metrics = {
        "schema": USER_EDIT_METRICS_SCHEMA,
        "task": "user_edit_metrics",
        "metrics_id": stable_hash(
            {
                "source": source_compact,
                "final": final_compact,
                "start": round(final_start, 3),
                "end": round(final_end, 3),
                "segment_id": str(seg.get("segment_id") or seg.get("id") or ""),
            }
        )[:24],
        "changed": changed,
        "severity": severity,
        "edit_burden_score": round(burden, 4),
        "text": {
            "source_available": bool(source_text),
            "source_chars": len(source_compact),
            "final_chars": len(final_compact),
            "levenshtein_distance": distance,
            "edit_ratio": round(edit_ratio, 4),
            "similarity": round(similarity, 4),
            "length_delta": len(final_compact) - len(source_compact),
        },
        "timing": {
            "reference_available": ref_start is not None and ref_end is not None,
            "reference_source": ref_source,
            "source_start": None if ref_start is None else round(ref_start, 3),
            "source_end": None if ref_end is None else round(ref_end, 3),
            "final_start": round(final_start, 3),
            "final_end": round(final_end, 3),
            "start_shift_sec": round(start_shift, 4),
            "end_shift_sec": round(end_shift, 4),
            "duration_delta_sec": round(duration_delta, 4),
            "move_distance_sec": round(move_distance, 4),
        },
        "split_merge": {
            "source_line_count": source_lines,
            "final_line_count": final_lines,
            "line_count_delta": final_lines - source_lines,
            "source_segment_count": source_segments,
            "final_segment_count": final_segments,
            "segment_count_delta": final_segments - source_segments,
            "split_added": split_added,
            "merge_likely": merge_likely,
        },
        "style": {
            "source_line_break_pattern": source_line_pattern,
            "final_line_break_pattern": final_line_pattern,
            "line_break_changed": line_break_changed,
            "punctuation_changed": punctuation_changed,
            "parenthetical_removed": source_parentheticals > final_parentheticals,
            "parenthetical_added": final_parentheticals > source_parentheticals,
            "whitespace_normalized": whitespace_normalized,
            "style_correction_count": style_correction_count,
        },
    }
    return metrics


def user_edit_metric_reasons(metrics: dict[str, Any] | None) -> list[str]:
    data = dict(metrics or {})
    reasons: list[str] = []
    if not data.get("changed"):
        return reasons
    severity = str(data.get("severity") or "")
    if severity and severity != "none":
        reasons.append(f"user_edit_{severity}")
    text = dict(data.get("text") or {})
    timing = dict(data.get("timing") or {})
    split_merge = dict(data.get("split_merge") or {})
    style = dict(data.get("style") or {})
    if _safe_float(text.get("edit_ratio"), 0.0) >= 0.18:
        reasons.append("text_edit_distance_high")
    if _safe_float(timing.get("move_distance_sec"), 0.0) >= 0.3:
        reasons.append("timing_move_high")
    if split_merge.get("split_added"):
        reasons.append("split_added_by_user")
    if split_merge.get("merge_likely"):
        reasons.append("merge_corrected_by_user")
    if _safe_int(style.get("style_correction_count"), 0) > 0:
        reasons.append("style_corrected_by_user")
    return sorted(set(reasons))


__all__ = [
    "USER_EDIT_METRICS_SCHEMA",
    "measure_user_edit_metrics",
    "source_text_for_edit_metrics",
    "user_edit_metric_reasons",
]
