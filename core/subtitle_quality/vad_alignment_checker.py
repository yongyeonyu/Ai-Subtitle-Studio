# Version: 03.01.22
# Phase: PHASE2
"""VAD alignment checks for subtitle quality review."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Any

from core.native_cut_boundary import interval_overlaps as _native_interval_overlaps


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_vad_segments(vad_segments: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in vad_segments or ():
        if not isinstance(item, dict):
            continue
        start = max(0.0, _as_float(item.get("start"), 0.0))
        end = max(start, _as_float(item.get("end"), start))
        if end <= start:
            continue
        out = dict(item)
        out["start"] = start
        out["end"] = end
        normalized.append(out)
    return normalized


def vad_overlap_seconds(
    start: float,
    end: float,
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> float:
    return _vad_overlap_seconds_prepared(start, end, normalize_vad_segments(vad_segments))


def _vad_overlap_seconds_prepared(
    start: float,
    end: float,
    vad_segments: list[dict[str, Any]],
) -> float:
    start = max(0.0, _as_float(start, 0.0))
    end = max(start, _as_float(end, start))
    if end <= start or not vad_segments:
        return 0.0
    try:
        native = _native_interval_overlaps(
            [start],
            [end],
            [float(vad["start"]) for vad in vad_segments],
            [float(vad["end"]) for vad in vad_segments],
        )
        if native is not None:
            return float(native[0] if native else 0.0)
    except Exception:
        pass
    return _vad_overlap_seconds_python_prepared(start, end, vad_segments)


def _vad_overlap_seconds_python_prepared(
    start: float,
    end: float,
    vad_segments: list[dict[str, Any]],
) -> float:
    overlap = 0.0
    for vad in vad_segments:
        overlap += max(0.0, min(end, vad["end"]) - max(start, vad["start"]))
    return overlap


def _vad_alignment_info_from_overlap(
    start: float,
    end: float,
    overlap: float,
    *,
    has_vad: bool,
) -> dict[str, Any]:
    duration = max(0.0, end - start)
    if duration <= 0.0 or not has_vad:
        return {
            "vad_overlap_ratio": None,
            "vad_overlap_sec": 0.0,
            "vad_duration_sec": round(duration, 6),
            "vad_aligned": None,
        }
    ratio = round(max(0.0, min(1.0, overlap / duration)), 6)
    return {
        "vad_overlap_ratio": ratio,
        "vad_overlap_sec": round(overlap, 6),
        "vad_duration_sec": round(duration, 6),
        "vad_aligned": ratio >= 0.35,
    }


def vad_alignment_info(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return _vad_alignment_info_prepared(segment, normalize_vad_segments(vad_segments))


def _vad_alignment_info_prepared(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    start = _as_float(segment.get("start"), 0.0)
    end = _as_float(segment.get("end"), start)
    duration = max(0.0, end - start)
    if duration <= 0.0 or not vad_segments:
        return _vad_alignment_info_from_overlap(start, end, 0.0, has_vad=False)

    overlap = _vad_overlap_seconds_prepared(start, end, vad_segments)
    return _vad_alignment_info_from_overlap(start, end, overlap, has_vad=True)


def vad_overlap_ratio(segment: dict[str, Any], vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> float | None:
    return vad_alignment_info(segment, vad_segments).get("vad_overlap_ratio")


def annotate_segment_vad_alignment(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return _annotate_segment_vad_alignment_prepared(segment, normalize_vad_segments(vad_segments))


def _annotate_segment_vad_alignment_prepared(
    segment: dict[str, Any],
    vad_segments: list[dict[str, Any]],
) -> dict[str, Any]:
    return _annotate_segment_vad_alignment_with_info(segment, _vad_alignment_info_prepared(segment, vad_segments))


def _annotate_segment_vad_alignment_with_info(segment: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    out = dict(segment or {})
    asr_metadata = dict(out.get("asr_metadata") or {})
    asr_metadata["vad_alignment"] = info
    out["asr_metadata"] = asr_metadata

    quality = dict(out.get("quality") or {})
    flags = list(quality.get("flags") or ())
    ratio = info.get("vad_overlap_ratio")
    if ratio is not None:
        quality["vad_alignment_score"] = round(float(ratio) * 100.0, 3)
        if ratio < 0.2 and "outside_vad_speech" not in flags:
            flags.append("outside_vad_speech")
    if flags:
        quality["flags"] = tuple(flags)
    out["quality"] = quality
    return out


def annotate_segments_vad_alignment(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    items = [dict(segment or {}) for segment in (segments or ())]
    vad = normalize_vad_segments(vad_segments)
    if not items:
        return []

    starts: list[float] = []
    ends: list[float] = []
    for item in items:
        start = max(0.0, _as_float(item.get("start"), 0.0))
        end = max(start, _as_float(item.get("end"), start))
        starts.append(start)
        ends.append(end)

    overlaps: list[float] | None = None
    if vad:
        try:
            native = _native_interval_overlaps(
                starts,
                ends,
                [float(v["start"]) for v in vad],
                [float(v["end"]) for v in vad],
            )
            if native is not None and len(native) == len(items):
                overlaps = [float(value) for value in native]
        except Exception:
            overlaps = None
        if overlaps is None:
            overlaps = [_vad_overlap_seconds_python_prepared(start, end, vad) for start, end in zip(starts, ends)]
    else:
        overlaps = [0.0 for _ in items]

    annotated: list[dict[str, Any]] = []
    for item, start, end, overlap in zip(items, starts, ends, overlaps):
        info = _vad_alignment_info_from_overlap(start, end, overlap, has_vad=bool(vad))
        annotated.append(_annotate_segment_vad_alignment_with_info(item, info))
    return annotated


def adjust_segments_to_vad_boundaries(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    max_shift_sec: float = 0.7,
    edge_pad_sec: float = 0.04,
) -> tuple[list[dict[str, Any]], int]:
    """Snap subtitle edges to nearby VAD speech boundaries without stretching rows."""
    vad = sorted(normalize_vad_segments(vad_segments), key=lambda item: (item["start"], item["end"]))
    if not segments or not vad:
        return [dict(seg) for seg in (segments or [])], 0

    max_shift = max(0.0, _as_float(max_shift_sec, 0.7))
    pad = max(0.0, _as_float(edge_pad_sec, 0.04))
    vad_starts = [float(item["start"]) for item in vad]
    max_vad_duration = max((float(item["end"]) - float(item["start"]) for item in vad), default=0.0)

    def _nearby_refs(start: float, end: float, window: float) -> list[dict[str, Any]]:
        lower = max(0.0, start - window)
        upper = end + window
        lo = bisect_left(vad_starts, max(0.0, lower - max_vad_duration))
        hi = bisect_right(vad_starts, upper)
        return [v for v in vad[lo:hi] if v["end"] >= lower and v["start"] <= upper]

    adjusted: list[dict[str, Any]] = []
    changed = 0

    for segment in segments:
        out = dict(segment or {})
        start = max(0.0, _as_float(out.get("start"), 0.0))
        end = max(start, _as_float(out.get("end"), start))
        if end <= start:
            adjusted.append(out)
            continue

        overlaps = _nearby_refs(start, end, 0.0)
        nearby = _nearby_refs(start, end, max_shift)
        refs = overlaps or nearby
        if not refs:
            adjusted.append(out)
            continue

        new_start = start
        new_end = end

        # 시작점은 가까운 VAD 시작 경계 또는 자막이 음성보다 먼저 열린 경우에만 조정합니다.
        first = refs[0]
        if abs(first["start"] - start) <= max_shift or (start < first["start"] and first["start"] < end):
            new_start = max(0.0, first["start"] - pad)

        # 끝점은 가까운 VAD 끝 경계 또는 자막이 음성보다 늦게 닫힌 경우에만 조정합니다.
        last = refs[-1]
        if abs(last["end"] - end) <= max_shift or (start < last["end"] and end > last["end"]):
            new_end = max(new_start + 0.05, last["end"] + pad)

        if new_end <= new_start:
            new_end = new_start + max(0.05, end - start)

        if abs(new_start - start) > 0.001 or abs(new_end - end) > 0.001:
            changed += 1
            meta = dict(out.get("asr_metadata") or {})
            meta["vad_timing_adjustment"] = {
                "from": [round(start, 3), round(end, 3)],
                "to": [round(new_start, 3), round(new_end, 3)],
            }
            out["asr_metadata"] = meta
        out["start"] = round(new_start, 3)
        out["end"] = round(new_end, 3)
        adjusted.append(out)

    adjusted.sort(key=lambda item: (_as_float(item.get("start")), _as_float(item.get("end"))))
    for idx in range(1, len(adjusted)):
        prev = adjusted[idx - 1]
        cur = adjusted[idx]
        if _as_float(prev.get("end")) > _as_float(cur.get("start")):
            prev["end"] = round(max(_as_float(prev.get("start")) + 0.05, _as_float(cur.get("start")) - 0.02), 3)
    adjusted = annotate_segments_vad_alignment(adjusted, vad)
    return adjusted, changed


def prioritize_vad_voice_starts(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    max_pull_sec: float = 1.25,
    edge_pad_sec: float = 0.04,
    min_overlap_sec: float = 0.04,
    min_gap_sec: float = 0.02,
    max_stt_lead_sec: float = 0.12,
) -> tuple[list[dict[str, Any]], int]:
    """Pull late subtitle starts back to the detected VAD speech onset."""

    def stt_anchor_start(row: dict[str, Any]) -> float | None:
        selected_source = str(row.get("stt_selected_source") or row.get("stt_ensemble_source") or "").strip().upper()
        selected_base = selected_source.split("_", 1)[0]
        candidates = [
            candidate
            for candidate in list(row.get("stt_candidates") or [])
            if isinstance(candidate, dict)
        ]
        ordered: list[dict[str, Any]] = []
        if selected_base:
            ordered.extend(
                candidate
                for candidate in candidates
                if str(
                    candidate.get("source")
                    or candidate.get("stt_selected_source")
                    or candidate.get("stt_source")
                    or ""
                ).strip().upper().split("_", 1)[0] == selected_base
            )
        ordered.extend(candidate for candidate in candidates if candidate not in ordered)
        for item in ordered:
            for key in ("_stt_original_candidate_start", "original_start", "start"):
                try:
                    value = float(item.get(key))
                except (TypeError, ValueError):
                    continue
                if value >= 0.0:
                    return value
        row_has_original_anchor = any(row.get(key) not in (None, "") for key in ("_stt_original_candidate_start", "original_start"))
        row_has_stt_source = selected_base in {"STT1", "STT2"}
        if row_has_original_anchor or row_has_stt_source:
            for key in ("_stt_original_candidate_start", "original_start", "start"):
                try:
                    value = float(row.get(key))
                except (TypeError, ValueError):
                    continue
                if value >= 0.0:
                    return value
        return None

    vad = sorted(normalize_vad_segments(vad_segments), key=lambda item: (item["start"], item["end"]))
    rows = sorted(
        [dict(seg) for seg in (segments or []) if isinstance(seg, dict)],
        key=lambda item: (_as_float(item.get("start")), _as_float(item.get("end"))),
    )
    if not rows or not vad:
        return rows, 0

    max_pull = max(0.0, _as_float(max_pull_sec, 1.25))
    pad = max(0.0, _as_float(edge_pad_sec, 0.04))
    min_overlap = max(0.0, _as_float(min_overlap_sec, 0.04))
    min_gap = max(0.0, _as_float(min_gap_sec, 0.02))
    max_stt_lead = max(0.0, _as_float(max_stt_lead_sec, 0.12))
    changed = 0
    previous_end: float | None = None

    for row in rows:
        if row.get("is_gap"):
            continue
        start = max(0.0, _as_float(row.get("start"), 0.0))
        end = max(start, _as_float(row.get("end"), start))
        if end <= start:
            previous_end = end
            continue

        best: dict[str, Any] | None = None
        best_delay = 0.0
        for ref in vad:
            vad_start = float(ref["start"])
            vad_end = float(ref["end"])
            if vad_start >= start - 0.001:
                continue
            if vad_end <= start + min_overlap:
                continue
            overlap = max(0.0, min(end, vad_end) - max(start, vad_start))
            if overlap < min_overlap:
                continue
            delay = start - vad_start
            if delay > max_pull:
                continue
            if best is None or delay > best_delay:
                best = ref
                best_delay = delay

        if best is None:
            previous_end = end
            continue

        desired = max(0.0, float(best["start"]) - pad)
        anchor_start = stt_anchor_start(row)
        if anchor_start is not None:
            desired = max(desired, max(0.0, anchor_start - max_stt_lead))
        if previous_end is not None:
            desired = max(desired, previous_end + min_gap)
        if desired >= start - 0.001:
            previous_end = end
            continue

        old_start = start
        row["start"] = round(desired, 3)
        row["timeline_start"] = row["start"]
        meta = dict(row.get("asr_metadata") or {})
        meta["vad_voice_start_priority"] = {
            "from": round(old_start, 3),
            "to": round(desired, 3),
            "vad_start": round(float(best["start"]), 3),
            "vad_end": round(float(best["end"]), 3),
            "max_pull_sec": round(max_pull, 3),
            "edge_pad_sec": round(pad, 3),
            "max_stt_lead_sec": round(max_stt_lead, 3),
        }
        if anchor_start is not None:
            meta["vad_voice_start_priority"]["stt_anchor_start"] = round(anchor_start, 3)
        row["asr_metadata"] = meta
        changed += 1
        previous_end = end

    if changed:
        rows = annotate_segments_vad_alignment(rows, vad)
    return rows, changed


def _span_from_mapping(item: dict[str, Any]) -> tuple[float, float] | None:
    for start_key, end_key in (
        ("_stt_original_candidate_start", "_stt_original_candidate_end"),
        ("original_start", "original_end"),
        ("start", "end"),
    ):
        try:
            start = float(item.get(start_key))
            end = float(item.get(end_key))
        except (TypeError, ValueError):
            continue
        if end > start >= 0.0:
            return start, end
    return None


def _stt_source_base(item: dict[str, Any]) -> str:
    return str(
        item.get("source")
        or item.get("stt_selected_source")
        or item.get("stt_ensemble_source")
        or item.get("stt_source")
        or ""
    ).strip().upper().split("_", 1)[0]


def _stt_spans_by_source(row: dict[str, Any]) -> dict[str, tuple[float, float]]:
    spans: dict[str, tuple[float, float]] = {}
    for candidate in list(row.get("stt_candidates") or []):
        if not isinstance(candidate, dict):
            continue
        source = _stt_source_base(candidate)
        if source not in {"STT1", "STT2"} or source in spans:
            continue
        span = _span_from_mapping(candidate)
        if span is not None:
            spans[source] = span
    row_source = _stt_source_base(row)
    if row_source in {"STT1", "STT2"} and row_source not in spans:
        span = _span_from_mapping(row)
        if span is not None:
            spans[row_source] = span
    return spans


def _span_duration(span: tuple[float, float]) -> float:
    return max(0.0, float(span[1]) - float(span[0]))


def _spans_similar(
    left: tuple[float, float],
    right: tuple[float, float],
    *,
    start_tolerance_sec: float,
    end_tolerance_sec: float,
    duration_tolerance_sec: float,
) -> bool:
    return (
        abs(float(left[0]) - float(right[0])) <= start_tolerance_sec
        and abs(float(left[1]) - float(right[1])) <= end_tolerance_sec
        and abs(_span_duration(left) - _span_duration(right)) <= duration_tolerance_sec
    )


def _best_vad_span_for_consensus(
    row: dict[str, Any],
    vad: list[dict[str, Any]],
    stt_spans: dict[str, tuple[float, float]],
    *,
    max_gap_sec: float,
) -> tuple[float, float] | None:
    anchors = list(stt_spans.values())
    row_span = _span_from_mapping(row)
    if row_span is not None:
        anchors.append(row_span)
    if not anchors:
        return None
    best: tuple[float, tuple[float, float]] | None = None
    for ref in vad:
        span = (float(ref["start"]), float(ref["end"]))
        score = 0.0
        for anchor in anchors:
            overlap = max(0.0, min(span[1], anchor[1]) - max(span[0], anchor[0]))
            gap = 0.0 if overlap > 0.0 else min(abs(span[1] - anchor[0]), abs(anchor[1] - span[0]))
            if overlap > 0.0:
                score = max(score, 2.0 + overlap)
            elif gap <= max_gap_sec:
                score = max(score, 1.0 - (gap / max(0.001, max_gap_sec)))
        if score <= 0.0:
            continue
        if best is None or score > best[0]:
            best = (score, span)
    return None if best is None else best[1]


def _consensus_span_from_sources(
    source_spans: dict[str, tuple[float, float]],
    *,
    start_tolerance_sec: float,
    end_tolerance_sec: float,
    duration_tolerance_sec: float,
    edge_pad_sec: float,
) -> tuple[tuple[float, float], dict[str, Any]] | None:
    if "VAD" in source_spans and "STT1" in source_spans and "STT2" not in source_spans:
        vad_span = source_spans["VAD"]
        stt1_span = source_spans["STT1"]
        if not _spans_similar(
            vad_span,
            stt1_span,
            start_tolerance_sec=start_tolerance_sec,
            end_tolerance_sec=end_tolerance_sec,
            duration_tolerance_sec=duration_tolerance_sec,
        ):
            return None
        span = (min(vad_span[0], stt1_span[0]), max(vad_span[1], stt1_span[1]))
        return span, {
            "matched_sources": ["VAD", "STT1"],
            "action": "stt1_vad_union_span",
            "source_spans": {
                key: [round(value[0], 3), round(value[1], 3)]
                for key, value in source_spans.items()
            },
        }
    preferred_pairs = (
        ("VAD", "STT1"),
        ("VAD", "STT2"),
        ("STT1", "STT2"),
    )
    best: tuple[float, tuple[str, str], tuple[float, float]] | None = None
    for left_key, right_key in preferred_pairs:
        left = source_spans.get(left_key)
        right = source_spans.get(right_key)
        if left is None or right is None:
            continue
        if not _spans_similar(
            left,
            right,
            start_tolerance_sec=start_tolerance_sec,
            end_tolerance_sec=end_tolerance_sec,
            duration_tolerance_sec=duration_tolerance_sec,
        ):
            continue
        start_delta = abs(left[0] - right[0])
        end_delta = abs(left[1] - right[1])
        duration_delta = abs(_span_duration(left) - _span_duration(right))
        distance = start_delta + end_delta + duration_delta
        if "VAD" in {left_key, right_key}:
            vad_span = source_spans["VAD"]
            consensus = (max(0.0, vad_span[0] - edge_pad_sec), max(vad_span[0] + 0.05, vad_span[1] + edge_pad_sec))
            priority_bonus = -1.0
        else:
            consensus = ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)
            priority_bonus = 0.0
        score = distance + priority_bonus
        if best is None or score < best[0]:
            best = (score, (left_key, right_key), consensus)
    if best is None:
        return None
    _, pair, span = best
    return span, {
        "matched_sources": list(pair),
        "source_spans": {
            key: [round(value[0], 3), round(value[1], 3)]
            for key, value in source_spans.items()
        },
    }


def apply_vad_stt_timing_consensus(
    segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    vad_segments: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    start_tolerance_sec: float = 0.35,
    end_tolerance_sec: float = 0.45,
    duration_tolerance_sec: float = 0.45,
    max_vad_gap_sec: float = 0.65,
    edge_pad_sec: float = 0.04,
    min_gap_sec: float = 0.02,
) -> tuple[list[dict[str, Any]], int]:
    """Apply a 2-of-3 VAD/STT1/STT2 timing consensus as a final timing anchor."""
    vad = sorted(normalize_vad_segments(vad_segments), key=lambda item: (item["start"], item["end"]))
    rows = sorted(
        [dict(seg) for seg in (segments or []) if isinstance(seg, dict)],
        key=lambda item: (_as_float(item.get("start")), _as_float(item.get("end"))),
    )
    if not rows:
        return rows, 0

    start_tol = max(0.0, _as_float(start_tolerance_sec, 0.35))
    end_tol = max(0.0, _as_float(end_tolerance_sec, 0.45))
    dur_tol = max(0.0, _as_float(duration_tolerance_sec, 0.45))
    max_gap = max(0.0, _as_float(max_vad_gap_sec, 0.65))
    pad = max(0.0, _as_float(edge_pad_sec, 0.04))
    min_gap = max(0.0, _as_float(min_gap_sec, 0.02))
    changed = 0
    previous_end: float | None = None

    for row in rows:
        if row.get("is_gap"):
            continue
        row_span = _span_from_mapping(row)
        if row_span is None:
            continue
        source_spans = _stt_spans_by_source(row)
        vad_span = _best_vad_span_for_consensus(row, vad, source_spans, max_gap_sec=max_gap)
        if vad_span is not None:
            source_spans["VAD"] = vad_span
        if len(source_spans) < 2:
            previous_end = row_span[1]
            continue
        consensus = _consensus_span_from_sources(
            source_spans,
            start_tolerance_sec=start_tol,
            end_tolerance_sec=end_tol,
            duration_tolerance_sec=dur_tol,
            edge_pad_sec=pad,
        )
        if consensus is None:
            previous_end = row_span[1]
            continue
        (new_start, new_end), policy = consensus
        if previous_end is not None:
            new_start = max(new_start, previous_end + min_gap)
        new_end = max(new_start + 0.05, new_end)
        if abs(new_start - row_span[0]) <= 0.001 and abs(new_end - row_span[1]) <= 0.001:
            previous_end = row_span[1]
            continue
        row["start"] = round(new_start, 3)
        row["end"] = round(new_end, 3)
        row["timeline_start"] = row["start"]
        meta = dict(row.get("asr_metadata") or {})
        meta["vad_stt_timing_consensus"] = {
            "task": "vad_stt_timing_consensus",
            "from": [round(row_span[0], 3), round(row_span[1], 3)],
            "to": [row["start"], row["end"]],
            "start_tolerance_sec": round(start_tol, 3),
            "end_tolerance_sec": round(end_tol, 3),
            "duration_tolerance_sec": round(dur_tol, 3),
            **policy,
        }
        row["asr_metadata"] = meta
        changed += 1
        previous_end = new_end

    if changed:
        rows = annotate_segments_vad_alignment(rows, vad)
    return rows, changed


def review_vad_enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(settings.get("review_vad_before_stt_enabled", False))


def review_vad_config(settings: dict[str, Any] | None) -> dict[str, Any]:
    settings = settings or {}
    enabled = review_vad_enabled(settings)
    strict = bool(settings.get("review_vad_strict_mode", True))
    return {
        "review_vad_before_stt_enabled": enabled,
        "review_vad_strict_mode": strict,
        "review_vad_speech_pad_sec": _as_float(settings.get("review_vad_speech_pad_sec"), 0.35),
        "review_vad_min_silence_sec": _as_float(settings.get("review_vad_min_silence_sec"), 0.8),
    }


def apply_review_vad_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(settings or {})
    cfg = review_vad_config(out)
    if not cfg["review_vad_before_stt_enabled"] or not cfg["review_vad_strict_mode"]:
        return out
    out["vad_speech_pad"] = max(0.0, cfg["review_vad_speech_pad_sec"])
    out["vad_min_silence"] = max(0.1, cfg["review_vad_min_silence_sec"])
    return out
