"""Pure subtitle timing contracts shared by Python and native helper seams."""

from core.frame_time import (
    frame_to_sec,
    normalize_fps,
    sec_to_ceil_frame,
    sec_to_frame,
    sec_to_nearest_frame,
)


TIMING_FUSION_SCHEMA = "ai_subtitle_studio.subtitle_timing_fusion.v1"
COMMON_SPLIT_GUARD_SCHEMA = "ai_subtitle_studio.common_subtitle_split_guard.v1"


def timing_float(value: object, default: float | None = 0.0) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def segment_scope_key(seg: dict):
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


def segment_time_bounds(row: dict) -> tuple[float, float]:
    start = timing_float(row.get("start", row.get("timeline_start", 0.0)), 0.0)
    end = timing_float(row.get("end", row.get("timeline_end", start)), start)
    start = float(start or 0.0)
    end = float(end if end is not None else start)
    return start, max(start, end)


def compact_timing_text(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def build_timing_frame_fields(
    start: float,
    end: float,
    fps_value: object,
    *,
    anchor_safe: bool = False,
) -> dict | None:
    if fps_value in (None, ""):
        return None

    fps = normalize_fps(fps_value)
    if anchor_safe:
        start_frame = sec_to_nearest_frame(start, fps)
        if frame_to_sec(start_frame, fps) + 1e-9 < float(start):
            start_frame = sec_to_ceil_frame(start, fps)
        end_frame = sec_to_nearest_frame(end, fps)
        if frame_to_sec(end_frame, fps) + 1e-9 < float(end):
            end_frame = sec_to_ceil_frame(end, fps)
    else:
        start_frame = sec_to_frame(start, fps)
        end_frame = sec_to_frame(end, fps)

    end_frame = max(start_frame + 1, end_frame)
    timeline_start = frame_to_sec(start_frame, fps)
    timeline_end = frame_to_sec(end_frame, fps)
    return {
        "timeline_start_frame": start_frame,
        "timeline_end_frame": end_frame,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_rate": fps,
        "timeline_frame_rate": fps,
        "timeline_start": timeline_start,
        "timeline_end": timeline_end,
        "start": timeline_start,
        "end": timeline_end,
        "frame_range": {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": fps,
        },
    }


def build_timing_fusion_policy(
    *,
    old_start: float,
    old_end: float,
    new_start: float,
    new_end: float,
    evidence: list[dict],
) -> dict:
    return {
        "schema": TIMING_FUSION_SCHEMA,
        "task": "subtitle_timing_fusion",
        "old_start": round(old_start, 3),
        "old_end": round(old_end, 3),
        "new_start": new_start,
        "new_end": new_end,
        "start_shift": round(new_start - old_start, 4),
        "end_shift": round(new_end - old_end, 4),
        "evidence": evidence,
    }
