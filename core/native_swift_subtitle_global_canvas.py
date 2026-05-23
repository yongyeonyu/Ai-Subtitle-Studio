from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


def summarize_global_canvas_via_swift(
    rows: list[dict[str, Any]],
    *,
    duration: float = 0.0,
    bin_count: int = 120,
) -> dict[str, Any] | None:
    payload = {
        "segments": [dict(row) for row in list(rows or []) if isinstance(row, dict)],
        "duration": float(duration or 0.0),
        "bin_count": int(bin_count or 120),
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_global_canvas_summary",
        payload,
        context={"bridge": "native_swift_subtitle_global_canvas"},
    )
    if not isinstance(native, dict):
        return None
    if str(native.get("schema") or "") != "ai_subtitle_studio.subtitle_global_canvas.summary.v1":
        return None
    return native


__all__ = ["summarize_global_canvas_via_swift"]
