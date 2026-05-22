from __future__ import annotations

from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task


def roughcut_boundary_candidates_via_swift(
    rows: list[dict[str, Any]],
    boundary_rows: list[Any],
    *,
    source: str,
) -> list[dict[str, Any]] | None:
    """Plan roughcut chunk boundary candidates in the shared Swift worker."""
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_ROUGHCUT"):
        return None
    if len(rows or []) < 2 or not boundary_rows:
        return []
    decoded = request_native_core_task(
        "roughcut_boundary_candidates",
        {
            "rows": rows,
            "boundary_rows": boundary_rows,
            "source": str(source or "boundary"),
        },
    )
    candidates = decoded.get("candidates") if isinstance(decoded, dict) else None
    if not isinstance(candidates, list):
        return None
    out: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            end_index = int(item.get("end_index"))
            distance = float(item.get("distance", 0.0) or 0.0)
            time_value = float(item.get("time", 0.0) or 0.0)
        except Exception:
            return None
        out.append(
            {
                "end_index": end_index,
                "source": str(item.get("source") or source or "boundary"),
                "distance": distance,
                "time": time_value,
            }
        )
    return out


__all__ = ["roughcut_boundary_candidates_via_swift"]
