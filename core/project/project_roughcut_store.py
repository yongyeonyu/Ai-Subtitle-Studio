from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_nearest_frame

MIDDLE_SEGMENT_SCHEMA = "middle_segments.v2"
PRELIMINARY_MIDDLE_SEGMENT_SCHEMA = "middle_segments.preliminary.v2"
ROUGHCUT_RESULT_SCHEMA = "roughcut_result.frame.v1"

_SEGMENT_TOP_LEVEL_DROP_KEYS = {
    "start",
    "end",
    "timeline_start",
    "timeline_end",
    "frame_rate",
}
_CHAPTER_DROP_KEYS = {
    "start",
    "end",
    "timeline_start",
    "timeline_end",
    "timeline_start_frame",
    "timeline_end_frame",
    "frame_rate",
}


def _iter_rows(rows: Any):
    if rows is None:
        return ()
    return rows


def _copy_row(row: Any) -> dict[str, Any] | None:
    return dict(row) if isinstance(row, dict) else None


def _copy_rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in _iter_rows(rows) if isinstance(row, dict)]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_frame_value(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(round(float(value))))
    except (TypeError, ValueError):
        return None


def _frame_bounds(item: dict[str, Any], primary_fps: float) -> tuple[int, int]:
    frame_range = item.get("frame_range")
    frame_range = frame_range if isinstance(frame_range, dict) else {}
    fps = normalize_fps(
        item.get("timeline_frame_rate")
        or item.get("frame_rate")
        or frame_range.get("timeline_frame_rate")
        or primary_fps
    )
    start_frame = _safe_frame_value(
        item.get("start_frame", item.get("timeline_start_frame", frame_range.get("start")))
    )
    end_frame = _safe_frame_value(
        item.get("end_frame", item.get("timeline_end_frame", frame_range.get("end")))
    )
    if start_frame is None:
        start_sec = _safe_float(item.get("start", item.get("timeline_start", 0.0)), 0.0)
        start_frame = sec_to_nearest_frame(start_sec, fps)
    if end_frame is None:
        end_sec = _safe_float(item.get("end", item.get("timeline_end", start_frame / fps)), start_frame / fps)
        end_frame = sec_to_nearest_frame(max(start_frame / fps, end_sec), fps)
    return int(start_frame), max(int(start_frame), int(end_frame))


def _apply_frame_range_fields(item: dict[str, Any], *, start_frame: int, end_frame: int, fps: float) -> dict[str, Any]:
    start_sec = frame_to_sec(start_frame, fps)
    end_sec = max(start_sec, frame_to_sec(end_frame, fps))
    item["start_frame"] = int(start_frame)
    item["end_frame"] = int(end_frame)
    item["timeline_start_frame"] = int(start_frame)
    item["timeline_end_frame"] = int(end_frame)
    item["frame_rate"] = fps
    item["timeline_frame_rate"] = fps
    item["start"] = start_sec
    item["end"] = end_sec
    item["timeline_start"] = start_sec
    item["timeline_end"] = end_sec
    item["frame_range"] = {
        "unit": "frame",
        "start": int(start_frame),
        "end": int(end_frame),
        "timeline_frame_rate": fps,
    }
    return item


def _normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        values = [value]
    else:
        values = list(value or [])
    return [str(item).strip() for item in values if str(item).strip()]


