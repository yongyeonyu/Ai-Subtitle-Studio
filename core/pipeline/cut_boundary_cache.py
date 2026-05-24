"""Cut-boundary cache key and payload helpers."""

from __future__ import annotations

import hashlib
import json
import os

from core.engine.subtitle_cut_boundary import (
    subtitle_cut_boundary_cache_payload,
    subtitle_cut_boundary_settings_payload,
    truthy_setting,
)
from core.media_fingerprint import media_fingerprint_digest
from core.native_swift_cut_boundary_cache import (
    cut_boundary_cache_plan_via_swift,
    cut_boundary_cache_settings_payload_via_swift,
)


def cut_boundary_cache_settings_payload(settings: dict) -> dict:
    native = cut_boundary_cache_settings_payload_via_swift(settings)
    if isinstance(native, dict) and native:
        return native
    return subtitle_cut_boundary_settings_payload(settings)


def cut_boundary_cache_file_entries(files: list[str]) -> list[dict]:
    entries: list[dict] = []
    for path in list(files or []):
        try:
            st = os.stat(path)
            entries.append(
                {
                    "path": os.path.abspath(str(path)),
                    "size": int(st.st_size),
                    "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
                    "fingerprint_digest": media_fingerprint_digest(path, sample_bytes=256 * 1024, include_samples=True),
                }
            )
        except Exception:
            entries.append(
                {
                    "path": os.path.abspath(str(path)),
                    "size": 0,
                    "mtime_ns": 0,
                    "fingerprint_digest": "",
                }
            )
    return entries


def cut_boundary_cache_base_payload(files: list[str], settings: dict) -> dict:
    file_entries = cut_boundary_cache_file_entries(files)
    native = cut_boundary_cache_plan_via_swift(file_entries=file_entries, settings=settings)
    if isinstance(native, dict):
        payload = native.get("base_payload")
        if isinstance(payload, dict):
            return payload
    return subtitle_cut_boundary_cache_payload(
        file_entries=file_entries,
        settings_payload=cut_boundary_cache_settings_payload(settings),
    )


def cut_boundary_cache_path_for_start(files: list[str], settings: dict) -> str:
    try:
        from core.runtime import config

        cache_root = os.path.join(config.OUTPUT_DIR, "cut_boundary_cache")
    except Exception:
        cache_root = os.path.join("output", "cut_boundary_cache")

    os.makedirs(cache_root, exist_ok=True)
    file_entries = cut_boundary_cache_file_entries(files)
    native = cut_boundary_cache_plan_via_swift(file_entries=file_entries, settings=settings)
    if isinstance(native, dict):
        cache_path = str(native.get("cache_path") or "")
        if cache_path:
            return cache_path
    raw = json.dumps(cut_boundary_cache_base_payload(files, settings), ensure_ascii=False, sort_keys=True).encode("utf-8")
    key = hashlib.sha256(raw).hexdigest()[:24]
    return os.path.join(cache_root, f"cut_boundaries_{key}.json")
