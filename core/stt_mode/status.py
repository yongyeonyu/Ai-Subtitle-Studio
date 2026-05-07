# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Small STT Mode status formatting helpers."""
from __future__ import annotations

from typing import Any


def format_stt_status(
    *,
    state: str,
    completed_count: int = 0,
    total_count: int = 0,
    current_segment: dict[str, Any] | None = None,
) -> str:
    parts = [f"STT Mode {completed_count}/{total_count}"]
    if current_segment:
        start = float(current_segment.get("start", current_segment.get("timeline_start", 0.0)) or 0.0)
        end = float(current_segment.get("end", current_segment.get("timeline_end", start)) or start)
        parts.append(f"{start:0.2f}-{end:0.2f}s")
        confidence = current_segment.get("vad_confidence")
        label = str(current_segment.get("vad_confidence_label") or "")
        if confidence not in (None, "") or label:
            try:
                confidence_text = f"{float(confidence):0.2f}"
            except (TypeError, ValueError):
                confidence_text = "n/a"
            parts.append(f"VAD {confidence_text} {label}".strip())
    parts.append(str(state or "ready_to_listen"))
    return " · ".join(parts)


__all__ = ["format_stt_status"]
