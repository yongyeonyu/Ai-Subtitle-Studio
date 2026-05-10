"""User-facing cut-boundary level resolution policy."""

from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def normalize_cut_boundary_level(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "사용안함": "off",
        "사용 안함": "off",
        "미사용": "off",
        "off": "off",
        "false": "off",
        "0": "off",
        "disabled": "off",
        "disable": "off",
        "none": "off",
        "낮음": "low",
        "low": "low",
        "중간": "medium",
        "medium": "medium",
        "mid": "medium",
        "middle": "medium",
        "사용": "low",
        "자동": "low",
        "auto": "low",
        "adaptive": "low",
        "on": "low",
        "true": "low",
        "1": "low",
        "enabled": "low",
        "높음": "medium",
        "high": "medium",
    }
    return aliases.get(raw, "medium")


def _cut_boundary_auto_requested(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    return raw in {"auto", "adaptive", "자동"}


def _cut_boundary_operation_mode(settings: dict) -> str:
    for key in (
        "subtitle_mode",
        "simple_operation_mode",
        "auto_start_mode",
        "stt_quality_preset",
        "quality_mode",
    ):
        value = str(settings.get(key) or "").strip().lower()
        if value:
            return value
    return ""


def _resolve_adaptive_cut_boundary_level(settings: dict) -> str:
    mode = _cut_boundary_operation_mode(settings)
    if mode in {"high", "quality", "precise"}:
        return "medium"

    duration = _as_float(
        settings.get(
            "cut_boundary_media_duration_sec",
            settings.get("media_duration_sec", settings.get("duration_sec", 0.0)),
        ),
        0.0,
    )
    long_sec = max(60.0, _as_float(settings.get("cut_boundary_auto_long_media_sec", 15.0 * 60.0), 15.0 * 60.0))
    short_sec = max(30.0, _as_float(settings.get("cut_boundary_auto_short_media_sec", 10.0 * 60.0), 10.0 * 60.0))

    if duration >= long_sec:
        return "low"
    if 0.0 < duration <= short_sec:
        return "medium"
    if mode in {"auto", "balanced", "stt", "fast"}:
        return "low"
    return "medium"


def cut_boundary_adaptive_enabled(settings: dict | None = None) -> bool:
    settings = settings or {}
    has_explicit_level = False
    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        has_explicit_level = has_explicit_level or key in settings
        if key in settings and _cut_boundary_auto_requested(settings.get(key)):
            return True
    if has_explicit_level:
        return False
    return bool(settings.get("cut_boundary_adaptive_level_enabled", False))


def cut_boundary_level(settings: dict | None = None) -> str:
    settings = settings or {}

    for key in (
        "scan_cut_boundary_level",
        "cut_boundary_level",
        "scan_cut_level",
    ):
        if key in settings:
            if _cut_boundary_auto_requested(settings.get(key)):
                return _resolve_adaptive_cut_boundary_level(settings)
            return normalize_cut_boundary_level(settings.get(key))

    if cut_boundary_adaptive_enabled(settings):
        return _resolve_adaptive_cut_boundary_level(settings)

    for key in (
        "cut_boundary_detection_enabled",
        "scan_cut_enabled",
        "scan_cut_auto_enabled",
        "cut_boundary_enabled",
    ):
        if key in settings:
            return "medium" if bool(settings.get(key)) else "off"

    return "medium"


def cut_boundary_enabled(settings: dict | None = None) -> bool:
    return cut_boundary_level(settings or {}) != "off"


__all__ = [
    "cut_boundary_adaptive_enabled",
    "cut_boundary_enabled",
    "cut_boundary_level",
    "normalize_cut_boundary_level",
]
