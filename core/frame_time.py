# Version: 03.06.16
# Phase: PHASE2
"""Frame-based time helpers for editor/timeline synchronization."""

from __future__ import annotations

from dataclasses import dataclass
import math

DEFAULT_FPS = 30.0


def normalize_fps(value: float | int | str | None, default: float = DEFAULT_FPS) -> float:
    try:
        fps = float(value)
    except (TypeError, ValueError):
        fps = float(default)
    if fps <= 0:
        fps = float(default)
    return max(1.0, min(240.0, fps))


def sec_to_frame(sec: float | int | str | None, fps: float | int | str | None) -> int:
    try:
        value = float(sec)
    except (TypeError, ValueError):
        value = 0.0
    return max(0, int(math.floor(max(0.0, value) * normalize_fps(fps) + 1e-6)))


def frame_to_sec(frame: float | int | str | None, fps: float | int | str | None) -> float:
    try:
        value = int(round(float(frame)))
    except (TypeError, ValueError):
        value = 0
    return max(0.0, value / normalize_fps(fps))


def snap_sec_to_frame(sec: float | int | str | None, fps: float | int | str | None) -> float:
    return round(frame_to_sec(sec_to_frame(sec, fps), fps), 6)


def frame_duration(fps: float | int | str | None) -> float:
    return round(1.0 / normalize_fps(fps), 9)


def frame_count(duration_sec: float | int | str | None, fps: float | int | str | None) -> int:
    try:
        value = float(duration_sec)
    except (TypeError, ValueError):
        value = 0.0
    return max(0, int(round(max(0.0, value) * normalize_fps(fps))))


@dataclass(frozen=True)
class FrameTimeMap:
    fps: float
    duration_sec: float
    total_frames: int

    def frame_for_sec(self, sec: float | int | str | None) -> int:
        frame = sec_to_frame(sec, self.fps)
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
