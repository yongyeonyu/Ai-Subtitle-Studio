# Version: 03.14.28
# Phase: PHASE2
"""Shared project JSON file I/O helpers."""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from core.json_file import write_json_file_atomic

_PROJECT_FILE_CACHE: dict[str, dict[str, Any]] = {}
_PROJECT_FILE_CACHE_LOCK = threading.RLock()


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


def prime_project_file_cache(filepath: str, project: dict[str, Any]) -> None:
    """Pin an already-loaded project payload in the process cache."""
    if not isinstance(project, dict):
        return
    key = _project_cache_key(filepath)
    signature = _project_file_signature(key)
    with _PROJECT_FILE_CACHE_LOCK:
        _PROJECT_FILE_CACHE[key] = {"signature": signature, "project": project}


def read_project_file(filepath: str) -> dict[str, Any]:
    """Read a project JSON file with the app-wide encoding/settings."""
    key = _project_cache_key(filepath)
    signature = _project_file_signature(key)
    with _PROJECT_FILE_CACHE_LOCK:
        cached = _PROJECT_FILE_CACHE.get(key)
        if cached and cached.get("signature") == signature:
            project = cached.get("project")
            return project if isinstance(project, dict) else {}

    with open(key, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    project = data if isinstance(data, dict) else {}
    with _PROJECT_FILE_CACHE_LOCK:
        _PROJECT_FILE_CACHE[key] = {"signature": signature, "project": project}
    return project


def write_project_file(filepath: str, project: dict[str, Any]) -> None:
    """Write a project JSON file with stable UTF-8 formatting."""
    key = _project_cache_key(filepath)
    folder = os.path.dirname(key)
    if folder:
        os.makedirs(folder, exist_ok=True)
    write_json_file_atomic(key, project, indent=2, backup=False)
    prime_project_file_cache(key, project)
