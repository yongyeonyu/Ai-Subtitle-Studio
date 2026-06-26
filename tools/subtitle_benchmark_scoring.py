#!/usr/bin/env python3
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable

from core.native_swift_subtitle_timing import score_timing_metrics_via_swift
from core.native_subtitle_timing import timing_metrics as cpp_timing_metrics
from core.native_text_similarity import character_error_rate, similarity_ratio


def parse_srt(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = re.split(r"\n\s*\n", text.strip())
    rows: list[dict[str, Any]] = []
    for block in blocks:
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), "")
        if not time_line:
            continue
        try:
            left, right = [part.strip() for part in time_line.split("-->", 1)]
            start = srt_time_to_sec(left)
            end = srt_time_to_sec(right)
        except Exception:
            continue
        idx = lines.index(time_line)
        body = "\n".join(lines[idx + 1:]).strip()
        if body:
            rows.append({"start": start, "end": end, "text": body})
    return rows


def srt_time_to_sec(value: str) -> float:
    raw = str(value or "").strip().replace(",", ".")
    hms = raw.split(":")
    if len(hms) != 3:
        raise ValueError(f"bad srt time: {value}")
    hour = float(hms[0])
    minute = float(hms[1])
    sec = float(hms[2])
    return hour * 3600.0 + minute * 60.0 + sec


def clip_reference(rows: list[dict[str, Any]], start_sec: float, end_sec: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        start = float(row.get("start", 0.0) or 0.0)
        end = float(row.get("end", start) or start)
        if end <= start_sec or start >= end_sec:
            continue
        out.append(
            {
                **row,
                "start": max(0.0, start - start_sec),
                "end": max(0.0, min(end, end_sec) - start_sec),
            }
        )
    return out


def _compact_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"（[^）]*）", "", text)
    text = text.replace("-", "")
    text = re.sub(r"\s+", "", text, flags=re.UNICODE)
    for bracket in ("(", ")", "（", "）"):
        text = text.replace(bracket, "")
    return text.casefold()


def _joined_text(rows: Iterable[dict[str, Any]]) -> str:
    return " ".join(str(row.get("text", "") or "").replace("\n", " ").strip() for row in rows if str(row.get("text", "") or "").strip())


def _overlap(left: dict[str, Any], right: dict[str, Any]) -> float:
    start = max(float(left.get("start", 0.0) or 0.0), float(right.get("start", 0.0) or 0.0))
    end = min(float(left.get("end", start) or start), float(right.get("end", start) or start))
    return max(0.0, end - start)


def _row_start(row: dict[str, Any]) -> float:
    return float(row.get("start", 0.0) or 0.0)


def _row_end(row: dict[str, Any]) -> float:
    start = _row_start(row)
    return float(row.get("end", start) or start)


def _best_ref_for(hyp: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    best_row = None
    best_score = -1.0
    hyp_mid = (_row_start(hyp) + _row_end(hyp)) / 2.0
    for ref in refs:
        overlap = _overlap(hyp, ref)
        ref_mid = (_row_start(ref) + _row_end(ref)) / 2.0
        proximity = max(0.0, 1.0 - abs(hyp_mid - ref_mid) / 4.0)
        score = overlap * 2.0 + proximity
        if score > best_score:
            best_score = score
            best_row = ref
    return best_row


def _window_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start": _row_start(rows[0]),
        "end": _row_end(rows[-1]),
        "text": _joined_text(rows),
        "reference_window_count": len(rows),
    }


