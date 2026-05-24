from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift

_SCHEMA = "ai_subtitle_studio.stt.duration_first_order.v1"
_COMPUTE_PROFILE_SCHEMA = "ai_subtitle_studio.stt.compute_profile.v1"
_SUBMISSION_ENABLED_SCHEMA = "ai_subtitle_studio.stt.duration_first_submission_enabled.v1"
_WORKER_TIMEOUT_SCHEMA = "ai_subtitle_studio.stt.worker_silence_timeout.v1"
_STRAGGLER_CONFIG_SCHEMA = "ai_subtitle_studio.stt.straggler_config.v1"


def compute_profile_from_native_units_via_swift(compute_units: object, *, fallback: str = "ane_gpu") -> str | None:
    result = run_subtitle_core_operation_via_swift(
        "stt_compute_profile",
        {"compute_units": compute_units, "fallback": fallback},
        context={"bridge": "native_swift_transcribe_plan"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _COMPUTE_PROFILE_SCHEMA:
        return None
    value = str(result.get("profile") or "").strip()
    return value or None


def duration_first_submission_enabled_via_swift(
    *,
    rescue_pass: bool,
    precision_pass: bool,
    word_timestamps: bool,
    enabled_setting: bool,
) -> bool | None:
    result = run_subtitle_core_operation_via_swift(
        "stt_duration_first_submission_enabled",
        {
            "rescue_pass": bool(rescue_pass),
            "precision_pass": bool(precision_pass),
            "word_timestamps": bool(word_timestamps),
            "enabled_setting": bool(enabled_setting),
        },
        context={"bridge": "native_swift_transcribe_plan"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SUBMISSION_ENABLED_SCHEMA:
        return None
    value = result.get("enabled")
    return value if isinstance(value, bool) else None


def stt_worker_silence_timeout_via_swift(
    settings: dict[str, Any] | None,
    *,
    log_label: str,
    word_timestamps: bool,
) -> float | None:
    result = run_subtitle_core_operation_via_swift(
        "stt_worker_silence_timeout",
        {
            "settings": dict(settings or {}),
            "log_label": str(log_label or ""),
            "word_timestamps": bool(word_timestamps),
        },
        context={"bridge": "native_swift_transcribe_plan"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _WORKER_TIMEOUT_SCHEMA:
        return None
    try:
        value = float(result.get("timeout"))
    except Exception:
        return None
    return max(0.0, value)


def stt_straggler_config_via_swift(
    settings: dict[str, Any] | None,
    *,
    mode: str,
) -> dict[str, Any] | None:
    result = run_subtitle_core_operation_via_swift(
        "stt_straggler_config",
        {"settings": dict(settings or {}), "mode": str(mode or "precision")},
        context={"bridge": "native_swift_transcribe_plan"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _STRAGGLER_CONFIG_SCHEMA:
        return None
    try:
        return {
            "timeout": float(result.get("timeout") or 0.0),
            "max_missing_chunks": int(result.get("max_missing_chunks") or 0),
            "min_received_ratio": float(result.get("min_received_ratio") or 0.0),
        }
    except Exception:
        return None


def duration_first_order_via_swift(items: list[dict[str, Any]]) -> list[int] | None:
    rows = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    starts = [float(row.get("ov_start_offset", idx) or idx) for idx, row in enumerate(rows)]
    durations = [max(0.001, float(row.get("duration", 0.001) or 0.001)) for row in rows]
    result = run_subtitle_core_operation_via_swift(
        "stt_duration_first_order",
        {"starts": starts, "durations": durations},
        context={"bridge": "native_swift_transcribe_plan"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SCHEMA:
        return None
    try:
        order = [int(item) for item in list(result.get("order") or [])]
    except Exception:
        return None
    if len(order) != len(rows):
        return None
    if sorted(order) != list(range(len(rows))):
        return None
    return order


__all__ = [
    "compute_profile_from_native_units_via_swift",
    "duration_first_order_via_swift",
    "duration_first_submission_enabled_via_swift",
    "stt_straggler_config_via_swift",
    "stt_worker_silence_timeout_via_swift",
]
