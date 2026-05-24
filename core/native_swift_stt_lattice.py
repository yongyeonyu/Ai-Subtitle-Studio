from __future__ import annotations

"""Swift-native STT lattice bridge with Python/C++ fallback handled by caller."""

from typing import Any

from core.native_swift_subtitle import find_native_cli_path, native_swift_runtime_enabled
from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift
from core.runtime.config import IS_MAC

_SCHEMA = "ai_subtitle_studio.stt_lattice.match.v1"


def swift_stt_lattice_enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_STT_LATTICE") and find_native_cli_path() is not None


def best_word_match(
    *,
    anchor_start: float,
    anchor_end: float,
    word_starts: list[float],
    word_ends: list[float],
    textual_scores: list[float],
    used_indices: set[int] | list[int] | tuple[int, ...] | None,
    min_match_score: float,
) -> tuple[int | None, float] | None:
    if not swift_stt_lattice_enabled():
        return None
    payload: dict[str, Any] = {
        "anchor_start": float(anchor_start),
        "anchor_end": float(anchor_end),
        "word_starts": [float(item) for item in list(word_starts or [])],
        "word_ends": [float(item) for item in list(word_ends or [])],
        "textual_scores": [float(item or 0.0) for item in list(textual_scores or [])],
        "used_indices": sorted(int(item) for item in (used_indices or ()) if int(item) >= 0),
        "min_match_score": float(min_match_score),
    }
    result = run_subtitle_core_operation_via_swift(
        "stt_lattice_best_word_match",
        payload,
        context={"bridge": "native_swift_stt_lattice"},
    )
    if not isinstance(result, dict):
        return None
    if str(result.get("schema") or "") != _SCHEMA or result.get("error"):
        return None
    try:
        idx = int(result.get("best_index", -1))
        score = float(result.get("best_score") or 0.0)
    except Exception:
        return None
    if idx < 0:
        return None, score
    return idx, score


__all__ = ["best_word_match", "swift_stt_lattice_enabled"]