def normalize_middle_segment_rows(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(_iter_rows(rows), start=1):
        item = _copy_row(raw)
        if item is None:
            continue
        major_id = str(item.get("major_id") or item.get("segment_id") or item.get("id") or chr(64 + min(idx, 26))).strip()
        if not major_id:
            major_id = chr(64 + min(idx, 26))
        segment_id = str(item.get("segment_id") or item.get("id") or major_id).strip() or major_id
        title = str(item.get("title") or item.get("name") or f"중분류 {major_id}").strip()
        summary = str(item.get("summary") or item.get("llm_summary") or "").strip()
        placeholder = bool(
            item.get("is_topicless_placeholder")
            or item.get("is_cut_boundary_placeholder")
            or str(item.get("story_role") or "") == "topicless_placeholder"
            or title == "주제없음"
        )
        default_display_title = major_id if placeholder else f"{major_id} - {title}"
        tags = _normalize_tags(item.get("tags", item.get("keywords", [])))
        stored_keywords = _normalize_tags(item.get("keywords", tags))
        start_frame, end_frame = _frame_bounds(item, fps)
        item.update(
            {
                "id": str(item.get("id") or major_id),
                "segment_id": segment_id,
                "chapter_id": str(item.get("chapter_id") or major_id),
                "major_id": major_id,
                "title": title,
                "name": str(item.get("name") or title),
                "display_title": str(item.get("display_title") or default_display_title).strip(),
                "display_name": str(item.get("display_name") or item.get("display_title") or default_display_title).strip(),
                "label": str(item.get("label") or item.get("display_title") or default_display_title).strip(),
                "summary": summary,
                "llm_summary": str(item.get("llm_summary") or summary)[:240],
                "tags": tags,
                "keywords": stored_keywords,
                "source": str(item.get("source") or ("cut_boundary" if placeholder else "roughcut_draft")).strip(),
                "level": str(item.get("level") or "middle"),
                "segment_type": str(item.get("segment_type") or "middle"),
                "roughcut_level": str(item.get("roughcut_level") or "middle"),
                "category": str(item.get("category") or "middle"),
                "is_middle_segment": True,
                "is_topicless_placeholder": placeholder,
                "is_cut_boundary_placeholder": bool(item.get("is_cut_boundary_placeholder") or placeholder),
            }
        )
        _apply_frame_range_fields(item, start_frame=start_frame, end_frame=end_frame, fps=fps)
        minor_groups = item.get("minor_groups")
        if isinstance(minor_groups, list):
            item["minor_groups"] = normalize_roughcut_minor_groups(minor_groups, primary_fps=fps)
        out.append(item)
    return out


def mark_preliminary_middle_segment_rows(rows: Any) -> list[dict[str, Any]]:
    stamped_rows: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        row["segment_stage"] = "preliminary"
        row["segment_stage_name"] = "예비 중분류 세그먼트"
        row["source"] = str(row.get("source") or "roughcut_llm_preliminary")
        row["preview_lane"] = "global_top"
        row["preview_reference"] = "cut_boundary_topicless_middle_segments"
        stamped_rows.append(row)
    return stamped_rows


def compact_middle_segment_rows(rows: Any) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        for key in _SEGMENT_TOP_LEVEL_DROP_KEYS:
            row.pop(key, None)
        row["timeline_frame_rate"] = normalize_fps(row.get("timeline_frame_rate") or row.get("frame_rate") or 30.0)
        minor_groups = row.get("minor_groups")
        if isinstance(minor_groups, list):
            row["minor_groups"] = compact_roughcut_minor_groups(minor_groups)
        compacted.append(row)
    return compacted


def restore_middle_segment_rows(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    restored: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        start_frame, end_frame = _frame_bounds(row, fps)
        _apply_frame_range_fields(row, start_frame=start_frame, end_frame=end_frame, fps=fps)
        minor_groups = row.get("minor_groups")
        if isinstance(minor_groups, list):
            row["minor_groups"] = restore_roughcut_minor_groups(minor_groups, primary_fps=fps)
        restored.append(row)
    return restored


def normalize_roughcut_minor_groups(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    out: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        start_frame, end_frame = _frame_bounds(row, fps)
        _apply_frame_range_fields(row, start_frame=start_frame, end_frame=end_frame, fps=fps)
        out.append(row)
    return out


def compact_roughcut_minor_groups(rows: Any) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        for key in _SEGMENT_TOP_LEVEL_DROP_KEYS:
            row.pop(key, None)
        row["timeline_frame_rate"] = normalize_fps(row.get("timeline_frame_rate") or row.get("frame_rate") or 30.0)
        compacted.append(row)
    return compacted


def restore_roughcut_minor_groups(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    restored: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        start_frame, end_frame = _frame_bounds(row, fps)
        _apply_frame_range_fields(row, start_frame=start_frame, end_frame=end_frame, fps=fps)
        restored.append(row)
    return restored


def normalize_roughcut_chapters(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    out: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        start_frame, end_frame = _frame_bounds(row, fps)
        _apply_frame_range_fields(row, start_frame=start_frame, end_frame=end_frame, fps=fps)
        out.append(row)
    return out


def compact_roughcut_chapters(rows: Any) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        for key in _CHAPTER_DROP_KEYS:
            row.pop(key, None)
        row["timeline_frame_rate"] = normalize_fps(row.get("timeline_frame_rate") or row.get("frame_rate") or 30.0)
        compacted.append(row)
    return compacted


def restore_roughcut_chapters(rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    fps = normalize_fps(primary_fps)
    restored: list[dict[str, Any]] = []
    for row in _copy_rows(rows):
        start_frame, end_frame = _frame_bounds(row, fps)
        _apply_frame_range_fields(row, start_frame=start_frame, end_frame=end_frame, fps=fps)
        restored.append(row)
    return restored


def _result_like_to_dict(result_like: Any) -> dict[str, Any]:
    if isinstance(result_like, dict):
        return deepcopy(result_like)
    if is_dataclass(result_like):
        return asdict(result_like)
    if result_like is None:
        return {}
    payload: dict[str, Any] = {}
    for key in (
        "segments",
        "chapters",
        "edit_decisions",
        "edl_segments",
        "guide_markdown",
        "markdown_guide",
        "video_summary",
        "warnings",
        "draft_state",
        "schema_version",
        "result_schema_version",
        "packed_phrases",
        "chunks",
        "cut_points",
        "title_suggestions",
    ):
        value = getattr(result_like, key, None)
        if value not in (None, ""):
            payload[key] = deepcopy(value)
    return payload


def normalize_roughcut_result_payload(result_like: Any, *, primary_fps: float) -> dict[str, Any]:
    payload = _result_like_to_dict(result_like)
    if not payload:
        return {}
    normalized = dict(payload)
    if isinstance(normalized.get("segments"), list):
        normalized["segments"] = normalize_middle_segment_rows(normalized.get("segments"), primary_fps=primary_fps)
    if isinstance(normalized.get("chapters"), list):
        normalized["chapters"] = normalize_roughcut_chapters(normalized.get("chapters"), primary_fps=primary_fps)
    normalized["schema"] = str(normalized.get("schema") or ROUGHCUT_RESULT_SCHEMA)
    normalized["schema_version"] = str(
        normalized.get("schema_version")
        or normalized.get("result_schema_version")
        or ROUGHCUT_RESULT_SCHEMA
    )
    if "markdown_guide" not in normalized and normalized.get("guide_markdown"):
        normalized["markdown_guide"] = normalized.get("guide_markdown")
    return normalized


def compact_roughcut_result_payload(result_like: Any, *, primary_fps: float | None = None) -> dict[str, Any]:
    payload = _result_like_to_dict(result_like)
    if not payload:
        return {}
    compacted = dict(payload)
    fps = normalize_fps(primary_fps or compacted.get("timeline_frame_rate") or 30.0)
    if isinstance(compacted.get("segments"), list):
        compacted["segments"] = compact_middle_segment_rows(
            normalize_middle_segment_rows(compacted.get("segments"), primary_fps=fps)
        )
    if isinstance(compacted.get("chapters"), list):
        compacted["chapters"] = compact_roughcut_chapters(
            normalize_roughcut_chapters(compacted.get("chapters"), primary_fps=fps)
        )
    compacted.pop("edl", None)
    if compacted.get("markdown_guide") == compacted.get("guide_markdown"):
        compacted.pop("markdown_guide", None)
    compacted["schema"] = str(compacted.get("schema") or ROUGHCUT_RESULT_SCHEMA)
    compacted["schema_version"] = str(
        compacted.get("schema_version")
        or compacted.get("result_schema_version")
        or ROUGHCUT_RESULT_SCHEMA
    )
    return compacted


def restore_roughcut_result_payload(result_like: Any, *, primary_fps: float) -> dict[str, Any]:
    payload = _result_like_to_dict(result_like)
    if not payload:
        return {}
    restored = dict(payload)
    if isinstance(restored.get("segments"), list):
        restored["segments"] = restore_middle_segment_rows(restored.get("segments"), primary_fps=primary_fps)
    if isinstance(restored.get("chapters"), list):
        restored["chapters"] = restore_roughcut_chapters(restored.get("chapters"), primary_fps=primary_fps)
    if "guide_markdown" not in restored and restored.get("markdown_guide"):
        restored["guide_markdown"] = restored.get("markdown_guide")
    return restored


def selected_roughcut_candidate(roughcut_state: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(roughcut_state or {}) if isinstance(roughcut_state, dict) else {}
    selected = str(state.get("selected_candidate_id") or "").strip()
    candidates = [dict(item) for item in list(state.get("candidates") or []) if isinstance(item, dict)]
    if not candidates:
        return {}
    candidate = next((item for item in candidates if str(item.get("candidate_id") or "") == selected), None)
    return candidate or candidates[0]


def store_project_middle_segments(project: dict[str, Any], rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    saved_rows = normalize_middle_segment_rows(rows, primary_fps=primary_fps)
    analysis = project.setdefault("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
        project["analysis"] = analysis
    if saved_rows:
        analysis["middle_segment_schema"] = MIDDLE_SEGMENT_SCHEMA
        analysis["middle_segments"] = list(saved_rows)
        analysis["middle_segments_updated_at"] = datetime.now().isoformat()
        analysis["middle_segments_placeholder_only"] = all(
            bool(row.get("is_topicless_placeholder") or row.get("is_cut_boundary_placeholder"))
            for row in saved_rows
        )
        project["middle_segments"] = list(saved_rows)
    else:
        analysis.pop("middle_segment_schema", None)
        analysis.pop("middle_segments", None)
        analysis.pop("middle_segments_updated_at", None)
        analysis.pop("middle_segments_placeholder_only", None)
        project.pop("middle_segments", None)
    return saved_rows


def store_project_preliminary_middle_segments(project: dict[str, Any], rows: Any, *, primary_fps: float) -> list[dict[str, Any]]:
    if not isinstance(project, dict):
        return []
    analysis = project.setdefault("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
        project["analysis"] = analysis
    saved_rows = normalize_middle_segment_rows(rows, primary_fps=primary_fps)
    stamped_rows = mark_preliminary_middle_segment_rows(saved_rows)
    if stamped_rows:
        analysis["preliminary_middle_segments_schema"] = PRELIMINARY_MIDDLE_SEGMENT_SCHEMA
        analysis["preliminary_middle_segments"] = list(stamped_rows)
        analysis["preliminary_middle_segments_updated_at"] = datetime.now().isoformat()
        project["preliminary_middle_segments"] = list(stamped_rows)
    else:
        analysis.pop("preliminary_middle_segments_schema", None)
        analysis.pop("preliminary_middle_segments", None)
        analysis.pop("preliminary_middle_segments_updated_at", None)
        project.pop("preliminary_middle_segments", None)
    return stamped_rows


def store_project_roughcut_result(project: dict[str, Any], result_like: Any, *, primary_fps: float) -> dict[str, Any]:
    if not isinstance(project, dict):
        return {}
    analysis = project.setdefault("analysis", {})
    if not isinstance(analysis, dict):
        analysis = {}
        project["analysis"] = analysis
    normalized = normalize_roughcut_result_payload(result_like, primary_fps=primary_fps)
    if normalized:
        analysis["roughcut_result_schema"] = ROUGHCUT_RESULT_SCHEMA
        analysis["roughcut_result"] = normalized
        analysis["roughcut_result_updated_at"] = datetime.now().isoformat()
        project["roughcut_result"] = normalized
    else:
        analysis.pop("roughcut_result_schema", None)
        analysis.pop("roughcut_result", None)
        analysis.pop("roughcut_result_updated_at", None)
        project.pop("roughcut_result", None)
    return normalized


def compact_project_roughcut_payload(project: dict[str, Any], *, primary_fps: float) -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    analysis = project.get("analysis")
    if isinstance(analysis, dict):
        for key in ("cut_boundary_topicless_middle_segments", "topicless_middle_segments", "roughcut_topicless_segments"):
            if isinstance(analysis.get(key), list):
                analysis[key] = compact_middle_segment_rows(
                    normalize_middle_segment_rows(analysis.get(key), primary_fps=primary_fps)
                )
        if isinstance(analysis.get("middle_segments"), list):
            analysis["middle_segments"] = compact_middle_segment_rows(
                normalize_middle_segment_rows(analysis.get("middle_segments"), primary_fps=primary_fps)
            )
        if isinstance(analysis.get("preliminary_middle_segments"), list):
            analysis["preliminary_middle_segments"] = compact_middle_segment_rows(
                normalize_middle_segment_rows(analysis.get("preliminary_middle_segments"), primary_fps=primary_fps)
            )
        if isinstance(analysis.get("roughcut_result"), dict):
            analysis["roughcut_result"] = compact_roughcut_result_payload(
                analysis.get("roughcut_result"),
                primary_fps=primary_fps,
            )
    roughcut_state = project.get("roughcut_state")
    if isinstance(roughcut_state, dict):
        candidates = roughcut_state.get("candidates")
        if isinstance(candidates, list):
            roughcut_state["candidates"] = [
                compact_roughcut_result_payload(item, primary_fps=primary_fps)
                for item in candidates
                if isinstance(item, dict)
            ]
        for key in ("segments", "chapters"):
            value = roughcut_state.get(key)
            if key == "segments" and isinstance(value, list):
                roughcut_state[key] = compact_middle_segment_rows(
                    normalize_middle_segment_rows(value, primary_fps=primary_fps)
                )
            elif key == "chapters" and isinstance(value, list):
                roughcut_state[key] = compact_roughcut_chapters(
                    normalize_roughcut_chapters(value, primary_fps=primary_fps)
                )
        if roughcut_state.get("markdown_guide") == roughcut_state.get("guide_markdown"):
            roughcut_state.pop("markdown_guide", None)
        roughcut_state.pop("edl", None)
    if isinstance(project.get("roughcut_result"), dict):
        project["roughcut_result"] = compact_roughcut_result_payload(
            project.get("roughcut_result"),
            primary_fps=primary_fps,
        )
        if isinstance(analysis, dict) and isinstance(analysis.get("roughcut_result"), dict):
            project.pop("roughcut_result", None)
    project.pop("middle_segments", None)
    project.pop("preliminary_middle_segments", None)
    return project


def hydrate_project_roughcut_payload(project: dict[str, Any], *, primary_fps: float) -> dict[str, Any]:
    if not isinstance(project, dict):
        return project
    analysis = project.get("analysis")
    if isinstance(analysis, dict):
        for key in ("cut_boundary_topicless_middle_segments", "topicless_middle_segments", "roughcut_topicless_segments"):
            if isinstance(analysis.get(key), list):
                analysis[key] = restore_middle_segment_rows(analysis.get(key), primary_fps=primary_fps)
        if isinstance(analysis.get("middle_segments"), list):
            analysis["middle_segments"] = restore_middle_segment_rows(analysis.get("middle_segments"), primary_fps=primary_fps)
            project["middle_segments"] = _copy_rows(analysis.get("middle_segments"))
        if isinstance(analysis.get("preliminary_middle_segments"), list):
            analysis["preliminary_middle_segments"] = restore_middle_segment_rows(
                analysis.get("preliminary_middle_segments"),
                primary_fps=primary_fps,
            )
            project["preliminary_middle_segments"] = _copy_rows(analysis.get("preliminary_middle_segments"))
        if isinstance(analysis.get("roughcut_result"), dict):
            analysis["roughcut_result"] = restore_roughcut_result_payload(
                analysis.get("roughcut_result"),
                primary_fps=primary_fps,
            )
            project["roughcut_result"] = deepcopy(analysis.get("roughcut_result"))
    if isinstance(project.get("middle_segments"), list):
        project["middle_segments"] = restore_middle_segment_rows(project.get("middle_segments"), primary_fps=primary_fps)
    if isinstance(project.get("preliminary_middle_segments"), list):
        project["preliminary_middle_segments"] = restore_middle_segment_rows(
            project.get("preliminary_middle_segments"),
            primary_fps=primary_fps,
        )
    if isinstance(project.get("roughcut_result"), dict):
        project["roughcut_result"] = restore_roughcut_result_payload(
            project.get("roughcut_result"),
            primary_fps=primary_fps,
        )
    roughcut_state = project.get("roughcut_state")
    if isinstance(roughcut_state, dict):
        if isinstance(roughcut_state.get("segments"), list):
            roughcut_state["segments"] = restore_middle_segment_rows(
                roughcut_state.get("segments"),
                primary_fps=primary_fps,
            )
        if isinstance(roughcut_state.get("chapters"), list):
            roughcut_state["chapters"] = restore_roughcut_chapters(
                roughcut_state.get("chapters"),
                primary_fps=primary_fps,
            )
        candidates = roughcut_state.get("candidates")
        if isinstance(candidates, list):
            roughcut_state["candidates"] = [
                restore_roughcut_result_payload(item, primary_fps=primary_fps)
                for item in candidates
                if isinstance(item, dict)
            ]
        if "guide_markdown" not in roughcut_state and roughcut_state.get("markdown_guide"):
            roughcut_state["guide_markdown"] = roughcut_state.get("markdown_guide")
    if not isinstance(project.get("roughcut_result"), dict):
        selected = selected_roughcut_candidate(project.get("roughcut_state"))
        if selected:
            project["roughcut_result"] = restore_roughcut_result_payload(selected, primary_fps=primary_fps)
    return project
