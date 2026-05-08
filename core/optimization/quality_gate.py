from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BackendQualityGate:
    max_cer_regression_pp: float = 0.3
    max_timing_mae_regression_ms: float = 50.0
    max_missed_speech_delta: float = 0.0
    max_missed_cut_delta: float = 0.0
    min_ui_frame_time_improvement_ratio: float = 0.30


def _metric(row: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    try:
        return float(dict(row or {}).get(key, default) or default)
    except Exception:
        return float(default)


def quality_gate_passed(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *,
    task: str,
    gate: BackendQualityGate | None = None,
) -> bool:
    gate = gate or BackendQualityGate()
    task_key = str(task or "").strip().lower()
    base = dict(baseline or {})
    cand = dict(candidate or {})

    if task_key == "stt":
        cer_delta_pp = (_metric(cand, "cer") - _metric(base, "cer")) * 100.0
        timing_delta = _metric(cand, "timing_mae_ms") - _metric(base, "timing_mae_ms")
        return cer_delta_pp <= gate.max_cer_regression_pp and timing_delta <= gate.max_timing_mae_regression_ms
    if task_key == "vad":
        missed_delta = _metric(cand, "missed_speech_count") - _metric(base, "missed_speech_count")
        return missed_delta <= gate.max_missed_speech_delta
    if task_key in {"cut", "cut_boundary"}:
        missed_delta = _metric(cand, "missed_cut_count") - _metric(base, "missed_cut_count")
        return missed_delta <= gate.max_missed_cut_delta
    if task_key in {"editor", "timeline", "ui"}:
        base_frame = max(0.001, _metric(base, "frame_time_ms"))
        cand_frame = max(0.001, _metric(cand, "frame_time_ms"))
        improvement = (base_frame - cand_frame) / base_frame
        return improvement >= gate.min_ui_frame_time_improvement_ratio
    return bool(cand.get("passed_quality_gate", False))
