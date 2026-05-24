from __future__ import annotations

"""Durable helpers for STT recheck planning and cleanup."""

from dataclasses import dataclass
from typing import Any, Callable

from core.audio import stt_rescue
from core.native_stt_recheck import (
    low_score_primary_indices as native_low_score_primary_indices,
    match_low_score_pair_indices as native_match_low_score_pair_indices,
    overlap_range_components as native_overlap_range_components,
    overlap_segment_groups as native_overlap_segment_groups,
    uncovered_vad_indices as native_uncovered_vad_indices,
    word_precision_candidate_indices as native_word_precision_candidate_indices,
)

_RECHECK_OVERLAP_THRESHOLD = 0.18
_SEGMENT_RANGE_OVERLAP_RATIO = 0.35
_RANGE_COMPONENT_OVERLAP_RATIO = 0.92


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _segment_text(segment: dict[str, Any]) -> str:
    return str(segment.get("text") or "").strip()


def _segment_score(segment: dict[str, Any], score_fn: Callable[[dict[str, Any]], float]) -> float:
    try:
        return max(0.0, min(100.0, float(score_fn(segment) or 0.0)))
    except Exception:
        return 0.0


def normalize_scored_tracks(
    tracks: dict[str, list[dict[str, Any]]],
    *,
    keep_score: float,
    filter_fn: Callable[[list[dict[str, Any]], float], list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    normalized: dict[str, list[dict[str, Any]]] = {}
    dropped_counts: dict[str, int] = {}
    for label in ("STT1", "STT2"):
        original = [dict(seg) for seg in (tracks.get(label, []) or []) if isinstance(seg, dict)]
        filtered = filter_fn(original, float(keep_score))
        normalized[label] = filtered
        dropped_counts[label] = max(0, len(original) - len(filtered))
    return normalized, dropped_counts


def route_hint_recheck_ranges(
    primary_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    score_fn: Callable[[dict[str, Any]], float],
    apply_budget: bool = True,
) -> list[stt_rescue.SttRecheckRange]:
    ranges: list[stt_rescue.SttRecheckRange] = []
    for primary in primary_segments or []:
        if not bool(primary.get("stt_route_secondary_recheck_hint")):
            continue
        text = _segment_text(primary)
        if not text:
            continue
        start = max(0.0, _as_float(primary.get("start"), 0.0))
        end = max(_as_float(primary.get("end"), start), start + 0.1)
        score = float(score_fn(primary) or 0.0)
        ranges.append(
            stt_rescue.SttRecheckRange(
                start=round(start, 3),
                end=round(end, 3),
                primary_score=round(score, 2),
                secondary_score=0.0,
                primary_text=text,
                secondary_text="",
                primary=dict(primary),
                secondary={},
            )
        )
    if not ranges:
        return []
    if apply_budget:
        return stt_rescue.budget_recheck_ranges(ranges, settings)
    ranges.sort(key=lambda item: (item.start, item.end))
    return ranges


def _build_recheck_range(
    *,
    primary: dict[str, Any],
    secondary: dict[str, Any] | None,
    primary_score: float,
    secondary_score: float,
) -> stt_rescue.SttRecheckRange:
    secondary = dict(secondary or {})
    primary_start = max(0.0, _as_float(primary.get("start"), 0.0))
    secondary_start = _as_float(secondary.get("start"), primary_start)
    start = max(0.0, min(primary_start, secondary_start))
    primary_end = max(primary_start + 0.1, _as_float(primary.get("end"), primary_start))
    secondary_end = max(secondary_start, _as_float(secondary.get("end"), secondary_start))
    end = max(primary_end, secondary_end, start + 0.1)
    return stt_rescue.SttRecheckRange(
        start=round(start, 3),
        end=round(end, 3),
        primary_score=round(float(primary_score), 2),
        secondary_score=round(float(secondary_score), 2),
        primary_text=_segment_text(primary),
        secondary_text=_segment_text(secondary),
        primary=dict(primary),
        secondary=secondary,
    )


def _python_match_low_score_pair_indices(
    primary_segments: list[dict[str, Any]],
    secondary_segments: list[dict[str, Any]],
    *,
    threshold: float,
    score_fn: Callable[[dict[str, Any]], float],
    overlap_threshold: float,
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    used_secondary: set[int] = set()
    for primary_idx, primary in enumerate(primary_segments or []):
        if not _segment_text(primary):
            continue
        primary_score = _segment_score(primary, score_fn)
        if primary_score > threshold:
            continue
        best_idx = -1
        best_overlap = 0.0
        for secondary_idx, secondary in enumerate(secondary_segments or []):
            if secondary_idx in used_secondary or not _segment_text(secondary):
                continue
            secondary_score = _segment_score(secondary, score_fn)
            if secondary_score > threshold:
                continue
            overlap = max(
                0.0,
                min(_as_float(primary.get("end"), 0.0), _as_float(secondary.get("end"), 0.0))
                - max(_as_float(primary.get("start"), 0.0), _as_float(secondary.get("start"), 0.0)),
            )
            span = max(
                0.001,
                min(
                    max(0.0, _as_float(primary.get("end"), 0.0) - _as_float(primary.get("start"), 0.0)),
                    max(0.0, _as_float(secondary.get("end"), 0.0) - _as_float(secondary.get("start"), 0.0)),
                ),
            )
            ratio = overlap / span
            if ratio > best_overlap:
                best_idx = secondary_idx
                best_overlap = ratio
        if best_idx >= 0 and best_overlap >= overlap_threshold:
            used_secondary.add(best_idx)
            pairs.append((primary_idx, best_idx))
    return pairs


def low_score_recheck_ranges(
    primary_segments: list[dict[str, Any]],
    secondary_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    score_fn: Callable[[dict[str, Any]], float],
    overlap_threshold: float = _RECHECK_OVERLAP_THRESHOLD,
    apply_budget: bool = True,
) -> list[stt_rescue.SttRecheckRange]:
    threshold = stt_rescue.threshold(settings)
    native_pairs = native_match_low_score_pair_indices(
        primary_starts=[_as_float(seg.get("start"), 0.0) for seg in primary_segments or [] if isinstance(seg, dict)],
        primary_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in primary_segments or [] if isinstance(seg, dict)],
        primary_scores=[_segment_score(seg, score_fn) for seg in primary_segments or [] if isinstance(seg, dict)],
        primary_nonempty=[1 if _segment_text(seg) else 0 for seg in primary_segments or [] if isinstance(seg, dict)],
        secondary_starts=[_as_float(seg.get("start"), 0.0) for seg in secondary_segments or [] if isinstance(seg, dict)],
        secondary_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in secondary_segments or [] if isinstance(seg, dict)],
        secondary_scores=[_segment_score(seg, score_fn) for seg in secondary_segments or [] if isinstance(seg, dict)],
        secondary_nonempty=[1 if _segment_text(seg) else 0 for seg in secondary_segments or [] if isinstance(seg, dict)],
        threshold=float(threshold),
        overlap_threshold=float(overlap_threshold),
    )
    valid_primary = [seg for seg in primary_segments or [] if isinstance(seg, dict)]
    valid_secondary = [seg for seg in secondary_segments or [] if isinstance(seg, dict)]
    pairs = native_pairs
    if pairs is None:
        pairs = _python_match_low_score_pair_indices(
            valid_primary,
            valid_secondary,
            threshold=float(threshold),
            score_fn=score_fn,
            overlap_threshold=float(overlap_threshold),
        )
    ranges = [
        _build_recheck_range(
            primary=valid_primary[primary_idx],
            secondary=valid_secondary[secondary_idx],
            primary_score=_segment_score(valid_primary[primary_idx], score_fn),
            secondary_score=_segment_score(valid_secondary[secondary_idx], score_fn),
        )
        for primary_idx, secondary_idx in pairs
        if 0 <= primary_idx < len(valid_primary) and 0 <= secondary_idx < len(valid_secondary)
    ]
    if apply_budget:
        return stt_rescue.budget_recheck_ranges(ranges, settings)
    ranges.sort(key=lambda item: (item.start, item.end))
    return ranges


def primary_low_score_recheck_ranges(
    primary_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    score_fn: Callable[[dict[str, Any]], float],
    apply_budget: bool = True,
) -> list[stt_rescue.SttRecheckRange]:
    threshold = stt_rescue.threshold(settings)
    valid_primary = [seg for seg in primary_segments or [] if isinstance(seg, dict)]
    native_indices = native_low_score_primary_indices(
        primary_scores=[_segment_score(seg, score_fn) for seg in valid_primary],
        primary_nonempty=[1 if _segment_text(seg) else 0 for seg in valid_primary],
        threshold=float(threshold),
    )
    indices = native_indices
    if indices is None:
        indices = [
            idx for idx, seg in enumerate(valid_primary)
            if _segment_text(seg) and _segment_score(seg, score_fn) <= threshold
        ]
    ranges = [
        _build_recheck_range(
            primary=valid_primary[idx],
            secondary=None,
            primary_score=_segment_score(valid_primary[idx], score_fn),
            secondary_score=0.0,
        )
        for idx in indices
        if 0 <= idx < len(valid_primary)
    ]
    if apply_budget:
        return stt_rescue.budget_recheck_ranges(ranges, settings)
    ranges.sort(key=lambda item: (item.start, item.end))
    return ranges


def resolve_precision_model(
    settings: dict[str, Any] | None,
    *,
    primary_model: str,
) -> str:
    settings = dict(settings or {})
    configured_precision_model = str(settings.get("stt_word_timestamps_precision_model") or "").strip()
    selected_primary_model = str(settings.get("selected_whisper_model") or "").strip()
    return configured_precision_model or selected_primary_model or str(primary_model or "").strip()


def precision_pass_overrides() -> dict[str, Any]:
    return {
        "stt_ensemble_enabled": False,
        "stt_selective_secondary_recheck_enabled": False,
        "stt_candidate_scoring_enabled": True,
        "runtime_backend_autotune_enabled": False,
        "stt_backend_policy": "native",
        "stt_quality_preset": "precise",
        "stt_rescue_whisper_mode": True,
        "stt_primary_fast_native_enabled": False,
        "stt_npu_prefer_enabled": True,
        "whisperkit_native_auto_enabled": True,
        "stt_whisperkit_native_allocator_can_raise_workers": True,
        "stt_whisperkit_precision_aggressive_gpu_enabled": True,
        "stt_whisperkit_word_timestamp_concurrent_workers": 10,
        "stt_whisperkit_concurrent_max_workers": 10,
        "stt_whisperkit_gpu_saturation_max_workers": 10,
        "stt_word_timestamp_precision_pass": True,
        "stt_word_timestamps_mode": "always",
        "stt_word_timestamps_default_enabled": True,
        "stt_word_timestamps_precision_enabled": True,
        "stt_word_timestamp_worker_response_timeout_sec": 30.0,
        "stt_word_timestamp_worker_straggler_timeout_sec": 8.0,
        "stt_word_timestamp_worker_straggler_max_missing_chunks": 3,
        "stt_word_timestamp_worker_straggler_min_received_ratio": 0.86,
        "stt_word_timestamp_straggler_skip_enabled": True,
        "stt_duration_first_submission_enabled": True,
        "w_none_temp_max": 0.0,
        "whisper_chunk_overlap_sec": 0.0,
    }


def low_score_recheck_overrides() -> dict[str, Any]:
    return {
        "stt_ensemble_enabled": False,
        "stt_candidate_scoring_enabled": True,
        "stt_quality_preset": "precise",
        "stt_rescue_whisper_mode": True,
        "w_none_temp_max": 0.0,
        "whisper_chunk_overlap_sec": 0.0,
    }


def selective_secondary_recheck_overrides() -> dict[str, Any]:
    return {
        "stt_ensemble_enabled": False,
        "stt_candidate_scoring_enabled": True,
        "stt_quality_preset": "precise",
        "stt_rescue_whisper_mode": True,
        "stt_selective_secondary_recheck_enabled": False,
        "stt_word_timestamp_precision_pass": False,
        "stt_word_timestamps_mode": "off",
        "stt_word_timestamps_default_enabled": False,
        "stt_word_timestamps_precision_enabled": False,
        "stt_persistent_runtime_reuse_enabled": False,
        "stt_duration_first_submission_enabled": True,
        "w_none_temp_max": 0.0,
        "whisper_chunk_overlap_sec": 0.0,
    }


def collect_prepared_recheck_clips(
    *,
    ranges: list[stt_rescue.SttRecheckRange],
    out_dir: str,
    settings: dict[str, Any] | None,
    prepare_clip_fn: Callable[[stt_rescue.SttRecheckRange, str, int, dict[str, Any]], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    settings = dict(settings or {})
    for idx, item in enumerate(ranges or []):
        clip = prepare_clip_fn(item, out_dir, idx, settings)
        if clip:
            prepared.append(clip)
    return prepared


def annotate_candidate_segments(
    segments: list[dict[str, Any]],
    *,
    annotate_fn: Callable[..., list[dict[str, Any]]],
    source: str,
    settings: dict[str, Any] | None,
    vad_segments: list[dict[str, Any]] | None,
    peer_segments: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if not segments:
        return [], None
    try:
        annotated = annotate_fn(
            segments,
            source=source,
            peer_segments=peer_segments,
            vad_segments=vad_segments,
            settings=settings,
        )
        return list(annotated or []), None
    except Exception as exc:
        return segments, str(exc)


def collect_and_annotate_segments(
    *,
    collect_fn: Callable[..., list[dict[str, Any]]],
    chunk_dir: str,
    model: str,
    label: str,
    settings_overrides: dict[str, Any] | None,
    annotate_fn: Callable[..., list[dict[str, Any]]],
    annotate_source: str,
    settings: dict[str, Any] | None,
    vad_segments: list[dict[str, Any]] | None,
    peer_segments: list[dict[str, Any]] | None = None,
    is_single: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    segments = list(
        collect_fn(
            chunk_dir,
            model,
            is_single=is_single,
            label=label,
            settings_overrides=settings_overrides,
        )
        or []
    )
    if not segments:
        return [], None
    return annotate_candidate_segments(
        segments,
        annotate_fn=annotate_fn,
        source=annotate_source,
        settings=settings,
        vad_segments=vad_segments,
        peer_segments=peer_segments,
    )


def _python_uncovered_vad_indices(
    vad_segments: list[dict[str, Any]],
    primary_segments: list[dict[str, Any]],
    *,
    min_duration: float,
    overlap_threshold: float,
) -> list[int]:
    uncovered: list[int] = []
    for idx, vad in enumerate(vad_segments or []):
        if not isinstance(vad, dict):
            continue
        start = max(0.0, _as_float(vad.get("start"), 0.0))
        end = max(start, _as_float(vad.get("end"), start))
        if (end - start) < min_duration:
            continue
        covered = False
        for seg in primary_segments or []:
            if not _segment_text(seg):
                continue
            overlap = max(0.0, min(end, _as_float(seg.get("end"), 0.0)) - max(start, _as_float(seg.get("start"), 0.0)))
            if overlap / max(0.001, end - start) >= overlap_threshold:
                covered = True
                break
        if not covered:
            uncovered.append(idx)
    return uncovered


def uncovered_vad_indices(
    vad_segments: list[dict[str, Any]],
    primary_segments: list[dict[str, Any]],
    *,
    min_duration: float,
    overlap_threshold: float = _RECHECK_OVERLAP_THRESHOLD,
) -> list[int]:
    valid_vad_indices = [idx for idx, seg in enumerate(vad_segments or []) if isinstance(seg, dict)]
    valid_vad_segments = [vad_segments[idx] for idx in valid_vad_indices]
    valid_primary_segments = [seg for seg in list(primary_segments or []) if isinstance(seg, dict)]
    native_result = native_uncovered_vad_indices(
        vad_starts=[max(0.0, _as_float(seg.get("start"), 0.0)) for seg in valid_vad_segments],
        vad_ends=[
            max(max(0.0, _as_float(seg.get("start"), 0.0)), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0)))
            for seg in valid_vad_segments
        ],
        primary_starts=[_as_float(seg.get("start"), 0.0) for seg in valid_primary_segments],
        primary_ends=[
            max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0)))
            for seg in valid_primary_segments
        ],
        primary_nonempty=[1 if _segment_text(seg) else 0 for seg in valid_primary_segments],
        min_duration=float(min_duration),
        overlap_threshold=float(overlap_threshold),
    )
    if native_result is not None:
        return [
            valid_vad_indices[idx]
            for idx in native_result
            if 0 <= idx < len(valid_vad_indices)
        ]
    return _python_uncovered_vad_indices(
        vad_segments,
        primary_segments,
        min_duration=float(min_duration),
        overlap_threshold=float(overlap_threshold),
    )


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged: list[tuple[float, float]] = []
    for start, end in ordered:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        prev_start, prev_end = merged[-1]
        merged[-1] = (prev_start, max(prev_end, end))
    return merged


