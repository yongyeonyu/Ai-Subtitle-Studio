# Version: 03.14.29
# Phase: PHASE2
"""Final subtitle timing and frame-field adjustment helpers."""

from core.engine.subtitle_timing_contracts import (
    COMMON_SPLIT_GUARD_SCHEMA,
    TIMING_FUSION_SCHEMA,
    build_timing_frame_fields,
    build_timing_fusion_policy,
    compact_timing_text,
    segment_scope_key,
    segment_time_bounds,
    timing_float,
)
from core.engine.subtitle_settings import _get_user_settings, _setting_float
from core.frame_time import (
    frame_to_sec,
    normalize_fps,
    sec_to_frame,
)
from core.runtime.logger import get_logger

try:
    from core.native_swift_common_split import plan_common_split_via_swift
except Exception:  # pragma: no cover - optional macOS native bridge
    plan_common_split_via_swift = None  # type: ignore[assignment]


_as_float = timing_float
_compact_text = compact_timing_text
_segment_scope_key = segment_scope_key
_time_bounds = segment_time_bounds


def _setting_bool(settings: dict, key: str, default: bool = True) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    return bool(value)


def _clamp_float(value, lo: float, hi: float, default: float) -> float:
    try:
        raw = float(value)
    except Exception:
        raw = float(default)
    return max(lo, min(hi, raw))


def _clamp_int(value, lo: int, hi: int, default: int) -> int:
    try:
        raw = int(round(float(value)))
    except Exception:
        raw = int(default)
    return max(lo, min(hi, raw))


def _cut_scene_bounds(seg: dict) -> tuple[float | None, float | None]:
    start = seg.get("cut_scene_start")
    end = seg.get("cut_scene_end")
    if start is None and seg.get("cut_scene_start_frame") is not None:
        fps = seg.get("timeline_frame_rate") or seg.get("frame_rate") or seg.get("fps")
        if fps not in (None, ""):
            try:
                start = frame_to_sec(int(seg.get("cut_scene_start_frame")), normalize_fps(fps))
            except Exception:
                start = None
    if end is None and seg.get("cut_scene_end_frame") is not None:
        fps = seg.get("timeline_frame_rate") or seg.get("frame_rate") or seg.get("fps")
        if fps not in (None, ""):
            try:
                end = frame_to_sec(int(seg.get("cut_scene_end_frame")), normalize_fps(fps))
            except Exception:
                end = None
    try:
        start_value = float(start) if start is not None else None
    except Exception:
        start_value = None
    try:
        end_value = float(end) if end is not None else None
    except Exception:
        end_value = None
    return start_value, end_value


def _score_to_percent(value, default: float = 0.0) -> float:
    try:
        score = float(value)
    except Exception:
        return default
    return max(0.0, min(100.0, score * 100.0 if 0.0 <= score <= 1.0 else score))


def _segment_boundary_confidence(seg: dict) -> float:
    scores: list[float] = []
    profile = dict(seg.get("_lora_generation_profile") or {})
    if profile.get("top_score") is not None:
        scores.append(_score_to_percent(profile.get("top_score")))
    quality = dict(seg.get("quality") or {})
    for key in ("confidence_score", "score"):
        if quality.get(key) is not None:
            scores.append(_score_to_percent(quality.get(key)))
    for key in ("score", "stt_score", "_lora_segment_score"):
        if seg.get(key) is not None:
            scores.append(_score_to_percent(seg.get(key)))
    lattice = dict(seg.get("_stt_lattice_policy") or {})
    if lattice.get("confidence") is not None:
        scores.append(_score_to_percent(lattice.get("confidence")))
    verifier = dict(seg.get("_llm_verifier_policy") or {})
    if verifier.get("accepted") and verifier.get("similarity") is not None:
        scores.append(_score_to_percent(verifier.get("similarity")))
    return max(scores or [0.0])


def _cut_crossing_evidence(seg: dict, settings: dict) -> dict:
    profile = dict(seg.get("_lora_generation_profile") or {})
    quality = dict(seg.get("quality") or {})
    lattice = dict(seg.get("_stt_lattice_policy") or {})
    verifier = dict(seg.get("_llm_verifier_policy") or {})
    threshold = max(0.0, min(100.0, _setting_float(settings, "subtitle_cut_boundary_high_confidence_score", 96.0)))
    evidence = {
        "threshold": round(threshold, 3),
        "combined_confidence": round(_segment_boundary_confidence(seg), 3),
        "lora_score": round(_score_to_percent(profile.get("top_score")), 3) if profile.get("top_score") is not None else None,
        "segment_score": round(_score_to_percent(seg.get("score", seg.get("stt_score"))), 3) if seg.get("score", seg.get("stt_score")) is not None else None,
        "quality_score": round(_score_to_percent(quality.get("confidence_score", quality.get("score"))), 3) if quality else None,
        "stt_lattice_confidence": round(_score_to_percent(lattice.get("confidence")), 3) if lattice.get("confidence") is not None else None,
        "llm_verifier_similarity": round(_score_to_percent(verifier.get("similarity")), 3) if verifier.get("accepted") and verifier.get("similarity") is not None else None,
    }
    return {key: value for key, value in evidence.items() if value is not None}


def _allow_cut_scene_crossing(seg: dict, settings: dict) -> bool:
    enabled = settings.get("subtitle_cut_boundary_allow_high_confidence_crossing", False)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return False
    evidence = _cut_crossing_evidence(seg, settings)
    return evidence.get("combined_confidence", 0.0) >= evidence.get("threshold", 96.0)


