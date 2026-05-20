# Version: 04.00.10
# Phase: PHASE2
"""Project/editor session bridge helpers.

This module keeps project open/save callers from knowing every editor widget
attribute name. It consumes the explicit editor session model when available
and falls back to legacy widget state outside this small boundary.
"""

from __future__ import annotations

from typing import Any


def _list_view_value(view: dict[str, Any], key: str) -> list:
    value = view.get(key)
    return [] if value is None else list(value)


def _row_count_value(rows: Any) -> int:
    if rows is None:
        return 0
    try:
        return max(0, len(rows))
    except TypeError:
        return sum(1 for _item in rows)


def editor_session_rows(editor: Any, key: str) -> list:
    """Return one session row view without hydrating the full project payload."""

    session = getattr(editor, "editor_session_model", None)
    if session is None:
        return []
    method_name = {
        "segments": "final_subtitle_rows",
        "stt_preview_segments": "stt_preview_rows",
        "voice_activity_segments": "voice_activity_rows",
    }.get(str(key or ""))
    if method_name:
        method = getattr(session, method_name, None)
        if callable(method):
            try:
                return list(method())
            except (RuntimeError, AttributeError, TypeError, ValueError):
                return []
    if str(key or "") in {"boundary_times", "provisional_boundaries"}:
        try:
            value = getattr(session, str(key), None)
            return [] if value is None else list(value)
        except (RuntimeError, AttributeError, TypeError, ValueError):
            return []

    view = editor_session_save_view(editor)
    if view is None:
        return []
    return _list_view_value(view, str(key or ""))


def editor_session_save_view(editor: Any) -> dict[str, Any] | None:
    session = getattr(editor, "editor_session_model", None)
    view_fn = getattr(session, "project_save_view", None)
    if not callable(view_fn):
        return None
    try:
        view = view_fn()
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return None
    if not isinstance(view, dict):
        return None
    return {
        "segments": _list_view_value(view, "segments"),
        "stt_preview_segments": _list_view_value(view, "stt_preview_segments"),
        "voice_activity_segments": _list_view_value(view, "voice_activity_segments"),
        "boundary_times": _list_view_value(view, "boundary_times"),
        "provisional_boundaries": _list_view_value(view, "provisional_boundaries"),
        "stt_preview_subtitle_drafts": view.get("stt_preview_subtitle_drafts"),
    }


def editor_session_row_counts(editor: Any) -> dict[str, int] | None:
    session = getattr(editor, "editor_session_model", None)
    if session is None:
        return None
    try:
        return {
            "final_subtitle_segment_count": _row_count_value(getattr(session, "final_segments", None)),
            "stt_preview_segment_count": _row_count_value(getattr(session, "stt_preview_segments", None)),
            "voice_activity_segment_count": _row_count_value(getattr(session, "voice_activity_segments", None)),
            "provisional_cut_boundary_count": _row_count_value(getattr(session, "provisional_boundaries", None)),
        }
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return None


__all__ = [
    "editor_session_row_counts",
    "editor_session_rows",
    "editor_session_save_view",
]