def missing_voice_candidate_spans(
    *,
    vad_segments: list[dict[str, Any]],
    primary_segments: list[dict[str, Any]],
    min_duration: float,
    internal_gap_min_duration: float,
    max_end: float | None = None,
) -> list[tuple[float, float]]:
    """Return voice spans that VAD sees but the primary STT track did not cover."""
    min_duration = max(0.2, float(min_duration))
    internal_gap_min_duration = max(min_duration, float(internal_gap_min_duration))
    spans: list[tuple[float, float]] = []
    text_segments = [seg for seg in list(primary_segments or []) if isinstance(seg, dict) and _segment_text(seg)]

    for vad in vad_segments or []:
        if not isinstance(vad, dict):
            continue
        start = max(0.0, _as_float(vad.get("start"), 0.0))
        end = max(start, _as_float(vad.get("end"), start))
        if max_end is not None:
            end = min(end, max(0.0, float(max_end)))
        if end - start < min_duration:
            continue

        covered: list[tuple[float, float]] = []
        for seg in text_segments:
            seg_start = max(0.0, _as_float(seg.get("start"), 0.0))
            seg_end = max(seg_start, _as_float(seg.get("end"), seg_start))
            overlap_start = max(start, seg_start)
            overlap_end = min(end, seg_end)
            if overlap_end > overlap_start:
                covered.append((overlap_start, overlap_end))

        # Do not treat a long VAD row as covered just because some later STT text
        # exists inside it. This keeps Macau/X5-style internal STT dropouts from
        # bypassing the selective STT2 rescue stage.
        previous = start
        for covered_start, covered_end in _merge_intervals(covered):
            gap = covered_start - previous
            if gap >= internal_gap_min_duration:
                spans.append((round(previous, 3), round(covered_start, 3)))
            previous = max(previous, covered_end)
        if end - previous >= internal_gap_min_duration:
            spans.append((round(previous, 3), round(end, 3)))

        if not covered and end - start >= min_duration:
            span = (round(start, 3), round(end, 3))
            if span not in spans:
                spans.append(span)

    spans.sort(key=lambda item: (item[0], item[1]))
    return spans


