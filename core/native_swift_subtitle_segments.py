from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


def summarize_segments_via_swift(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    payload = {
        "segments": [dict(row) for row in list(rows or []) if isinstance(row, dict)],
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_segments_summary",
        payload,
        context={"bridge": "native_swift_subtitle_segments"},
    )
    if not isinstance(native, dict):
        return None
    if str(native.get("schema") or "") != "ai_subtitle_studio.subtitle_segments.summary.v1":
        return None
    return native


__all__ = ["summarize_segments_via_swift"]
