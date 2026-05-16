from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import Any

from core.project.project_assets import copy_project_rows
from core.runtime.logger import get_logger


def _editor_timeline_canvas(editor: Any) -> Any:
    timeline = getattr(editor, "timeline", None)
    return getattr(timeline, "canvas", None) if timeline is not None else None


def _copy_boundary_rows(rows: Any) -> list[Any]:
    out: list[Any] = []
    for item in (() if rows is None else rows):
        out.append(dict(item) if isinstance(item, dict) else item)
    return out


def _row_count(rows: Any) -> int:
    if rows is None:
        return 0
    try:
        return max(0, len(rows))
    except TypeError:
        return sum(1 for _item in rows)


def _has_rows(rows: Any) -> bool:
    if rows is None:
        return False
    try:
        return len(rows) > 0
    except TypeError:
        return True


def _is_deleted_qt_runtime_error(exc: BaseException) -> bool:
    text = str(exc or "")
    return "wrapped C/C++ object" in text and "has been deleted" in text


def _log_runtime_capture_nonfatal(step: str, exc: BaseException) -> None:
    if _is_deleted_qt_runtime_error(exc):
        return
    get_logger().log(
        f"⚠️ 프로젝트 보조 상태 수집 실패 [{step}]: {exc}",
        level="WARN",
        stage="project",
    )


def _runtime_capture_best_effort(step: str, callback, *, default=None):
    try:
        return callback()
    except RuntimeError as exc:
        if _is_deleted_qt_runtime_error(exc):
            return default
        _log_runtime_capture_nonfatal(step, exc)
        return default
    except Exception as exc:
        _log_runtime_capture_nonfatal(step, exc)
        return default


def copy_editor_live_stt_preview_segments(editor: Any) -> list[dict[str, Any]]:
    return copy_project_rows(getattr(editor, "_live_stt_preview_segments", None))


def copy_editor_voice_activity_segments(editor: Any, *, refresh: bool = True) -> list[dict[str, Any]]:
    canvas = _editor_timeline_canvas(editor)
    if canvas is None:
        return []
    if refresh and hasattr(canvas, "_refresh_voice_activity_segments"):
        _runtime_capture_best_effort(
            "voice activity refresh",
            canvas._refresh_voice_activity_segments,
            default=None,
        )
    return _runtime_capture_best_effort(
        "voice activity rows copy",
        lambda: copy_project_rows(getattr(canvas, "voice_activity_segments", None)),
        default=[],
    )


def editor_provisional_cut_boundaries_for_save(editor: Any) -> list[Any]:
    helper = getattr(editor, "_project_provisional_cut_boundaries_for_save", None)
    if callable(helper):
        provisional = _runtime_capture_best_effort(
            "project provisional cut boundaries",
            lambda: _copy_boundary_rows(helper()),
            default=[],
        )
        if provisional:
            return provisional

    canvas = _editor_timeline_canvas(editor)
    provisional = _runtime_capture_best_effort(
        "timeline provisional cut boundaries",
        lambda: _copy_boundary_rows(getattr(canvas, "scan_boundary_times", None)),
        default=[],
    )
    if provisional:
        return provisional
    return _copy_boundary_rows(getattr(editor, "_auto_cut_boundary_scan_lines", None))


def _editor_runtime_sources(editor: Any) -> list[Any]:
    sources: list[Any] = [editor]
    timeline = getattr(editor, "timeline", None)
    canvas = _editor_timeline_canvas(editor)
    global_canvas = getattr(timeline, "global_canvas", None) if timeline is not None else None
    window = None
    try:
        window = editor.window()
    except Exception:
        window = None
    for item in (window, timeline, canvas, global_canvas):
        if item is not None:
            sources.append(item)
    return sources


def _first_row_list_from_sources(sources: list[Any], attrs: tuple[str, ...]) -> list[dict[str, Any]]:
    for source in sources:
        for attr in attrs:
            rows = getattr(source, attr, None)
            copied = copy_project_rows(rows)
            if copied:
                return copied
    return []


def _copy_roughcut_result_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if is_dataclass(value):
        return asdict(value)
    if value is None:
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
        try:
            item = getattr(value, key, None)
        except Exception:
            item = None
        if item not in (None, ""):
            payload[key] = deepcopy(item)
    return payload