def missing_voice_recheck_ranges(
    *,
    primary_segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    existing_count: int = 0,
    min_duration: float = 0.55,
    chunk_path_for_time: Callable[[float], str],
) -> list[stt_rescue.SttRecheckRange]:
    if not vad_segments:
        return []
    limit = max(0, stt_rescue.max_recheck_segments(settings) - max(0, int(existing_count or 0)))
    if limit <= 0:
        return []

    candidates: list[stt_rescue.SttRecheckRange] = []
    internal_gap_min_duration = max(
        max(0.2, float(min_duration)),
        _as_float((settings or {}).get("stt_missing_voice_internal_gap_min_duration_sec"), 1.2),
    )
    configured_max_end = _as_float((settings or {}).get("_stt_recheck_target_end_sec"), -1.0)
    max_end = configured_max_end if configured_max_end > 0.0 else None
    for start, end in missing_voice_candidate_spans(
        vad_segments=vad_segments,
        primary_segments=primary_segments,
        min_duration=max(0.2, float(min_duration)),
        internal_gap_min_duration=internal_gap_min_duration,
        max_end=max_end,
    ):
        # Missing-voice rescue must anchor on the gap start, not the midpoint.
        # Long VAD spans can cross overlapped STT chunks; midpoint routing may
        # pick the later chunk and silently trim away the actual missing audio.
        source_path = str(chunk_path_for_time(start + 0.01) or "")
        if not source_path:
            continue
        synthetic = {
            "start": start,
            "end": end,
            "text": "",
            "score": 0.0,
            "chunk_path": source_path,
            "asr_metadata": {"chunk_path": source_path, "missing_voice_candidate": True},
        }
        candidates.append(
            stt_rescue.SttRecheckRange(
                start=round(start, 3),
                end=round(end, 3),
                primary_score=0.0,
                secondary_score=0.0,
                primary_text="",
                secondary_text="",
                primary=synthetic,
                secondary={},
            )
        )
        if len(candidates) >= limit:
            break

    if candidates:
        return candidates

    for idx in uncovered_vad_indices(
        vad_segments,
        primary_segments,
        min_duration=max(0.2, float(min_duration)),
    ):
        vad = vad_segments[idx]
        start = max(0.0, _as_float(vad.get("start"), 0.0))
        end = max(start, _as_float(vad.get("end"), start))
        source_path = str(chunk_path_for_time((start + end) / 2.0) or "")
        if not source_path:
            continue
        synthetic = {
            "start": start,
            "end": end,
            "text": "",
            "score": 0.0,
            "chunk_path": source_path,
            "asr_metadata": {"chunk_path": source_path, "missing_voice_candidate": True},
        }
        candidates.append(
            stt_rescue.SttRecheckRange(
                start=round(start, 3),
                end=round(end, 3),
                primary_score=0.0,
                secondary_score=0.0,
                primary_text="",
                secondary_text="",
                primary=synthetic,
                secondary={},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def word_precision_ranges(
    segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    *,
    needs_precision_fn: Callable[[dict[str, Any], dict[str, Any]], bool],
    score_fn: Callable[[dict[str, Any]], float],
    has_score_fn: Callable[[dict[str, Any]], bool],
) -> list[stt_rescue.SttRecheckRange]:
    settings = dict(settings or {})
    if not bool(settings.get("stt_word_timestamps_precision_enabled", True)):
        return []
    limit = max(
        1,
        min(200, int(_as_float(settings.get("stt_word_timestamps_precision_max_segments"), 24))),
    )
    max_audio_sec = max(
        10.0,
        min(1800.0, _as_float(settings.get("stt_word_timestamps_precision_max_audio_sec"), 90.0)),
    )
    starts: list[float] = []
    ends: list[float] = []
    scores: list[float] = []
    has_scores: list[int] = []
    needs_flags: list[int] = []
    selected_flags: list[int] = []
    red_flags: list[int] = []
    yellow_flags: list[int] = []
    risk_flags: list[int] = []
    missing_word_flags: list[int] = []
    ranges_by_index: dict[int, stt_rescue.SttRecheckRange] = {}
    prioritized: list[tuple[tuple[float, float, float], stt_rescue.SttRecheckRange]] = []
    for idx, seg in enumerate(segments or []):
        start = max(0.0, _as_float(seg.get("start"), 0.0))
        end = max(start + 0.1, _as_float(seg.get("end"), start))
        needs_precision = bool(needs_precision_fn(seg, settings))
        score = round(float(score_fn(seg) or 0.0), 2) if needs_precision else 0.0
        quality = dict(seg.get("quality") or {}) if needs_precision else {}
        flags = {str(flag) for flag in (quality.get("flags") or ())}
        has_score = bool(has_score_fn(seg)) if needs_precision else False
        starts.append(start)
        ends.append(end)
        scores.append(score)
        has_scores.append(1 if has_score else 0)
        needs_flags.append(1 if needs_precision else 0)
        selected_flags.append(
            1 if any(bool(seg.get(key)) for key in ("editor_selected", "selected", "precision_review", "needs_review")) else 0
        )
        label = str(quality.get("confidence_label") or "").strip().lower()
        red_flags.append(1 if label == "red" else 0)
        yellow_flags.append(1 if label == "yellow" else 0)
        risk_flags.append(1 if flags.intersection({"outside_vad_speech", "high_cps", "short_duration_long_text"}) else 0)
        missing_word_flags.append(1 if flags.intersection({"word_timestamps_missing"}) else 0)
        if not needs_precision:
            continue
        priority = 0.0
        if selected_flags[-1]:
            priority += 100.0
        if red_flags[-1]:
            priority += 40.0
        elif yellow_flags[-1]:
            priority += 20.0
        if risk_flags[-1]:
            priority += 15.0
        if missing_word_flags[-1]:
            priority += 5.0
        if has_score:
            priority += max(0.0, 100.0 - score) / 4.0
        item = stt_rescue.SttRecheckRange(
            start=round(start, 3),
            end=round(end, 3),
            primary_score=score,
            secondary_score=0.0,
            primary_text=_segment_text(seg),
            secondary_text="",
            primary=dict(seg),
            secondary={},
        )
        ranges_by_index[idx] = item
        prioritized.append(((-priority, score, start), item))
    native_indices = native_word_precision_candidate_indices(
        starts=starts,
        ends=ends,
        scores=scores,
        has_scores=has_scores,
        needs_precision=needs_flags,
        selected_flags=selected_flags,
        red_flags=red_flags,
        yellow_flags=yellow_flags,
        risk_flags=risk_flags,
        missing_word_flags=missing_word_flags,
        limit=limit,
        max_audio_sec=max_audio_sec,
    )
    if native_indices is not None:
        selected: list[stt_rescue.SttRecheckRange] = []
        seen: set[int] = set()
        for idx in native_indices:
            if idx in seen:
                continue
            seen.add(idx)
            item = ranges_by_index.get(idx)
            if item is not None:
                selected.append(item)
        return selected
    prioritized.sort(key=lambda pair: pair[0])
    selected: list[stt_rescue.SttRecheckRange] = []
    selected_sec = 0.0
    for _priority, item in prioritized:
        duration = max(0.05, float(item.end or 0.0) - float(item.start or 0.0))
        if len(selected) >= limit:
            break
        if selected and selected_sec + duration > max_audio_sec:
            continue
        selected.append(item)
        selected_sec += duration
    selected.sort(key=lambda item: (item.start, item.end))
    return selected


def _python_overlap_range_components(
    range_starts: list[float],
    range_ends: list[float],
    *,
    min_overlap_ratio: float,
) -> list[list[int]]:
    groups = overlap_segment_groups(
        range_starts=range_starts,
        range_ends=range_ends,
        segment_starts=range_starts,
        segment_ends=range_ends,
        min_overlap_ratio=min_overlap_ratio,
    )
    visited: set[int] = set()
    components: list[list[int]] = []
    for start_idx in range(len(range_starts)):
        if start_idx in visited:
            continue
        stack = [start_idx]
        component: list[int] = []
        visited.add(start_idx)
        while stack:
            current = stack.pop()
            component.append(current)
            neighbors = groups[current] if current < len(groups) else []
            for neighbor in neighbors:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))
    return components


