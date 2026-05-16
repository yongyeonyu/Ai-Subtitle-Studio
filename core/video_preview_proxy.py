from __future__ import annotations

"""Shared 720p preview proxy path helpers.

The editor builds these proxies for smooth playback. Cut-boundary scanning can
reuse an existing proxy to avoid repeatedly decoding very large 4K/HEVC files.
"""

import os
from typing import Any

from core.media_fingerprint import media_fingerprint_digest
from core.runtime import config
from core.runtime.memory_manager import register_runtime_cache_path, prune_runtime_disk_caches, scaled_runtime_cache_budget_bytes

_PREVIEW_PROXY_CACHE_BUDGET_RATIO = 0.24
_PREVIEW_PROXY_CACHE_BUDGET_MIN_BYTES = 512 * 1024 * 1024
_PREVIEW_PROXY_CACHE_BUDGET_MAX_BYTES = 4 * 1024 * 1024 * 1024


def preview_proxy_cache_dir() -> str:
    root = os.path.join(config.DATASET_DIR, "video_preview_cache")
    os.makedirs(root, exist_ok=True)
    return root


def preview_proxy_path_for(path: str) -> str:
    root = preview_proxy_cache_dir()
    digest = media_fingerprint_digest(path, sample_bytes=1024 * 1024, include_samples=True)[:20]
    base = os.path.splitext(os.path.basename(str(path or "")))[0]
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base)[:48]
    return os.path.join(root, f"{safe}_{digest}_preview_720p_hevc.mp4")


def preview_proxy_cache_budget_bytes(*, settings: dict[str, Any] | None = None) -> int:
    return scaled_runtime_cache_budget_bytes(
        ratio=_PREVIEW_PROXY_CACHE_BUDGET_RATIO,
        minimum_bytes=_PREVIEW_PROXY_CACHE_BUDGET_MIN_BYTES,
        maximum_bytes=_PREVIEW_PROXY_CACHE_BUDGET_MAX_BYTES,
        settings=settings,
    )


def prune_preview_proxy_cache(
    *,
    settings: dict[str, Any] | None = None,
    target_total_bytes: int | None = None,
) -> dict[str, Any]:
    target_bytes = (
        max(0, int(target_total_bytes or 0))
        if target_total_bytes is not None
        else preview_proxy_cache_budget_bytes(settings=settings)
    )
    return prune_runtime_disk_caches(paths=[preview_proxy_cache_dir()], target_total_bytes=target_bytes)


def register_preview_proxy_created(
    path: str,
    *,
    settings: dict[str, Any] | None = None,
    target_total_bytes: int | None = None,
) -> dict[str, Any]:
    register_runtime_cache_path(path, root=preview_proxy_cache_dir())
    return prune_preview_proxy_cache(settings=settings, target_total_bytes=target_total_bytes)


def existing_preview_proxy_for(path: str) -> str:
    if not path:
        return ""
    try:
        proxy = preview_proxy_path_for(path)
    except Exception:
        return ""
    return proxy if proxy and os.path.exists(proxy) else ""


def cut_boundary_scan_source(path: str, settings: dict | None = None) -> str:
    data = dict(settings or {})
    raw_value = data.get("scan_cut_use_preview_proxy_enabled", "1")
    value = str(raw_value).strip().lower()
    if value in {"0", "false", "off", "no", "사용 안함", "끔"}:
        return str(path or "")
    proxy = existing_preview_proxy_for(str(path or ""))
    return proxy or str(path or "")


__all__ = [
    "cut_boundary_scan_source",
    "existing_preview_proxy_for",
    "preview_proxy_cache_budget_bytes",
    "preview_proxy_cache_dir",
    "preview_proxy_path_for",
    "prune_preview_proxy_cache",
    "register_preview_proxy_created",
]
