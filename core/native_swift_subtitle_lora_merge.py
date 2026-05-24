from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift

_SCHEMA = "ai_subtitle_studio.subtitle_lora.selective_merge.v1"
_SETTINGS_SCHEMA = "ai_subtitle_studio.subtitle_lora.merge_settings.v1"
_PACKAGING_MODE_SCHEMA = "ai_subtitle_studio.subtitle_lora.packaging_mode.v1"
_PACKAGING_CANDIDATE_SCORE_SCHEMA = "ai_subtitle_studio.subtitle_lora.packaging_candidate_score.v1"
_PACKAGING_REASONS_SCHEMA = "ai_subtitle_studio.subtitle_lora.packaging_reasons.v1"


def lora_merge_settings_via_swift(settings: dict[str, Any] | None) -> dict[str, Any] | None:
    result = run_subtitle_core_operation_via_swift(
        "subtitle_lora_merge_settings",
        {"settings": dict(settings or {})},
        context={"bridge": "native_swift_subtitle_lora_merge"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SETTINGS_SCHEMA:
        return None
    keys = (
        "split_length_threshold",
        "sub_min_duration",
        "sub_gap_break_sec",
        "word_timing_gap_break_sec",
        "continuous_threshold",
    )
    out = {key: result.get(key) for key in keys}
    if any(value is None for value in out.values()):
        return None
    return out


def lora_packaging_mode_via_swift(settings: dict[str, Any] | None) -> str | None:
    result = run_subtitle_core_operation_via_swift(
        "subtitle_lora_packaging_mode",
        {"settings": dict(settings or {})},
        context={"bridge": "native_swift_subtitle_lora_merge"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _PACKAGING_MODE_SCHEMA:
        return None
    value = str(result.get("mode") or "").strip()
    if value not in {"full", "readability_selective"}:
        return None
    return value


def lora_packaging_candidate_score_via_swift(
    *,
    line_lengths: list[int],
    pattern: str,
    strategy: str,
    current_pattern: str,
    target_patterns: list[str],
    target_line_count: int,
    threshold: int,
) -> float | None:
    result = run_subtitle_core_operation_via_swift(
        "subtitle_lora_packaging_candidate_score",
        {
            "line_lengths": [int(item) for item in list(line_lengths or [])],
            "pattern": str(pattern or ""),
            "strategy": str(strategy or ""),
            "current_pattern": str(current_pattern or ""),
            "target_patterns": [str(item) for item in list(target_patterns or [])],
            "target_line_count": int(target_line_count or 0),
            "threshold": int(threshold or 0),
        },
        context={"bridge": "native_swift_subtitle_lora_merge"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _PACKAGING_CANDIDATE_SCORE_SCHEMA:
        return None


def lora_packaging_reasons_via_swift(
    *,
    threshold: int,
    chars: int,
    line_count: int,
    current_pattern: str,
    target_patterns: list[str],
    target_line_count: int,
    quality_label: str,
    quality_score: float,
    quality_max_score: float,
) -> list[str] | None:
    result = run_subtitle_core_operation_via_swift(
        "subtitle_lora_packaging_reasons",
        {
            "threshold": int(threshold or 0),
            "chars": int(chars or 0),
            "line_count": int(line_count or 0),
            "current_pattern": str(current_pattern or ""),
            "target_patterns": [str(item) for item in list(target_patterns or [])],
            "target_line_count": int(target_line_count or 0),
            "quality_label": str(quality_label or ""),
            "quality_score": float(quality_score or 0.0),
            "quality_max_score": float(quality_max_score or 0.0),
        },
        context={"bridge": "native_swift_subtitle_lora_merge"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _PACKAGING_REASONS_SCHEMA:
        return None
    reasons = result.get("reasons")
    if not isinstance(reasons, list):
        return None
    return [str(item) for item in reasons if str(item or "").strip()]
    if result.get("valid") is not True:
        return float("-inf")
    try:
        return float(result.get("score"))
    except Exception:
        return None


def selective_lora_merge_indexes_via_swift(
    rows: list[dict],
    settings: dict[str, Any] | None,
    merge_settings: dict[str, Any] | None,
) -> tuple[set[int], dict[int, list[str]]] | None:
    result = run_subtitle_core_operation_via_swift(
        "subtitle_lora_selective_merge_indexes",
        {
            "rows": [dict(row) for row in list(rows or []) if isinstance(row, dict)],
            "settings": dict(settings or {}),
            "merge_settings": dict(merge_settings or {}),
        },
        context={"bridge": "native_swift_subtitle_lora_merge"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SCHEMA:
        return None
    try:
        selected = {int(item) for item in list(result.get("selected_indexes") or []) if int(item) >= 0}
    except Exception:
        return None
    raw_reasons = result.get("reasons_map")
    if not isinstance(raw_reasons, dict):
        raw_reasons = {}
    reasons_map: dict[int, list[str]] = {}
    for key, reasons in raw_reasons.items():
        try:
            index = int(key)
        except Exception:
            continue
        if index < 0:
            continue
        reasons_map[index] = [str(item) for item in list(reasons or []) if str(item or "").strip()]
    return selected, reasons_map


__all__ = [
    "lora_merge_settings_via_swift",
    "lora_packaging_candidate_score_via_swift",
    "lora_packaging_mode_via_swift",
    "lora_packaging_reasons_via_swift",
    "selective_lora_merge_indexes_via_swift",
]
