# Version: 03.14.29
# Phase: PHASE2
"""Final subtitle timing and frame-field adjustment helpers."""

from core.engine.subtitle_settings import _get_user_settings, _setting_float
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame


TIMING_FUSION_SCHEMA = "ai_subtitle_studio.subtitle_timing_fusion.v1"


def _setting_bool(settings: dict, key: str, default: bool = True) -> bool:
    value = settings.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "끔"}
    return bool(value)


def _segment_scope_key(seg: dict):
    clip_idx = seg.get("_clip_idx")
    if clip_idx is not None:
        clip_key = ("clip_idx", str(clip_idx))
    else:
        clip_file = seg.get("_clip_file") or seg.get("clip_file")
        if clip_file:
            clip_key = ("clip_file", str(clip_file))
        else:
            clip_key = None

    cut_scene = seg.get("cut_scene_index")
    cut_start = seg.get("cut_scene_start_frame", seg.get("cut_scene_start"))
    cut_end = seg.get("cut_scene_end_frame", seg.get("cut_scene_end"))
    if cut_scene is not None or cut_start is not None or cut_end is not None:
        return (
            "cut_scene",
            clip_key,
            str(cut_scene if cut_scene is not None else ""),
            str(cut_start if cut_start is not None else ""),
            str(cut_end if cut_end is not None else ""),
        )

    if clip_key is not None:
        return clip_key
    return None


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
    enabled = settings.get("subtitle_cut_boundary_allow_high_confidence_crossing", True)
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


def _update_frame_fields(seg: dict, start: float, end: float) -> None:
    fps_value = seg.get("timeline_frame_rate") or seg.get("frame_rate") or seg.get("fps")
    if fps_value in (None, ""):
        return
    fps = normalize_fps(fps_value)
    start_frame = sec_to_frame(start, fps)
    end_frame = max(start_frame + 1, sec_to_frame(end, fps))
    seg["timeline_start_frame"] = start_frame
    seg["timeline_end_frame"] = end_frame
    seg["start_frame"] = start_frame
    seg["end_frame"] = end_frame
    seg["frame_rate"] = fps
    seg["timeline_frame_rate"] = fps
    seg["timeline_start"] = frame_to_sec(start_frame, fps)
    seg["timeline_end"] = frame_to_sec(end_frame, fps)
    seg["start"] = seg["timeline_start"]
    seg["end"] = seg["timeline_end"]
    seg["frame_range"] = {
        "unit": "frame",
        "start": start_frame,
        "end": end_frame,
        "timeline_frame_rate": fps,
    }


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


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


def _time_bounds(row: dict) -> tuple[float, float]:
    start = _as_float(row.get("start", row.get("timeline_start", 0.0)))
    end = _as_float(row.get("end", row.get("timeline_end", start)), start)
    return start, max(start, end)


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
    return (start, end) if end > start else None


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

    start = max(0.0, round(start, 3))
    end = round(max(start + min_duration, end), 3)
    if abs(start - old_start) < 0.001 and abs(end - old_end) < 0.001:
        return seg
    seg["start"] = start
    seg["end"] = end
    seg["_timing_fusion_policy"] = {
        "schema": TIMING_FUSION_SCHEMA,
        "task": "subtitle_timing_fusion",
        "old_start": round(old_start, 3),
        "old_end": round(old_end, 3),
        "new_start": start,
        "new_end": end,
        "start_shift": round(start - old_start, 4),
        "end_shift": round(end - old_end, 4),
        "evidence": evidence,
    }
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
    start = max(0.0, float(start or 0.0))
    end = max(start + 0.05, float(end or start + 0.05))
    candidate["start"] = round(start, 3)
    candidate["end"] = round(end, 3)
    candidate["timeline_start"] = candidate["start"]
    candidate["timeline_end"] = candidate["end"]
    fps = _candidate_frame_rate(candidate, fallback_segment)
    if fps:
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
    """Align visible STT1/STT2 preview lanes to final subtitle spans without editing text."""
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
        ).upper()
        if source not in {"STT1", "STT2"}:
            out.append(row)
            continue
        span = _overlapped_subtitle_span(row, subtitles, edge_pad_sec=edge_pad_sec)
        if span is not None:
            _update_candidate_time_fields(row, span[0], span[1], row)
            row["stt_preview_aligned_to_subtitle_segments"] = True
            row["stt_alignment_preserved_text"] = True
        out.append(row)
    return out


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

    if not force and all(seg.get("_final_gap_settings_applied") for seg in candidates):
        return candidates

    s = dict(settings or _get_user_settings() or {})
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
        seg["start"] = start
        seg["end"] = end
        fused = apply_timing_fusion_policy(seg, seg_settings)
        if fused is not seg:
            seg.update(fused)

    for idx, cur in enumerate(adj):
        if cur.get("is_gap"):
            cur["_final_gap_settings_applied"] = True
            continue

        nxt = None
        for candidate in adj[idx + 1:]:
            if not candidate.get("is_gap"):
                nxt = candidate
                break

        if nxt is not None and _same_timing_scope(cur, nxt):
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
                if gap <= cont_thresh:
                    cur["end"] = float(cur["end"]) + (gap * push_rate)
                    nxt["start"] = max(0.0, float(nxt["start"]) - (gap * pull_rate))
                else:
                    extension = min(single_ext, gap / 2.0)
                    cur["end"] = float(cur["end"]) + extension
                    nxt["start"] = max(0.0, float(nxt["start"]) - extension)

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