def overlap_range_components(
    *,
    range_starts: list[float],
    range_ends: list[float],
    min_overlap_ratio: float = _RANGE_COMPONENT_OVERLAP_RATIO,
) -> list[list[int]]:
    native_result = native_overlap_range_components(
        range_starts=range_starts,
        range_ends=range_ends,
        min_overlap_ratio=float(min_overlap_ratio),
    )
    if native_result is not None:
        return native_result
    return _python_overlap_range_components(
        [float(item) for item in list(range_starts or [])],
        [float(item) for item in list(range_ends or [])],
        min_overlap_ratio=float(min_overlap_ratio),
    )


def _range_priority(item: stt_rescue.SttRecheckRange) -> tuple[float, float, float, float]:
    has_text = 0.0 if (str(item.primary_text or "").strip() or str(item.secondary_text or "").strip()) else 1.0
    best_score = float(item.best_original_score)
    duration = max(0.05, float(item.end or 0.0) - float(item.start or 0.0))
    return (has_text, best_score, -duration, float(item.start))


def _is_missing_voice_range(item: stt_rescue.SttRecheckRange) -> bool:
    if str(item.primary_text or "").strip() or str(item.secondary_text or "").strip():
        return False
    meta = dict((item.primary or {}).get("asr_metadata") or {})
    return bool(meta.get("missing_voice_candidate"))


