# Version: 03.06.16
# Phase: PHASE2
"""Frame-based time helpers for editor/timeline synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import math

DEFAULT_FPS = 30.0


def _iter_segments(segments):
    if segments is None:
        return ()
    return segments


def normalize_fps(value: float | int | str | None, default: float = DEFAULT_FPS) -> float:
    try:
        fps = float(value)
    except (TypeError, ValueError):
        fps = float(default)
    if fps <= 0:
        fps = float(default)
    return max(1.0, min(240.0, fps))


def _coerce_nonnegative_sec(sec: float | int | str | None) -> float:
    try:
        value = float(sec)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, value)


def _coerce_frame_int(frame: float | int | str | None, default: int = 0) -> int:
    try:
        value = int(round(float(frame)))
    except (TypeError, ValueError):
        value = int(default)
    return max(0, value)


def sec_to_floor_frame(sec: float | int | str | None, fps: float | int | str | None) -> int:
    value = _coerce_nonnegative_sec(sec)
    return max(0, int(math.floor(value * normalize_fps(fps) + 1e-6)))


def sec_to_nearest_frame(sec: float | int | str | None, fps: float | int | str | None) -> int:
    value = _coerce_nonnegative_sec(sec)
    return max(0, int(math.floor((value * normalize_fps(fps)) + 0.5)))


def sec_to_ceil_frame(sec: float | int | str | None, fps: float | int | str | None) -> int:
    value = _coerce_nonnegative_sec(sec)
    return max(0, int(math.ceil((value * normalize_fps(fps)) - 1e-6)))


def sec_to_frame(sec: float | int | str | None, fps: float | int | str | None) -> int:
    return sec_to_floor_frame(sec, fps)


def frame_to_sec(frame: float | int | str | None, fps: float | int | str | None) -> float:
    value = _coerce_frame_int(frame)
    return max(0.0, value / normalize_fps(fps))


def snap_sec_to_frame(sec: float | int | str | None, fps: float | int | str | None) -> float:
    return round(frame_to_sec(sec_to_nearest_frame(sec, fps), fps), 6)


def frame_duration(fps: float | int | str | None) -> float:
    return round(1.0 / normalize_fps(fps), 9)


def frame_tolerance_sec(fps: float | int | str | None, frames: float = 1.0) -> float:
    try:
        frame_count_value = float(frames)
    except (TypeError, ValueError):
        frame_count_value = 1.0
    return max(0.0, frame_count_value) / normalize_fps(fps)


def frame_to_position_ms(frame: float | int | str | None, fps: float | int | str | None) -> int:
    return max(0, int(round(frame_to_sec(frame, fps) * 1000.0)))


def frame_count(duration_sec: float | int | str | None, fps: float | int | str | None) -> int:
    value = _coerce_nonnegative_sec(duration_sec)
    return max(0, int(round(value * normalize_fps(fps))))


def segment_frame_bounds(
    segment: dict | None,
    fps: float | int | str | None,
    *,
    min_frames: int = 1,
) -> tuple[int, int]:
    item = dict(segment or {})
    normalized_fps = normalize_fps(fps)
    minimum = max(0, int(min_frames or 0))

    start_frame = None
    end_frame = None

    frame_range = item.get("frame_range")
    if isinstance(frame_range, dict):
        if start_frame is None and frame_range.get("start") is not None:
            start_frame = _coerce_frame_int(frame_range.get("start"))
        if end_frame is None and frame_range.get("end") is not None:
            end_frame = _coerce_frame_int(frame_range.get("end"))

    for key in ("timeline_start_frame", "start_frame"):
        if start_frame is None and item.get(key) is not None:
            start_frame = _coerce_frame_int(item.get(key))
    for key in ("timeline_end_frame", "end_frame"):
        if end_frame is None and item.get(key) is not None:
            end_frame = _coerce_frame_int(item.get(key))

    vector_time = item.get("time")
    if isinstance(vector_time, dict):
        source_fps = normalize_fps(
            vector_time.get("timeline_frame_rate")
            or vector_time.get("frame_rate")
            or vector_time.get("fps")
            or normalized_fps
        )
        if start_frame is None and vector_time.get("start_frame") is not None:
            source_start_frame = _coerce_frame_int(vector_time.get("start_frame"))
            start_frame = sec_to_nearest_frame(frame_to_sec(source_start_frame, source_fps), normalized_fps)
        if end_frame is None and vector_time.get("end_frame") is not None:
            source_end_frame = _coerce_frame_int(vector_time.get("end_frame"))
            end_frame = sec_to_nearest_frame(frame_to_sec(source_end_frame, source_fps), normalized_fps)

    start_sec = _coerce_nonnegative_sec(item.get("start", item.get("timeline_start", 0.0)))
    end_sec = _coerce_nonnegative_sec(item.get("end", item.get("timeline_end", start_sec)))
    end_sec = max(start_sec, end_sec)
    if isinstance(vector_time, dict):
        if start_frame is None and vector_time.get("start_sec") is not None:
            start_sec = _coerce_nonnegative_sec(vector_time.get("start_sec"))
        if end_frame is None and vector_time.get("end_sec") is not None:
            end_sec = _coerce_nonnegative_sec(vector_time.get("end_sec"))
            end_sec = max(start_sec, end_sec)

    if start_frame is None:
        start_frame = sec_to_nearest_frame(start_sec, normalized_fps)
    if end_frame is None:
        end_frame = sec_to_nearest_frame(end_sec, normalized_fps)

    if minimum > 0 and end_frame <= start_frame:
        end_frame = start_frame + minimum
    elif end_frame < start_frame:
        end_frame = start_frame

    return int(start_frame), int(max(start_frame + minimum, end_frame) if minimum > 0 else max(start_frame, end_frame))


def normalize_segment_to_frame_grid(
    segment: dict | None,
    fps: float | int | str | None,
    *,
    min_frames: int = 1,
) -> dict:
    item = dict(segment or {})
    normalized_fps = normalize_fps(fps)
    start_frame, end_frame = segment_frame_bounds(item, normalized_fps, min_frames=min_frames)
    item["start"] = frame_to_sec(start_frame, normalized_fps)
    item["end"] = frame_to_sec(end_frame, normalized_fps)
    if not bool(item.get("is_gap", False)):
        item["start_frame"] = start_frame
        item["end_frame"] = end_frame
        item["timeline_start_frame"] = start_frame
        item["timeline_end_frame"] = end_frame
        item["frame_rate"] = normalized_fps
        item["timeline_frame_rate"] = normalized_fps
        item["frame_range"] = {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": normalized_fps,
        }
    return item


def clamp_segment_to_duration(
    segment: dict | None,
    total_duration_sec: float | int | str | None,
    *,
    fps: float | int | str | None = None,
    drop_empty: bool = True,
) -> dict | None:
    item = dict(segment or {})
    try:
        total = max(0.0, float(total_duration_sec or 0.0))
    except (TypeError, ValueError):
        total = 0.0
    if total <= 0.0:
        return item

    start = _coerce_nonnegative_sec(item.get("start", item.get("timeline_start", 0.0)))
    end = _coerce_nonnegative_sec(item.get("end", item.get("timeline_end", start)))
    end = max(start, end)

    if start >= total - 1e-9:
        return None if drop_empty else {**item, "start": total, "end": total}

    clamped_start = min(start, total)
    clamped_end = min(max(end, clamped_start), total)
    if clamped_end <= clamped_start + 1e-9:
        return None if drop_empty else {**item, "start": clamped_start, "end": clamped_start}

    item["start"] = round(clamped_start, 6)
    item["end"] = round(clamped_end, 6)

    if not bool(item.get("is_gap", False)):
        source_fps = fps
        if source_fps in (None, ""):
            source_fps = item.get("timeline_frame_rate", item.get("frame_rate", DEFAULT_FPS))
        normalized_fps = normalize_fps(source_fps)
        total_frames = frame_count(total, normalized_fps)
        start_frame = min(sec_to_nearest_frame(clamped_start, normalized_fps), total_frames)
        end_frame = min(max(start_frame + 1, sec_to_nearest_frame(clamped_end, normalized_fps)), total_frames)
        if end_frame <= start_frame:
            return None if drop_empty else {**item, "start": clamped_start, "end": clamped_start}
        item["start_frame"] = start_frame
        item["end_frame"] = end_frame
        item["timeline_start_frame"] = start_frame
        item["timeline_end_frame"] = end_frame
        item["frame_rate"] = normalized_fps
        item["timeline_frame_rate"] = normalized_fps
        item["frame_range"] = {
            "unit": "frame",
            "start": start_frame,
            "end": end_frame,
            "timeline_frame_rate": normalized_fps,
        }
    return item


def clamp_segments_to_duration(
    segments: list[dict] | tuple[dict, ...] | None,
    total_duration_sec: float | int | str | None,
    *,
    fps: float | int | str | None = None,
    preserve_order: bool = True,
    drop_empty: bool = True,
) -> list[dict]:
    rows: list[dict] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        clamped = clamp_segment_to_duration(
            seg,
            total_duration_sec,
            fps=fps,
            drop_empty=drop_empty,
        )
        if isinstance(clamped, dict):
            rows.append(clamped)
    if not preserve_order:
        rows.sort(
            key=lambda seg: (
                float(seg.get("start", 0.0) or 0.0),
                float(seg.get("end", seg.get("start", 0.0)) or 0.0),
            )
        )
    return rows


def normalize_segments_to_frame_grid(
    segments: list[dict] | tuple[dict, ...] | None,
    fps: float | int | str | None,
    *,
    min_frames: int = 1,
    collapse_micro_gaps: bool = False,
    max_gap_frames: int = 1,
    preserve_order: bool = False,
) -> list[dict]:
    normalized_fps = normalize_fps(fps)
    rows = [
        normalize_segment_to_frame_grid(seg, normalized_fps, min_frames=min_frames)
        for seg in _iter_segments(segments)
        if isinstance(seg, dict)
    ]
    if not preserve_order:
        rows.sort(
            key=lambda seg: (
                int(seg.get("timeline_start_frame", seg.get("start_frame", 0)) or 0),
                int(seg.get("timeline_end_frame", seg.get("end_frame", 0)) or 0),
            )
        )

    if collapse_micro_gaps and rows:
        max_gap = max(0, int(max_gap_frames or 0))
        for index in range(1, len(rows)):
            prev = rows[index - 1]
            cur = rows[index]
            if bool(prev.get("is_gap")) or bool(cur.get("is_gap")):
                continue
            prev_start, prev_end = segment_frame_bounds(prev, normalized_fps, min_frames=min_frames)
            cur_start, cur_end = segment_frame_bounds(cur, normalized_fps, min_frames=min_frames)
            gap_frames = cur_start - prev_end
            if abs(gap_frames) > max_gap:
                continue
            shared = prev_end
            cur_start = shared
            if cur_end <= cur_start:
                cur_end = cur_start + max(1, int(min_frames or 1))
            prev["end"] = frame_to_sec(shared, normalized_fps)
            prev["end_frame"] = shared
            prev["timeline_end_frame"] = shared
            if isinstance(prev.get("frame_range"), dict):
                prev["frame_range"] = {
                    **dict(prev.get("frame_range") or {}),
                    "end": shared,
                    "timeline_frame_rate": normalized_fps,
                }
            cur["start"] = frame_to_sec(cur_start, normalized_fps)
            cur["end"] = frame_to_sec(cur_end, normalized_fps)
            cur["start_frame"] = cur_start
            cur["end_frame"] = cur_end
            cur["timeline_start_frame"] = cur_start
            cur["timeline_end_frame"] = cur_end
            if isinstance(cur.get("frame_range"), dict):
                cur["frame_range"] = {
                    **dict(cur.get("frame_range") or {}),
                    "start": cur_start,
                    "end": cur_end,
                    "timeline_frame_rate": normalized_fps,
                }
    return rows


@dataclass(frozen=True)
class FrameTimeMap:
    fps: float
    duration_sec: float
    total_frames: int

    def frame_for_sec(self, sec: float | int | str | None) -> int:
        frame = sec_to_nearest_frame(sec, self.fps)
        if self.total_frames <= 0:
            return frame
        return max(0, min(frame, max(0, self.total_frames - 1)))

    def sec_for_frame(self, frame: float | int | str | None) -> float:
        frame_idx = frame
        try:
            frame_idx = int(round(float(frame_idx)))
        except (TypeError, ValueError):
            frame_idx = 0
        if self.total_frames > 0:
            frame_idx = max(0, min(frame_idx, max(0, self.total_frames - 1)))
        return frame_to_sec(frame_idx, self.fps)

    def position_ms_for_frame(self, frame: float | int | str | None) -> int:
        return frame_to_position_ms(frame, self.fps)

    def position_ms_for_sec(self, sec: float | int | str | None) -> int:
        return self.position_ms_for_frame(self.frame_for_sec(sec))

    def snap_sec(self, sec: float | int | str | None) -> float:
        return round(self.sec_for_frame(self.frame_for_sec(sec)), 6)

    def frame_for_position_ms(self, position_ms: float | int | str | None) -> int:
        try:
            sec = float(position_ms) / 1000.0
        except (TypeError, ValueError):
            sec = 0.0
        return self.frame_for_sec(sec)

    def sec_for_position_ms(self, position_ms: float | int | str | None) -> float:
        return self.sec_for_frame(self.frame_for_position_ms(position_ms))


def build_frame_time_map(duration_sec: float | int | str | None, fps: float | int | str | None) -> FrameTimeMap:
    normalized_fps = normalize_fps(fps)
    try:
        duration = max(0.0, float(duration_sec or 0.0))
    except (TypeError, ValueError):
        duration = 0.0
    return FrameTimeMap(
        fps=normalized_fps,
        duration_sec=duration,
        total_frames=frame_count(duration, normalized_fps),
    )
