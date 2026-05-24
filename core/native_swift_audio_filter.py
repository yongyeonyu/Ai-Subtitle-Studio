from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift

_SCHEMA = "ai_subtitle_studio.audio.fast_flatten_filter.v1"
_SAMPLE_SPAN_SCHEMA = "ai_subtitle_studio.audio.route_sample_span.v1"
_AUDIO_AI_VARIANT_SCHEMA = "ai_subtitle_studio.audio.ai_variant.v1"
_ROUTE_PREVIEW_DIVERGENCE_SCHEMA = "ai_subtitle_studio.audio.route_preview_divergence.v1"
_ROUTE_SPLIT_DECISION_SCHEMA = "ai_subtitle_studio.audio.route_split_decision.v1"


def audio_route_sample_span_via_swift(
    start: float,
    end: float,
    settings: dict[str, Any] | None,
) -> tuple[float, float] | None:
    result = run_subtitle_core_operation_via_swift(
        "audio_route_sample_span",
        {"start": float(start or 0.0), "end": float(end or 0.0), "settings": dict(settings or {})},
        context={"bridge": "native_swift_audio_filter"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SAMPLE_SPAN_SCHEMA:
        return None
    try:
        return float(result.get("start") or 0.0), float(result.get("duration") or 0.0)
    except Exception:
        return None


def audio_ai_variant_via_swift(
    *,
    audio_ai: str,
    fast_flatten_enabled: bool,
    clearvoice_native_ffmpeg_enabled: bool,
    clearvoice_model_name: str,
) -> str | None:
    result = run_subtitle_core_operation_via_swift(
        "audio_ai_variant",
        {
            "audio_ai": str(audio_ai or "none"),
            "fast_flatten_enabled": bool(fast_flatten_enabled),
            "clearvoice_native_ffmpeg_enabled": bool(clearvoice_native_ffmpeg_enabled),
            "clearvoice_model_name": str(clearvoice_model_name or ""),
        },
        context={"bridge": "native_swift_audio_filter"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _AUDIO_AI_VARIANT_SCHEMA:
        return None
    value = str(result.get("variant") or "").strip()
    return value if value or str(audio_ai or "none").strip().lower() == "none" else None


def audio_route_preview_divergence_via_swift(route: dict[str, Any] | None) -> float | None:
    result = run_subtitle_core_operation_via_swift(
        "audio_route_preview_divergence",
        {"route": dict(route or {})},
        context={"bridge": "native_swift_audio_filter"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _ROUTE_PREVIEW_DIVERGENCE_SCHEMA:
        return None
    try:
        return float(result.get("divergence") or 0.0)
    except Exception:
        return None


def audio_route_split_decision_via_swift(**payload: Any) -> bool | None:
    result = run_subtitle_core_operation_via_swift(
        "audio_route_split_decision",
        dict(payload or {}),
        context={"bridge": "native_swift_audio_filter"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _ROUTE_SPLIT_DECISION_SCHEMA:
        return None
    value = result.get("split")
    return value if isinstance(value, bool) else None


def fast_flatten_filter_via_swift(settings: dict[str, Any] | None) -> str | None:
    result = run_subtitle_core_operation_via_swift(
        "audio_fast_flatten_filter",
        {"settings": dict(settings or {})},
        context={"bridge": "native_swift_audio_filter"},
    )
    if not isinstance(result, dict) or str(result.get("schema") or "") != _SCHEMA:
        return None
    value = str(result.get("filter") or "").strip()
    return value or None


__all__ = [
    "audio_ai_variant_via_swift",
    "audio_route_preview_divergence_via_swift",
    "audio_route_sample_span_via_swift",
    "audio_route_split_decision_via_swift",
    "fast_flatten_filter_via_swift",
]