def _best_ref_window_for(
    hyp: dict[str, Any],
    refs: list[dict[str, Any]],
    *,
    max_refs: int = 8,
    search_pad_sec: float = 3.0,
) -> dict[str, Any] | None:
    if not refs:
        return None
    hyp_start = _row_start(hyp)
    hyp_end = _row_end(hyp)
    hyp_mid = (hyp_start + hyp_end) / 2.0
    candidate_indices = [
        idx
        for idx, ref in enumerate(refs)
        if _row_end(ref) >= hyp_start - search_pad_sec and _row_start(ref) <= hyp_end + search_pad_sec
    ]
    if not candidate_indices:
        ref_row = _best_ref_for(hyp, refs)
        return _window_row([ref_row]) if ref_row else None

    lo = max(0, min(candidate_indices) - 1)
    hi = min(len(refs) - 1, max(candidate_indices) + 1)
    hyp_text = _compact_text(hyp.get("text"))
    best_window: dict[str, Any] | None = None
    best_score = -1.0
    for start_idx in range(lo, hi + 1):
        for end_idx in range(start_idx, min(hi, start_idx + max_refs - 1) + 1):
            window = refs[start_idx:end_idx + 1]
            window_start = _row_start(window[0])
            window_end = _row_end(window[-1])
            window_mid = (window_start + window_end) / 2.0
            overlap = max(0.0, min(hyp_end, window_end) - max(hyp_start, window_start))
            max_span = max(hyp_end - hyp_start, window_end - window_start, 0.001)
            overlap_ratio = min(1.0, overlap / max_span)
            center_delta = abs(hyp_mid - window_mid)
            if overlap_ratio <= 0.0 and center_delta > search_pad_sec:
                continue
            ref_text = _compact_text(_joined_text(window))
            text_similarity = similarity_ratio(ref_text, hyp_text) if ref_text or hyp_text else 1.0
            start_err = abs(hyp_start - window_start)
            end_err = abs(hyp_end - window_end)
            weighted_err = start_err * 0.7 + end_err * 0.3
            timing_proximity = max(0.0, 1.0 - weighted_err / max(1.0, search_pad_sec + 1.0))
            center_proximity = max(0.0, 1.0 - center_delta / max(1.0, search_pad_sec + 1.0))
            compactness = max(0.0, 1.0 - max(0, len(window) - 1) / max(1.0, float(max_refs)))
            score = text_similarity * 4.0 + overlap_ratio * 1.5 + timing_proximity + center_proximity * 0.25 + compactness * 0.15
            if score > best_score:
                best_score = score
                best_window = _window_row(window)
    if best_window is not None:
        return best_window
    ref_row = _best_ref_for(hyp, refs)
    return _window_row([ref_row]) if ref_row else None