def _collapsed_range_owner(
    items: list[stt_rescue.SttRecheckRange],
    *,
    winner: stt_rescue.SttRecheckRange,
    start: float,
) -> stt_rescue.SttRecheckRange:
    # Regression note: X5/Macau can produce a long VAD row with an internal STT
    # dropout, then a later low-score text candidate from the overlapped next
    # chunk. If the later text candidate owns the collapsed range, the prepared
    # recheck clip starts at the later chunk boundary and the missing speech is
    # trimmed away. Keep the earliest missing-voice source as owner whenever it
    # defines the collapsed start; do not "simplify" this without checking real
    # X5 timing artifacts.
    missing_at_start = [
        item
        for item in items
        if _is_missing_voice_range(item) and abs(float(item.start) - float(start)) <= 0.001
    ]
    if missing_at_start and float(missing_at_start[0].start) < float(winner.start) - 0.001:
        return min(missing_at_start, key=lambda item: (float(item.start), float(item.end)))
    return winner


def collapse_duplicate_recheck_ranges(
    ranges: list[stt_rescue.SttRecheckRange],
    *,
    min_overlap_ratio: float = _RANGE_COMPONENT_OVERLAP_RATIO,
) -> list[stt_rescue.SttRecheckRange]:
    if not ranges:
        return []
    components = overlap_range_components(
        range_starts=[float(item.start) for item in ranges],
        range_ends=[max(float(item.start), float(item.end)) for item in ranges],
        min_overlap_ratio=min_overlap_ratio,
    )
    collapsed: list[stt_rescue.SttRecheckRange] = []
    for component in components:
        items = [ranges[idx] for idx in component if 0 <= idx < len(ranges)]
        if not items:
            continue
        winner = min(items, key=_range_priority)
        start = round(min(float(item.start) for item in items), 3)
        end = round(max(max(float(item.start), float(item.end)) for item in items), 3)
        owner = _collapsed_range_owner(items, winner=winner, start=start)
        collapsed.append(
            stt_rescue.SttRecheckRange(
                start=start,
                end=max(start + 0.1, end),
                primary_score=owner.primary_score,
                secondary_score=owner.secondary_score,
                primary_text=owner.primary_text,
                secondary_text=owner.secondary_text,
                primary=dict(owner.primary),
                secondary=dict(owner.secondary),
            )
        )
    collapsed.sort(key=lambda item: (item.start, item.end))
    return collapsed


def selective_secondary_recheck_ranges(
    *,
    primary_segments: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    score_fn: Callable[[dict[str, Any]], float],
    chunk_path_for_time: Callable[[float], str],
) -> tuple[list[stt_rescue.SttRecheckRange], int]:
    settings = dict(settings or {})
    ranges: list[stt_rescue.SttRecheckRange] = list(
        primary_low_score_recheck_ranges(
            primary_segments,
            settings,
            score_fn=score_fn,
            apply_budget=False,
        )
    )
    ranges.extend(
        missing_voice_recheck_ranges(
            primary_segments=primary_segments,
            vad_segments=vad_segments,
            settings=settings,
            existing_count=0,
            min_duration=max(0.2, _as_float(settings.get("stt_missing_voice_min_duration_sec"), 0.55)),
            chunk_path_for_time=chunk_path_for_time,
        )
    )
    ranges.extend(
        route_hint_recheck_ranges(
            primary_segments,
            settings,
            score_fn=score_fn,
            apply_budget=False,
        )
    )
    collapsed = collapse_duplicate_recheck_ranges(ranges)
    raw_count = len(collapsed)
    return stt_rescue.budget_recheck_ranges(collapsed, settings), raw_count


@dataclass(frozen=True)
class RecheckReplacementBatch:
    applied_ranges: list[stt_rescue.SttRecheckRange]
    applied_segments: list[dict[str, Any]]
    skipped_ranges: list[stt_rescue.SttRecheckRange]


@dataclass(frozen=True)
class CollectedRecheckBatch:
    prepared_clips: list[dict[str, Any]]
    collected_segments: list[dict[str, Any]]
    annotate_error: str | None


@dataclass(frozen=True)
class RecheckTrackApplyResult:
    selection: RecheckReplacementBatch
    preview_tracks: dict[str, list[dict[str, Any]]]
    merged_tracks: dict[str, list[dict[str, Any]]] | None


def _python_overlap_segment_groups(
    range_starts: list[float],
    range_ends: list[float],
    segment_starts: list[float],
    segment_ends: list[float],
    *,
    min_overlap_ratio: float,
) -> list[list[int]]:
    groups: list[list[int]] = []
    for range_idx, range_start in enumerate(range_starts):
        range_end = max(float(range_start), float(range_ends[range_idx] if range_idx < len(range_ends) else range_start))
        range_duration = max(0.0, range_end - float(range_start))
        indices: list[int] = []
        for seg_idx, seg_start in enumerate(segment_starts):
            seg_end = max(float(seg_start), float(segment_ends[seg_idx] if seg_idx < len(segment_ends) else seg_start))
            overlap = max(0.0, min(seg_end, range_end) - max(float(seg_start), float(range_start)))
            span = max(0.001, min(max(0.0, seg_end - float(seg_start)), range_duration))
            if overlap / span >= min_overlap_ratio:
                indices.append(seg_idx)
        groups.append(indices)
    return groups


