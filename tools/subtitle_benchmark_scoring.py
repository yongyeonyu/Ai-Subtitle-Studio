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


def _best_ref_for(hyp: dict[str, Any], refs: list[dict[str, Any]]) -> dict[str, Any] | None:
    best_row = None
    best_score = -1.0
    hyp_mid = (float(hyp.get("start", 0.0) or 0.0) + float(hyp.get("end", 0.0) or 0.0)) / 2.0
    for ref in refs:
        overlap = _overlap(hyp, ref)
        ref_mid = (float(ref.get("start", 0.0) or 0.0) + float(ref.get("end", 0.0) or 0.0)) / 2.0
        proximity = max(0.0, 1.0 - abs(hyp_mid - ref_mid) / 4.0)
        score = overlap * 2.0 + proximity
        if score > best_score:
            best_score = score
            best_row = ref
    return best_row


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
                    local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
        else:
            for row in hyp:
                ref_row = _best_ref_for(row, ref)
                if ref_row:
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
            local_text_scores.append(similarity_ratio(_compact_text(ref_row.get("text")), _compact_text(row.get("text"))))
        avg_timing_error = sum(timing_errors) / max(1, len(timing_errors))
        overlap_score = (sum(overlap_scores) / max(1, len(overlap_scores))) * 100.0 if overlap_scores else 0.0
        timing_backend = "python"
    timing_score = max(0.0, min(100.0, 100.0 - avg_timing_error * 26.0))
    local_text_score = (sum(local_text_scores) / max(1, len(local_text_scores))) * 100.0 if local_text_scores else 0.0
    count_score = max(0.0, 100.0 - abs(len(hyp) - len(ref)) / max(1, len(ref)) * 100.0)
    quality_score = text_score * 0.52 + timing_score * 0.22 + overlap_score * 0.12 + local_text_score * 0.08 + count_score * 0.06
    timing_priority_quality_score = (
        text_score * 0.44
        + timing_score * 0.32
        + overlap_score * 0.12
        + local_text_score * 0.08
        + count_score * 0.04
    )
    return {
        "reference_segments": len(ref),
        "hypothesis_segments": len(hyp),
        "cer": round(float(cer), 6),
        "global_text_similarity": round(float(text_similarity), 6),
        "text_score": round(text_score, 3),
        "timing_mae_sec": round(avg_timing_error, 4),
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
        "quality_score": round(quality_score, 3),
        "timing_priority_quality_score": round(timing_priority_quality_score, 3),
    }