def collect_editor_roughcut_project_state(editor: Any) -> dict[str, Any]:
    if editor is None:
        return {
            "middle_segments": [],
            "preliminary_middle_segments": [],
            "roughcut_result": {},
        }
    sources = _editor_runtime_sources(editor)
    middle_segments = _first_row_list_from_sources(
        sources,
        (
            "_middle_segments",
            "middle_segments",
            "_roughcut_segments",
            "roughcut_segments",
            "_chapter_segments",
            "chapter_segments",
            "_roughcut_draft_segments",
            "_cut_boundary_topicless_middle_segments",
            "cut_boundary_topicless_middle_segments",
        ),
    )
    preliminary_middle_segments = _first_row_list_from_sources(
        sources,
        ("_preliminary_middle_segments", "preliminary_middle_segments"),
    )
    roughcut_result: dict[str, Any] = {}
    for source in sources:
        for attr in ("_roughcut_result", "roughcut_result", "_roughcut_draft_result"):
            roughcut_result = _copy_roughcut_result_payload(getattr(source, attr, None))
            if roughcut_result:
                break
        if roughcut_result:
            break
    if not middle_segments and isinstance(roughcut_result.get("segments"), list):
        middle_segments = copy_project_rows(roughcut_result.get("segments"))
    return {
        "middle_segments": middle_segments,
        "preliminary_middle_segments": preliminary_middle_segments,
        "roughcut_result": roughcut_result,
    }


def collect_editor_project_aux_state(editor: Any) -> dict[str, list[Any]]:
    if editor is None:
        return {
            "stt_preview_segments": [],
            "voice_activity_segments": [],
            "provisional_cut_boundaries": [],
            "middle_segments": [],
            "preliminary_middle_segments": [],
            "roughcut_result": {},
        }
    roughcut_state = collect_editor_roughcut_project_state(editor)
    return {
        "stt_preview_segments": copy_editor_live_stt_preview_segments(editor),
        "voice_activity_segments": copy_editor_voice_activity_segments(editor),
        "provisional_cut_boundaries": editor_provisional_cut_boundaries_for_save(editor),
        "middle_segments": roughcut_state["middle_segments"],
        "preliminary_middle_segments": roughcut_state["preliminary_middle_segments"],
        "roughcut_result": roughcut_state["roughcut_result"],
    }


def count_editor_project_aux_state(editor: Any, *, refresh: bool = True) -> dict[str, int]:
    if editor is None:
        return {
            "stt_preview_segment_count": 0,
            "voice_activity_segment_count": 0,
            "provisional_cut_boundary_count": 0,
            "middle_segment_count": 0,
            "preliminary_middle_segment_count": 0,
        }
    canvas = _editor_timeline_canvas(editor)
    if refresh and canvas is not None and hasattr(canvas, "_refresh_voice_activity_segments"):
        _runtime_capture_best_effort(
            "voice activity refresh",
            canvas._refresh_voice_activity_segments,
            default=None,
        )

    provisional = None
    helper = getattr(editor, "_project_provisional_cut_boundaries_for_save", None)
    if callable(helper):
        provisional = _runtime_capture_best_effort(
            "project provisional cut boundaries",
            helper,
            default=None,
        )
    if not _has_rows(provisional) and canvas is not None:
        provisional = getattr(canvas, "scan_boundary_times", [])
    if not _has_rows(provisional):
        provisional = getattr(editor, "_auto_cut_boundary_scan_lines", [])

    return {
        "stt_preview_segment_count": _row_count(getattr(editor, "_live_stt_preview_segments", [])),
        "voice_activity_segment_count": _row_count(
            getattr(canvas, "voice_activity_segments", []) if canvas is not None else []
        ),
        "provisional_cut_boundary_count": _row_count(provisional),
        "middle_segment_count": _row_count(collect_editor_roughcut_project_state(editor).get("middle_segments")),
        "preliminary_middle_segment_count": _row_count(
            collect_editor_roughcut_project_state(editor).get("preliminary_middle_segments")
        ),
    }
