from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_nearest_frame
from core.roughcut.thumbnail_cache import ThumbnailCacheResult, ensure_thumbnail, thumbnail_cache_path
from core.runtime.temp_workspace import preview_workspace_dir

PREVIEW_FRAME_CACHE_SCHEMA = "ai_subtitle_studio.preview_frame_cache.v1"
PREVIEW_FRAME_CACHE_PURPOSE = "editor_preview_skimming"
PREVIEW_FRAME_CACHE_SOURCE = "preview_frame_cache"


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


def preview_frame_manifest_path(thumbnail_path: str | Path) -> Path:
    return Path(thumbnail_path).expanduser().with_suffix(Path(thumbnail_path).suffix + ".json")


def build_preview_frame_manifest(
    source_path: str,
    sec: float,
    *,
    fps: float = 30.0,
    width: int = 320,
    thumbnail_path: str | Path = "",
) -> dict[str, Any]:
    fps_value = normalize_fps(fps)
    frame = sec_to_nearest_frame(sec, fps_value)
    snapped = frame_to_sec(frame, fps_value)
    normalized_source = str(Path(str(source_path or "")).expanduser())
    return {
        "schema": PREVIEW_FRAME_CACHE_SCHEMA,
        "purpose": PREVIEW_FRAME_CACHE_PURPOSE,
        "source": PREVIEW_FRAME_CACHE_SOURCE,
        "cache_kind": "nle_preview_skimming_frame",
        "evidence_role": "user_preview_only",
        "cut_boundary_evidence": False,
        "ui_thread_decode_allowed": False,
        "source_basename": Path(normalized_source).name,
        "source_path_sha1": hashlib.sha1(normalized_source.encode("utf-8", errors="ignore")).hexdigest(),
        "request_sec": round(max(0.0, float(sec or 0.0)), 6),
        "snapped_sec": round(snapped, 6),
        "frame": int(frame),
        "fps": fps_value,
        "width": max(160, int(width or 320)),
        "thumbnail_path": str(thumbnail_path or ""),
    }


def write_preview_frame_manifest(
    thumbnail_path: str | Path,
    source_path: str,
    sec: float,
    *,
    fps: float = 30.0,
    width: int = 320,
) -> Path:
    manifest_path = preview_frame_manifest_path(thumbnail_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_preview_frame_manifest(
        source_path,
        sec,
        fps=fps,
        width=width,
        thumbnail_path=str(thumbnail_path or ""),
    )
    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(manifest_path)
    return manifest_path


def read_preview_frame_manifest(thumbnail_path: str | Path) -> dict[str, Any]:
    manifest_path = preview_frame_manifest_path(thumbnail_path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
    fps_value = normalize_fps(fps)
    snapped = frame_to_sec(sec_to_nearest_frame(sec, fps_value), fps_value)
    result = ensure_thumbnail(
        source_path,
        snapped,
        cache_dir=preview_frame_cache_dir(root),
        width=max(160, int(width or 320)),
        settings=settings,
    )
    if result.status in ("cached", "created") and result.path:
        try:
            write_preview_frame_manifest(result.path, source_path, snapped, fps=fps_value, width=width)
        except OSError:
            pass
    return result


__all__ = [
    "PREVIEW_FRAME_CACHE_PURPOSE",
    "PREVIEW_FRAME_CACHE_SCHEMA",
    "PREVIEW_FRAME_CACHE_SOURCE",
    "build_preview_frame_manifest",
    "ensure_preview_frame",
    "nearest_cached_preview_frame",
    "preview_frame_cache_dir",
    "preview_frame_cache_path",
    "preview_frame_manifest_path",
    "read_preview_frame_manifest",
    "write_preview_frame_manifest",
]
