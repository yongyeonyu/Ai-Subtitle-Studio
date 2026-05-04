"""Shared media queue ordering helpers for folder/NAS/iCloud sources."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable


MEDIA_QUEUE_EXTENSIONS = (
    ".mp4",
    ".mov",
    ".m4v",
    ".lrf",
    ".wav",
    ".m4a",
    ".m2a",
    ".mp3",
    ".aac",
)


def natural_sort_key(value: str) -> tuple:
    text = str(value or "")
    parts = re.split(r"(\d+)", text.casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def media_entry_allowed(path: str, valid_extensions: Iterable[str] | None = None) -> bool:
    name = os.path.basename(str(path or ""))
    if not name or name.startswith(".") or "_자막소스.mov" in name:
        return False
    valid = tuple(ext.lower() for ext in (valid_extensions or MEDIA_QUEUE_EXTENSIONS))
    return os.path.splitext(name)[1].lower() in valid


def normalized_excluded_paths(paths: Iterable[str] | None = None) -> set[str]:
    return {os.path.normpath(str(path)) for path in (paths or []) if path}


def path_is_excluded(path: str, excluded_paths: Iterable[str] | None = None) -> bool:
    norm = os.path.normpath(str(path or ""))
    for excluded in normalized_excluded_paths(excluded_paths):
        if norm == excluded or norm.startswith(excluded + os.sep):
            return True
    return False


def ordered_child_paths(
    current_path: str,
    *,
    valid_extensions: Iterable[str] | None = None,
    excluded_paths: Iterable[str] | None = None,
) -> tuple[list[str], list[str]]:
    try:
        names = os.listdir(current_path)
    except (OSError, PermissionError):
        return [], []

    excluded = normalized_excluded_paths(excluded_paths)
    dirs = []
    files = []
    for name in names:
        if not name or name.startswith("."):
            continue
        full_path = os.path.join(current_path, name)
        if path_is_excluded(full_path, excluded):
            continue
        if os.path.isdir(full_path):
            dirs.append(full_path)
        elif os.path.isfile(full_path) and media_entry_allowed(full_path, valid_extensions):
            files.append(full_path)

    dirs.sort(key=lambda path: natural_sort_key(os.path.basename(path)))
    files.sort(key=lambda path: natural_sort_key(os.path.basename(path)))
    return dirs, files


def ordered_media_files(
    root_path: str,
    *,
    valid_extensions: Iterable[str] | None = None,
    excluded_paths: Iterable[str] | None = None,
) -> list[str]:
    root_path = str(root_path or "")
    if not root_path or path_is_excluded(root_path, excluded_paths):
        return []
    if os.path.isfile(root_path):
        return [root_path] if media_entry_allowed(root_path, valid_extensions) else []
    if not os.path.isdir(root_path):
        return []

    ordered = []

    def visit(current_path: str):
        dirs, files = ordered_child_paths(
            current_path,
            valid_extensions=valid_extensions,
            excluded_paths=excluded_paths,
        )
        for folder in dirs:
            visit(folder)
        ordered.extend(files)

    visit(root_path)
    return ordered
