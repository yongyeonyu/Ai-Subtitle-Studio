from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


def score_timing_metrics_via_swift(
    hypothesis: list[dict[str, Any]],
    reference: list[dict[str, Any]],
) -> dict[str, Any] | None:
    payload = {
        "hypothesis": [dict(row) for row in list(hypothesis or [])],
        "reference": [dict(row) for row in list(reference or [])],
    }
    native = run_subtitle_core_operation_via_swift(
        "subtitle_timing_metrics",
        payload,
        context={"bridge": "native_swift_subtitle_timing"},
    )
    if not isinstance(native, dict):
        return None
    try:
        return {
            "timing_mae_sec": float(native.get("timing_mae_sec", 0.0) or 0.0),
            "overlap_score": float(native.get("overlap_score", 0.0) or 0.0),
            "matched_pairs": int(native.get("matched_pairs", 0) or 0),
            "native_backend": "swift",
        }
    except Exception:
        return None


__all__ = ["score_timing_metrics_via_swift"]
