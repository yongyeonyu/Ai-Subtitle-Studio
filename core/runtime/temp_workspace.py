from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

TEMP_WORKSPACE_DIRNAME = "AISubtitleStudioTemporaryWorkspace"
TRACE_PACKAGE_RETENTION_LIMIT = 10
REQUIRED_SUBDIRECTORIES = (
    "Diagnostics/Trace",
    "Diagnostics/Trace/runs",
    "Diagnostics/Packages",
    "Exports",
    "Voice",
    "Preview",
)


def _workspace_owner_suffix() -> str:
    try:
        uid = str(os.getuid())
    except AttributeError:
        uid = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(uid))
    return safe or "user"


def temp_workspace_root(root: str | Path | None = None) -> Path:
    if root:
        return Path(root).expanduser()
    override = os.environ.get("AI_SUBTITLE_STUDIO_TEMP_WORKSPACE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / f"{TEMP_WORKSPACE_DIRNAME}-{_workspace_owner_suffix()}"


def ensure_temp_workspace(root: str | Path | None = None) -> dict[str, Path]:
    base = temp_workspace_root(root)
    paths: dict[str, Path] = {"root": base}
    for relative in REQUIRED_SUBDIRECTORIES:
        path = base / relative
        path.mkdir(parents=True, exist_ok=True)
        paths[relative] = path
    return paths


def trace_workspace_dir(root: str | Path | None = None) -> Path:
    return ensure_temp_workspace(root)["Diagnostics/Trace"]


def package_workspace_dir(root: str | Path | None = None) -> Path:
    return ensure_temp_workspace(root)["Diagnostics/Packages"]


def trace_runs_workspace_dir(root: str | Path | None = None) -> Path:
    return ensure_temp_workspace(root)["Diagnostics/Trace/runs"]


def preview_workspace_dir(root: str | Path | None = None) -> Path:
    return ensure_temp_workspace(root)["Preview"]


def workspace_usage(root: str | Path | None = None) -> dict[str, Any]:
    base = temp_workspace_root(root)
    total_bytes = 0
    file_count = 0
    directories: list[dict[str, Any]] = []
    for relative in REQUIRED_SUBDIRECTORIES:
        path = base / relative
        bytes_here = 0
        files_here = 0
        if path.exists():
            for candidate in path.rglob("*"):
                try:
                    if not candidate.is_file():
                        continue
                    stat = candidate.stat()
                except OSError:
                    continue
                bytes_here += max(0, int(stat.st_size or 0))
                files_here += 1
        total_bytes += bytes_here
        file_count += files_here
        directories.append({
            "path": str(path),
            "exists": path.exists(),
            "bytes": bytes_here,
            "files": files_here,
        })
    return {
        "root": str(base),
        "exists": base.exists(),
        "total_bytes": total_bytes,
        "file_count": file_count,
        "directories": directories,
    }


def cleanup_temp_workspace(root: str | Path | None = None) -> dict[str, Any]:
    base = temp_workspace_root(root)
    before = workspace_usage(base)
    removed = False
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
        removed = not base.exists()
    return {
        "root": str(base),
        "removed": removed,
        "before": before,
        "after": workspace_usage(base),
    }


def prune_temp_workspace(
    root: str | Path | None = None,
    *,
    target_total_bytes: int = 2 * 1024 * 1024 * 1024,
    max_age_sec: float = 7 * 24 * 3600,
) -> dict[str, Any]:
    base = temp_workspace_root(root)
    now = time.time()
    before = workspace_usage(base)
    removed_files = 0
    removed_bytes = 0
    files: list[tuple[float, int, Path]] = []
    if base.exists():
        for candidate in base.rglob("*"):
            try:
                if not candidate.is_file():
                    continue
                stat = candidate.stat()
            except OSError:
                continue
            files.append((float(stat.st_mtime or 0.0), max(0, int(stat.st_size or 0)), candidate))

    total = int(before.get("total_bytes", 0) or 0)
    for mtime, size, path in sorted(files, key=lambda item: item[0]):
        too_old = max_age_sec >= 0 and (now - mtime) > float(max_age_sec)
        too_large = total > int(target_total_bytes)
        if not (too_old or too_large):
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed_files += 1
        removed_bytes += size
        total = max(0, total - size)

    for directory in sorted((p for p in base.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            continue

    after = workspace_usage(base)
    return {
        "root": str(base),
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "before": before,
        "after": after,
    }


def prune_trace_run_directories(
    root: str | Path | None = None,
    *,
    max_runs: int = 20,
) -> dict[str, Any]:
    runs_dir = trace_runs_workspace_dir(root)
    try:
        keep_count = max(0, int(max_runs))
    except (TypeError, ValueError):
        keep_count = 20
    run_dirs: list[tuple[float, str, Path]] = []
    if runs_dir.exists():
        for candidate in runs_dir.iterdir():
            try:
                if not candidate.is_dir():
                    continue
                stat = candidate.stat()
            except OSError:
                continue
            run_dirs.append((float(stat.st_mtime or 0.0), candidate.name, candidate))
    before_count = len(run_dirs)
    removed: list[str] = []
    for _, _, path in sorted(run_dirs, key=lambda item: (item[0], item[1]))[: max(0, before_count - keep_count)]:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue
        if not path.exists():
            removed.append(path.name)
    after_count = 0
    try:
        after_count = sum(1 for candidate in runs_dir.iterdir() if candidate.is_dir())
    except OSError:
        after_count = 0
    return {
        "root": str(temp_workspace_root(root)),
        "runs_dir": str(runs_dir),
        "max_runs": keep_count,
        "before_run_count": before_count,
        "after_run_count": after_count,
        "removed_count": len(removed),
        "removed_runs": removed,
    }


def prune_trace_package_directories(
    root: str | Path | None = None,
    *,
    max_packages: int = TRACE_PACKAGE_RETENTION_LIMIT,
) -> dict[str, Any]:
    packages_dir = package_workspace_dir(root)
    try:
        keep_count = max(0, int(max_packages))
    except (TypeError, ValueError):
        keep_count = TRACE_PACKAGE_RETENTION_LIMIT
    package_dirs: list[tuple[float, str, Path]] = []
    if packages_dir.exists():
        for candidate in packages_dir.iterdir():
            try:
                if not candidate.is_dir():
                    continue
                stat = candidate.stat()
            except OSError:
                continue
            package_dirs.append((float(stat.st_mtime or 0.0), candidate.name, candidate))
    before_count = len(package_dirs)
    removed: list[str] = []
    for _, _, path in sorted(package_dirs, key=lambda item: (item[0], item[1]))[: max(0, before_count - keep_count)]:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue
        if not path.exists():
            removed.append(path.name)
    after_count = 0
    try:
        after_count = sum(1 for candidate in packages_dir.iterdir() if candidate.is_dir())
    except OSError:
        after_count = 0
    return {
        "root": str(temp_workspace_root(root)),
        "packages_dir": str(packages_dir),
        "max_packages": keep_count,
        "before_package_count": before_count,
        "after_package_count": after_count,
        "removed_count": len(removed),
        "removed_packages": removed,
    }
