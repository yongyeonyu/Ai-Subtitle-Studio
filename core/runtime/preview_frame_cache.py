from __future__ import annotations

from pathlib import Path
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_nearest_frame
from core.roughcut.thumbnail_cache import ThumbnailCacheResult, ensure_thumbnail, thumbnail_cache_path
from core.runtime.temp_workspace import preview_workspace_dir


def preview_frame_cache_dir(root: str | Path | None = None) -> Path:
    path = preview_workspace_dir(root) / "FrameThumbnails"
    path.mkdir(parents=True, exist_ok=True)
    return path


def preview_frame_cache_path(
    source_path: str,
    sec: float,
    *,
    width: int = 320,
    root: str | Path | None = None,
) -> Path:
    return thumbnail_cache_path(
        str(source_path or ""),
        max(0.0, float(sec or 0.0)),
        preview_frame_cache_dir(root),
        width=max(160, int(width or 320)),
    )


def nearest_cached_preview_frame(
    source_path: str,
    sec: float,
    *,
    fps: float = 30.0,
    width: int = 320,
    tolerance_frames: int = 8,
    root: str | Path | None = None,
) -> str:
    if not source_path:
        return ""
    fps_value = normalize_fps(fps)
    target_frame = sec_to_nearest_frame(sec, fps_value)
    offsets = [0]
    for delta in range(1, max(0, int(tolerance_frames or 0)) + 1):
        offsets.extend((-delta, delta))
    for delta in offsets:
        frame = max(0, target_frame + delta)
        candidate = preview_frame_cache_path(
            source_path,
            frame_to_sec(frame, fps_value),
            width=width,
            root=root,
        )
        try:
            if candidate.exists() and candidate.stat().st_size > 0:
                return str(candidate)
        except OSError:
            continue
    return ""


def ensure_preview_frame(
    source_path: str,
    sec: float,
    *,
    fps: float = 30.0,
    width: int = 320,
    root: str | Path | None = None,
    settings: dict[str, Any] | None = None,
) -> ThumbnailCacheResult:
    snapped = frame_to_sec(sec_to_nearest_frame(sec, normalize_fps(fps)), normalize_fps(fps))
    return ensure_thumbnail(
        source_path,
        snapped,
        cache_dir=preview_frame_cache_dir(root),
        width=max(160, int(width or 320)),
        settings=settings,
    )


__all__ = [
    "ensure_preview_frame",
    "nearest_cached_preview_frame",
    "preview_frame_cache_dir",
    "preview_frame_cache_path",
]