def _start_weighted_timing_errors(pairs: Iterable[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[float, float, float]:
    start_errors: list[float] = []
    end_errors: list[float] = []
    weighted_errors: list[float] = []
    for hyp, ref in pairs:
        start_err = abs(_row_start(hyp) - _row_start(ref))
        end_err = abs(_row_end(hyp) - _row_end(ref))
        start_errors.append(start_err)
        end_errors.append(end_err)
        weighted_errors.append(start_err * 0.7 + end_err * 0.3)
    if not weighted_errors:
        return 0.0, 0.0, 0.0
    return (
        sum(start_errors) / len(start_errors),
        sum(end_errors) / len(end_errors),
        sum(weighted_errors) / len(weighted_errors),
    )


def _split_merge_alignment_metrics(hyp: list[dict[str, Any]], ref: list[dict[str, Any]]) -> dict[str, float]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    local_text_scores: list[float] = []
    overlap_scores: list[float] = []
    for row in hyp:
        ref_window = _best_ref_window_for(row, ref)
        if not ref_window:
            continue
        pairs.append((row, ref_window))
        local_text_scores.append(similarity_ratio(_compact_text(ref_window.get("text")), _compact_text(row.get("text"))))
        span = max(
            _row_end(row) - _row_start(row),
            _row_end(ref_window) - _row_start(ref_window),
            0.001,
        )
        overlap_scores.append(min(1.0, _overlap(row, ref_window) / span))
    start_mae, end_mae, start_weighted_mae = _start_weighted_timing_errors(pairs)
    timing_mae = (
        sum((abs(_row_start(row) - _row_start(ref_window)) + abs(_row_end(row) - _row_end(ref_window))) / 2.0 for row, ref_window in pairs)
        / max(1, len(pairs))
        if pairs
        else 0.0
    )
    return {
        "timing_mae_sec": timing_mae,
        "start_timing_mae_sec": start_mae,
        "end_timing_mae_sec": end_mae,
        "start_weighted_timing_mae_sec": start_weighted_mae,
        "timing_score": max(0.0, min(100.0, 100.0 - start_weighted_mae * 26.0)),
        "overlap_score": (sum(overlap_scores) / max(1, len(overlap_scores))) * 100.0 if overlap_scores else 0.0,
        "local_text_score": (sum(local_text_scores) / max(1, len(local_text_scores))) * 100.0 if local_text_scores else 0.0,
    }


def _segmentation_tolerant_count_score(
    classic_count_score: float,
    *,
    global_text_similarity: float,
    split_merge_local_text_score: float,
) -> float:
    coverage_score = global_text_similarity * 70.0 + (split_merge_local_text_score / 100.0) * 30.0
    return max(0.0, min(100.0, max(classic_count_score, coverage_score)))


TimingBackend = Callable[[list[dict[str, Any]], list[dict[str, Any]]], dict[str, Any] | None]


def score_against_reference(
    hypothesis: list[dict[str, Any]],
    reference: list[dict[str, Any]],
    *,
    swift_timing_backend: TimingBackend | None = None,
    cpp_timing_backend: TimingBackend | None = None,
) -> dict[str, Any]:
    hyp = [dict(row) for row in hypothesis if str(row.get("text", "") or "").strip()]
    ref = [dict(row) for row in reference if str(row.get("text", "") or "").strip()]
    ref_compact = _compact_text(_joined_text(ref))
    hyp_compact = _compact_text(_joined_text(hyp))
    cer = character_error_rate(ref_compact, hyp_compact) if ref_compact else 1.0
    text_similarity = similarity_ratio(ref_compact, hyp_compact) if ref_compact or hyp_compact else 1.0
    text_score = max(0.0, min(100.0, (1.0 - min(1.0, cer)) * 72.0 + text_similarity * 28.0))

    swift_backend = swift_timing_backend or score_timing_metrics_via_swift
    cpp_backend = cpp_timing_backend or cpp_timing_metrics
    native_timing = swift_backend(hyp, ref) or cpp_backend(hyp, ref)
    local_text_scores: list[float] = []
    timing_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if native_timing:
        avg_timing_error = float(native_timing.get("timing_mae_sec", 0.0) or 0.0)
        overlap_score = float(native_timing.get("overlap_score", 0.0) or 0.0)
        timing_backend = str(native_timing.get("native_backend") or "native")
        max_start_error = float(native_timing.get("max_start_error_sec", 0.0) or 0.0)
        max_end_error = float(native_timing.get("max_end_error_sec", 0.0) or 0.0)
        max_pair_timing_error = float(native_timing.get("max_pair_timing_error_sec", 0.0) or 0.0)
        worst_match_hypothesis_index = int(native_timing.get("worst_match_hypothesis_index", -1))
        worst_match_reference_index = int(native_timing.get("worst_match_reference_index", -1))
        matched_reference_indices = native_timing.get("matched_reference_indices")
        if isinstance(matched_reference_indices, list) and len(matched_reference_indices) >= len(hyp):
            for row, ref_index in zip(hyp, matched_reference_indices):
                try:
                    ref_row = ref[int(ref_index)]
                except Exception:
                    ref_row = _best_ref_for(row, ref)
                if ref_row:
                    timing_pairs.append((row, ref_row))
                    local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
        else:
            for row in hyp:
                ref_row = _best_ref_for(row, ref)
                if ref_row:
                    timing_pairs.append((row, ref_row))
                    local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
    else:
        timing_errors: list[float] = []
        overlap_scores: list[float] = []
        max_start_error = 0.0
        max_end_error = 0.0
        max_pair_timing_error = 0.0
        worst_match_hypothesis_index = -1
        worst_match_reference_index = -1
        for hyp_index, row in enumerate(hyp):
            ref_row = _best_ref_for(row, ref)
            if not ref_row:
                continue
            start_err = abs(float(row.get("start", 0.0) or 0.0) - float(ref_row.get("start", 0.0) or 0.0))
            end_err = abs(float(row.get("end", 0.0) or 0.0) - float(ref_row.get("end", 0.0) or 0.0))
            pair_timing_error = (start_err + end_err) / 2.0
            timing_errors.append(pair_timing_error)
            max_start_error = max(max_start_error, start_err)
            max_end_error = max(max_end_error, end_err)
            if pair_timing_error > max_pair_timing_error:
                max_pair_timing_error = pair_timing_error
                worst_match_hypothesis_index = hyp_index
                try:
                    worst_match_reference_index = ref.index(ref_row)
                except ValueError:
                    worst_match_reference_index = -1
            span = max(
                float(row.get("end", 0.0) or 0.0) - float(row.get("start", 0.0) or 0.0),
                float(ref_row.get("end", 0.0) or 0.0) - float(ref_row.get("start", 0.0) or 0.0),
                0.001,
            )
            overlap_scores.append(min(1.0, _overlap(row, ref_row) / span))
            timing_pairs.append((row, ref_row))
            local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
        avg_timing_error = sum(timing_errors) / max(1, len(timing_errors))
        overlap_score = (sum(overlap_scores) / max(1, len(overlap_scores))) * 100.0 if overlap_scores else 0.0
        timing_backend = "python"
    start_mae, end_mae, start_weighted_timing_mae = _start_weighted_timing_errors(timing_pairs)
    timing_score_mae = start_weighted_timing_mae if timing_pairs else avg_timing_error
    timing_score = max(0.0, min(100.0, 100.0 - timing_score_mae * 26.0))
    local_text_score = (sum(local_text_scores) / max(1, len(local_text_scores))) * 100.0 if local_text_scores else 0.0
    count_score = max(0.0, 100.0 - abs(len(hyp) - len(ref)) / max(1, len(ref)) * 100.0)
    split_merge = _split_merge_alignment_metrics(hyp, ref)
    segmentation_score = _segmentation_tolerant_count_score(
        count_score,
        global_text_similarity=float(text_similarity),
        split_merge_local_text_score=float(split_merge.get("local_text_score", local_text_score) or local_text_score),
    )
    scoring_timing_score = float(split_merge.get("timing_score", timing_score) or timing_score)
    scoring_overlap_score = float(split_merge.get("overlap_score", overlap_score) or overlap_score)
    scoring_local_text_score = float(split_merge.get("local_text_score", local_text_score) or local_text_score)
    quality_score = (
        text_score * 0.52
        + scoring_timing_score * 0.22
        + scoring_overlap_score * 0.12
        + scoring_local_text_score * 0.08
        + segmentation_score * 0.06
    )
    return {
        "reference_segments": len(ref),
        "hypothesis_segments": len(hyp),
        "scoring_alignment": "split_merge_aware.v1",
        "cer": round(float(cer), 6),
        "global_text_similarity": round(float(text_similarity), 6),
        "text_score": round(text_score, 3),
        "timing_mae_sec": round(avg_timing_error, 4),
        "start_timing_mae_sec": round(start_mae, 4),
        "end_timing_mae_sec": round(end_mae, 4),
        "start_weighted_timing_mae_sec": round(start_weighted_timing_mae, 4),
        "max_start_error_sec": round(max_start_error, 4),
        "max_end_error_sec": round(max_end_error, 4),
        "max_pair_timing_error_sec": round(max_pair_timing_error, 4),
        "worst_match_hypothesis_index": worst_match_hypothesis_index,
        "worst_match_reference_index": worst_match_reference_index,
        "timing_score": round(timing_score, 3),
        "overlap_score": round(overlap_score, 3),
        "timing_metrics_backend": timing_backend,
        "local_text_score": round(local_text_score, 3),
        "count_score": round(count_score, 3),
        "split_merge_timing_mae_sec": round(float(split_merge.get("timing_mae_sec", avg_timing_error) or 0.0), 4),
        "split_merge_start_timing_mae_sec": round(float(split_merge.get("start_timing_mae_sec", start_mae) or 0.0), 4),
        "split_merge_end_timing_mae_sec": round(float(split_merge.get("end_timing_mae_sec", end_mae) or 0.0), 4),
        "split_merge_start_weighted_timing_mae_sec": round(float(split_merge.get("start_weighted_timing_mae_sec", start_weighted_timing_mae) or 0.0), 4),
        "split_merge_timing_score": round(scoring_timing_score, 3),
        "split_merge_overlap_score": round(scoring_overlap_score, 3),
        "split_merge_local_text_score": round(scoring_local_text_score, 3),
        "segmentation_score": round(segmentation_score, 3),
        "quality_score": round(quality_score, 3),
    }