def overlap_segment_groups(
    *,
    range_starts: list[float],
    range_ends: list[float],
    segment_starts: list[float],
    segment_ends: list[float],
    min_overlap_ratio: float = _SEGMENT_RANGE_OVERLAP_RATIO,
) -> list[list[int]]:
    native_result = native_overlap_segment_groups(
        range_starts=range_starts,
        range_ends=range_ends,
        segment_starts=segment_starts,
        segment_ends=segment_ends,
        min_overlap_ratio=float(min_overlap_ratio),
    )
    if native_result is not None:
        return native_result
    return _python_overlap_segment_groups(
        [float(item) for item in list(range_starts or [])],
        [float(item) for item in list(range_ends or [])],
        [float(item) for item in list(segment_starts or [])],
        [float(item) for item in list(segment_ends or [])],
        min_overlap_ratio=float(min_overlap_ratio),
    )


def select_recheck_replacements(
    *,
    prepared_clips: list[dict[str, Any]],
    rescue_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    replacement_is_better_fn: Callable[[list[dict[str, Any]], stt_rescue.SttRecheckRange, dict[str, Any] | None], bool],
    mark_segments_fn: Callable[[list[dict[str, Any]], stt_rescue.SttRecheckRange], list[dict[str, Any]]],
    decorate_segment_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    overlap_ratio: float = _SEGMENT_RANGE_OVERLAP_RATIO,
) -> RecheckReplacementBatch:
    if not prepared_clips or not rescue_segments:
        return RecheckReplacementBatch(applied_ranges=[], applied_segments=[], skipped_ranges=[])

    groups = overlap_segment_groups(
        range_starts=[float(clip.get("start", 0.0) or 0.0) for clip in prepared_clips],
        range_ends=[float(clip.get("end", clip.get("start", 0.0)) or clip.get("start", 0.0) or 0.0) for clip in prepared_clips],
        segment_starts=[_as_float(seg.get("start"), 0.0) for seg in rescue_segments],
        segment_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in rescue_segments],
        min_overlap_ratio=overlap_ratio,
    )
    applied_ranges: list[stt_rescue.SttRecheckRange] = []
    applied_segments: list[dict[str, Any]] = []
    skipped_ranges: list[stt_rescue.SttRecheckRange] = []
    for clip, indices in zip(prepared_clips, groups):
        item = clip["range"]
        subset = [dict(rescue_segments[idx]) for idx in indices if 0 <= int(idx) < len(rescue_segments)]
        if not replacement_is_better_fn(subset, item, settings):
            skipped_ranges.append(item)
            continue
        marked = mark_segments_fn(subset, item)
        if decorate_segment_fn is not None:
            marked = [decorate_segment_fn(dict(seg)) for seg in marked]
        applied_ranges.append(item)
        applied_segments.extend(marked)
    return RecheckReplacementBatch(
        applied_ranges=applied_ranges,
        applied_segments=applied_segments,
        skipped_ranges=skipped_ranges,
    )


def prepare_and_collect_recheck_segments(
    *,
    ranges: list[stt_rescue.SttRecheckRange],
    out_dir: str,
    settings: dict[str, Any] | None,
    prepare_clip_fn: Callable[[stt_rescue.SttRecheckRange, str, int, dict[str, Any]], dict[str, Any] | None],
    collect_fn: Callable[..., list[dict[str, Any]]],
    model: str,
    label: str,
    settings_overrides: dict[str, Any] | None,
    annotate_fn: Callable[..., list[dict[str, Any]]],
    annotate_source: str,
    vad_segments: list[dict[str, Any]] | None,
    peer_segments: list[dict[str, Any]] | None = None,
    is_single: bool = False,
) -> CollectedRecheckBatch:
    prepared = collect_prepared_recheck_clips(
        ranges=ranges,
        out_dir=out_dir,
        settings=settings,
        prepare_clip_fn=prepare_clip_fn,
    )
    if not prepared:
        return CollectedRecheckBatch(prepared_clips=[], collected_segments=[], annotate_error=None)
    collected_segments, annotate_error = collect_and_annotate_segments(
        collect_fn=collect_fn,
        chunk_dir=out_dir,
        model=model,
        label=label,
        settings_overrides=settings_overrides,
        annotate_fn=annotate_fn,
        annotate_source=annotate_source,
        settings=settings,
        vad_segments=vad_segments,
        peer_segments=peer_segments,
        is_single=is_single,
    )
    return CollectedRecheckBatch(
        prepared_clips=prepared,
        collected_segments=collected_segments,
        annotate_error=annotate_error,
    )


def apply_recheck_selection_to_tracks(
    *,
    prepared_clips: list[dict[str, Any]],
    rescue_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None,
    replacement_is_better_fn: Callable[[list[dict[str, Any]], stt_rescue.SttRecheckRange, dict[str, Any] | None], bool],
    mark_segments_fn: Callable[[list[dict[str, Any]], stt_rescue.SttRecheckRange], list[dict[str, Any]]],
    base_tracks: dict[str, list[dict[str, Any]]],
    decorate_segment_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    track_segment_copies: dict[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] | None = None,
    retention_ratios: dict[str, float | None] | None = None,
    overlap_ratio: float = _SEGMENT_RANGE_OVERLAP_RATIO,
) -> RecheckTrackApplyResult:
    selection = select_recheck_replacements(
        prepared_clips=prepared_clips,
        rescue_segments=rescue_segments,
        settings=settings,
        replacement_is_better_fn=replacement_is_better_fn,
        mark_segments_fn=mark_segments_fn,
        decorate_segment_fn=decorate_segment_fn,
        overlap_ratio=overlap_ratio,
    )
    if not selection.applied_segments:
        return RecheckTrackApplyResult(
            selection=selection,
            preview_tracks={},
            merged_tracks={},
        )

    preview_tracks: dict[str, list[dict[str, Any]]] = {}
    merged_tracks: dict[str, list[dict[str, Any]]] = {}
    for track_name, base_segments in dict(base_tracks or {}).items():
        copy_fn = (track_segment_copies or {}).get(track_name)
        if callable(copy_fn):
            applied_segments = copy_fn(selection.applied_segments)
        else:
            applied_segments = [dict(seg) for seg in selection.applied_segments]
        preview = merge_segments_with_replacements(
            base_segments=base_segments,
            applied_ranges=selection.applied_ranges,
            applied_segments=applied_segments,
            overlap_ratio=overlap_ratio,
        )
        preview_tracks[track_name] = list(preview or [])
        retention_ratio = (retention_ratios or {}).get(track_name) if retention_ratios else None
        merged = preview
        if retention_ratio is not None and not _meets_retention_ratio(
            base_segments=base_segments,
            merged_segments=preview,
            min_retention_ratio=retention_ratio,
        ):
            return RecheckTrackApplyResult(
                selection=selection,
                preview_tracks=preview_tracks,
                merged_tracks=None,
            )
        merged_tracks[track_name] = list(merged or [])
    return RecheckTrackApplyResult(
        selection=selection,
        preview_tracks=preview_tracks,
        merged_tracks=merged_tracks,
    )


def _meets_retention_ratio(
    *,
    base_segments: list[dict[str, Any]],
    merged_segments: list[dict[str, Any]],
    min_retention_ratio: float | None,
) -> bool:
    if min_retention_ratio is None or not base_segments:
        return True
    minimum_kept = max(1, int(len(base_segments) * float(min_retention_ratio)))
    return len(list(merged_segments or [])) >= minimum_kept


