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
PREVIEW_FRAME_MEDIA_IDENTITY_SCHEMA = "ai_subtitle_studio.preview_frame_media_identity.v1"
PREVIEW_FRAME_RELINK_REUSE_POLICY = "same_media_identity_same_fps_frame_width_only"
PREVIEW_FRAME_PROXY_REUSE_POLICY = "original_source_cache_only_proxy_switch_keeps_original_path"
_MEDIA_IDENTITY_SAMPLE_BYTES = 128 * 1024


def _source_path_sha1(source_path: str) -> str:
    normalized = str(Path(str(source_path or "")).expanduser())
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()


def _sample_sha1(path: Path, *, size: int, sample_bytes: int) -> str:
    digest = hashlib.sha1()
    sample_size = max(1, int(sample_bytes or _MEDIA_IDENTITY_SAMPLE_BYTES))
    try:
        with path.open("rb") as handle:
            digest.update(handle.read(sample_size))
            if size > sample_size:
                handle.seek(max(0, size - sample_size))
                digest.update(handle.read(sample_size))
    except OSError:
        return ""
    return digest.hexdigest()


def preview_frame_media_identity(
    source_path: str,
    *,
    sample_bytes: int = _MEDIA_IDENTITY_SAMPLE_BYTES,
) -> dict[str, Any]:
    """Return a path-independent preview-cache identity for safe relink reuse."""
    source = Path(str(source_path or "")).expanduser()
    normalized = str(source)
    path_digest = _source_path_sha1(normalized)
    try:
        stat = source.stat()
    except OSError:
        return {
            "schema": PREVIEW_FRAME_MEDIA_IDENTITY_SCHEMA,
            "exists": False,
            "source_path_sha1": path_digest,
            "source_size_bytes": 0,
            "source_mtime_ns": 0,
            "source_sample_bytes": max(1, int(sample_bytes or _MEDIA_IDENTITY_SAMPLE_BYTES)),
            "source_sample_sha1": "",
            "source_media_identity_digest": path_digest,
            "source_media_identity_policy": "path_sha1_missing_source_fallback",
            "path_independent": False,
        }
    size = int(getattr(stat, "st_size", 0) or 0)
    mtime_ns = int(
        getattr(stat, "st_mtime_ns", 0)
        or int(float(getattr(stat, "st_mtime", 0.0) or 0.0) * 1_000_000_000)
    )
    sample_size = max(1, int(sample_bytes or _MEDIA_IDENTITY_SAMPLE_BYTES))
    sample_digest = _sample_sha1(source, size=size, sample_bytes=sample_size)
    identity_text = f"size={size}|sample={sample_digest}" if sample_digest else f"size={size}|path={path_digest}"
    identity_digest = hashlib.sha1(identity_text.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "schema": PREVIEW_FRAME_MEDIA_IDENTITY_SCHEMA,
        "exists": True,
        "source_path_sha1": path_digest,
        "source_size_bytes": size,
        "source_mtime_ns": mtime_ns,
        "source_sample_bytes": sample_size,
        "source_sample_sha1": sample_digest,
        "source_media_identity_digest": identity_digest,
        "source_media_identity_policy": (
            "path_independent_size_head_tail_sample_v1"
            if sample_digest
            else "path_sha1_sample_unavailable_fallback"
        ),
        "path_independent": bool(sample_digest),
    }


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
    identity = preview_frame_media_identity(normalized_source)
    return {
        "schema": PREVIEW_FRAME_CACHE_SCHEMA,
        "purpose": PREVIEW_FRAME_CACHE_PURPOSE,
        "source": PREVIEW_FRAME_CACHE_SOURCE,
        "cache_kind": "nle_preview_skimming_frame",
        "evidence_role": "user_preview_only",
        "cut_boundary_evidence": False,
        "ui_thread_decode_allowed": False,
        "source_basename": Path(normalized_source).name,
        "source_path_sha1": identity["source_path_sha1"],
        "source_exists": identity["exists"],
        "source_size_bytes": identity["source_size_bytes"],
        "source_mtime_ns": identity["source_mtime_ns"],
        "source_sample_bytes": identity["source_sample_bytes"],
        "source_sample_sha1": identity["source_sample_sha1"],
        "source_media_identity_digest": identity["source_media_identity_digest"],
        "source_media_identity_policy": identity["source_media_identity_policy"],
        "relink_reuse_policy": PREVIEW_FRAME_RELINK_REUSE_POLICY,
        "proxy_switch_reuse_policy": PREVIEW_FRAME_PROXY_REUSE_POLICY,
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


def _thumbnail_from_manifest_path(manifest_path: Path) -> Path:
    if manifest_path.suffix == ".json":
        return manifest_path.with_suffix("")
    return manifest_path


def _manifest_matches_relinked_source(
    manifest: dict[str, Any],
    *,
    media_identity_digest: str,
    frames: set[int],
    fps: float,
    width: int,
) -> bool:
    if not media_identity_digest:
        return False
    if manifest.get("schema") != PREVIEW_FRAME_CACHE_SCHEMA:
        return False
    if manifest.get("purpose") != PREVIEW_FRAME_CACHE_PURPOSE:
        return False
    if manifest.get("source") != PREVIEW_FRAME_CACHE_SOURCE:
        return False
    if manifest.get("cache_kind") != "nle_preview_skimming_frame":
        return False
    if manifest.get("evidence_role") != "user_preview_only" or manifest.get("cut_boundary_evidence") is not False:
        return False
    if manifest.get("source_media_identity_digest") != media_identity_digest:
        return False
    try:
        if int(manifest.get("frame")) not in frames:
            return False
        if int(manifest.get("width") or 0) != int(width):
            return False
        if abs(float(manifest.get("fps") or 0.0) - float(fps)) > 1e-6:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _nearest_relinked_cached_preview_frame(
    source_path: str,
    *,
    frames: set[int],
    fps: float,
    width: int,
    root: str | Path | None,
    max_manifest_scan: int,
) -> str:
    identity = preview_frame_media_identity(source_path)
    if not identity.get("path_independent"):
        return ""
    media_identity_digest = str(identity.get("source_media_identity_digest") or "")
    scanned = 0
    try:
        manifest_paths = preview_frame_cache_dir(root).glob("*.jpg.json")
    except OSError:
        return ""
    for manifest_path in manifest_paths:
        if scanned >= max(0, int(max_manifest_scan or 0)):
            break
        scanned += 1
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        if not _manifest_matches_relinked_source(
            manifest,
            media_identity_digest=media_identity_digest,
            frames=frames,
            fps=fps,
            width=width,
        ):
            continue
        thumbnail_path = _thumbnail_from_manifest_path(manifest_path)
        try:
            if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
                return str(thumbnail_path)
        except OSError:
            continue
    return ""


def nearest_cached_preview_frame(
    source_path: str,
    sec: float,
    *,
    fps: float = 30.0,
    width: int = 320,
    tolerance_frames: int = 8,
    root: str | Path | None = None,
    allow_relink_scan: bool = True,
    max_manifest_scan: int = 160,
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
    if allow_relink_scan:
        frames = {max(0, target_frame + delta) for delta in offsets}
        relinked = _nearest_relinked_cached_preview_frame(
            source_path,
            frames=frames,
            fps=fps_value,
            width=max(160, int(width or 320)),
            root=root,
            max_manifest_scan=max_manifest_scan,
        )
        if relinked:
            return relinked
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
    "PREVIEW_FRAME_MEDIA_IDENTITY_SCHEMA",
    "PREVIEW_FRAME_PROXY_REUSE_POLICY",
    "PREVIEW_FRAME_RELINK_REUSE_POLICY",
    "build_preview_frame_manifest",
    "ensure_preview_frame",
    "nearest_cached_preview_frame",
    "preview_frame_cache_dir",
    "preview_frame_cache_path",
    "preview_frame_media_identity",
    "preview_frame_manifest_path",
    "read_preview_frame_manifest",
    "write_preview_frame_manifest",
]
