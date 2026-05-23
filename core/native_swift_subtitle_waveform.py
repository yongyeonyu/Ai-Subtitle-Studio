from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


def summarize_waveform_via_swift(
    waveform: Any,
    *,
    duration: float = 0.0,
    speech_threshold: float = 0.02,
) -> dict[str, Any] | None:
    try:
        raw_values = waveform.tolist() if hasattr(waveform, "tolist") else list(waveform or [])
        values = [float(value) for value in list(raw_values or [])]
    except Exception:
        return None
    native = run_subtitle_core_operation_via_swift(
        "subtitle_waveform_summary",
        {
            "waveform": values,
            "duration": float(duration or 0.0),
            "speech_threshold": float(speech_threshold or 0.0),
        },
        context={"bridge": "native_swift_subtitle_waveform"},
    )
    if not isinstance(native, dict):
        return None
    if str(native.get("schema") or "") != "ai_subtitle_studio.subtitle_waveform.summary.v1":
        return None
    return native


__all__ = ["summarize_waveform_via_swift"]
