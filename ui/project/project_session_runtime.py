from __future__ import annotations

import os
from typing import Any

from core.project.project_context import project_clip_boundaries, project_media_files
from core.project.project_manager import get_boundary_times


def load_local_project_settings() -> dict[str, Any]:
    try:
        from core.project.data_manager import load_settings

        return dict(load_settings() or {})
    except Exception:
        try:
            from core.settings import load_settings

            return dict(load_settings() or {})
        except Exception:
            return {}


def save_local_project_settings(settings: dict[str, Any]) -> None:
    if not isinstance(settings, dict):
        return
    try:
        from core.project.data_manager import save_settings

        save_settings(settings)
        return
    except Exception:
        pass
    try:
        from core.settings import save_settings

        save_settings(settings)
    except Exception:
        pass


def clear_multiclip_runtime_state(owner: Any) -> None:
    setattr(owner, "_multiclip_files", [])
    setattr(owner, "_multiclip_boundaries", [])
    setattr(owner, "_accumulated_vad", [])
    setattr(owner, "_reuse_existing_multiclip_subtitles", False)


def _emit_project_boundary_signal(owner: Any, rows: list[Any]) -> None:
    signal = getattr(owner, "_sig_update_project_boundary_times", None)
    if signal is None or not hasattr(signal, "emit"):
        return
    try:
        signal.emit(list(rows or []))
    except Exception:
        return


def set_project_boundary_rows(
    owner: Any,
    rows: list[Any] | None,
    *,
    emit_boundary_signal: bool = True,
) -> list[Any]:
    boundary_rows = list(rows or [])
    setattr(owner, "_project_boundary_times", boundary_rows)
    if emit_boundary_signal:
        _emit_project_boundary_signal(owner, boundary_rows)
    return boundary_rows


def detach_project_session(
    owner: Any,
    *,
    auto_pipeline: bool = False,
    clear_multiclip: bool = True,
    emit_boundary_signal: bool = True,
) -> None:
    setattr(owner, "_current_project_path", None)
    set_project_boundary_rows(owner, [], emit_boundary_signal=emit_boundary_signal)
    setattr(owner, "_is_auto_pipeline", bool(auto_pipeline))
    if clear_multiclip:
        clear_multiclip_runtime_state(owner)


def attach_project_session(
    owner: Any,
    filepath: str,
    project: dict[str, Any] | None,
    *,
    auto_pipeline: bool = False,
    clear_multiclip: bool = False,
    emit_boundary_signal: bool = True,
) -> list[Any]:
    setattr(owner, "_current_project_path", filepath)
    setattr(owner, "_is_auto_pipeline", bool(auto_pipeline))
    if clear_multiclip:
        clear_multiclip_runtime_state(owner)
    boundaries = get_boundary_times(project or {}) if isinstance(project, dict) else []
    return set_project_boundary_rows(
        owner,
        list(boundaries or []),
        emit_boundary_signal=emit_boundary_signal,
    )


def apply_project_multiclip_runtime(
    owner: Any,
    media: list[str] | None,
    project: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    media_paths = [str(path or "").strip() for path in list(media or []) if str(path or "").strip()]
    boundaries = project_clip_boundaries(project or {}) if isinstance(project, dict) else []
    if len(media_paths) > 1:
        setattr(owner, "_multiclip_files", list(media_paths))
        setattr(owner, "_multiclip_boundaries", list(boundaries or []))
    else:
        setattr(owner, "_multiclip_files", [])
        setattr(owner, "_multiclip_boundaries", [])
    return list(boundaries or [])


def set_runtime_multiclip_state(
    owner: Any,
    media: list[str] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    project_boundary_rows: list[Any] | None = None,
    emit_boundary_signal: bool = True,
) -> list[dict[str, Any]]:
    media_paths = [str(path or "").strip() for path in list(media or []) if str(path or "").strip()]
    runtime_boundaries = [dict(item) for item in list(boundaries or []) if isinstance(item, dict)]
    if len(media_paths) > 1:
        setattr(owner, "_multiclip_files", list(media_paths))
        setattr(owner, "_multiclip_boundaries", runtime_boundaries)
    else:
        setattr(owner, "_multiclip_files", [])
        setattr(owner, "_multiclip_boundaries", [])
    if project_boundary_rows is not None:
        set_project_boundary_rows(
            owner,
            project_boundary_rows,
            emit_boundary_signal=emit_boundary_signal,
        )
    return runtime_boundaries


def sorted_project_media_paths(project: dict[str, Any] | None) -> list[str]:
    media_files = project_media_files(project or {})
    if media_files:
        return [path for path in media_files if os.path.exists(path)]
    return [
        item["path"]
        for item in sorted((project or {}).get("media", []), key=lambda x: x.get("order", 0))
        if os.path.exists(item["path"])
    ]
