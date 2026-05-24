from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.cut_boundary_api import (
    CUT_BOUNDARY_ALGORITHM_ID,
    CUT_BOUNDARY_ALGORITHM_VERSION,
    CUT_BOUNDARY_API_VERSION,
)

SUBTITLE_CUT_BOUNDARY_FACADE_SCHEMA = "ai_subtitle_studio.subtitle_cut_boundary.cache_plan.v1"


@dataclass(frozen=True)
class SubtitleCutBoundaryCachePlan:
    schema: str
    file_count: int
    settings_key_count: int
    api_version: str
    algorithm_version: str
    algorithm_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "file_count": self.file_count,
            "settings_key_count": self.settings_key_count,
            "api_version": self.api_version,
            "algorithm_version": self.algorithm_version,
            "algorithm_id": self.algorithm_id,
        }


def truthy_setting(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "auto"}:
            return bool(default)
        return lowered not in {"0", "false", "no", "off", "미사용", "사용안함", "disabled"}
    return bool(value)


def subtitle_cut_boundary_settings_payload(settings: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(settings or {})
    try:
        duration_sec = max(0.0, float(data.get("cut_boundary_media_duration_sec", 0.0) or 0.0))
    except Exception:
        duration_sec = 0.0
    duration_bucket = int(duration_sec // 300.0 * 300.0) if duration_sec > 0.0 else 0
    return {
        "scan_cut_auto_sample_step_sec": data.get("scan_cut_auto_sample_step_sec", 2.0),
        "scan_cut_auto_threshold": data.get("scan_cut_auto_threshold", data.get("scan_cut_threshold", 24.0)),
        "scan_cut_threshold": data.get("scan_cut_threshold", 24.0),
        "scan_cut_mode": data.get("scan_cut_mode", ""),
        "scan_cut_boundary_level": data.get("scan_cut_boundary_level", data.get("cut_boundary_level", "medium")),
        "scan_cut_boundary_resolved_level": data.get("scan_cut_boundary_resolved_level", ""),
        "scan_cut_boundary_resolved_mask": data.get("scan_cut_boundary_resolved_mask", ""),
        "scan_cut_boundary_provisional_level": data.get("scan_cut_boundary_provisional_level", ""),
        "scan_cut_boundary_provisional_mask": data.get("scan_cut_boundary_provisional_mask", ""),
        "cut_boundary_auto_long_media_sec": data.get("cut_boundary_auto_long_media_sec", 15.0 * 60.0),
        "cut_boundary_auto_short_media_sec": data.get("cut_boundary_auto_short_media_sec", 10.0 * 60.0),
        "cut_boundary_media_duration_bucket_sec": duration_bucket,
        "cut_boundary_adaptive_level_enabled": bool(data.get("cut_boundary_adaptive_level_enabled", False)),
        "scan_cut_grid_mask": data.get("scan_cut_grid_mask", ""),
        "scan_cut_compare_max_width": data.get("scan_cut_compare_max_width", 1920),
        "scan_cut_compare_max_height": data.get("scan_cut_compare_max_height", 1080),
        "scan_cut_follower_deferred_until_pioneer_done": bool(data.get("scan_cut_follower_deferred_until_pioneer_done", False)),
        "scan_cut_follower_stream_start_percent": data.get("scan_cut_follower_stream_start_percent", 25),
        "scan_cut_follower_stream_batch_size": data.get("scan_cut_follower_stream_batch_size", 16),
        "scan_cut_follower_verify_micro_batch_max": data.get("scan_cut_follower_verify_micro_batch_max", 16),
        "scan_cut_realtime_preview_enabled": truthy_setting(data.get("scan_cut_realtime_preview_enabled"), True),
        "scan_cut_audio_gain_enabled": data.get("scan_cut_audio_gain_enabled", True),
        "scan_cut_audio_gain_threshold_db": data.get("scan_cut_audio_gain_threshold_db", 10.0),
        "scan_cut_audio_gain_window_sec": data.get("scan_cut_audio_gain_window_sec", None),
        "scan_cut_audio_gain_min_gap_sec": data.get("scan_cut_audio_gain_min_gap_sec", None),
    }


def subtitle_cut_boundary_cache_payload(
    *,
    file_entries: list[dict[str, Any]] | None,
    settings_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "version": 7,
        "cut_boundary_api_version": CUT_BOUNDARY_API_VERSION,
        "cut_boundary_algorithm_version": CUT_BOUNDARY_ALGORITHM_VERSION,
        "cut_boundary_algorithm_id": CUT_BOUNDARY_ALGORITHM_ID,
        "files": [dict(item) for item in list(file_entries or []) if isinstance(item, dict)],
        "settings": dict(settings_payload or {}),
    }


def summarize_subtitle_cut_boundary_cache_plan(
    *,
    file_entries: list[dict[str, Any]] | None,
    settings_payload: dict[str, Any] | None,
) -> SubtitleCutBoundaryCachePlan:
    payload = subtitle_cut_boundary_cache_payload(
        file_entries=file_entries,
        settings_payload=settings_payload,
    )
    return SubtitleCutBoundaryCachePlan(
        schema=SUBTITLE_CUT_BOUNDARY_FACADE_SCHEMA,
        file_count=len(payload["files"]),
        settings_key_count=len(payload["settings"]),
        api_version=str(payload["cut_boundary_api_version"]),
        algorithm_version=str(payload["cut_boundary_algorithm_version"]),
        algorithm_id=str(payload["cut_boundary_algorithm_id"]),
    )


__all__ = [
    "SUBTITLE_CUT_BOUNDARY_FACADE_SCHEMA",
    "SubtitleCutBoundaryCachePlan",
    "subtitle_cut_boundary_cache_payload",
    "subtitle_cut_boundary_settings_payload",
    "summarize_subtitle_cut_boundary_cache_plan",
    "truthy_setting",
]