def merge_segments_with_replacements(
    *,
    base_segments: list[dict[str, Any]],
    applied_ranges: list[stt_rescue.SttRecheckRange],
    applied_segments: list[dict[str, Any]],
    min_retention_ratio: float | None = None,
    overlap_ratio: float = _SEGMENT_RANGE_OVERLAP_RATIO,
) -> list[dict[str, Any]] | None:
    if not applied_ranges:
        updated = [seg for seg in base_segments or []]
        updated.sort(key=lambda seg: (_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), 0.0)))
        return updated

    # Regression note: STT2 rescue ranges are padded/wide requests, not a proof
    # that STT2 produced replacement text for the whole span. Dropping STT1 by
    # the request range deleted correct X5/Macau STT1 text when STT2 only
    # returned a later fragment. Keep this anchored to actual replacement
    # segment spans so blank parts of a recheck never erase accurate STT1 text.
    effective_ranges = [
        (
            _as_float(seg.get("start"), 0.0),
            max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))),
        )
        for seg in list(applied_segments or [])
        if _segment_text(seg)
    ]
    if not effective_ranges:
        effective_ranges = [
            (float(item.start), max(float(item.start), float(item.end)))
            for item in applied_ranges
        ]
    range_starts = [start for start, _end in effective_ranges]
    range_ends = [end for _start, end in effective_ranges]
    segment_starts = [_as_float(seg.get("start"), 0.0) for seg in base_segments or []]
    segment_ends = [max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in base_segments or []]
    groups = overlap_segment_groups(
        range_starts=range_starts,
        range_ends=range_ends,
        segment_starts=segment_starts,
        segment_ends=segment_ends,
        min_overlap_ratio=overlap_ratio,
    )
    dropped_indices = {idx for row in groups for idx in row}
    updated = [seg for idx, seg in enumerate(base_segments or []) if idx not in dropped_indices] + list(applied_segments or [])
    updated.sort(key=lambda seg: (_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), 0.0)))
    if not _meets_retention_ratio(
        base_segments=base_segments,
        merged_segments=updated,
        min_retention_ratio=min_retention_ratio,
    ):
        return None
    return updated


def _word_precision_edges(
    candidate: dict[str, Any],
    *,
    fallback_start: float,
    fallback_end: float,
) -> tuple[float, float, list[dict[str, Any]]] | None:
    words = [dict(word) for word in (candidate.get("words") or [])]
    if not words:
        return None
    start = _as_float(words[0].get("start", candidate.get("start", fallback_start)), fallback_start)
    end = _as_float(words[-1].get("end", candidate.get("end", fallback_end)), fallback_end)
    if end <= start + 0.05:
        return None
    return start, end, words


def _word_precision_split_replacements(
    *,
    base: dict[str, Any],
    candidates: list[dict[str, Any]],
    settings: dict[str, Any],
    score_fn: Callable[[dict[str, Any]], float],
    text_similarity_fn: Callable[[str, str], float] | None,
    min_similarity: float,
    max_timing_shift: float,
) -> list[dict[str, Any]]:
    if len(candidates) < 2:
        return []
    original_start = _as_float(base.get("start"), 0.0)
    original_end = max(original_start, _as_float(base.get("end"), original_start))
    original_text = _segment_text(base)
    if not original_text:
        return []
    base_duration = original_end - original_start
    split_min_base_duration = max(
        0.8,
        _as_float(settings.get("stt_word_timestamps_precision_split_min_base_duration_sec"), 3.0),
    )
    if base_duration < split_min_base_duration:
        return []

    prepared: list[tuple[float, float, dict[str, Any], list[dict[str, Any]]]] = []
    seen: set[tuple[int, int, str]] = set()
    for candidate in sorted(candidates, key=lambda item: (_as_float(item.get("start"), 0.0), _as_float(item.get("end"), 0.0))):
        text = _segment_text(candidate)
        if not text:
            continue
        edges = _word_precision_edges(candidate, fallback_start=original_start, fallback_end=original_end)
        if edges is None:
            continue
        start, end, words = edges
        if start < original_start - max_timing_shift or end > original_end + max_timing_shift:
            continue
        if end - start < 0.28:
            continue
        key = (int(round(start * 1000)), int(round(end * 1000)), text)
        if key in seen:
            continue
        seen.add(key)
        prepared.append((start, end, dict(candidate), words))

    if len(prepared) < 2:
        return []
    combined_text = " ".join(_segment_text(candidate) for _start, _end, candidate, _words in prepared).strip()
    if callable(text_similarity_fn):
        similarity = float(text_similarity_fn(original_text, combined_text) or 0.0)
    else:
        similarity = 1.0 if original_text == combined_text else 0.5
    # 변경 금지: word-timestamp 분할은 타이밍을 정밀하게 만들기 위한 장치이지
    # STT1 원문을 축약하거나 누락시키는 교정 단계가 아니다. X5에서
    # "아 이 시트! 시트 되게 편해요"가 "이 시트 / 시트"로 쪼개지며
    # 뒤 자막이 한 칸씩 밀린 회귀가 있었으므로, 여러 후보를 합친 텍스트가
    # 원문을 충분히 보존할 때만 분할한다.
    split_min_similarity = max(
        float(min_similarity),
        min(1.0, max(0.74, _as_float(settings.get("stt_word_timestamps_precision_split_min_similarity"), 0.74))),
    )
    if similarity < split_min_similarity:
        return []

    combined_start = min(start for start, _end, _candidate, _words in prepared)
    combined_end = max(end for _start, end, _candidate, _words in prepared)
    if max(abs(combined_start - original_start), abs(combined_end - original_end)) > max_timing_shift:
        return []

    replacements: list[dict[str, Any]] = []
    split_count = len(prepared)
    for split_idx, (start, end, candidate, words) in enumerate(prepared):
        out = dict(base)
        out["start"] = start
        out["end"] = end
        # 변경 금지: 긴 STT1 자막 하나를 word-timestamp 후보 여러 개로
        # 나눌 때는 원문 전체를 각 조각에 복제하지 않는다. X5 회귀 원인은
        # 정확한 word 후보가 있었는데도 단일 후보 비교만 하며 분할을 버린 점이었다.
        out["text"] = _segment_text(candidate)
        out["words"] = words
        for key in (
            "quality",
            "score",
            "stt_score",
            "score_color",
            "stt_score_color",
            "stt_score_label",
            "stt_score_flags",
            "stt_score_components",
            "word_count",
        ):
            if key in candidate:
                out[key] = candidate[key]
        meta = dict(out.get("asr_metadata") or {})
        meta["selective_word_timestamps"] = {
            "enabled": True,
            "source": str(candidate.get("stt_selected_source") or candidate.get("stt_ensemble_source") or "STT1"),
            "similarity": round(similarity, 6),
            "kept_original_text": False,
            "split_from_base": True,
            "split_index": split_idx,
            "split_count": split_count,
            "edge_shift": round(max(abs(start - original_start), abs(end - original_end)), 4),
            "range_start": round(original_start, 3),
            "range_end": round(original_end, 3),
        }
        out["asr_metadata"] = meta
        out["stt_word_precision_applied"] = True
        out["stt_word_precision_split_applied"] = True
        if "stt_selected_source" not in out:
            out["stt_selected_source"] = str(base.get("stt_selected_source") or "STT1")
        if "stt_ensemble_source" not in out:
            out["stt_ensemble_source"] = str(base.get("stt_ensemble_source") or "STT1_SELECTIVE")
        replacements.append(out)

    replacements.sort(key=lambda seg: (_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), 0.0)))
    return replacements


