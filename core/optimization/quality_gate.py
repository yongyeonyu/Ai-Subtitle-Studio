from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BackendQualityGate:
    max_cer_regression_pp: float = 0.3
    max_timing_mae_regression_ms: float = 50.0
    max_quality_score_drop: float = 0.25
    max_readability_score_drop: float = 1.0
    min_segment_retention_ratio: float = 0.95
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


def _nested_metric(row: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    data = dict(row or {})
    if key in data:
        return _metric(data, key, default)
    quality = dict(data.get("quality") or {})
    if key in quality:
        return _metric(quality, key, default)
    readability = dict(data.get("readability") or {})
    if key in readability:
        return _metric(readability, key, default)
    return float(default)


def subtitle_quality_gate(
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    *,
    gate: BackendQualityGate | None = None,
) -> dict[str, Any]:
    """Return a benchmark gate verdict that keeps faster variants from reducing subtitle quality."""
    gate = gate or BackendQualityGate()
    base = dict(baseline or {})
    cand = dict(candidate or {})
    reasons: list[str] = []
    if cand.get("error"):
        reasons.append("candidate_error")

    base_quality = _nested_metric(base, "quality_score")
    cand_quality = _nested_metric(cand, "quality_score")
    quality_delta = cand_quality - base_quality
    if quality_delta < -float(gate.max_quality_score_drop):
        reasons.append("quality_score_drop")

    base_readability = _nested_metric(base, "readability_score")
    cand_readability = _nested_metric(cand, "readability_score")
    readability_delta = cand_readability - base_readability
    if readability_delta < -float(gate.max_readability_score_drop):
        reasons.append("readability_score_drop")

    base_cer = _nested_metric(base, "cer")
    cand_cer = _nested_metric(cand, "cer")
    cer_delta_pp = (cand_cer - base_cer) * 100.0
    if cer_delta_pp > float(gate.max_cer_regression_pp):
        reasons.append("cer_regression")

    base_timing = _nested_metric(base, "timing_mae_sec") * 1000.0
    cand_timing = _nested_metric(cand, "timing_mae_sec") * 1000.0
    timing_delta_ms = cand_timing - base_timing
    if timing_delta_ms > float(gate.max_timing_mae_regression_ms):
        reasons.append("timing_mae_regression")

    base_segments = max(1.0, _nested_metric(base, "hypothesis_segments", _metric(base, "final_segments", 0.0)))
    cand_segments = _nested_metric(cand, "hypothesis_segments", _metric(cand, "final_segments", 0.0))
    segment_retention = cand_segments / base_segments if base_segments > 0.0 else 1.0
    if segment_retention < float(gate.min_segment_retention_ratio):
        reasons.append("segment_retention_drop")

    return {
        "passed": not reasons,
        "reasons": reasons,
        "quality_delta": round(quality_delta, 3),
        "readability_delta": round(readability_delta, 3),
        "cer_delta_pp": round(cer_delta_pp, 4),
        "timing_mae_delta_ms": round(timing_delta_ms, 3),
        "segment_retention_ratio": round(segment_retention, 4),
    }
