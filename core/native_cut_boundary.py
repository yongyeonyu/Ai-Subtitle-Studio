from __future__ import annotations

"""Optional native C++ helpers for cut-boundary verification."""

import os
from typing import Any

try:
    from core import _native_cut_boundary as _native  # type: ignore
except Exception:  # pragma: no cover - exercised when extension is not built.
    _native = None  # type: ignore


HAS_NATIVE_CUT_BOUNDARY = _native is not None


def native_cut_boundary_enabled() -> bool:
    if _native is None:
        return False
    value = str(os.environ.get("AI_SUBTITLE_NATIVE_CUT_BOUNDARY", "1") or "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def cut_boundary_backend() -> str:
    return "cpp" if native_cut_boundary_enabled() else "python"


def delta_bytes(left: bytes, right: bytes, *, target_samples: int = 64) -> float | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        return float(_native.delta_bytes(left, right, int(target_samples or 64)))
    except Exception:
        return None


def gray_delta(
    prev_thumb: Any,
    next_thumb: Any,
    *,
    region_threshold: float,
    target_samples: int,
) -> tuple[float, int, list[float]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        score, hits, deltas = _native.gray_delta(
            prev_thumb,
            next_thumb,
            float(region_threshold),
            int(target_samples or 64),
        )
        return float(score), int(hits), [float(item) for item in list(deltas or [])]
    except Exception:
        return None


def color_avg_delta(
    prev_avg: Any,
    next_avg: Any,
    *,
    threshold: float,
    weight_luma: float,
    weight_chroma: float,
) -> tuple[float, int, list[float]] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        score, hits, deltas = _native.color_avg_delta(
            prev_avg,
            next_avg,
            float(threshold),
            float(weight_luma),
            float(weight_chroma),
        )
        return float(score), int(hits), [float(item) for item in list(deltas or [])]
    except Exception:
        return None


def interval_overlaps(
    segment_starts: Any,
    segment_ends: Any,
    vad_starts: Any,
    vad_ends: Any,
) -> list[float] | None:
    if not native_cut_boundary_enabled():
        return None
    try:
        values = _native.interval_overlaps(segment_starts, segment_ends, vad_starts, vad_ends)
        return [float(item) for item in list(values or [])]
    except Exception:
        return None
