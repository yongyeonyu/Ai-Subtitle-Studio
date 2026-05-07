# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Build comfortable STT work segments from VAD ensemble regions."""
from __future__ import annotations

from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.stt_mode.models import STT_WORK_SEGMENT_SOURCE, canonical_frame_timing
from core.stt_mode.settings import setting_bool, setting_float


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _copy_timing(row: dict[str, Any], start_frame: int, end_frame: int, fps: float) -> dict[str, Any]:
    out = dict(row)
    timing = canonical_frame_timing(
        frame_to_sec(start_frame, fps),
        frame_to_sec(max(start_frame, end_frame), fps),
        frame_rate=fps,
        timeline_frame_rate=fps,
    )
    out.update(timing)
    return out


def _row_frames(row: dict[str, Any], fps: float) -> tuple[int, int]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start_frame = row.get("timeline_start_frame", row.get("start_frame", frame_range.get("start")))
    end_frame = row.get("timeline_end_frame", row.get("end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_frame(row.get("timeline_start", row.get("start", 0.0)), fps)
    if end_frame is None:
        end_frame = sec_to_frame(row.get("timeline_end", row.get("end", 0.0)), fps)
    start = max(0, int(start_frame or 0))
    end = max(start, int(end_frame or start))
    return start, end


def _boundary_frames(cut_boundaries: list[dict[str, Any]] | None, fps: float) -> list[int]:
    frames: set[int] = set()
    for row in cut_boundaries or []:
        if not isinstance(row, dict):
            continue
        frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
        frame = row.get("timeline_frame", row.get("frame", frame_range.get("start")))
        if frame is None:
            frame = sec_to_frame(row.get("time", row.get("start", row.get("timeline_start", 0.0))), fps)
        try:
            frames.add(max(0, int(frame)))
        except (TypeError, ValueError):
            continue
    return sorted(frames)


def split_at_cut_boundaries(
    segment: dict[str, Any],
    *,
    cut_boundaries: list[dict[str, Any]] | None = None,
    fps: float = 30.0,
    min_duration_sec: float = 0.45,
) -> list[dict[str, Any]]:
    start, end = _row_frames(segment, fps)
    min_frames = max(1, sec_to_frame(min_duration_sec, fps))
    boundaries = [frame for frame in _boundary_frames(cut_boundaries, fps) if start + min_frames <= frame <= end - min_frames]
    if not boundaries:
        return [_copy_timing(segment, start, end, fps)]
    out: list[dict[str, Any]] = []
    cursor = start
    for frame in boundaries + [end]:
        if frame - cursor >= min_frames:
            item = _copy_timing(segment, cursor, frame, fps)
            item["vad_decision"] = str(item.get("vad_decision") or "cut_boundary_split")
            item.setdefault("split_reason", "cut_boundary")
            out.append(item)
        cursor = frame
    return out


def merge_short_segments(
    segments: list[dict[str, Any]],
    *,
    fps: float = 30.0,
    min_duration_sec: float = 0.45,
    merge_gap_sec: float = 0.35,
) -> list[dict[str, Any]]:
    if not segments:
        return []
    min_frames = max(1, sec_to_frame(min_duration_sec, fps))
    gap_frames = max(0, sec_to_frame(merge_gap_sec, fps))
    rows = sorted((dict(row) for row in segments), key=lambda row: _row_frames(row, fps))
    out: list[dict[str, Any]] = []
    for row in rows:
        start, end = _row_frames(row, fps)
        if not out:
            out.append(_copy_timing(row, start, end, fps))
            continue
        prev = out[-1]
        prev_start, prev_end = _row_frames(prev, fps)
        should_merge = (end - start < min_frames or prev_end - prev_start < min_frames) and start - prev_end <= gap_frames
        if should_merge:
            merged = dict(prev)
            merged["end_frame"] = max(prev_end, end)
            merged["timeline_end_frame"] = max(prev_end, end)
            merged["vad_sources"] = sorted(set(prev.get("vad_sources") or []) | set(row.get("vad_sources") or []))
            merged["vad_confidence"] = max(_safe_float(prev.get("vad_confidence")), _safe_float(row.get("vad_confidence")))
            merged["vad_confidence_label"] = str(prev.get("vad_confidence_label") or row.get("vad_confidence_label") or "medium")
            merged["merge_reason"] = "short_fragment"
            out[-1] = _copy_timing(merged, prev_start, max(prev_end, end), fps)
        else:
            out.append(_copy_timing(row, start, end, fps))
    return out


def split_long_segments(
    segments: list[dict[str, Any]],
    *,
    fps: float = 30.0,
    max_duration_sec: float = 9.0,
    target_duration_sec: float = 4.0,
) -> list[dict[str, Any]]:
    max_frames = max(1, sec_to_frame(max_duration_sec, fps))
    target_frames = max(1, sec_to_frame(target_duration_sec, fps))
    out: list[dict[str, Any]] = []
    for row in segments or []:
        start, end = _row_frames(row, fps)
        if end - start <= max_frames:
            out.append(_copy_timing(row, start, end, fps))
            continue
        cursor = start
        part = 1
        while cursor < end:
            next_end = min(end, cursor + target_frames)
            if end - next_end < max(1, target_frames // 2):
                next_end = end
            item = _copy_timing(row, cursor, next_end, fps)
            item["split_reason"] = "max_work_segment"
            item["split_part"] = part
            out.append(item)
            cursor = next_end
            part += 1
    return out


def add_playback_ranges(
    segments: list[dict[str, Any]],
    *,
    media_duration: float | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    preroll = setting_float(settings, "stt_mode_playback_preroll_sec", 0.25)
    postroll = setting_float(settings, "stt_mode_playback_postroll_sec", 0.35)
    duration = None if media_duration is None else max(0.0, float(media_duration or 0.0))
    out: list[dict[str, Any]] = []
    for row in segments or []:
        item = dict(row)
        start = _safe_float(item.get("timeline_start", item.get("start", 0.0)))
        end = _safe_float(item.get("timeline_end", item.get("end", start)), start)
        playback_start = max(0.0, start - max(0.0, preroll))
        playback_end = end + max(0.0, postroll)
        if duration is not None:
            playback_end = min(duration, playback_end)
        item["playback"] = {
            "start": round(playback_start, 3),
            "end": round(max(playback_start, playback_end), 3),
            "preroll_sec": round(max(0.0, preroll), 3),
            "postroll_sec": round(max(0.0, postroll), 3),
        }
        out.append(item)
    return out


def build_stt_work_segments(
    vad_segments: list[dict[str, Any]],
    *,
    cut_boundaries: list[dict[str, Any]] | None = None,
    media_duration: float | None = None,
    fps: float | int | str | None = None,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timeline_fps = normalize_fps(fps or 30.0)
    min_sec = setting_float(settings, "stt_mode_min_work_segment_sec", 0.45)
    target_sec = setting_float(settings, "stt_mode_target_work_segment_sec", 4.0)
    max_sec = setting_float(settings, "stt_mode_max_work_segment_sec", 9.0)
    merge_gap = setting_float(settings, "stt_mode_merge_gap_sec", 0.35)
    respect_cuts = setting_bool(settings, "stt_mode_respect_cut_boundaries", True)
    split_long = setting_bool(settings, "stt_mode_split_long_segments", True)

    split_rows: list[dict[str, Any]] = []
    for row in vad_segments or []:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        row.setdefault("source", STT_WORK_SEGMENT_SOURCE)
        row.setdefault("is_stt_work_segment", True)
        if respect_cuts:
            split_rows.extend(
                split_at_cut_boundaries(
                    row,
                    cut_boundaries=cut_boundaries,
                    fps=timeline_fps,
                    min_duration_sec=min_sec,
                )
            )
        else:
            start, end = _row_frames(row, timeline_fps)
            split_rows.append(_copy_timing(row, start, end, timeline_fps))

    merged = merge_short_segments(
        split_rows,
        fps=timeline_fps,
        min_duration_sec=min_sec,
        merge_gap_sec=merge_gap,
    )
    if split_long:
        merged = split_long_segments(
            merged,
            fps=timeline_fps,
            max_duration_sec=max_sec,
            target_duration_sec=target_sec,
        )
    rows = add_playback_ranges(merged, media_duration=media_duration, settings=settings)
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        start, end = _row_frames(row, timeline_fps)
        if end <= start:
            continue
        item = _copy_timing(row, start, end, timeline_fps)
        item["id"] = str(item.get("id") or f"stt_segment_{idx + 1:04d}")
        item["index"] = idx + 1
        item["line"] = idx
        item["source"] = STT_WORK_SEGMENT_SOURCE
        item["text"] = str(item.get("text", "") or "")
        item["stt_mode"] = True
        item["stt_pending"] = True
        item["stt_mode_status"] = str(item.get("stt_mode_status") or "empty")
        item["is_stt_work_segment"] = True
        if "playback" in row:
            item["playback"] = row["playback"]
        out.append(item)
    return out


__all__ = [
    "add_playback_ranges",
    "build_stt_work_segments",
    "merge_short_segments",
    "split_at_cut_boundaries",
    "split_long_segments",
]
