# Version: 03.14.29
# Phase: PHASE2
"""Final subtitle timing and frame-field adjustment helpers."""

from core.engine.subtitle_settings import _get_user_settings, _setting_float
from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame


def _segment_scope_key(seg: dict):
    clip_idx = seg.get("_clip_idx")
    if clip_idx is not None:
        return ("clip_idx", str(clip_idx))
    clip_file = seg.get("_clip_file") or seg.get("clip_file")
    if clip_file:
        return ("clip_file", str(clip_file))
    return None


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


def _time_bounds(row: dict) -> tuple[float, float]:
    start = _as_float(row.get("start", row.get("timeline_start", 0.0)))
    end = _as_float(row.get("end", row.get("timeline_end", start)), start)
    return start, max(start, end)


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
    cont_thresh = max(0.0, _setting_float(s, "continuous_threshold", 2.0))
    push_rate = max(0.0, min(1.0, _setting_float(s, "gap_push_rate", 0.7)))
    pull_rate = max(0.0, min(1.0, 1.0 - push_rate))
    single_ext = max(0.0, _setting_float(s, "single_subtitle_end", 0.2))
    min_duration = max(0.05, _setting_float(s, "sub_min_duration", 0.2))

    adj = sorted(candidates, key=lambda x: (float(x.get("start", 0.0) or 0.0), float(x.get("end", 0.0) or 0.0)))
    for seg in adj:
        if seg.get("is_gap"):
            continue
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
        elif single_ext > 0.0:
            cur["end"] = float(cur["end"]) + single_ext

        if float(cur["end"]) <= float(cur["start"]):
            cur["end"] = float(cur["start"]) + min_duration
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
