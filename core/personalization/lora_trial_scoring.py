from __future__ import annotations

from pathlib import Path
from typing import Any

from core.native_text_similarity import edit_distance
from core.personalization.lora_models import TrialRecord, line_break_pattern_for_text
from core.personalization.lora_storage import (
    append_prompt_trials,
    append_setting_trials,
    load_best_settings,
    personalization_path_lookup_keys,
    save_best_settings,
)


def _norm(text: Any) -> str:
    return " ".join(str(text or "").replace("\n", " ").strip().split())


def _punctuation_pattern(text: Any) -> str:
    return "".join(ch for ch in str(text or "") if ch in ".,!?~")


def _levenshtein(seq_a: list[Any], seq_b: list[Any]) -> int:
    return edit_distance(seq_a, seq_b)


def _interval_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _interval_iou(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    overlap = _interval_overlap(a_start, a_end, b_start, b_end)
    union = max(a_end, b_end) - min(a_start, b_start)
    return overlap / union if union > 0 else 0.0


def candidate_segments_to_rows(
    segments: list[dict[str, Any]],
    *,
    media_id: str = "",
    media_path: str = "",
    subtitle_path: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segments or [], start=1):
        text = str(segment.get("text") or "").strip()
        rows.append(
            {
                "media_id": media_id,
                "media_path": media_path,
                "subtitle_path": subtitle_path,
                "segment_id": str(segment.get("segment_id") or f"{Path(str(subtitle_path or media_path or 'candidate')).stem}:{index}"),
                "start_sec": float(segment.get("start", 0.0) or 0.0),
                "end_sec": float(segment.get("end", 0.0) or 0.0),
                "speech_training_text": text,
                "line_break_pattern": line_break_pattern_for_text(text),
                "punctuation_pattern": _punctuation_pattern(text),
            }
        )
    return rows


def _match_rows(
    truth_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    remaining = list(candidate_rows or [])
    matches: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for truth_row in truth_rows or []:
        best_index = -1
        best_score = -1.0
        for index, candidate_row in enumerate(remaining):
            score = _interval_iou(
                float(truth_row.get("start_sec", 0.0) or 0.0),
                float(truth_row.get("end_sec", 0.0) or 0.0),
                float(candidate_row.get("start_sec", 0.0) or 0.0),
                float(candidate_row.get("end_sec", 0.0) or 0.0),
            )
            if score > best_score:
                best_index = index
                best_score = score
        candidate = remaining.pop(best_index) if best_index >= 0 else None
        matches.append((truth_row, candidate))
    return matches


def _boundary_f1(
    truth_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    tolerance_sec: float = 0.35,
) -> float:
    truth_boundaries = [float(row.get("end_sec", 0.0) or 0.0) for row in list(truth_rows or [])[:-1]]
    candidate_boundaries = [float(row.get("end_sec", 0.0) or 0.0) for row in list(candidate_rows or [])[:-1]]
    if not truth_boundaries and not candidate_boundaries:
        return 1.0
    matched_candidate_indexes: set[int] = set()
    hits = 0
    for boundary in truth_boundaries:
        for index, candidate_boundary in enumerate(candidate_boundaries):
            if index in matched_candidate_indexes:
                continue
            if abs(boundary - candidate_boundary) <= tolerance_sec:
                matched_candidate_indexes.add(index)
                hits += 1
                break
    precision = hits / len(candidate_boundaries) if candidate_boundaries else 0.0
    recall = hits / len(truth_boundaries) if truth_boundaries else 0.0
    if precision + recall == 0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def score_candidate_rows(
    truth_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    matches = _match_rows(truth_rows, candidate_rows)
    char_distance = 0
    char_total = 0
    token_distance = 0
    token_total = 0
    overlap_scores: list[float] = []
    start_deltas: list[float] = []
    end_deltas: list[float] = []
    line_break_hits = 0
    punctuation_hits = 0
    parenthetical_hits = 0

    for truth_row, candidate_row in matches:
        truth_text = _norm(truth_row.get("speech_training_text"))
        candidate_text = _norm((candidate_row or {}).get("speech_training_text"))
        char_distance += _levenshtein(list(truth_text), list(candidate_text))
        char_total += max(1, len(truth_text))

        truth_tokens = truth_text.split()
        candidate_tokens = candidate_text.split()
        token_distance += _levenshtein(truth_tokens, candidate_tokens)
        token_total += max(1, len(truth_tokens))

        if candidate_row:
            overlap_scores.append(
                _interval_iou(
                    float(truth_row.get("start_sec", 0.0) or 0.0),
                    float(truth_row.get("end_sec", 0.0) or 0.0),
                    float(candidate_row.get("start_sec", 0.0) or 0.0),
                    float(candidate_row.get("end_sec", 0.0) or 0.0),
                )
            )
            start_deltas.append(
                abs(float(truth_row.get("start_sec", 0.0) or 0.0) - float(candidate_row.get("start_sec", 0.0) or 0.0))
            )
            end_deltas.append(
                abs(float(truth_row.get("end_sec", 0.0) or 0.0) - float(candidate_row.get("end_sec", 0.0) or 0.0))
            )
            if str(truth_row.get("line_break_pattern") or "") == str(candidate_row.get("line_break_pattern") or ""):
                line_break_hits += 1
            if str(truth_row.get("punctuation_pattern") or "") == str(candidate_row.get("punctuation_pattern") or ""):
                punctuation_hits += 1

            excluded_text = str(truth_row.get("excluded_parenthetical_text") or "")
            excluded_parts = [item.strip() for item in excluded_text.split("|") if item.strip()]
            if not excluded_parts or not any(item in candidate_text for item in excluded_parts):
                parenthetical_hits += 1

    pair_count = max(1, len(matches))
    cer = char_distance / max(1, char_total)
    wer = token_distance / max(1, token_total)
    timing_overlap_score = sum(overlap_scores) / pair_count if overlap_scores else 0.0
    line_break_match_score = line_break_hits / pair_count
    punctuation_match_score = punctuation_hits / pair_count
    parenthetical_exclusion_correctness = parenthetical_hits / pair_count
    split_merge_f1 = _boundary_f1(truth_rows, candidate_rows)

    final_score = max(
        0.0,
        min(
            100.0,
            (
                (1.0 - min(1.0, cer)) * 40.0
                + (1.0 - min(1.0, wer)) * 20.0
                + timing_overlap_score * 15.0
                + line_break_match_score * 10.0
                + punctuation_match_score * 5.0
                + parenthetical_exclusion_correctness * 5.0
                + split_merge_f1 * 5.0
            ),
        ),
    )
    return {
        "korean_text_edit_distance": char_distance,
        "character_error_rate": round(cer, 4),
        "eojeol_error_rate": round(wer, 4),
        "timing_overlap_score": round(timing_overlap_score, 4),
        "boundary_start_delta": round(sum(start_deltas) / pair_count if start_deltas else 0.0, 4),
        "boundary_end_delta": round(sum(end_deltas) / pair_count if end_deltas else 0.0, 4),
        "line_break_match_score": round(line_break_match_score, 4),
        "punctuation_match_score": round(punctuation_match_score, 4),
        "parenthetical_exclusion_correctness": round(parenthetical_exclusion_correctness, 4),
        "segment_split_merge_f1": round(split_merge_f1, 4),
        "final_score": round(final_score, 2),
    }


def _update_best_settings(
    trial_type: str,
    media_id: str,
    trial_payload: dict[str, Any],
    *,
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    best_settings = load_best_settings(store_dir)
    key = "by_style_cluster" if trial_type == "prompt" else "by_media_id"
    existing = dict((best_settings.get(key) or {}).get(media_id) or {})
    existing_score = float(existing.get("score", -1.0) or -1.0)
    if float(trial_payload.get("score", -1.0) or -1.0) > existing_score:
        best_settings.setdefault(key, {})
        best_settings[key][media_id] = trial_payload
        media_path = str(trial_payload.get("media_path") or "")
        if media_path:
            best_settings.setdefault("by_media_path", {})
            for path_key in personalization_path_lookup_keys(media_path):
                best_settings["by_media_path"][path_key] = trial_payload
        save_best_settings(best_settings, store_dir)
    return best_settings


def record_setting_trial_result(
    *,
    media_id: str,
    media_path: str,
    subtitle_path: str,
    config: dict[str, Any],
    metrics: dict[str, Any],
    reason: str = "",
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    trial = TrialRecord(
        trial_type="setting",
        media_id=media_id,
        media_path=media_path,
        subtitle_path=subtitle_path,
        config=config,
        status="complete",
        score=float(metrics.get("final_score", 0.0) or 0.0),
        metrics=metrics,
        reason=reason,
    ).to_record()
    append_result = append_setting_trials([trial], store_dir)
    best_settings = _update_best_settings(
        "setting",
        media_id,
        {
            "config": config,
            "score": trial["score"],
            "media_path": media_path,
            "subtitle_path": subtitle_path,
        },
        store_dir=store_dir,
    )
    return {
        "trial": trial,
        "append_result": append_result,
        "best_settings": best_settings,
    }


def record_prompt_trial_result(
    *,
    media_id: str,
    media_path: str,
    subtitle_path: str,
    config: dict[str, Any],
    prompt_template_id: str,
    prompt_text: str,
    metrics: dict[str, Any],
    reason: str = "",
    store_dir: str | Path | None = None,
) -> dict[str, Any]:
    trial = TrialRecord(
        trial_type="prompt",
        media_id=media_id,
        media_path=media_path,
        subtitle_path=subtitle_path,
        config=config,
        prompt_template_id=prompt_template_id,
        prompt_text=prompt_text,
        status="complete",
        score=float(metrics.get("final_score", 0.0) or 0.0),
        metrics=metrics,
        reason=reason,
    ).to_record()
    append_result = append_prompt_trials([trial], store_dir)
    best_settings = _update_best_settings(
        "prompt",
        media_id,
        {
            "prompt_template_id": prompt_template_id,
            "prompt_text": prompt_text,
            "score": trial["score"],
            "media_path": media_path,
            "subtitle_path": subtitle_path,
        },
        store_dir=store_dir,
    )
    return {
        "trial": trial,
        "append_result": append_result,
        "best_settings": best_settings,
    }


__all__ = [
    "candidate_segments_to_rows",
    "record_prompt_trial_result",
    "record_setting_trial_result",
    "score_candidate_rows",
]
