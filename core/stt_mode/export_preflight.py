# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""STT Mode export preflight checks."""
from __future__ import annotations

from typing import Any

from core.frame_time import normalize_fps, sec_to_frame
from core.stt_mode.quality import subtitle_line_violations
from core.stt_mode.settings import setting_float, setting_int


STT_EXPORT_PREFLIGHT_SCHEMA = "ai_subtitle_studio.stt_export_preflight.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _frame_bounds(row: dict[str, Any], fps: float) -> tuple[int | None, int | None]:
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start = row.get("timeline_start_frame", row.get("start_frame", frame_range.get("start")))
    end = row.get("timeline_end_frame", row.get("end_frame", frame_range.get("end")))
    if start is None and row.get("start") is not None:
        start = sec_to_frame(row.get("timeline_start", row.get("start")), fps)
    if end is None and row.get("end") is not None:
        end = sec_to_frame(row.get("timeline_end", row.get("end")), fps)
    try:
        start_i = int(start)
        end_i = int(end)
    except (TypeError, ValueError):
        return None, None
    return start_i, end_i


def _cut_frames(cut_boundaries: list[dict[str, Any]] | None, fps: float) -> list[int]:
    frames: list[int] = []
    for row in cut_boundaries or []:
        if not isinstance(row, dict):
            continue
        frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
        frame = row.get("timeline_frame", row.get("frame", frame_range.get("start")))
        if frame is None:
            frame = sec_to_frame(row.get("time", row.get("start", row.get("timeline_start", 0.0))), fps)
        try:
            frames.append(int(frame))
        except (TypeError, ValueError):
            continue
    return sorted(set(frames))


def run_stt_export_preflight(
    *,
    final_segments: list[dict[str, Any]],
    work_segments: list[dict[str, Any]] | None = None,
    raw_dictation_segments: list[dict[str, Any]] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
    fps: float | int | str | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeline_fps = normalize_fps(fps or 30.0)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    max_lines = setting_int(settings, "stt_mode_max_lines", 2)
    max_chars = setting_int(settings, "stt_mode_target_chars_per_line", 12) + 8
    min_duration = setting_float(settings, "stt_mode_min_subtitle_duration_sec", 0.6)
    max_duration = setting_float(settings, "stt_mode_max_subtitle_duration_sec", 5.5)
    cuts = _cut_frames(cut_boundaries, timeline_fps)

    raw_by_stt = {str(row.get("stt_segment_id") or ""): row for row in raw_dictation_segments or [] if isinstance(row, dict)}
    final_by_parent: set[str] = set()

    for idx, row in enumerate(final_segments or []):
        if not isinstance(row, dict):
            continue
        seg_id = str(row.get("id") or f"final_{idx + 1}")
        refs.append({"id": seg_id, "index": idx + 1})
        text = str(row.get("text", "") or "").strip()
        if not text:
            errors.append({"code": "empty_final_text", "segment_id": seg_id})
        start_frame, end_frame = _frame_bounds(row, timeline_fps)
        if start_frame is None or end_frame is None:
            errors.append({"code": "missing_frame_fields", "segment_id": seg_id})
            continue
        if end_frame <= start_frame:
            errors.append({"code": "invalid_frame_range", "segment_id": seg_id})
        duration = (end_frame - start_frame) / timeline_fps
        if duration < min_duration:
            warnings.append({"code": "duration_too_short", "segment_id": seg_id, "duration": round(duration, 3)})
        if duration > max_duration:
            warnings.append({"code": "duration_too_long", "segment_id": seg_id, "duration": round(duration, 3)})
        for violation in subtitle_line_violations(text, max_lines=max_lines, max_chars_per_line=max_chars):
            warnings.append({"code": violation, "segment_id": seg_id})
        if any(start_frame < frame < end_frame for frame in cuts):
            warnings.append({"code": "cut_boundary_crossing", "segment_id": seg_id})
        for raw_id in row.get("parent_dictation_ids") or []:
            final_by_parent.add(str(raw_id))

    for row in work_segments or []:
        if not isinstance(row, dict):
            continue
        if row.get("stt_pending") or str(row.get("stt_mode_status") or "") in {"", "empty", "listened", "needs_review"}:
            warnings.append({"code": "pending_stt_work_segment", "segment_id": str(row.get("id") or "")})

    for row in raw_dictation_segments or []:
        if not isinstance(row, dict):
            continue
        raw_id = str(row.get("id") or "")
        stt_id = str(row.get("stt_segment_id") or "")
        if raw_id and raw_id not in final_by_parent and stt_id in raw_by_stt:
            warnings.append({"code": "raw_dictation_without_final", "raw_id": raw_id, "stt_segment_id": stt_id})

    status = "blocked" if errors else ("warning" if warnings else "ok")
    return {
        "schema": STT_EXPORT_PREFLIGHT_SCHEMA,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "segment_refs": refs,
    }


def exportable_stt_segments(final_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in final_segments or []
        if isinstance(row, dict) and not row.get("stt_pending") and str(row.get("text", "") or "").strip()
    ]
    rows.sort(key=lambda row: (row.get("timeline_start_frame", row.get("start_frame", 0)), _safe_float(row.get("start"))))
    return rows


__all__ = [
    "STT_EXPORT_PREFLIGHT_SCHEMA",
    "exportable_stt_segments",
    "run_stt_export_preflight",
]
