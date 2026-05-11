"""Cut-boundary startup prescan scheduling policy.

This module keeps the fast temporary-line path separate from the large
pipeline mixin so the benchmark-locked pioneer/follower choices stay easy to
review.
"""

from __future__ import annotations

from typing import Any


def _float_min(data: dict[str, Any], key: str, fallback: float, cap: float) -> float:
    try:
        value = float(data.get(key, fallback) or fallback)
    except Exception:
        value = fallback
    return min(value, cap)


def _int_min(data: dict[str, Any], key: str, fallback: int, cap: int) -> int:
    try:
        value = int(data.get(key, fallback) or fallback)
    except Exception:
        value = fallback
    return min(value, cap)


def _to_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _to_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _to_bool(value: Any, fallback: bool) -> bool:
    if value is None:
        return bool(fallback)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(fallback)
    if text in {"1", "true", "yes", "on", "enabled", "enable", "사용", "켜기", "켬"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable", "미사용", "끄기", "끔"}:
        return False
    return bool(fallback)


def fast_cut_boundary_prescan_settings(settings: dict | None) -> dict:
    """Return benchmark-stable settings for temporary cut-boundary prescan.

    The fast path intentionally separates temporary discovery from formal
    verification: temporary lines use the low-profile OpenCV 4-way scout, while
    the follower verifies candidates with the resolved quality level.
    """
    tuned = dict(settings or {})

    # Do not let the native/fast backend route replace the 4-way scout with
    # FFmpeg scene prepass during startup. That path can be useful as an
    # explicit diagnostic, but it regressed the old quick temporary-line UX.
    tuned["scan_cut_ffmpeg_scene_prepass_enabled"] = False
    tuned["scan_cut_ffmpeg_scene_replace_opencv_enabled"] = False
    tuned["scan_cut_ffmpeg_scene_timeout_sec"] = _float_min(tuned, "scan_cut_ffmpeg_scene_timeout_sec", 6.0, 6.0)

    # Startup provisional scan must stay on the fastest OpenCV scout path.
    # Apple-native policy is excellent for some later stages, but here it may
    # keep the 4K original on the generic decoder path and delay visible lines.
    tuned["cut_boundary_backend_policy"] = "fast"
    tuned["scan_cut_cv2_video_backend"] = "avfoundation"
    tuned["scan_cut_compare_max_width"] = _int_min(tuned, "scan_cut_compare_max_width", 1920, 1920)
    tuned["scan_cut_compare_max_height"] = _int_min(tuned, "scan_cut_compare_max_height", 1080, 1080)
    tuned["scan_cut_pioneer_packet_scout_enabled"] = True
    tuned["scan_cut_pioneer_pipe_enabled"] = False
    tuned["scan_cut_pioneer_pipe_fps"] = 1.0
    tuned["scan_cut_pioneer_pipe_width"] = 320
    tuned["scan_cut_pioneer_pipe_height"] = 180
    tuned["scan_cut_pioneer_pipe_dense_flow_enabled"] = True
    tuned["scan_cut_pioneer_min_gap_sec"] = 1.0
    tuned["scan_cut_pioneer_dense_flow_confirm_enabled"] = True
    tuned["scan_cut_pioneer_strict_multiplier"] = min(
        float(tuned.get("scan_cut_pioneer_strict_multiplier", 0.72) or 0.72),
        0.72,
    )
    tuned["scan_cut_cv2_threads_per_worker"] = 1
    tuned["scan_cut_pioneer_sequential_decode_enabled"] = False
    tuned["scan_cut_pioneer_workers"] = 4
    tuned["scan_cut_verify_workers"] = 4
    tuned["scan_cut_pioneer_cpu_max_workers"] = 4
    tuned["scan_cut_follower_cpu_max_workers"] = 4
    tuned["scan_cut_follower_outer_splits"] = 4
    tuned["scan_cut_pioneer_worker_overlap_steps"] = 1

    # Start follower verification while the pioneer is still scanning, in small
    # batches so visible provisional lines turn into verified lines quickly.
    tuned["scan_cut_follower_stream_start_percent"] = _int_min(
        tuned,
        "scan_cut_follower_stream_start_percent",
        25,
        25,
    )
    tuned["scan_cut_follower_stream_batch_size"] = 4
    tuned["scan_cut_follower_verify_micro_batch_max"] = 16
    tuned["scan_cut_realtime_preview_enabled"] = True
    tuned["scan_cut_follower_stream_min_interval_sec"] = _float_min(
        tuned,
        "scan_cut_follower_stream_min_interval_sec",
        0.10,
        0.10,
    )
    return tuned


def _probe_first_media(files: list[str], duration_sec: float) -> tuple[int, int, float]:
    width = 0
    height = 0
    if not files:
        return width, height, duration_sec
    try:
        from core.media_info import probe_media

        info = probe_media(str(files[0]))
        width = int(info.get("width", 0) or 0)
        height = int(info.get("height", 0) or 0)
        if duration_sec <= 0.0:
            duration_sec = float(info.get("duration", 0.0) or 0.0)
    except Exception:
        pass
    return width, height, duration_sec


def _has_preview_proxy(files: list[str]) -> bool:
    if not files:
        return False
    try:
        from core.video_preview_proxy import existing_preview_proxy_for

        return bool(existing_preview_proxy_for(str(files[0])))
    except Exception:
        return False


def cut_boundary_adaptive_prescan_plan(settings: dict | None, files: list[str] | None) -> dict:
    """Choose cut-boundary follower scheduling without changing detection quality."""
    settings = dict(settings or {})
    files = list(files or [])

    try:
        duration_sec = float(settings.get("cut_boundary_media_duration_sec", 0.0) or 0.0)
    except Exception:
        duration_sec = 0.0
    width, height, duration_sec = _probe_first_media(files, duration_sec)
    has_preview_proxy = _has_preview_proxy(files)

    try:
        min_duration = float(settings.get("scan_cut_long4k_min_duration_sec", 900.0) or 900.0)
    except Exception:
        min_duration = 900.0
    try:
        min_width = int(settings.get("scan_cut_long4k_min_width", 3000) or 3000)
    except Exception:
        min_width = 3000
    try:
        min_height = int(settings.get("scan_cut_long4k_min_height", 1700) or 1700)
    except Exception:
        min_height = 1700

    enabled = bool(settings.get("scan_cut_adaptive_follower_schedule_enabled", True))
    native_streaming_enabled = _to_bool(
        settings.get("scan_cut_long4k_native_streaming_follower_enabled"),
        True,
    ) and _to_bool(settings.get("runtime_native_cut_boundary_enabled"), True)
    is_4k = width >= min_width or height >= min_height
    width_unknown = width <= 0 and height <= 0
    long_media = duration_sec >= min_duration
    long_4k = bool(enabled and long_media and (is_4k or (width_unknown and duration_sec >= max(1200.0, min_duration))))

    if long_4k:
        if native_streaming_enabled:
            stream_start = _to_int(
                settings.get("scan_cut_long4k_native_follower_stream_start_percent", settings.get("scan_cut_follower_stream_start_percent", 25))
                or settings.get("scan_cut_follower_stream_start_percent", 25)
                or 25,
                25,
            )
            stream_batch = _to_int(
                settings.get("scan_cut_long4k_native_follower_stream_batch_size", settings.get("scan_cut_follower_stream_batch_size", 4))
                or settings.get("scan_cut_follower_stream_batch_size", 4)
                or 4,
                4,
            )
            base_step_sec = _to_float(settings.get("scan_cut_long4k_provisional_sample_step_sec", 4.0) or 4.0, 4.0)
            scout_enabled = bool(settings.get("scan_cut_pioneer_packet_scout_enabled", True))
            if scout_enabled:
                provisional_step_sec = 1.0
            elif not has_preview_proxy:
                max_samples = max(60, _to_int(settings.get("scan_cut_no_proxy_pioneer_max_samples", 180) or 180, 180))
                no_proxy_floor = _to_float(settings.get("scan_cut_no_proxy_min_sample_step_sec", 8.0) or 8.0, 8.0)
                budget_step_sec = (duration_sec / float(max_samples)) if duration_sec > 0.0 else base_step_sec
                provisional_step_sec = max(base_step_sec, no_proxy_floor, budget_step_sec)
            else:
                provisional_step_sec = base_step_sec
            return {
                "mode": "long_4k_native_streaming_follower",
                "follower_start_after_pioneer": False,
                "stream_start_percent": max(0, min(50, stream_start)),
                "stream_batch_size": max(4, min(8, stream_batch)),
                "stream_min_interval_sec": max(
                    0.05,
                    _to_float(settings.get("scan_cut_follower_stream_min_interval_sec", 0.10) or 0.10, 0.10),
                ),
                "follower_start_delay_sec": 0.0,
                "provisional_sample_step_sec": max(1.0, min(16.0, provisional_step_sec)),
                "pioneer_sequential_decode": False,
                "has_preview_proxy": bool(has_preview_proxy),
                "duration_sec": duration_sec,
                "width": width,
                "height": height,
            }
        stream_start = _to_int(settings.get("scan_cut_long4k_follower_stream_start_percent", 100) or 100, 100)
        stream_batch = _to_int(settings.get("scan_cut_long4k_follower_stream_batch_size", 16) or 16, 16)
        start_delay = _to_float(settings.get("scan_cut_long4k_follower_start_delay_sec", 0.0) or 0.0, 0.0)
        base_step_sec = _to_float(settings.get("scan_cut_long4k_provisional_sample_step_sec", 4.0) or 4.0, 4.0)
        scout_enabled = bool(settings.get("scan_cut_pioneer_packet_scout_enabled", True))
        if scout_enabled:
            provisional_step_sec = 1.0
        elif not has_preview_proxy:
            max_samples = max(60, _to_int(settings.get("scan_cut_no_proxy_pioneer_max_samples", 180) or 180, 180))
            no_proxy_floor = _to_float(settings.get("scan_cut_no_proxy_min_sample_step_sec", 8.0) or 8.0, 8.0)
            budget_step_sec = (duration_sec / float(max_samples)) if duration_sec > 0.0 else base_step_sec
            provisional_step_sec = max(base_step_sec, no_proxy_floor, budget_step_sec)
        else:
            provisional_step_sec = base_step_sec
        return {
            "mode": "long_4k_deferred_follower",
            "follower_start_after_pioneer": True,
            "stream_start_percent": max(90, min(100, stream_start)),
            "stream_batch_size": max(8, stream_batch),
            "stream_min_interval_sec": max(
                0.10,
                _to_float(settings.get("scan_cut_follower_stream_min_interval_sec", 0.10) or 0.10, 0.10),
            ),
            "follower_start_delay_sec": max(0.0, min(10.0, start_delay)),
            "provisional_sample_step_sec": max(1.0, min(16.0, provisional_step_sec)),
            "pioneer_sequential_decode": False,
            "has_preview_proxy": bool(has_preview_proxy),
            "duration_sec": duration_sec,
            "width": width,
            "height": height,
        }

    base_step_sec = _to_float(
        settings.get("scan_cut_provisional_sample_step_sec", settings.get("scan_cut_auto_sample_step_sec", 2.0))
        or settings.get("scan_cut_auto_sample_step_sec", 2.0)
        or 2.0,
        2.0,
    )
    if bool(settings.get("scan_cut_pioneer_packet_scout_enabled", True)):
        provisional_step_sec = 1.0
    elif not has_preview_proxy and duration_sec > 0.0:
        max_samples = max(80, _to_int(settings.get("scan_cut_no_proxy_pioneer_max_samples", 180) or 180, 180))
        provisional_step_sec = max(base_step_sec, duration_sec / float(max_samples))
    else:
        provisional_step_sec = base_step_sec
    return {
        "mode": "short_streaming_follower",
        "follower_start_after_pioneer": False,
        "stream_start_percent": _to_int(settings.get("scan_cut_follower_stream_start_percent", 25) or 25, 25),
        "stream_batch_size": _to_int(settings.get("scan_cut_follower_stream_batch_size", 4) or 4, 4),
        "stream_min_interval_sec": _to_float(settings.get("scan_cut_follower_stream_min_interval_sec", 0.10) or 0.10, 0.10),
        "follower_start_delay_sec": 0.0,
        "provisional_sample_step_sec": max(0.5, min(4.0, provisional_step_sec)),
        "pioneer_sequential_decode": False,
        "has_preview_proxy": bool(has_preview_proxy),
        "duration_sec": duration_sec,
        "width": width,
        "height": height,
    }


__all__ = [
    "cut_boundary_adaptive_prescan_plan",
    "fast_cut_boundary_prescan_settings",
]
