# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Rule/LoRA-policy resegmentation for STT Mode raw dictation."""
from __future__ import annotations

from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.stt_mode.models import FINAL_SUBTITLE_SOURCE, canonical_frame_timing
from core.stt_mode.quality import normalize_protected_terms, normalize_text, split_text_chunks, wrap_subtitle_lines
from core.stt_mode.settings import setting_bool, setting_float, setting_int, stt_settings


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _frame_bounds(row: dict[str, Any], fps: float) -> tuple[int, int]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start = row.get("timeline_start_frame", row.get("start_frame", frame_range.get("start")))
    end = row.get("timeline_end_frame", row.get("end_frame", frame_range.get("end")))
    if start is None:
        start = sec_to_frame(row.get("timeline_start", row.get("start", 0.0)), fps)
    if end is None:
        end = sec_to_frame(row.get("timeline_end", row.get("end", 0.0)), fps)
    start_i = max(0, _safe_int(start))
    end_i = max(start_i, _safe_int(end, start_i))
    return start_i, end_i


def _window_bounds(rolling_window: dict[str, Any], raw_segments: list[dict[str, Any]], fps: float) -> tuple[int, int]:
    if rolling_window:
        start, end = _frame_bounds(rolling_window, fps)
        if end > start:
            return start, end
    starts: list[int] = []
    ends: list[int] = []
    for row in raw_segments or []:
        if not isinstance(row, dict):
            continue
        start, end = _frame_bounds(row, fps)
        starts.append(start)
        ends.append(end)
    if starts and ends:
        return min(starts), max(ends)
    return 0, sec_to_frame(1.0, fps)


