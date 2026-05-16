# Version: 03.01.31
# Phase: PHASE2
from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.runtime.memory_manager import register_runtime_cache_path, prune_runtime_disk_caches, scaled_runtime_cache_budget_bytes

from .frame_sampler import build_ffmpeg_frame_command

_THUMBNAIL_CACHE_BUDGET_RATIO = 0.08
_THUMBNAIL_CACHE_BUDGET_MIN_BYTES = 96 * 1024 * 1024
_THUMBNAIL_CACHE_BUDGET_MAX_BYTES = 768 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ThumbnailCacheResult:
    path: str = ""
    status: str = "missing"
    reason: str = ""
    timestamp: float = 0.0


@lru_cache(maxsize=256)
def default_thumbnail_cache_dir(project_path: str = "") -> Path:
    """Return a project-safe thumbnail cache that never touches dataset/video_preview_cache."""
    if project_path:
        project = Path(project_path).expanduser()
        base = project.parent / ".roughcut_thumbnail_cache"
        return base
    return Path(tempfile.gettempdir()) / "ai_subtitle_studio_roughcut_thumbnails"


@lru_cache(maxsize=4096)
def _cache_key(source_path: str, timestamp: float, width: int) -> str:
    raw = f"{Path(source_path).expanduser()}|{timestamp:.3f}|{int(width)}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:20]


def thumbnail_cache_path(source_path: str, timestamp: float, cache_dir: str | Path, width: int = 320) -> Path:
    suffix = f"{_cache_key(source_path, timestamp, width)}.jpg"
    return Path(cache_dir).expanduser() / suffix


def thumbnail_cache_budget_bytes(*, settings: dict[str, Any] | None = None) -> int:
    return scaled_runtime_cache_budget_bytes(
        ratio=_THUMBNAIL_CACHE_BUDGET_RATIO,
        minimum_bytes=_THUMBNAIL_CACHE_BUDGET_MIN_BYTES,
        maximum_bytes=_THUMBNAIL_CACHE_BUDGET_MAX_BYTES,
        settings=settings,
    )


def prune_thumbnail_cache(
    cache_dir: str | Path,
    *,
    settings: dict[str, Any] | None = None,
    target_total_bytes: int | None = None,
) -> dict[str, Any]:
    target_bytes = (
        max(0, int(target_total_bytes or 0))
        if target_total_bytes is not None
        else thumbnail_cache_budget_bytes(settings=settings)
    )
    return prune_runtime_disk_caches(paths=[Path(cache_dir).expanduser()], target_total_bytes=target_bytes)


def ensure_thumbnail(
    source_path: str,
    timestamp: float,
    *,
    cache_dir: str | Path | None = None,
    width: int = 320,
    ffmpeg_bin: str | None = None,
    settings: dict[str, Any] | None = None,
    cache_target_total_bytes: int | None = None,
) -> ThumbnailCacheResult:
    """Extract one thumbnail if possible, returning a non-throwing status result."""
    source = Path(str(source_path or "")).expanduser()
    if not source_path or not source.exists():
        return ThumbnailCacheResult(status="missing_source", reason="source_not_found", timestamp=max(0.0, float(timestamp or 0.0)))
    target_dir = Path(cache_dir) if cache_dir is not None else default_thumbnail_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = max(0.0, float(timestamp or 0.0))
    target = thumbnail_cache_path(str(source), ts, target_dir, width=width)
    if target.exists() and target.stat().st_size > 0:
        return ThumbnailCacheResult(path=str(target), status="cached", timestamp=ts)
    command = build_ffmpeg_frame_command(
        str(source),
        ts,
        str(target),
        width=width,
        quality=5,
        ffmpeg_bin=ffmpeg_bin or ffmpeg_binary(),
    )
    try:
        import subprocess

        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **hidden_subprocess_kwargs(strip_qt=True),
        )
    except Exception as exc:
        return ThumbnailCacheResult(status="failed", reason=str(exc), timestamp=ts)
    if not target.exists() or target.stat().st_size <= 0:
        return ThumbnailCacheResult(status="failed", reason="empty_thumbnail", timestamp=ts)
    try:
        register_runtime_cache_path(target, root=target_dir)
        prune_thumbnail_cache(target_dir, settings=settings, target_total_bytes=cache_target_total_bytes)
    except (OSError, ValueError):
        pass
    return ThumbnailCacheResult(path=str(target), status="created", timestamp=ts)


__all__ = [
    "ThumbnailCacheResult",
    "default_thumbnail_cache_dir",
    "ensure_thumbnail",
    "prune_thumbnail_cache",
    "thumbnail_cache_path",
    "thumbnail_cache_budget_bytes",
]
