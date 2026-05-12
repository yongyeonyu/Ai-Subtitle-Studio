# Version: 03.14.28
# Phase: PHASE2
"""Shared project JSON file I/O helpers."""
from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any

from core.json_file import write_json_file_atomic
from core.project.project_format import build_storage_project_payload, hydrate_project_runtime_views

_PROJECT_FILE_CACHE_MAX = 4
_PROJECT_FILE_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_PROJECT_FILE_CACHE_LOCK = threading.RLock()
_PROJECT_RUNTIME_KEYS = {
    "_project_file_path",
    "_external_subtitle_segments_cache",
    "_external_stt_tracks_cache",
    "_hot_open_subtitle_segments_cache",
    "_hot_open_stt_preview_segments_cache",
    "project_path",
}


def _project_cache_key(filepath: str) -> str:
    return os.path.abspath(os.path.expanduser(str(filepath or "")))


def _project_file_signature(filepath: str) -> tuple[int, int] | None:
    try:
        stat = os.stat(filepath)
        return int(stat.st_mtime_ns), int(stat.st_size)
    except OSError:
        return None


def clear_project_file_cache(filepath: str | None = None) -> None:
    """Clear cached project JSON data.

    Passing a path clears one project; omitting it clears the full process cache.
    """
    with _PROJECT_FILE_CACHE_LOCK:
        if filepath:
            _PROJECT_FILE_CACHE.pop(_project_cache_key(filepath), None)
        else:
            _PROJECT_FILE_CACHE.clear()


def _cache_project_payload(filepath: str, signature: tuple[int, int] | None, project: dict[str, Any]) -> None:
    key = _project_cache_key(filepath)
    with _PROJECT_FILE_CACHE_LOCK:
        _PROJECT_FILE_CACHE[key] = {"signature": signature, "project": project}
        _PROJECT_FILE_CACHE.move_to_end(key)
        while len(_PROJECT_FILE_CACHE) > _PROJECT_FILE_CACHE_MAX:
            _PROJECT_FILE_CACHE.popitem(last=False)


def prime_project_file_cache(filepath: str, project: dict[str, Any]) -> None:
    """Pin an already-loaded project payload in the process cache."""
    if not isinstance(project, dict):
        return
    key = _project_cache_key(filepath)
    project["_project_file_path"] = key
    signature = _project_file_signature(key)
    _cache_project_payload(key, signature, project)


def _attach_project_path(project: dict[str, Any], filepath: str) -> dict[str, Any]:
    if isinstance(project, dict):
        project["_project_file_path"] = _project_cache_key(filepath)
    return project


def _project_payload_for_disk(project: dict[str, Any]) -> dict[str, Any]:
    payload = dict(project if isinstance(project, dict) else {})
    for key in _PROJECT_RUNTIME_KEYS:
        payload.pop(key, None)
    try:
        from core.project.project_assets import PROJECT_EXTERNAL_STORAGE, project_uses_external_text_assets

        if project_uses_external_text_assets(payload):
            payload.pop("segments", None)
            subtitles = dict(payload.get("subtitles", {}) or {})
            subtitles.pop("segments", None)
            subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
            payload["subtitles"] = subtitles

            editor_state = dict(payload.get("editor_state", {}) or {})
            editor_subtitles = dict(editor_state.get("subtitles", {}) or {})
            editor_subtitles["segments"] = []
            editor_subtitles["storage"] = PROJECT_EXTERNAL_STORAGE
            editor_state["subtitles"] = editor_subtitles

            rendering = dict(editor_state.get("rendering", {}) or {})
            canvas = dict(rendering.get("subtitle_canvas", {}) or {})
            canvas["segments"] = []
            rendering["subtitle_canvas"] = canvas
            editor_state["rendering"] = rendering

            stt_state = dict(editor_state.get("stt", {}) or {})
            stt_state["preview_segments"] = []
            stt_state["candidate_tracks"] = {}
            editor_state["stt"] = stt_state
            editor_analysis = dict(editor_state.get("analysis", {}) or {})
            editor_analysis.pop("stt_candidate_tracks", None)
            editor_state["analysis"] = editor_analysis
            payload["editor_state"] = editor_state

            analysis = dict(payload.get("analysis", {}) or {})
            analysis.pop("stt_candidate_tracks", None)
            payload["analysis"] = analysis
    except Exception:
        pass
    return build_storage_project_payload(payload)


def _read_project_payload_from_disk(key: str) -> dict[str, Any]:
    data = None
    try:
        from core.native_swift_project import read_project_via_swift

        data = read_project_via_swift(key)
    except Exception:
        data = None
    if data is None:
        with open(key, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    return data if isinstance(data, dict) else {}


def read_project_file(filepath: str) -> dict[str, Any]:
    """Read a project JSON file with the app-wide encoding/settings."""
    key = _project_cache_key(filepath)
    signature = _project_file_signature(key)
    with _PROJECT_FILE_CACHE_LOCK:
        cached = _PROJECT_FILE_CACHE.get(key)
        if cached and cached.get("signature") == signature:
            _PROJECT_FILE_CACHE.move_to_end(key)
            project = cached.get("project")
            return _attach_project_path(project, key) if isinstance(project, dict) else {}

    data = _read_project_payload_from_disk(key)
    project = _attach_project_path(data if isinstance(data, dict) else {}, key)
    hydrate_project_runtime_views(project)
    _cache_project_payload(key, signature, project)
    return project


def write_project_file(filepath: str, project: dict[str, Any]) -> None:
    """Write a project JSON file with stable UTF-8 formatting."""
    key = _project_cache_key(filepath)
    folder = os.path.dirname(key)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = _project_payload_for_disk(project)
    wrote_native = False
    if str(os.environ.get("AI_SUBTITLE_STUDIO_SWIFT_PROJECT_WRITE", "0") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        try:
            from core.native_swift_project import write_project_via_swift

            wrote_native = write_project_via_swift(key, payload)
        except Exception:
            wrote_native = False
    if not wrote_native:
        write_json_file_atomic(key, payload, indent=2, backup=False)
    prime_project_file_cache(key, project)
