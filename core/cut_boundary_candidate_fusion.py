"""Pioneer cut-boundary candidate fusion.

This module clusters provisional detector rows from visual, packet, scene, audio,
and optional ML scouts. It does not turn analysis results into exact metadata;
the follower verifier still owns final hard-cut confirmation.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from core.frame_time import normalize_fps, sec_to_frame


FUSED_PIONEER_SOURCE = "pioneer_candidate_fusion"
FUSED_PIONEER_DETECTOR = "pioneer-candidate-fusion-v1"


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(number):
        return float(default)
    return number


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(float(low), min(float(high), float(value)))


def candidate_time_sec(row: Any, *, fps: float = 30.0) -> float | None:
    if not isinstance(row, dict):
        value = _finite_float(row, -1.0)
        return value if value > 0.0 else None
    for key in ("timeline_sec", "time", "clip_local_sec", "coarse_time", "local_sec", "sec"):
        if key in row:
            value = _finite_float(row.get(key), -1.0)
            if value > 0.0:
                return value
    for key in ("timeline_frame", "frame"):
        if key in row:
            frame = _finite_float(row.get(key), -1.0)
            if frame > 0.0:
                return frame / normalize_fps(row.get("fps") or row.get("frame_rate") or fps or 30.0)
    return None


def candidate_detector_kind(row: dict[str, Any]) -> str:
    source = str(row.get("source") or "").strip().lower()
    detector = str(row.get("detector") or "").strip().lower()
    joined = f"{source} {detector}"
    if "spectral" in joined:
        return "audio_spectral"
    if "audio" in joined:
        return "audio"
    if "packet" in joined or "keyframe" in joined:
        return "packet"
    if "ffmpeg_scene" in joined or "scene" in joined:
        return "scene"
    if "transnet" in joined or "ml" in joined or "model" in joined:
        return "ml"
    return "visual"


def _candidate_weight(row: dict[str, Any]) -> float:
    kind = candidate_detector_kind(row)
    score = _finite_float(row.get("score"), 0.0)
    if kind == "visual":
        return _clamp(0.56 + min(0.34, score / 260.0))
    if kind == "scene":
        return _clamp(0.48 + min(0.32, score * 0.60))
    if kind == "packet":
        packet_score = _finite_float(row.get("packet_score"), score)
        return _clamp(0.40 + min(0.30, packet_score / 12.0))
    if kind == "audio_spectral":
        flux_score = _finite_float(row.get("audio_spectral_flux_score"), score)
        return _clamp(0.30 + min(0.24, flux_score / 8.0))
    if kind == "audio":
        delta = abs(_finite_float(row.get("audio_gain_db_delta", row.get("delta_db")), score))
        return _clamp(0.24 + min(0.24, delta / 40.0))
    if kind == "ml":
        return _clamp(0.66 + min(0.28, score))
    return _clamp(0.20 + min(0.20, score / 100.0))


def _representative_sort_key(item: tuple[dict[str, Any], float]) -> tuple[int, float, float]:
    row, weight = item
    priority = {
        "visual": 5,
        "ml": 4,
        "scene": 3,
        "packet": 2,
        "audio_spectral": 1,
        "audio": 0,
    }.get(candidate_detector_kind(row), 0)
    return priority, float(weight), _finite_float(row.get("score"), 0.0)


def _fusion_score(weighted_rows: list[tuple[dict[str, Any], float]]) -> float:
    miss_probability = 1.0
    for _row, weight in weighted_rows:
        miss_probability *= 1.0 - _clamp(float(weight))
    return _clamp(1.0 - miss_probability)


def fuse_cut_boundary_candidate_rows(
    rows: Iterable[dict[str, Any]] | None,
    *,
    fps: float = 30.0,
    window_sec: float = 0.35,
    keep_threshold: float = 0.68,
    verify_threshold: float = 0.43,
    max_candidates: int | None = None,
) -> list[dict[str, Any]]:
    """Cluster provisional rows and annotate a representative row per cluster."""
    fps_value = normalize_fps(fps or 30.0)
    window = max(0.02, float(window_sec or 0.35))
    keep = _clamp(float(keep_threshold or 0.68))
    verify = _clamp(float(verify_threshold or 0.43), 0.0, keep)
    items: list[tuple[float, dict[str, Any]]] = []
    for raw in list(rows or []):
        if not isinstance(raw, dict):
            continue
        sec = candidate_time_sec(raw, fps=fps_value)
        if sec is None or sec <= 0.0:
            continue
        items.append((float(sec), dict(raw)))
    if not items:
        return []
    items.sort(key=lambda item: item[0])

    clusters: list[list[tuple[float, dict[str, Any]]]] = []
    for sec, row in items:
        if not clusters:
            clusters.append([(sec, row)])
            continue
        previous = clusters[-1]
        anchor = sum(item[0] for item in previous) / float(len(previous))
        if abs(sec - anchor) <= window:
            previous.append((sec, row))
        else:
            clusters.append([(sec, row)])

    fused: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        weighted = [(row, _candidate_weight(row)) for _sec, row in cluster]
        representative, representative_weight = max(weighted, key=_representative_sort_key)
        cluster_score = _fusion_score(weighted)
        sources = sorted({candidate_detector_kind(row) for _sec, row in cluster})
        if cluster_score >= keep:
            confidence = "high"
            decision = "keep"
        elif cluster_score >= verify:
            confidence = "medium"
            decision = "verify"
        else:
            confidence = "low"
            decision = "verify_low_confidence"

        sec = candidate_time_sec(representative, fps=fps_value) or cluster[0][0]
        frame = sec_to_frame(sec, fps_value)
        row = dict(representative)
        row.update(
            {
                "schema": "cut_boundary.v1",
                "id": row.get("id") or f"fusion_cut_{frame:08d}",
                "time": round(float(sec), 3),
                "timeline_sec": round(float(sec), 3),
                "frame": frame,
                "timeline_frame": frame,
                "fps": fps_value,
                "frame_rate": fps_value,
                "timeline_frame_rate": fps_value,
                "status": "provisional",
                "verified": False,
                "detector_stage": "pioneer_fusion",
                "fusion_schema": "cut_boundary_pioneer_fusion.v1",
                "fusion_source": FUSED_PIONEER_SOURCE,
                "fusion_detector": FUSED_PIONEER_DETECTOR,
                "fusion_index": index,
                "fusion_sources": sources,
                "fusion_evidence_count": len(cluster),
                "fusion_score": round(cluster_score, 4),
                "fusion_confidence": confidence,
                "fusion_decision": decision,
                "fusion_representative_weight": round(float(representative_weight), 4),
                "fusion_window_sec": round(window, 3),
            }
        )
        if "visual" not in sources and "ml" not in sources and "scene" not in sources:
            row["hard_cut_allowed"] = False
        row.setdefault("refine_pending", True)
        fused.append(row)

    fused.sort(key=lambda row: _finite_float(row.get("timeline_sec"), 0.0))
    if max_candidates is not None:
        fused = fused[: max(0, int(max_candidates))]
    return fused


__all__ = [
    "FUSED_PIONEER_DETECTOR",
    "FUSED_PIONEER_SOURCE",
    "candidate_detector_kind",
    "candidate_time_sec",
    "fuse_cut_boundary_candidate_rows",
]
