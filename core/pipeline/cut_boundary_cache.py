"""Cut-boundary cache key and payload helpers."""

from __future__ import annotations

import hashlib
import json
import os

from core.cut_boundary_api import CUT_BOUNDARY_ALGORITHM_ID, CUT_BOUNDARY_ALGORITHM_VERSION, CUT_BOUNDARY_API_VERSION
from core.media_fingerprint import media_fingerprint_digest
from core.native_swift_cut_boundary_cache import (
    cut_boundary_cache_plan_via_swift,
    cut_boundary_cache_settings_payload_via_swift,
)


def truthy_setting(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "auto"}:
            return bool(default)
        return lowered not in {"0", "false", "no", "off", "미사용", "사용안함", "disabled"}
    return bool(value)


def cut_boundary_cache_settings_payload(settings: dict) -> dict:
    native = cut_boundary_cache_settings_payload_via_swift(settings)
    if isinstance(native, dict) and native:
        return native
    settings = dict(settings or {})
    try:
        duration_sec = max(0.0, float(settings.get("cut_boundary_media_duration_sec", 0.0) or 0.0))
    except Exception:
        duration_sec = 0.0
    duration_bucket = int(duration_sec // 300.0 * 300.0) if duration_sec > 0.0 else 0
    return {
        "scan_cut_auto_sample_step_sec": settings.get("scan_cut_auto_sample_step_sec", 2.0),
        "scan_cut_auto_threshold": settings.get("scan_cut_auto_threshold", settings.get("scan_cut_threshold", 24.0)),
        "scan_cut_threshold": settings.get("scan_cut_threshold", 24.0),
        "scan_cut_mode": settings.get("scan_cut_mode", ""),
        "scan_cut_boundary_level": settings.get("scan_cut_boundary_level", settings.get("cut_boundary_level", "medium")),
        "scan_cut_boundary_resolved_level": settings.get("scan_cut_boundary_resolved_level", ""),
        "scan_cut_boundary_resolved_mask": settings.get("scan_cut_boundary_resolved_mask", ""),
        "scan_cut_boundary_provisional_level": settings.get("scan_cut_boundary_provisional_level", ""),
        "scan_cut_boundary_provisional_mask": settings.get("scan_cut_boundary_provisional_mask", ""),
        "cut_boundary_auto_long_media_sec": settings.get("cut_boundary_auto_long_media_sec", 15.0 * 60.0),
        "cut_boundary_auto_short_media_sec": settings.get("cut_boundary_auto_short_media_sec", 10.0 * 60.0),
        "cut_boundary_media_duration_bucket_sec": duration_bucket,
        "cut_boundary_adaptive_level_enabled": bool(settings.get("cut_boundary_adaptive_level_enabled", False)),
        "scan_cut_grid_mask": settings.get("scan_cut_grid_mask", ""),
        "scan_cut_compare_max_width": settings.get("scan_cut_compare_max_width", 1920),
        "scan_cut_compare_max_height": settings.get("scan_cut_compare_max_height", 1080),
        "scan_cut_follower_deferred_until_pioneer_done": bool(settings.get("scan_cut_follower_deferred_until_pioneer_done", False)),
        "scan_cut_follower_stream_start_percent": settings.get("scan_cut_follower_stream_start_percent", 25),
        "scan_cut_follower_stream_batch_size": settings.get("scan_cut_follower_stream_batch_size", 16),
        "scan_cut_follower_verify_micro_batch_max": settings.get("scan_cut_follower_verify_micro_batch_max", 16),
        "scan_cut_realtime_preview_enabled": truthy_setting(settings.get("scan_cut_realtime_preview_enabled"), True),
        "scan_cut_audio_gain_enabled": settings.get("scan_cut_audio_gain_enabled", True),
        "scan_cut_audio_gain_threshold_db": settings.get("scan_cut_audio_gain_threshold_db", 10.0),
        "scan_cut_audio_gain_window_sec": settings.get("scan_cut_audio_gain_window_sec", None),
        "scan_cut_audio_gain_min_gap_sec": settings.get("scan_cut_audio_gain_min_gap_sec", None),
    }


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
    return {
        "version": 7,
        "cut_boundary_api_version": CUT_BOUNDARY_API_VERSION,
        "cut_boundary_algorithm_version": CUT_BOUNDARY_ALGORITHM_VERSION,
        "cut_boundary_algorithm_id": CUT_BOUNDARY_ALGORITHM_ID,
        "files": file_entries,
        "settings": cut_boundary_cache_settings_payload(settings),
    }


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