def apply_word_precision_segments(
    *,
    base_segments: list[dict[str, Any]],
    precision_segments: list[dict[str, Any]],
    ranges: list[stt_rescue.SttRecheckRange],
    settings: dict[str, Any] | None,
    score_fn: Callable[[dict[str, Any]], float],
    text_similarity_fn: Callable[[str, str], float] | None,
) -> tuple[list[dict[str, Any]], int]:
    if not base_segments or not precision_segments or not ranges:
        return base_segments, 0

    settings = dict(settings or {})
    keep_text = bool(settings.get("stt_word_timestamps_precision_keep_text", True))
    min_similarity = max(0.0, min(1.0, _as_float(settings.get("stt_word_timestamps_precision_min_similarity"), 0.18)))
    max_timing_shift = max(0.05, _as_float(settings.get("stt_word_timestamps_precision_max_timing_shift_sec"), 0.55))
    min_duration_ratio = max(0.05, _as_float(settings.get("stt_word_timestamps_precision_min_duration_ratio"), 0.45))
    max_duration_ratio = max(min_duration_ratio, _as_float(settings.get("stt_word_timestamps_precision_max_duration_ratio"), 1.8))

    range_groups = overlap_segment_groups(
        range_starts=[float(item.start) for item in ranges],
        range_ends=[max(float(item.start), float(item.end)) for item in ranges],
        segment_starts=[_as_float(seg.get("start"), 0.0) for seg in base_segments],
        segment_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in base_segments],
    )
    targeted_base_indices = {idx for group in range_groups for idx in group}
    candidate_groups = overlap_segment_groups(
        range_starts=[_as_float(seg.get("start"), 0.0) for seg in base_segments],
        range_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in base_segments],
        segment_starts=[_as_float(seg.get("start"), 0.0) for seg in precision_segments],
        segment_ends=[max(_as_float(seg.get("start"), 0.0), _as_float(seg.get("end"), _as_float(seg.get("start"), 0.0))) for seg in precision_segments],
    )

    applied = 0
    updated: list[dict[str, Any]] = []
    for base_idx, seg in enumerate(base_segments):
        if base_idx not in targeted_base_indices:
            updated.append(seg)
            continue
        candidate_indices = candidate_groups[base_idx] if base_idx < len(candidate_groups) else []
        candidates = [
            dict(precision_segments[idx])
            for idx in candidate_indices
            if 0 <= idx < len(precision_segments) and precision_segments[idx].get("words")
        ]
        if not candidates:
            updated.append(seg)
            continue
        candidates.sort(
            key=lambda candidate: (
                float(score_fn(candidate) or 0.0),
                len(candidate.get("words") or []),
            ),
            reverse=True,
        )
        split_replacements = _word_precision_split_replacements(
            base=seg,
            candidates=candidates,
            settings=settings,
            score_fn=score_fn,
            text_similarity_fn=text_similarity_fn,
            min_similarity=min_similarity,
            max_timing_shift=max_timing_shift,
        )
        if split_replacements:
            updated.extend(split_replacements)
            applied += len(split_replacements)
            continue
        chosen = candidates[0]
        if callable(text_similarity_fn):
            similarity = float(text_similarity_fn(str(seg.get("text") or ""), str(chosen.get("text") or "")) or 0.0)
        else:
            similarity = 1.0 if _segment_text(seg) == _segment_text(chosen) else 0.5
        if similarity < min_similarity:
            updated.append(seg)
            continue

        original_start = _as_float(seg.get("start"), 0.0)
        original_end = max(original_start, _as_float(seg.get("end"), original_start))
        edges = _word_precision_edges(chosen, fallback_start=original_start, fallback_end=original_end)
        if edges is None:
            updated.append(seg)
            continue
        new_start, new_end, words = edges

        edge_shift = max(abs(new_start - original_start), abs(new_end - original_end))
        original_duration = max(0.05, original_end - original_start)
        new_duration = max(0.05, new_end - new_start)
        duration_ratio = new_duration / original_duration
        if edge_shift > max_timing_shift:
            updated.append(seg)
            continue
        if original_duration >= 0.2 and not (min_duration_ratio <= duration_ratio <= max_duration_ratio):
            updated.append(seg)
            continue

        out = dict(seg)
        out["words"] = words
        out["start"] = new_start
        out["end"] = new_end
        if not keep_text and _segment_text(chosen):
            out["text"] = _segment_text(chosen)
        meta = dict(out.get("asr_metadata") or {})
        meta["selective_word_timestamps"] = {
            "enabled": True,
            "source": str(chosen.get("stt_selected_source") or chosen.get("stt_ensemble_source") or "STT1"),
            "similarity": round(similarity, 6),
            "kept_original_text": bool(keep_text),
            "edge_shift": round(edge_shift, 4),
            "duration_ratio": round(duration_ratio, 4),
            "range_start": round(original_start, 3),
            "range_end": round(original_end, 3),
        }
        out["asr_metadata"] = meta
        out["stt_word_precision_applied"] = True
        updated.append(out)
        applied += 1
    return updated, applied


__all__ = [
    "apply_word_precision_segments",
    "apply_recheck_selection_to_tracks",
    "annotate_candidate_segments",
    "CollectedRecheckBatch",
    "RecheckTrackApplyResult",
    "collapse_duplicate_recheck_ranges",
    "collect_prepared_recheck_clips",
    "collect_and_annotate_segments",
    "low_score_recheck_overrides",
    "low_score_recheck_ranges",
    "prepare_and_collect_recheck_segments",
    "precision_pass_overrides",
    "RecheckReplacementBatch",
    "overlap_range_components",
    "missing_voice_recheck_ranges",
    "merge_segments_with_replacements",
    "normalize_scored_tracks",
    "overlap_segment_groups",
    "primary_low_score_recheck_ranges",
    "resolve_precision_model",
    "route_hint_recheck_ranges",
    "selective_secondary_recheck_ranges",
    "select_recheck_replacements",
    "selective_secondary_recheck_overrides",
    "uncovered_vad_indices",
    "word_precision_ranges",
]
