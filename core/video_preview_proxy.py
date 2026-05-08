from __future__ import annotations

"""Shared 720p preview proxy path helpers.

The editor builds these proxies for smooth playback. Cut-boundary scanning can
reuse an existing proxy to avoid repeatedly decoding very large 4K/HEVC files.
"""

import hashlib
import os

from core.media_fingerprint import media_file_fingerprint
from core.runtime import config


def preview_proxy_path_for(path: str) -> str:
    root = os.path.join(config.DATASET_DIR, "video_preview_cache")
    os.makedirs(root, exist_ok=True)
    fingerprint = media_file_fingerprint(path, sample_bytes=1024 * 1024, include_samples=True)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:20]
    base = os.path.splitext(os.path.basename(str(path or "")))[0]
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base)[:48]
    return os.path.join(root, f"{safe}_{digest}_preview_720p_hevc.mp4")


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


__all__ = ["cut_boundary_scan_source", "existing_preview_proxy_for", "preview_proxy_path_for"]