def _policy_value(*policies: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    for policy in policies:
        if isinstance(policy, dict) and key in policy:
            value = policy.get(key)
            if value not in (None, ""):
                return value
    return default


def _split_by_cut_boundaries(
    start_frame: int,
    end_frame: int,
    *,
    cut_boundaries: list[dict[str, Any]] | None,
    fps: float,
) -> list[tuple[int, int]]:
    frames: list[int] = []
    for row in cut_boundaries or []:
        if not isinstance(row, dict):
            continue
        frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
        frame = row.get("timeline_frame", row.get("frame", frame_range.get("start")))
        if frame is None:
            frame = sec_to_frame(row.get("time", row.get("start", row.get("timeline_start", 0.0))), fps)
        frame = _safe_int(frame)
        if start_frame < frame < end_frame:
            frames.append(frame)
    points = [start_frame] + sorted(set(frames)) + [end_frame]
    return [
        (points[idx], points[idx + 1])
        for idx in range(len(points) - 1)
        if points[idx + 1] > points[idx]
    ]


def _allocate_frames_by_text(
    chunks: list[str],
    *,
    start_frame: int,
    end_frame: int,
    fps: float,
    min_duration_sec: float,
    max_duration_sec: float,
) -> list[tuple[int, int]]:
    total_frames = max(1, end_frame - start_frame)
    lengths = [max(1, len(normalize_text(chunk).replace("\n", ""))) for chunk in chunks]
    total_len = max(1, sum(lengths))
    min_frames = max(1, sec_to_frame(min_duration_sec, fps))
    max_frames = max(min_frames, sec_to_frame(max_duration_sec, fps))
    spans: list[int] = []
    remaining = total_frames
    for idx, length in enumerate(lengths):
        if idx == len(lengths) - 1:
            span = remaining
        else:
            span = int(round(total_frames * (length / total_len)))
            span = max(min_frames, min(max_frames, span))
            span = min(span, max(min_frames, remaining - min_frames * (len(lengths) - idx - 1)))
        spans.append(max(1, span))
        remaining = max(0, remaining - span)
    if spans:
        spans[-1] += max(0, end_frame - start_frame - sum(spans))
    cursor = start_frame
    ranges: list[tuple[int, int]] = []
    for span in spans:
        next_frame = min(end_frame, cursor + max(1, span))
        ranges.append((cursor, max(cursor + 1, next_frame)))
        cursor = next_frame
    if ranges:
        ranges[-1] = (ranges[-1][0], end_frame)
    return ranges


def resegment_raw_dictation_window(
    *,
    rolling_window: dict[str, Any],
    raw_segments: list[dict[str, Any]],
    fps: float | int | str,
    settings: dict[str, Any] | None = None,
    stt_lora_policy: dict[str, Any] | None = None,
    subtitle_style_policy: dict[str, Any] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Turn raw human dictation into final subtitle segments without LLM usage."""
    cfg = stt_settings(settings)
    timeline_fps = normalize_fps(fps or cfg.get("timeline_frame_rate") or 30.0)
    raw_rows = [dict(row) for row in raw_segments or [] if isinstance(row, dict)]
    text = normalize_text(rolling_window.get("text") if isinstance(rolling_window, dict) else "")
    if not text:
        text = normalize_text(" ".join(str(row.get("text") or row.get("raw_text") or "") for row in raw_rows))
    if not text:
        return []

    protected_terms = normalize_protected_terms(
        cfg.get("protected_terms"),
        (stt_lora_policy or {}).get("protected_terms") if isinstance(stt_lora_policy, dict) else [],
        (subtitle_style_policy or {}).get("protected_terms") if isinstance(subtitle_style_policy, dict) else [],
    )
    target_chars_per_line = max(
        8,
        _safe_int(
            _policy_value(subtitle_style_policy, stt_lora_policy, key="target_chars_per_line"),
            setting_int(cfg, "stt_mode_target_chars_per_line", 12),
        ),
    )
    max_lines = max(
        1,
        _safe_int(
            _policy_value(subtitle_style_policy, stt_lora_policy, key="max_lines"),
            setting_int(cfg, "stt_mode_max_lines", 2),
        ),
    )
    target_chars = max(8, target_chars_per_line * max(1, max_lines))
    chunks = split_text_chunks(text, target_chars=target_chars, protected_terms=protected_terms)
    chunks = [
        wrap_subtitle_lines(
            chunk,
            target_chars_per_line=target_chars_per_line,
            max_lines=max_lines,
            protected_terms=protected_terms,
        )
        for chunk in chunks
        if normalize_text(chunk)
    ]
    start_frame, end_frame = _window_bounds(rolling_window or {}, raw_rows, timeline_fps)
    if end_frame <= start_frame:
        end_frame = start_frame + sec_to_frame(max(0.6, len(text) / 8.0), timeline_fps)

    min_dur = max(
        0.2,
        float(
            _policy_value(
                subtitle_style_policy,
                stt_lora_policy,
                key="min_subtitle_duration_sec",
                default=setting_float(cfg, "stt_mode_min_subtitle_duration_sec", 0.6),
            )
        ),
    )
    max_dur = max(
        min_dur,
        float(
            _policy_value(
                subtitle_style_policy,
                stt_lora_policy,
                key="max_subtitle_duration_sec",
                default=setting_float(cfg, "stt_mode_max_subtitle_duration_sec", 5.5),
            )
        ),
    )
    frame_ranges = _allocate_frames_by_text(
        chunks,
        start_frame=start_frame,
        end_frame=end_frame,
        fps=timeline_fps,
        min_duration_sec=min_dur,
        max_duration_sec=max_dur,
    )
    parent_ids = [
        str(row.get("id") or "")
        for row in raw_rows
        if row.get("id")
    ]
    window_id = str((rolling_window or {}).get("id") or "stt_window")
    out: list[dict[str, Any]] = []
    for idx, (chunk, (seg_start, seg_end)) in enumerate(zip(chunks, frame_ranges), start=1):
        respect_cut_boundaries = bool(
            _policy_value(
                stt_lora_policy,
                subtitle_style_policy,
                key="respect_cut_boundaries",
                default=setting_bool(cfg, "stt_mode_respect_cut_boundaries", True),
            )
        )
        ranges = (
            _split_by_cut_boundaries(seg_start, seg_end, cut_boundaries=cut_boundaries, fps=timeline_fps)
            if respect_cut_boundaries else
            [(seg_start, seg_end)]
        )
        for part_idx, (part_start, part_end) in enumerate(ranges, start=1):
            text_part = chunk if len(ranges) == 1 else chunk
            timing = canonical_frame_timing(
                frame_to_sec(part_start, timeline_fps),
                frame_to_sec(part_end, timeline_fps),
                frame_rate=timeline_fps,
                timeline_frame_rate=timeline_fps,
            )
            item = {
                "id": f"stt_final_{len(out) + 1:04d}",
                "index": len(out) + 1,
                "line": len(out),
                "source": FINAL_SUBTITLE_SOURCE,
                "text": text_part,
                "parent_dictation_ids": parent_ids,
                "rolling_window_id": window_id,
                "style_resegmented": True,
                "style_source": "stt_lora_deep_rule",
                "whisper_used": False,
                "llm_used": False,
                "manual_edited": False,
                "locked": False,
                "stt_mode": True,
                "stt_pending": False,
            }
            if len(ranges) > 1:
                item["split_reason"] = "cut_boundary"
                item["split_part"] = part_idx
            item.update(timing)
            out.append(item)
    return out


__all__ = [
    "resegment_raw_dictation_window",
]