def _clamp_to_cut_scene(seg: dict, settings: dict, *, min_duration: float) -> None:
    if seg.get("is_gap"):
        return
    enabled = settings.get("subtitle_cut_boundary_guard_enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "off", "no", "끔"}
    if not enabled:
        return
    scene_start, scene_end = _cut_scene_bounds(seg)
    if scene_start is None and scene_end is None:
        return
    start = float(seg.get("start", 0.0) or 0.0)
    end = float(seg.get("end", start) or start)
    crossed_start = scene_start is not None and start < scene_start
    crossed_end = scene_end is not None and end > scene_end
    if not (crossed_start or crossed_end):
        return
    confidence = _segment_boundary_confidence(seg)
    if _allow_cut_scene_crossing(seg, settings):
        evidence = _cut_crossing_evidence(seg, settings)
        seg["_cut_boundary_guard_policy"] = {
            "task": "subtitle_cut_boundary_guard",
            "action": "allowed_high_confidence_crossing",
            "confidence": round(confidence, 3),
            "scene_start": scene_start,
            "scene_end": scene_end,
            "hard_cut_crossing_exception": True,
            "evidence": evidence,
        }
        return

    new_start = max(start, scene_start) if scene_start is not None else start
    new_end = min(end, scene_end) if scene_end is not None else end
    min_duration = max(0.02, float(min_duration or 0.05))
    if new_end <= new_start + min_duration:
        if scene_end is not None:
            new_end = scene_end
            new_start = max(scene_start or 0.0, new_end - min_duration)
        else:
            new_end = new_start + min_duration
    seg["start"] = round(max(0.0, new_start), 3)
    seg["end"] = round(max(seg["start"] + 0.02, new_end), 3)
    seg["_cut_boundary_guard_policy"] = {
        "task": "subtitle_cut_boundary_guard",
        "action": "clamped_to_cut_scene",
        "confidence": round(confidence, 3),
        "scene_start": scene_start,
        "scene_end": scene_end,
        "old_start": round(start, 3),
        "old_end": round(end, 3),
        "new_start": seg["start"],
        "new_end": seg["end"],
        "hard_cut_crossing_exception": False,
        "evidence": _cut_crossing_evidence(seg, settings),
    }
    if "words" in seg and isinstance(seg.get("words"), list):
        seg["words"] = [
            dict(word)
            for word in seg.get("words") or []
            if max(seg["start"], _as_float(word.get("start"), seg["start"]))
            < min(seg["end"], _as_float(word.get("end"), seg["end"]))
        ]


def _same_timing_scope(prev: dict, cur: dict) -> bool:
    prev_key = _segment_scope_key(prev)
    cur_key = _segment_scope_key(cur)
    if prev_key is None and cur_key is None:
        return True
    return prev_key == cur_key


def _gap_scope_key(seg: dict) -> tuple[str, str] | None:
    key = _segment_scope_key(seg)
    if isinstance(key, tuple) and key:
        if key[0] == "cut_scene":
            clip_key = key[1]
            return clip_key if isinstance(clip_key, tuple) else None
        if key[0] in {"clip_idx", "clip_file"} and len(key) >= 2:
            return key[0], str(key[1])
    return None


def _same_gap_scope(left: dict, right: dict) -> bool:
    left_key = _gap_scope_key(left)
    right_key = _gap_scope_key(right)
    if left_key is None and right_key is None:
        return True
    return left_key == right_key


def _update_frame_fields(seg: dict, start: float, end: float) -> None:
    fps_value = seg.get("timeline_frame_rate") or seg.get("frame_rate") or seg.get("fps")
    start_anchor, _ = _subtitle_start_anchor(seg)
    end_anchor, _ = _subtitle_end_anchor(seg)
    anchor_safe = bool(
        seg.get("_timing_anchor_policy")
        or seg.get("_timing_anchor_window_policy")
        or start_anchor is not None
        or end_anchor is not None
    )
    fields = build_timing_frame_fields(start, end, fps_value, anchor_safe=anchor_safe)
    if fields is None:
        return
    seg.update(fields)


def _as_time(row: dict) -> float | None:
    for key in ("timeline_sec", "time_sec", "sec", "time", "start", "end"):
        if row.get(key) not in (None, ""):
            return _as_float(row.get(key), 0.0)
    frame = row.get("frame", row.get("timeline_frame"))
    fps = row.get("timeline_frame_rate", row.get("frame_rate"))
    if frame is not None and fps not in (None, ""):
        try:
            return frame_to_sec(int(frame), normalize_fps(fps))
        except Exception:
            return None
    return None


def _segment_gap_settings(base: dict, segment: dict) -> dict:
    merged = dict(base or {})
    for key in ("_lora_segment_settings", "_lora_gap_settings"):
        payload = segment.get(key)
        if isinstance(payload, dict):
            merged.update(payload)
    return merged


def _lora_split_floor_chars(settings: dict, segment: dict) -> int:
    if not _setting_bool(settings, "subtitle_lora_split_floor_enabled", True):
        return 0
    has_lora_style = bool(
        segment.get("_lora_segment_settings")
        or segment.get("_lora_gap_settings")
        or segment.get("_lora_generation_profile")
        or segment.get("_lora_segment_score") is not None
    )
    if not has_lora_style:
        return 0
    return _clamp_int(settings.get("subtitle_lora_split_floor_chars"), 12, 36, 20)


def _word_span(seg: dict) -> tuple[float, float] | None:
    words = [word for word in list(seg.get("words") or []) if isinstance(word, dict)]
    if not words:
        return None
    starts = [_as_float(word.get("start"), 0.0) for word in words if word.get("start") not in (None, "")]
    ends = [_as_float(word.get("end"), 0.0) for word in words if word.get("end") not in (None, "")]
    if not starts or not ends:
        return None
    start = min(starts)
    end = max(ends)
    if end <= start:
        return None
    seg_start, seg_end = _time_bounds(seg)
    seg_dur = max(0.05, seg_end - seg_start)
    if (
        seg_start > 5.0
        and start < 2.0
        and end <= max(2.0, seg_dur + 1.0)
        and abs(start - seg_start) > 2.0
    ):
        return None
    return start, end


def _selected_stt_candidate_span(seg: dict) -> tuple[float, float] | None:
    word_span = _word_span(seg)
    if word_span is not None and isinstance(seg.get("_stt_word_match_timing_policy"), dict):
        return word_span

    def _prefer_word_span(bounds: tuple[float, float]) -> tuple[float, float]:
        if word_span is None or bool(seg.get("manual_stt_candidate_locked")):
            return bounds
        overlap = max(0.0, min(bounds[1], word_span[1]) - max(bounds[0], word_span[0]))
        base = max(0.001, min(bounds[1] - bounds[0], word_span[1] - word_span[0]))
        if overlap / base < 0.25 and max(abs(bounds[0] - word_span[0]), abs(bounds[1] - word_span[1])) > 0.35:
            return word_span
        return bounds

    raw_start = _as_float(
        seg.get(
            "_stt_original_candidate_start",
            seg.get("original_start"),
        ),
        None,
    )
    raw_end = _as_float(
        seg.get(
            "_stt_original_candidate_end",
            seg.get("original_end"),
        ),
        raw_start,
    ) if raw_start is not None else None
    if raw_start is not None and raw_end is not None and raw_end > raw_start:
        return _prefer_word_span((raw_start, raw_end))

    candidates = [dict(candidate) for candidate in list(seg.get("stt_candidates") or []) if isinstance(candidate, dict)]
    if not candidates:
        return None

    selected_sources: list[str] = []
    for key in (
        "stt_selected_source",
        "stt_ensemble_llm_selected_source",
        "stt_ensemble_source",
        "stt_ensemble_fast_selected_source",
        "stt_ensemble_deep_selected_source",
    ):
        value = str(seg.get(key, "") or "").strip().upper()
        if value and value not in selected_sources:
            selected_sources.append(value)

    def _candidate_bounds(candidate: dict) -> tuple[float, float] | None:
        start = _as_float(
            candidate.get(
                "original_start",
                candidate.get("_stt_original_candidate_start", candidate.get("start")),
            ),
            0.0,
        )
        end = _as_float(
            candidate.get(
                "original_end",
                candidate.get("_stt_original_candidate_end", candidate.get("end")),
            ),
            start,
        )
        if end <= start:
            candidate_word = _word_span(candidate)
            return candidate_word
        candidate_word = _word_span(candidate)
        if candidate_word is not None:
            overlap = max(0.0, min(end, candidate_word[1]) - max(start, candidate_word[0]))
            base = max(0.001, min(end - start, candidate_word[1] - candidate_word[0]))
            if overlap / base < 0.25 and max(abs(start - candidate_word[0]), abs(end - candidate_word[1])) > 0.35:
                return candidate_word
        return start, end

    for source in selected_sources:
        for candidate in candidates:
            candidate_source = str(
                candidate.get("source")
                or candidate.get("stt_source")
                or candidate.get("stt_preview_source")
                or candidate.get("stt_ensemble_source")
                or ""
            ).strip().upper()
            if candidate_source != source:
                continue
            bounds = _candidate_bounds(candidate)
            if bounds is not None:
                return bounds

    seg_text = _compact_text(seg.get("text", ""))
    if seg_text:
        for candidate in candidates:
            candidate_text = _compact_text(candidate.get("text", ""))
            if candidate_text != seg_text:
                continue
            bounds = _candidate_bounds(candidate)
            if bounds is not None:
                return bounds

    start, end = _time_bounds(seg)
    best: tuple[float, tuple[float, float]] | None = None
    for candidate in candidates:
        bounds = _candidate_bounds(candidate)
        if bounds is None:
            continue
        overlap = max(0.0, min(end, bounds[1]) - max(start, bounds[0]))
        candidate_duration = max(0.001, bounds[1] - bounds[0])
        segment_duration = max(0.001, end - start)
        score = (overlap / candidate_duration) * 0.65 + (overlap / segment_duration) * 0.35
        if best is None or score > best[0]:
            best = (score, bounds)
    return best[1] if best is not None and best[0] > 0.0 else None


def _subtitle_start_anchor(seg: dict) -> tuple[float | None, str | None]:
    anchors: list[tuple[float, str]] = []
    word = _word_span(seg)
    if word is not None:
        anchors.append((float(word[0]), "word_timestamp"))
    candidate = _selected_stt_candidate_span(seg)
    if candidate is not None:
        anchors.append((float(candidate[0]), "selected_stt_candidate"))
    if not anchors:
        return None, None
    start, source = max(anchors, key=lambda item: item[0])
    return start, source


def _subtitle_end_anchor(seg: dict) -> tuple[float | None, str | None]:
    word = _word_span(seg)
    if word is not None:
        return float(word[1]), "word_timestamp"
    candidate = _selected_stt_candidate_span(seg)
    if candidate is not None:
        return float(candidate[1]), "selected_stt_candidate"
    return None, None


def _clamp_segment_start_to_anchor(seg: dict, start: float, end: float, min_duration: float) -> tuple[float, float]:
    anchor_start, anchor_source = _subtitle_start_anchor(seg)
    if anchor_start is None or start >= anchor_start:
        return start, end
    end = max(end, anchor_start + max(0.05, min_duration))
    start = anchor_start
    policy = dict(seg.get("_timing_anchor_policy") or {})
    policy.update(
        {
            "task": "subtitle_timing_anchor",
            "anchor_source": anchor_source,
            "anchor_start": round(anchor_start, 3),
            "applied_start": round(start, 3),
        }
    )
    seg["_timing_anchor_policy"] = policy
    return start, end


def _clamp_segment_to_anchor_window(
    seg: dict,
    start: float,
    end: float,
    min_duration: float,
    settings: dict | None = None,
) -> tuple[float, float]:
    s = dict(settings or {})
    start_anchor, start_source = _subtitle_start_anchor(seg)
    end_anchor, end_source = _subtitle_end_anchor(seg)
    if start_anchor is None and end_anchor is None:
        return start, end

    max_start_lag = max(0.0, _setting_float(s, "subtitle_timing_anchor_max_start_lag_sec", 0.12))
    max_end_lead = max(0.0, _setting_float(s, "subtitle_timing_anchor_max_end_lead_sec", 0.12))
    max_end_lag = max(0.0, _setting_float(s, "subtitle_timing_anchor_max_end_lag_sec", 0.18))

    old_start = start
    old_end = end
    policy = dict(seg.get("_timing_anchor_window_policy") or {})
    adjustments: list[dict] = []

    if start_anchor is not None:
        minimum_start = float(start_anchor)
        maximum_start = minimum_start + max_start_lag
        if start < minimum_start:
            start = minimum_start
            adjustments.append(
                {
                    "edge": "start",
                    "direction": "earlier_than_anchor",
                    "anchor_source": start_source,
                    "anchor_time": round(minimum_start, 3),
                    "applied": round(start, 3),
                }
            )
        elif start > maximum_start:
            start = maximum_start
            adjustments.append(
                {
                    "edge": "start",
                    "direction": "too_late_from_anchor",
                    "anchor_source": start_source,
                    "anchor_time": round(minimum_start, 3),
                    "max_lag_sec": round(max_start_lag, 3),
                    "applied": round(start, 3),
                }
            )

    if end_anchor is not None:
        minimum_end = float(end_anchor) - max_end_lead
        maximum_end = float(end_anchor) + max_end_lag
        if end < minimum_end:
            end = minimum_end
            adjustments.append(
                {
                    "edge": "end",
                    "direction": "too_early_from_anchor",
                    "anchor_source": end_source,
                    "anchor_time": round(float(end_anchor), 3),
                    "max_lead_sec": round(max_end_lead, 3),
                    "applied": round(end, 3),
                }
            )
        elif end > maximum_end:
            end = maximum_end
            adjustments.append(
                {
                    "edge": "end",
                    "direction": "too_late_from_anchor",
                    "anchor_source": end_source,
                    "anchor_time": round(float(end_anchor), 3),
                    "max_lag_sec": round(max_end_lag, 3),
                    "applied": round(end, 3),
                }
            )

    end = max(end, start + max(0.05, min_duration))
    if not adjustments and abs(start - old_start) < 0.001 and abs(end - old_end) < 0.001:
        return start, end
    policy.update(
        {
            "task": "subtitle_timing_anchor_window",
            "old_start": round(old_start, 3),
            "old_end": round(old_end, 3),
            "new_start": round(start, 3),
            "new_end": round(end, 3),
            "adjustments": adjustments,
        }
    )
    seg["_timing_anchor_window_policy"] = policy
    return start, end


def _clamp_segment_to_selected_stt_window(
    seg: dict,
    start: float,
    end: float,
    min_duration: float,
    settings: dict | None = None,
) -> tuple[float, float]:
    if bool(seg.get("manual_stt_candidate_locked")):
        return start, end
    bounds = _selected_stt_candidate_span(seg)
    if bounds is None:
        return start, end

    window_start = float(bounds[0])
    window_end = float(bounds[1])
    if window_end <= window_start:
        return start, end

    old_start = start
    old_end = end
    s = dict(settings or {})
    max_end_lag = (
        max(0.0, _setting_float(s, "subtitle_timing_anchor_max_end_lag_sec", 0.0))
        if "subtitle_timing_anchor_max_end_lag_sec" in s
        else 0.0
    )
    start = max(float(start), window_start)
    end = min(float(end), window_end + max_end_lag)

    required = max(0.05, float(min_duration))
    if end < start + required:
        if old_start < window_start:
            start = window_start
            end = min(window_end + max_end_lag, start + required)
        elif old_end > window_end + max_end_lag:
            end = window_end + max_end_lag
            start = max(window_start, end - required)
        else:
            start = window_start
            end = window_end

    if end <= start:
        return old_start, old_end

    changed = abs(start - old_start) >= 0.001 or abs(end - old_end) >= 0.001
    if changed:
        seg["_timing_stt_window_policy"] = {
            "task": "subtitle_timing_selected_stt_window",
            "window_start": round(window_start, 3),
            "window_end": round(window_end, 3),
            "old_start": round(old_start, 3),
            "old_end": round(old_end, 3),
            "new_start": round(start, 3),
            "new_end": round(end, 3),
        }
    return start, end


def _candidate_vad_rows(seg: dict) -> list[dict]:
    rows: list[dict] = []
    for key in ("voice_activity_segments", "vad_segments", "_voice_activity_segments", "_vad_segments"):
        payload = seg.get(key)
        if isinstance(payload, list):
            rows.extend([dict(item) for item in payload if isinstance(item, dict)])
    return rows


def _overlapping_vad_span(seg: dict, *, pad: float = 0.18) -> tuple[float, float] | None:
    start, end = _time_bounds(seg)
    matches = []
    for row in _candidate_vad_rows(seg):
        r_start, r_end = _time_bounds(row)
        if min(end, r_end + pad) >= max(start, r_start - pad):
            matches.append((r_start, r_end))
    if not matches:
        return None
    starts, ends = zip(*matches)
    return max(0.0, min(starts)), max(ends)


def _median(values: list[float]) -> float | None:
    vals = sorted(value for value in values if value > 0.0)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _lora_duration_target(seg: dict) -> float | None:
    profile = dict(seg.get("_lora_generation_profile") or {})
    durations: list[float] = []
    for key in ("examples", "setting_sources", "context_hits"):
        for item in list(profile.get(key) or []):
            if isinstance(item, dict):
                duration = _as_float(item.get("duration_sec"), 0.0)
                if duration > 0.05:
                    durations.append(duration)
    settings = dict(seg.get("_lora_gap_settings") or {})
    if settings.get("sub_max_duration") not in (None, ""):
        durations.append(_as_float(settings.get("sub_max_duration"), 0.0))
    return _median(durations)


def _nearby_audio_boundary(seg: dict, target: float, *, window_sec: float) -> float | None:
    best: tuple[float, float] | None = None
    for key in (
        "audio_energy_boundaries",
        "audio_gain_boundaries",
        "audio_silence_boundaries",
        "_audio_energy_boundaries",
        "_audio_gain_boundaries",
        "_audio_silence_boundaries",
    ):
        rows = seg.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = _as_time(row)
            if value is None:
                continue
            distance = abs(value - target)
            if distance <= window_sec and (best is None or distance < best[0]):
                best = (distance, value)
    return best[1] if best else None


def _segment_boundary_value(seg: dict, key: str) -> float | None:
    value = seg.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _gap_boundary_candidates(left: dict, right: dict) -> list[tuple[int, float, float, str]]:
    left_end = _as_float(left.get("end"), 0.0)
    right_start = _as_float(right.get("start"), left_end)
    low = min(left_end, right_start)
    high = max(left_end, right_start)
    center = (low + high) / 2.0
    candidates: list[tuple[int, float, float, str]] = []
    seen: set[tuple[str, float]] = set()

    def add(priority: int, sec: float | None, source: str) -> None:
        if sec is None:
            return
        value = round(float(sec), 6)
        if value < (low - 0.001) or value > (high + 0.001):
            return
        key = (source, value)
        if key in seen:
            return
        seen.add(key)
        candidates.append((int(priority), abs(value - center), value, source))

    for sec in (
        _segment_boundary_value(left, "cut_scene_end"),
        _segment_boundary_value(right, "cut_scene_start"),
        _segment_boundary_value(left, "nearest_confirmed_cut_sec"),
        _segment_boundary_value(right, "nearest_confirmed_cut_sec"),
    ):
        add(0, sec, "confirmed_cut")

    for sec in (
        _segment_boundary_value(left, "nearest_provisional_cut_sec"),
        _segment_boundary_value(right, "nearest_provisional_cut_sec"),
    ):
        add(1, sec, "provisional_cut")

    for row in _candidate_vad_rows(left) + _candidate_vad_rows(right):
        add(2, _as_float(row.get("start"), None), "voice_boundary")
        add(2, _as_float(row.get("end"), None), "voice_boundary")

    for seg in (left, right):
        for key in (
            "audio_energy_boundaries",
            "audio_gain_boundaries",
            "audio_silence_boundaries",
            "_audio_energy_boundaries",
            "_audio_gain_boundaries",
            "_audio_silence_boundaries",
        ):
            rows = seg.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                add(3, _as_time(row), key)

    return sorted(candidates, key=lambda item: (item[0], item[1], item[2]))


def _preferred_gap_boundary(left: dict, right: dict) -> tuple[float, str] | None:
    candidates = _gap_boundary_candidates(left, right)
    if not candidates:
        return None
    _priority, _distance, sec, source = candidates[0]
    return float(sec), str(source)


def _piecewise_drift_enabled(settings: dict | None = None) -> bool:
    return _setting_bool(dict(settings or {}), "subtitle_timing_piecewise_drift_enabled", False)


def _piecewise_drift_trigger_sec(settings: dict | None = None) -> float:
    return max(0.0, _setting_float(dict(settings or {}), "subtitle_timing_piecewise_drift_trigger_sec", 0.05))


def _piecewise_drift_max_shift_sec(settings: dict | None = None) -> float:
    return max(0.0, _setting_float(dict(settings or {}), "subtitle_timing_piecewise_drift_max_shift_sec", 0.12))


def _piecewise_drift_min_run(settings: dict | None = None) -> int:
    return max(2, _clamp_int(dict(settings or {}).get("subtitle_timing_piecewise_drift_min_run_segments", 3), 2, 12, 3))


def _piecewise_drift_anchor_spread_sec(settings: dict | None = None) -> float:
    return max(0.0, _setting_float(dict(settings or {}), "subtitle_timing_piecewise_drift_anchor_spread_sec", 0.08))


def _signed_median(values: list[float]) -> float | None:
    vals = sorted(float(value) for value in values if abs(float(value)) > 0.0)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _segment_piecewise_drift(seg: dict, settings: dict | None = None) -> tuple[float | None, dict]:
    s = dict(settings or {})
    start, end = _time_bounds(seg)
    if end <= start:
        return None, {}
    max_shift = _piecewise_drift_max_shift_sec(s)
    if max_shift <= 0.0:
        return None, {}

    current_center = (start + end) * 0.5
    spread_limit = max(0.02, _piecewise_drift_anchor_spread_sec(s))
    trigger = _piecewise_drift_trigger_sec(s)
    candidates: list[tuple[str, float]] = []

    start_anchor, _start_source = _subtitle_start_anchor(seg)
    end_anchor, _end_source = _subtitle_end_anchor(seg)
    if start_anchor is not None and end_anchor is not None:
        start_drift = float(start_anchor) - start
        end_drift = float(end_anchor) - end
        if abs(start_drift - end_drift) <= spread_limit:
            candidates.append(("anchor_center", (start_drift + end_drift) * 0.5))

    vad_span = _overlapping_vad_span(seg, pad=max(0.18, spread_limit))
    if vad_span is not None:
        vad_center = (float(vad_span[0]) + float(vad_span[1])) * 0.5
        vad_drift = vad_center - current_center
        if abs(vad_drift) <= max_shift * 1.5:
            candidates.append(("vad_center", vad_drift))

    if not candidates:
        return None, {}
    drift = _signed_median([value for _source, value in candidates])
    if drift is None or abs(drift) < trigger:
        return None, {"candidates": [{"source": source, "drift_sec": round(value, 4)} for source, value in candidates]}
    return max(-max_shift, min(max_shift, drift)), {
        "candidates": [{"source": source, "drift_sec": round(value, 4)} for source, value in candidates],
        "trigger_sec": round(trigger, 4),
        "max_shift_sec": round(max_shift, 4),
    }


def _apply_piecewise_timing_drift(
    segments: list[dict],
    settings: dict | None = None,
    *,
    default_min_duration: float,
) -> list[dict]:
    s = dict(settings or {})
    if not segments or not _piecewise_drift_enabled(s):
        return segments

    trigger = _piecewise_drift_trigger_sec(s)
    min_run = _piecewise_drift_min_run(s)

    def _sign(value: float) -> int:
        if value >= trigger:
            return 1
        if value <= -trigger:
            return -1
        return 0

    def _flush(run_indices: list[int], run_drifts: list[float], run_scope: object) -> None:
        if len(run_indices) < min_run:
            return
        shift = _signed_median(run_drifts)
        if shift is None or abs(shift) < trigger:
            return
        for idx in run_indices:
            seg = segments[idx]
            seg_settings = _segment_gap_settings(s, seg)
            min_duration = max(0.05, _setting_float(seg_settings, "sub_min_duration", default_min_duration))
            start = max(0.0, float(seg.get("start", 0.0) or 0.0) + shift)
            end = float(seg.get("end", start + min_duration) or start + min_duration) + shift
            if end <= start + min_duration:
                end = start + min_duration
            seg["start"] = round(start, 3)
            seg["end"] = round(end, 3)
            seg["_piecewise_drift_policy"] = {
                "task": "subtitle_timing_piecewise_drift",
                "run_size": len(run_indices),
                "scope": str(run_scope),
                "applied_shift_sec": round(shift, 4),
                "trigger_sec": round(trigger, 4),
            }

    run_indices: list[int] = []
    run_drifts: list[float] = []
    run_scope = None
    run_sign = 0

    for idx, seg in enumerate(segments):
        if seg.get("is_gap"):
            _flush(run_indices, run_drifts, run_scope)
            run_indices, run_drifts, run_scope, run_sign = [], [], None, 0
            continue
        drift, _details = _segment_piecewise_drift(seg, s)
        scope = _segment_scope_key(seg)
        sign = _sign(float(drift or 0.0))
        if drift is None or sign == 0:
            _flush(run_indices, run_drifts, run_scope)
            run_indices, run_drifts, run_scope, run_sign = [], [], None, 0
            continue
        if run_indices and (scope != run_scope or sign != run_sign):
            _flush(run_indices, run_drifts, run_scope)
            run_indices, run_drifts = [], []
        if not run_indices:
            run_scope = scope
            run_sign = sign
        run_indices.append(idx)
        run_drifts.append(float(drift))

    _flush(run_indices, run_drifts, run_scope)
    return segments


def apply_timing_fusion_policy(segment: dict, settings: dict | None = None) -> dict:
    """Blend word, VAD, audio, cut, and LoRA timing evidence before final gap shaping."""
    seg = dict(segment or {})
    s = dict(settings or {})
    if seg.get("is_gap") or not _setting_bool(s, "subtitle_timing_fusion_enabled", True):
        return seg
    old_start, old_end = _time_bounds(seg)
    if old_end <= old_start:
        return seg

    max_shift = max(0.0, _setting_float(s, "subtitle_timing_fusion_max_shift_sec", 0.18))
    if max_shift <= 0.0:
        return seg
    min_duration = max(0.05, _setting_float(s, "sub_min_duration", 0.2))
    start = old_start
    end = old_end
    evidence: list[dict] = []

    def blend(current: float, target: float, weight: float) -> float:
        raw = current + (target - current) * max(0.0, min(1.0, weight))
        return current + max(-max_shift, min(max_shift, raw - current))

    word = _word_span(seg)
    if word:
        weight = max(0.0, min(1.0, _setting_float(s, "subtitle_timing_fusion_word_weight", 0.72)))
        new_start = blend(start, word[0], weight)
        new_end = blend(end, word[1], weight)
        evidence.append({"source": "word_timestamp", "start": round(word[0], 3), "end": round(word[1], 3), "weight": round(weight, 3)})
        start, end = new_start, new_end

    deep_timing = dict(seg.get("_deep_timing_policy") or {})
    if deep_timing:
        evidence.append(
            {
                "source": "deep_timing",
                "start_shift": deep_timing.get("start_shift"),
                "end_shift": deep_timing.get("end_shift"),
                "profile_score": deep_timing.get("profile_score"),
            }
        )

    vad = _overlapping_vad_span(seg)
    if vad:
        weight = max(0.0, min(1.0, _setting_float(s, "subtitle_timing_fusion_vad_weight", 0.46)))
        start = blend(start, vad[0], weight)
        end = blend(end, vad[1], weight)
        evidence.append({"source": "vad", "start": round(vad[0], 3), "end": round(vad[1], 3), "weight": round(weight, 3)})

    snap_window = max(0.0, _setting_float(s, "subtitle_timing_fusion_boundary_snap_window_sec", 0.12))
    if snap_window > 0.0:
        audio_start = _nearby_audio_boundary(seg, start, window_sec=snap_window)
        audio_end = _nearby_audio_boundary(seg, end, window_sec=snap_window)
        if audio_start is not None:
            start = blend(start, audio_start, 0.5)
            evidence.append({"source": "audio_boundary_start", "time": round(audio_start, 3), "window_sec": round(snap_window, 3)})
        if audio_end is not None:
            end = blend(end, audio_end, 0.5)
            evidence.append({"source": "audio_boundary_end", "time": round(audio_end, 3), "window_sec": round(snap_window, 3)})

    lora_duration = _lora_duration_target(seg)
    if lora_duration:
        current_duration = max(0.05, end - start)
        weight = max(0.0, min(1.0, _setting_float(s, "subtitle_timing_fusion_lora_duration_weight", 0.22)))
        target_duration = max(min_duration, lora_duration)
        fused_duration = current_duration + (target_duration - current_duration) * weight
        fused_end = start + max(min_duration, fused_duration)
        end = end + max(-max_shift, min(max_shift, fused_end - end))
        evidence.append({"source": "lora_duration", "duration_sec": round(lora_duration, 3), "weight": round(weight, 3)})

    scene_start, scene_end = _cut_scene_bounds(seg)
    if not _allow_cut_scene_crossing(seg, s):
        if scene_start is not None and start < scene_start:
            start = scene_start
            evidence.append({"source": "cut_scene_start", "time": round(scene_start, 3)})
        if scene_end is not None and end > scene_end:
            end = scene_end
            evidence.append({"source": "cut_scene_end", "time": round(scene_end, 3)})

    anchored_start, anchored_end = _clamp_segment_start_to_anchor(seg, start, end, min_duration)
    if abs(anchored_start - start) > 0.001:
        evidence.append(
            {
                "source": "selected_stt_anchor_start",
                "time": round(anchored_start, 3),
            }
        )
    start, end = anchored_start, anchored_end

    start = max(0.0, round(start, 3))
    end = round(max(start + min_duration, end), 3)
    if abs(start - old_start) < 0.001 and abs(end - old_end) < 0.001:
        return seg
    seg["start"] = start
    seg["end"] = end
    seg["_timing_fusion_policy"] = build_timing_fusion_policy(
        old_start=old_start,
        old_end=old_end,
        new_start=start,
        new_end=end,
        evidence=evidence,
    )
    return seg


def _ranges_overlap(left: dict, right: dict, *, pad: float = 0.0) -> float:
    left_start, left_end = _time_bounds(left)
    right_start, right_end = _time_bounds(right)
    return max(0.0, min(left_end, right_end) - max(left_start, right_start) + float(pad or 0.0))


def _center_in_range(row: dict, target: dict, *, pad: float = 0.0) -> bool:
    start, end = _time_bounds(row)
    target_start, target_end = _time_bounds(target)
    center = (start + end) / 2.0
    return (target_start - pad) <= center <= (target_end + pad)


def _same_candidate_scope(candidate: dict, segment: dict) -> bool:
    cand_key = _segment_scope_key(candidate)
    seg_key = _segment_scope_key(segment)
    return cand_key is None or seg_key is None or cand_key == seg_key


def _candidate_frame_rate(candidate: dict, fallback: dict) -> float | None:
    for source in (candidate, fallback):
        for key in ("timeline_frame_rate", "frame_rate", "fps", "source_frame_rate"):
            value = source.get(key)
            if value not in (None, ""):
                try:
                    return normalize_fps(value)
                except Exception:
                    continue
    return None


def _update_candidate_time_fields(candidate: dict, start: float, end: float, fallback_segment: dict) -> None:
    original_start = _as_float(
        candidate.get(
            "original_start",
            candidate.get("_stt_original_candidate_start", candidate.get("start")),
        ),
        0.0,
    )
    original_end = _as_float(
        candidate.get(
            "original_end",
            candidate.get("_stt_original_candidate_end", candidate.get("end")),
        ),
        original_start,
    )
    if original_end > original_start:
        candidate["original_start"] = round(original_start, 3)
        candidate["original_end"] = round(original_end, 3)
        candidate["_stt_original_candidate_start"] = round(original_start, 3)
        candidate["_stt_original_candidate_end"] = round(original_end, 3)

    start = max(0.0, float(start or 0.0))
    end = max(start + 0.05, float(end or start + 0.05))
    candidate["start"] = round(start, 3)
    candidate["end"] = round(end, 3)
    candidate["timeline_start"] = candidate["start"]
    candidate["timeline_end"] = candidate["end"]
    fps = _candidate_frame_rate(candidate, fallback_segment)
    if fps:
        original_start_frame = sec_to_frame(candidate["original_start"], fps) if "original_start" in candidate else None
        original_end_frame = (
            max(original_start_frame + 1, sec_to_frame(candidate["original_end"], fps))
            if original_start_frame is not None and "original_end" in candidate
            else None
        )
        if original_start_frame is not None and original_end_frame is not None:
            candidate["_stt_original_candidate_start_frame"] = original_start_frame
            candidate["_stt_original_candidate_end_frame"] = original_end_frame
        start_frame = sec_to_frame(candidate["start"], fps)
        end_frame = max(start_frame + 1, sec_to_frame(candidate["end"], fps))
        candidate["start_frame"] = start_frame
        candidate["end_frame"] = end_frame
        candidate["timeline_start_frame"] = start_frame
        candidate["timeline_end_frame"] = end_frame
        candidate["frame_rate"] = fps
        candidate["timeline_frame_rate"] = fps
        candidate["frame_range"] = {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        }


def _overlapped_subtitle_span(
    candidate: dict,
    subtitles: list[dict],
    *,
    edge_pad_sec: float = 0.08,
) -> tuple[float, float] | None:
    matches = []
    for segment in subtitles or []:
        if segment.get("is_gap") or not _same_candidate_scope(candidate, segment):
            continue
        overlap = _ranges_overlap(candidate, segment)
        if overlap > 0.0 or _center_in_range(candidate, segment, pad=edge_pad_sec):
            matches.append(segment)
    if not matches:
        return None
    starts, ends = zip(*(_time_bounds(item) for item in matches))
    return min(starts), max(ends)


def align_stt_candidates_to_subtitle_segments(
    segments: list[dict],
    *,
    edge_pad_sec: float = 0.08,
) -> list[dict]:
    """Align STT1/STT2 candidate timings to final subtitle slots without changing text."""
    if not segments:
        return segments
    subtitles = [
        dict(seg)
        for seg in segments
        if isinstance(seg, dict) and not seg.get("is_gap")
    ]
    if not subtitles:
        return []

    aligned = []
    for segment in subtitles:
        row = dict(segment)
        candidates = []
        for candidate in list(row.get("stt_candidates") or []):
            if not isinstance(candidate, dict):
                continue
            cand = dict(candidate)
            span = _overlapped_subtitle_span(cand, subtitles, edge_pad_sec=edge_pad_sec)
            if span is None:
                span = _time_bounds(row)
                cand["stt_alignment_fallback"] = "parent_subtitle"
            _update_candidate_time_fields(cand, span[0], span[1], row)
            cand["stt_aligned_to_subtitle_segments"] = True
            cand["stt_alignment_preserved_text"] = True
            candidates.append(cand)
        if candidates:
            row["stt_candidates"] = candidates
        aligned.append(row)
    return aligned


def align_stt_preview_to_subtitle_segments(
    preview_segments: list[dict],
    subtitle_segments: list[dict],
    *,
    edge_pad_sec: float = 0.08,
) -> list[dict]:
    """Keep STT1/STT2 preview lanes raw while aligning auxiliary preview rows to subtitles."""
    if not preview_segments:
        return []
    subtitles = [
        dict(seg)
        for seg in subtitle_segments or []
        if isinstance(seg, dict) and not seg.get("is_gap")
    ]
    if not subtitles:
        return [dict(row) for row in preview_segments if isinstance(row, dict)]

    out = []
    for preview in preview_segments or []:
        if not isinstance(preview, dict):
            continue
        row = dict(preview)
        source = str(
            row.get("stt_preview_source")
            or row.get("stt_source")
            or row.get("stt_ensemble_source")
            or ""
        ).strip().upper()
        if source in {"STT1", "STT2"}:
            out.append(row)
            continue
        span = _overlapped_subtitle_span(row, subtitles, edge_pad_sec=edge_pad_sec)
        if span is not None:
            _update_candidate_time_fields(row, span[0], span[1], row)
            row["preview_aligned_to_subtitle_segments"] = True
            row["stt_alignment_preserved_text"] = True
        out.append(row)
    return out


def _compact_len(value) -> int:
    return len(str(value or "").replace(" ", "").replace("\n", ""))


def _word_text(word: dict) -> str:
    return str((word or {}).get("word", "") or "").strip()


def _word_chars(words: list[dict]) -> int:
    return sum(_compact_len(_word_text(word)) for word in words)


def _word_duration(words: list[dict]) -> float:
    if not words:
        return 0.0
    start = _as_float(words[0].get("start"), 0.0)
    end = _as_float(words[-1].get("end"), start)
    return max(0.0, end - start)


def _words_for_common_split(seg: dict) -> list[dict]:
    words = [
        dict(word)
        for word in list(seg.get("words") or [])
        if isinstance(word, dict)
        and _word_text(word)
        and word.get("start") not in (None, "")
        and word.get("end") not in (None, "")
    ]
    if words:
        return sorted(words, key=lambda item: _as_float(item.get("start"), 0.0))

    tokens = [token for token in str(seg.get("text", "") or "").split() if token.strip()]
    if not tokens:
        return []
    start, end = _time_bounds(seg)
    end = max(start + 0.05, end)
    step = max(0.05, (end - start) / max(1, len(tokens)))
    speaker = seg.get("speaker")
    return [
        {
            "word": token,
            "start": round(start + idx * step, 3),
            "end": round(start + (idx + 1) * step, 3),
            "speaker": speaker,
        }
        for idx, token in enumerate(tokens)
    ]


def _is_common_split_break(left_word: dict, right_word: dict | None) -> bool:
    text = _word_text(left_word)
    next_text = _word_text(right_word or {})
    if text.endswith((".", ",", "!", "?", "~", "…", "。", "，")):
        return True
    clean = "".join(ch for ch in text if ch.isalnum() or ("가" <= ch <= "힣"))
    next_clean = "".join(ch for ch in next_text if ch.isalnum() or ("가" <= ch <= "힣"))
    end_tokens = (
        "거든요",
        "거든",
        "는데요",
        "는데",
        "네요",
        "습니다",
        "합니다",
        "했는데",
        "했고",
        "하고",
        "해서",
        "니까",
        "라고",
        "같아요",
        "같고",
        "예요",
        "이에요",
        "요",
        "죠",
        "다",
        "고",
    )
    start_tokens = (
        "그리고",
        "그래서",
        "근데",
        "그런데",
        "이번에는",
        "일단",
        "여기",
        "저기",
        "그러면",
        "자",
        "아",
        "오",
    )
    return any(clean.endswith(token) for token in end_tokens) or any(
        next_clean.startswith(token) for token in start_tokens
    )


def _common_split_policy_settings(settings: dict, seg: dict) -> dict:
    merged = _segment_gap_settings(settings, seg)
    threshold = _clamp_int(merged.get("split_length_threshold"), 8, 36, 20)
    lora_floor = _lora_split_floor_chars(merged, seg)
    if lora_floor:
        threshold = max(threshold, lora_floor)
    default_target = max(18, min(26, int(round(threshold * 1.1))))
    target_chars = _clamp_int(
        merged.get("subtitle_common_split_target_chars"),
        8,
        36,
        default_target,
    )
    if lora_floor:
        target_chars = max(target_chars, lora_floor)
    hard_chars = _clamp_int(
        merged.get("subtitle_common_split_hard_max_chars"),
        max(target_chars + 4, 16),
        56,
        max(target_chars + 10, int(round(target_chars * 1.6))),
    )
    if lora_floor:
        hard_chars = max(hard_chars, max(lora_floor + 8, int(round(lora_floor * 1.6))))
    configured_max_duration = _setting_float(merged, "sub_max_duration", 6.0)
    default_max_duration = min(max(2.4, configured_max_duration), 5.5)
    hard_duration = _clamp_float(
        merged.get("subtitle_common_split_hard_max_duration_sec"),
        2.0,
        8.0,
        default_max_duration,
    )
    min_duration = _clamp_float(
        merged.get("subtitle_common_split_min_chunk_duration_sec"),
        0.08,
        1.2,
        max(0.18, _setting_float(merged, "sub_min_duration", 0.2)),
    )
    return {
        "enabled": _setting_bool(merged, "subtitle_common_split_guard_enabled", True),
        "target_chars": target_chars,
        "hard_chars": hard_chars,
        "hard_duration": hard_duration,
        "min_duration": min_duration,
        "lora_floor_chars": lora_floor,
    }


def _common_split_violation(seg: dict, settings: dict) -> bool:
    if seg.get("is_gap"):
        return False
    policy = _common_split_policy_settings(settings, seg)
    if not policy["enabled"]:
        return False
    text = str(seg.get("text", "") or "").strip()
    if not text:
        return False
    start, end = _time_bounds(seg)
    duration = max(0.0, end - start)
    chars = _compact_len(text)
    if chars > policy["hard_chars"]:
        return True
    return duration > policy["hard_duration"] + 0.001


def _has_common_split_guard_violation(segments: list[dict], settings: dict) -> bool:
    return any(_common_split_violation(seg, settings) for seg in segments if isinstance(seg, dict))


def _best_common_split_index(words: list[dict]) -> int | None:
    if len(words) < 2:
        return None
    total_chars = max(1, _word_chars(words))
    total_duration = max(0.05, _word_duration(words))
    best: tuple[float, int] | None = None
    for idx in range(1, len(words)):
        left = words[:idx]
        right = words[idx:]
        left_chars = _word_chars(left)
        right_chars = _word_chars(right)
        left_duration = _word_duration(left)
        right_duration = _word_duration(right)
        char_balance = abs(left_chars - right_chars) / total_chars
        duration_balance = abs(left_duration - right_duration) / total_duration
        edge_penalty = 0.22 if len(left) == 1 or len(right) == 1 else 0.0
        natural_bonus = -0.18 if _is_common_split_break(words[idx - 1], words[idx]) else 0.0
        gap = _as_float(words[idx].get("start"), 0.0) - _as_float(words[idx - 1].get("end"), 0.0)
        gap_bonus = -0.12 if gap >= 0.28 else 0.0
        score = char_balance + (duration_balance * 0.45) + edge_penalty + natural_bonus + gap_bonus
        if best is None or score < best[0]:
            best = (score, idx)
    return best[1] if best else None


def _split_word_groups_for_common_guard(words: list[dict], policy: dict) -> list[list[dict]]:
    if len(words) < 2:
        return [words]
    total_chars = _word_chars(words)
    total_duration = _word_duration(words)
    target_chars = max(1, int(policy["target_chars"]))
    hard_duration = max(0.05, float(policy["hard_duration"]))
    target_count = max(
        1,
        int((total_chars + target_chars - 1) // target_chars),
        int((total_duration + hard_duration - 0.001) // hard_duration),
    )
    target_count = min(len(words), target_count)
    groups: list[list[dict]] = [words]

    def group_score(group: list[dict]) -> float:
        return max(
            _word_chars(group) / max(1.0, float(policy["target_chars"])),
            _word_duration(group) / max(0.05, float(policy["hard_duration"])),
        )

    while len(groups) < target_count:
        candidates = [
            (group_score(group), idx)
            for idx, group in enumerate(groups)
            if len(group) >= 2
        ]
        if not candidates:
            break
        _score, group_idx = max(candidates)
        split_idx = _best_common_split_index(groups[group_idx])
        if split_idx is None:
            break
        group = groups[group_idx]
        groups[group_idx:group_idx + 1] = [group[:split_idx], group[split_idx:]]

    changed = True
    while changed:
        changed = False
        for idx, group in list(enumerate(groups)):
            if len(group) < 2:
                continue
            if _word_chars(group) <= policy["hard_chars"] and _word_duration(group) <= policy["hard_duration"] + 0.001:
                continue
            split_idx = _best_common_split_index(group)
            if split_idx is None:
                continue
            groups[idx:idx + 1] = [group[:split_idx], group[split_idx:]]
            changed = True
            break
    return [group for group in groups if group]


def _common_split_row(seg: dict, group: list[dict], policy_meta: dict) -> dict:
    row = dict(seg)
    text = " ".join(_word_text(word) for word in group).strip()
    start = _as_float(group[0].get("start"), _as_float(seg.get("start"), 0.0))
    end = max(start + 0.05, _as_float(group[-1].get("end"), start + 0.05))
    row.update(
        {
            "start": round(max(0.0, start), 3),
            "end": round(max(start + 0.05, end), 3),
            "text": text,
            "words": [dict(word) for word in group],
            "_common_split_guard_policy": dict(policy_meta),
        }
    )
    row.pop("_final_gap_settings_applied", None)
    for key in (
        "timeline_start",
        "timeline_end",
        "timeline_start_frame",
        "timeline_end_frame",
        "start_frame",
        "end_frame",
        "frame_range",
    ):
        row.pop(key, None)
    return row


def _native_common_split_items(rows: list[dict], settings: dict) -> tuple[list[dict], list[list[dict]], list[dict]]:
    items: list[dict] = []
    words_by_row: list[list[dict]] = []
    policies: list[dict] = []
    for row in rows:
        policy = _common_split_policy_settings(settings, row)
        if row.get("is_gap") or not _common_split_violation(row, settings):
            policy = {**policy, "enabled": False}
        words = _words_for_common_split(row)
        start, end = _time_bounds(row)
        items.append(
            {
                "start": start,
                "end": end,
                "text": str(row.get("text", "") or ""),
                "words": [
                    {
                        "word": _word_text(word),
                        "start": _as_float(word.get("start"), start),
                        "end": _as_float(word.get("end"), start),
                    }
                    for word in words
                ],
                "policy": policy,
            }
        )
        words_by_row.append(words)
        policies.append(policy)
    return items, words_by_row, policies


def _apply_common_subtitle_split_guard_native(rows: list[dict], settings: dict) -> list[dict] | None:
    if plan_common_split_via_swift is None or not rows:
        return None
    items, words_by_row, policies = _native_common_split_items(rows, settings)
    plans = plan_common_split_via_swift(items, settings=settings)
    if plans is None or len(plans) != len(rows):
        return None

    output: list[dict] = []
    split_count = 0
    clamp_count = 0
    for row, words, policy, plan in zip(rows, words_by_row, policies, plans):
        row = dict(row)
        action = str(plan.get("action") or "keep")
        if action == "split":
            groups = list(plan.get("groups") or [])
            if len(groups) > 1 and words:
                start, end = _time_bounds(row)
                chars = _compact_len(row.get("text", ""))
                duration = max(0.0, end - start)
                policy_meta_base = {
                    "schema": COMMON_SPLIT_GUARD_SCHEMA,
                    "task": "common_subtitle_split_guard",
                    "action": "split",
                    "applies_to_modes": ["fast", "auto", "high"],
                    "source_start": round(start, 3),
                    "source_end": round(end, 3),
                    "source_duration_sec": round(duration, 3),
                    "source_chars": chars,
                    "target_chars": policy["target_chars"],
                    "hard_max_chars": policy["hard_chars"],
                    "hard_max_duration_sec": round(policy["hard_duration"], 3),
                    "split_count": len(groups),
                }
                emitted = 0
                for idx, group_plan in enumerate(groups):
                    try:
                        start_idx = max(0, int(group_plan.get("start_index", 0)))
                        end_idx = min(len(words), int(group_plan.get("end_index", start_idx)))
                    except Exception:
                        continue
                    group = words[start_idx:end_idx]
                    if not group:
                        continue
                    output.append(
                        _common_split_row(
                            row,
                            group,
                            {
                                **policy_meta_base,
                                "split_index": idx,
                            },
                        )
                    )
                    emitted += 1
                if emitted > 1:
                    split_count += emitted - 1
                    continue
            output.append(row)
            continue

        if action == "clamp":
            start, end = _time_bounds(row)
            old_end = end
            try:
                row["end"] = round(float(plan.get("new_end")), 3)
            except Exception:
                row["end"] = round(max(start + policy["min_duration"], start + policy["hard_duration"]), 3)
            row["_common_split_guard_policy"] = {
                "schema": COMMON_SPLIT_GUARD_SCHEMA,
                "task": "common_subtitle_split_guard",
                "action": "clamp_duration",
                "applies_to_modes": ["fast", "auto", "high"],
                "source_start": round(start, 3),
                "source_end": round(old_end, 3),
                "new_end": row["end"],
                "hard_max_duration_sec": round(policy["hard_duration"], 3),
                "reason": "not_enough_words_to_split",
            }
            row.pop("_final_gap_settings_applied", None)
            clamp_count += 1
        output.append(row)

    if split_count or clamp_count:
        get_logger().log(
            "[공통자막분할] "
            f"Fast/Auto/High 공통 룰 적용: 분할 {split_count}회, 길이 클램프 {clamp_count}개"
        )
    return output


def _apply_common_subtitle_split_guard(segments: list[dict], settings: dict) -> list[dict]:
    if not segments:
        return []
    rows = [dict(seg) for seg in segments]
    native = _apply_common_subtitle_split_guard_native(rows, settings)
    if native is not None:
        return native
    output: list[dict] = []
    split_count = 0
    clamp_count = 0
    for seg in rows:
        row = dict(seg)
        if not _common_split_violation(row, settings):
            output.append(row)
            continue
        policy = _common_split_policy_settings(settings, row)
        words = _words_for_common_split(row)
        if len(words) >= 2:
            groups = _split_word_groups_for_common_guard(words, policy)
        else:
            groups = [words]
        if len(groups) > 1:
            start, end = _time_bounds(row)
            chars = _compact_len(row.get("text", ""))
            duration = max(0.0, end - start)
            policy_meta_base = {
                "schema": COMMON_SPLIT_GUARD_SCHEMA,
                "task": "common_subtitle_split_guard",
                "action": "split",
                "applies_to_modes": ["fast", "auto", "high"],
                "source_start": round(start, 3),
                "source_end": round(end, 3),
                "source_duration_sec": round(duration, 3),
                "source_chars": chars,
                "target_chars": policy["target_chars"],
                "hard_max_chars": policy["hard_chars"],
                "hard_max_duration_sec": round(policy["hard_duration"], 3),
                "split_count": len(groups),
            }
            for idx, group in enumerate(groups):
                if not group:
                    continue
                output.append(
                    _common_split_row(
                        row,
                        group,
                        {
                            **policy_meta_base,
                            "split_index": idx,
                        },
                    )
                )
            split_count += max(0, len(groups) - 1)
            continue

        start, end = _time_bounds(row)
        duration = max(0.0, end - start)
        if duration > policy["hard_duration"] + 0.001:
            old_end = end
            row["end"] = round(max(start + policy["min_duration"], start + policy["hard_duration"]), 3)
            row["_common_split_guard_policy"] = {
                "schema": COMMON_SPLIT_GUARD_SCHEMA,
                "task": "common_subtitle_split_guard",
                "action": "clamp_duration",
                "applies_to_modes": ["fast", "auto", "high"],
                "source_start": round(start, 3),
                "source_end": round(old_end, 3),
                "new_end": row["end"],
                "hard_max_duration_sec": round(policy["hard_duration"], 3),
                "reason": "not_enough_words_to_split",
            }
            row.pop("_final_gap_settings_applied", None)
            clamp_count += 1
        output.append(row)
    if split_count or clamp_count:
        get_logger().log(
            "[공통자막분할] "
            f"Fast/Auto/High 공통 룰 적용: 분할 {split_count}회, 길이 클램프 {clamp_count}개"
        )
    return output


def _clamp_common_split_duration_after_gap(seg: dict, settings: dict) -> None:
    if seg.get("is_gap"):
        return
    policy = _common_split_policy_settings(settings, seg)
    if not policy["enabled"]:
        return
    start, end = _time_bounds(seg)
    if end - start <= policy["hard_duration"] + 0.001:
        return
    old_end = end
    seg["end"] = round(max(start + policy["min_duration"], start + policy["hard_duration"]), 3)
    current = dict(seg.get("_common_split_guard_policy") or {})
    if current.get("task") == "common_subtitle_split_guard":
        current["post_gap_duration_clamped"] = True
        current["post_gap_old_end"] = round(old_end, 3)
        current["post_gap_new_end"] = seg["end"]
    else:
        current = {
            "schema": COMMON_SPLIT_GUARD_SCHEMA,
            "task": "common_subtitle_split_guard",
            "action": "post_gap_duration_clamp",
            "applies_to_modes": ["fast", "auto", "high"],
            "source_start": round(start, 3),
            "source_end": round(old_end, 3),
            "new_end": seg["end"],
            "hard_max_duration_sec": round(policy["hard_duration"], 3),
        }
    seg["_common_split_guard_policy"] = current


def apply_final_gap_settings(
    segments: list[dict],
    settings: dict | None = None,
    *,
    force: bool = False,
) -> list[dict]:
    """Apply the user-facing Gap settings as the final subtitle timing pass."""
    if not segments:
        return segments

    candidates = [dict(seg) for seg in segments if isinstance(seg, dict)]
    if not candidates:
        return []

    s = dict(settings or _get_user_settings() or {})
    if (
        not force
        and all(seg.get("_final_gap_settings_applied") for seg in candidates)
        and not _has_common_split_guard_violation(candidates, s)
    ):
        return candidates

    default_min_duration = max(0.05, _setting_float(s, "sub_min_duration", 0.2))

    adj = sorted(candidates, key=lambda x: (float(x.get("start", 0.0) or 0.0), float(x.get("end", 0.0) or 0.0)))
    for seg in adj:
        if seg.get("is_gap"):
            continue
        seg_settings = _segment_gap_settings(s, seg)
        min_duration = max(0.05, _setting_float(seg_settings, "sub_min_duration", default_min_duration))
        try:
            start = max(0.0, float(seg.get("start", 0.0) or 0.0))
            end = float(seg.get("end", start + min_duration) or start + min_duration)
        except Exception:
            start = 0.0
            end = min_duration
        if end <= start:
            end = start + min_duration
        start, end = _clamp_segment_start_to_anchor(seg, start, end, min_duration)
        seg["start"] = start
        seg["end"] = end
        fused = apply_timing_fusion_policy(seg, seg_settings)
        if fused is not seg:
            seg.update(fused)

    adj = _apply_piecewise_timing_drift(adj, s, default_min_duration=default_min_duration)
    adj = _apply_common_subtitle_split_guard(adj, s)

    for idx, cur in enumerate(adj):
        if cur.get("is_gap"):
            cur["_final_gap_settings_applied"] = True
            continue

        nxt = None
        for candidate in adj[idx + 1:]:
            if not candidate.get("is_gap"):
                nxt = candidate
                break

        shared_gap_boundary = _preferred_gap_boundary(cur, nxt) if nxt is not None and _same_gap_scope(cur, nxt) else None
        if nxt is not None and (_same_timing_scope(cur, nxt) or shared_gap_boundary is not None):
            cur_settings = _segment_gap_settings(s, cur)
            cont_thresh = max(0.0, _setting_float(cur_settings, "continuous_threshold", 2.0))
            push_rate = max(0.0, min(1.0, _setting_float(cur_settings, "gap_push_rate", 0.7)))
            if "gap_pull_rate" in cur_settings:
                pull_rate = max(0.0, min(1.0, _setting_float(cur_settings, "gap_pull_rate", 1.0 - push_rate)))
            else:
                pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
            single_ext = max(0.0, _setting_float(cur_settings, "single_subtitle_end", 0.2))
            min_duration = max(0.05, _setting_float(cur_settings, "sub_min_duration", default_min_duration))
            gap = float(nxt.get("start", 0.0) or 0.0) - float(cur.get("end", 0.0) or 0.0)
            if gap < 0.0:
                cur["end"] = max(float(cur["start"]) + min_duration, float(nxt["start"]) - 0.02)
                if cur["end"] > float(nxt["start"]):
                    nxt["start"] = cur["end"]
                    if float(nxt["end"]) <= float(nxt["start"]):
                        nxt["end"] = float(nxt["start"]) + min_duration
            elif gap > 0.0:
                boundary_choice = None
                if gap <= cont_thresh:
                    boundary_choice = shared_gap_boundary
                if boundary_choice is not None:
                    boundary_sec, boundary_source = boundary_choice
                    boundary_sec = max(float(cur["end"]), min(float(nxt["start"]), float(boundary_sec)))
                    cur["end"] = boundary_sec
                    nxt["start"] = max(0.0, boundary_sec)
                    policy = {
                        "task": "subtitle_gap_boundary_join",
                        "action": "join_without_gap",
                        "source": boundary_source,
                        "boundary_sec": round(boundary_sec, 3),
                        "gap_sec": round(gap, 3),
                        "continuous_threshold_sec": round(cont_thresh, 3),
                    }
                    cur["_gap_boundary_policy"] = dict(policy)
                    nxt["_gap_boundary_policy"] = dict(policy)
                elif gap <= cont_thresh:
                    cur["end"] = float(cur["end"]) + (gap * push_rate)
                    nxt["start"] = max(0.0, float(nxt["start"]) - (gap * pull_rate))
                else:
                    extension = min(single_ext, gap / 2.0)
                    cur["end"] = float(cur["end"]) + extension
                    nxt["start"] = max(0.0, float(nxt["start"]) - extension)

                nxt_start, nxt_end = _clamp_segment_start_to_anchor(
                    nxt,
                    float(nxt["start"]),
                    float(nxt.get("end", float(nxt["start"]) + min_duration) or float(nxt["start"]) + min_duration),
                    min_duration,
                )
                nxt["start"] = nxt_start
                nxt["end"] = nxt_end

                if float(cur["end"]) > float(nxt["start"]):
                    boundary = (float(cur["end"]) + float(nxt["start"])) / 2.0
                    cur["end"] = max(float(cur["start"]) + min_duration, boundary)
                    nxt["start"] = max(0.0, cur["end"])
                    if float(nxt["end"]) <= float(nxt["start"]):
                        nxt["end"] = float(nxt["start"]) + min_duration
        else:
            cur_settings = _segment_gap_settings(s, cur)
            single_ext = max(0.0, _setting_float(cur_settings, "single_subtitle_end", 0.2))
            min_duration = max(0.05, _setting_float(cur_settings, "sub_min_duration", default_min_duration))
        if (nxt is None or not _same_timing_scope(cur, nxt)) and single_ext > 0.0:
            cur["end"] = float(cur["end"]) + single_ext

        if float(cur["end"]) <= float(cur["start"]):
            cur["end"] = float(cur["start"]) + min_duration
        cur["start"], cur["end"] = _clamp_segment_start_to_anchor(cur, float(cur["start"]), float(cur["end"]), min_duration)
        cur["start"], cur["end"] = _clamp_segment_to_anchor_window(
            cur,
            float(cur["start"]),
            float(cur["end"]),
            min_duration,
            cur_settings,
        )
        _clamp_common_split_duration_after_gap(cur, s)
        _clamp_to_cut_scene(cur, s, min_duration=min_duration)
        cur["start"], cur["end"] = _clamp_segment_to_anchor_window(
            cur,
            float(cur["start"]),
            float(cur["end"]),
            min_duration,
            cur_settings,
        )
        cur["start"], cur["end"] = _clamp_segment_to_selected_stt_window(
            cur,
            float(cur["start"]),
            float(cur["end"]),
            min_duration,
            cur_settings,
        )
        _clamp_to_cut_scene(cur, s, min_duration=min_duration)
        _update_frame_fields(cur, float(cur["start"]), float(cur["end"]))
        cur["_final_gap_settings_applied"] = True

    return adj


def adjust_timing(segments: list[dict]) -> list[dict]:
    if not segments:
        return segments
    adj = sorted([dict(s) for s in segments], key=lambda x: x["start"])
    for i in range(1, len(adj)):
        prev = adj[i - 1]
        cur = adj[i]

        if prev["end"] > cur["start"]:
            prev["end"] = max(prev["start"] + 0.1, cur["start"] - 0.02)

        if cur["end"] <= cur["start"]:
            cur["end"] = cur["start"] + 0.3
    return adj
