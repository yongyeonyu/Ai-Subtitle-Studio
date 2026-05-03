# Version: 03.14.00
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
