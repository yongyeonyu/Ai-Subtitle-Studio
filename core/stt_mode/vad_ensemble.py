# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Silero/TEN VAD ensemble logic for STT work segment generation."""
from __future__ import annotations

import os
import tempfile
from typing import Any

from core.frame_time import frame_to_sec, normalize_fps, sec_to_frame
from core.stt_mode.models import STT_WORK_SEGMENT_SOURCE, canonical_frame_timing
from core.stt_mode.segment_builder import build_stt_work_segments


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _source_key(provider: Any) -> str:
    text = str(provider or "").strip().lower()
    if text in {"ten", "tenvad", "ten-vad"}:
        return "ten_vad"
    if text in {"silero-vad", "silero_vad"}:
        return "silero"
    return text or "unknown"


def normalize_vad_candidate(
    row: dict[str, Any],
    *,
    provider: str,
    fps: float | int | str | None = None,
) -> dict[str, Any]:
    timeline_fps = normalize_fps(
        fps
        or row.get("timeline_frame_rate")
        or row.get("frame_rate")
        or 30.0
    )
    frame_range = row.get("frame_range", {}) if isinstance(row.get("frame_range"), dict) else {}
    start_frame = row.get("timeline_start_frame", row.get("start_frame", frame_range.get("start")))
    end_frame = row.get("timeline_end_frame", row.get("end_frame", frame_range.get("end")))
    if start_frame is None:
        start_frame = sec_to_frame(row.get("timeline_start", row.get("start", 0.0)), timeline_fps)
    if end_frame is None:
        end_frame = sec_to_frame(row.get("timeline_end", row.get("end", 0.0)), timeline_fps)
    start_frame = max(0, int(start_frame or 0))
    end_frame = max(start_frame, int(end_frame or start_frame))
    timing = canonical_frame_timing(
        frame_to_sec(start_frame, timeline_fps),
        frame_to_sec(end_frame, timeline_fps),
        frame_rate=timeline_fps,
        timeline_frame_rate=timeline_fps,
    )
    out = dict(row)
    out.update(timing)
    out["provider"] = _source_key(provider or row.get("provider") or row.get("source"))
    out["score"] = _safe_float(row.get("score", row.get("confidence", 0.0)))
    out["raw"] = row.get("raw", {key: value for key, value in row.items() if key not in out})
    return out


def _frames(row: dict[str, Any], fps: float) -> tuple[int, int]:
    normalized = normalize_vad_candidate(row, provider=str(row.get("provider") or row.get("source") or ""), fps=fps)
    return int(normalized["timeline_start_frame"]), int(normalized["timeline_end_frame"])


def _overlap(a: dict[str, Any], b: dict[str, Any], fps: float) -> tuple[int, int, int, float]:
    a_start, a_end = _frames(a, fps)
    b_start, b_end = _frames(b, fps)
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    union = max(1, max(a_end, b_end) - min(a_start, b_start))
    shorter = max(1, min(a_end - a_start, b_end - b_start))
    return inter, union, shorter, inter / union


def _confidence_label(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.52:
        return "medium"
    if score >= 0.28:
        return "low"
    return "needs_review"


def ensemble_vad_candidates(
    silero_candidates: list[dict[str, Any]] | None = None,
    ten_vad_candidates: list[dict[str, Any]] | None = None,
    *,
    media_duration: float | None = None,
    fps: float | int | str | None = None,
    settings: dict[str, Any] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Combine VAD candidates, then build user-friendly STT work segments."""
    timeline_fps = normalize_fps(fps or 30.0)
    silero = [
        normalize_vad_candidate(row, provider="silero", fps=timeline_fps)
        for row in silero_candidates or []
        if isinstance(row, dict)
    ]
    ten = [
        normalize_vad_candidate(row, provider="ten_vad", fps=timeline_fps)
        for row in ten_vad_candidates or []
        if isinstance(row, dict)
    ]

    used_ten: set[int] = set()
    consensus: list[dict[str, Any]] = []

    for s_idx, silero_row in enumerate(silero):
        best_idx = None
        best_metrics = (0, 1, 1, 0.0)
        for t_idx, ten_row in enumerate(ten):
            if t_idx in used_ten:
                continue
            metrics = _overlap(silero_row, ten_row, timeline_fps)
            if metrics[3] > best_metrics[3] or metrics[0] > best_metrics[0]:
                best_idx = t_idx
                best_metrics = metrics
        s_start, s_end = _frames(silero_row, timeline_fps)
        if best_idx is not None and best_metrics[0] > 0:
            ten_row = ten[best_idx]
            t_start, t_end = _frames(ten_row, timeline_fps)
            overlap_frames, union_frames, shorter_frames, iou = best_metrics
            agreement = overlap_frames / max(1, shorter_frames)
            start_delta = abs(s_start - t_start)
            end_delta = abs(s_end - t_end)
            delta_penalty = min(0.25, (start_delta + end_delta) / max(1, union_frames) * 0.35)
            score = max(0.0, min(1.0, 0.42 + iou * 0.35 + agreement * 0.35 - delta_penalty))
            start = min(s_start, t_start)
            end = max(s_end, t_end)
            row = {
                "id": f"stt_segment_seed_{len(consensus) + 1:04d}",
                "source": STT_WORK_SEGMENT_SOURCE,
                "vad_sources": ["silero", "ten_vad"],
                "vad_confidence": round(score, 4),
                "vad_confidence_label": _confidence_label(score),
                "vad_decision": "weighted_consensus",
                "candidate_refs": {
                    "silero": silero_row,
                    "ten_vad": ten_row,
                },
                "text": "",
            }
            row.update(
                canonical_frame_timing(
                    frame_to_sec(start, timeline_fps),
                    frame_to_sec(end, timeline_fps),
                    frame_rate=timeline_fps,
                    timeline_frame_rate=timeline_fps,
                )
            )
            consensus.append(row)
            used_ten.add(best_idx)
        else:
            score = min(0.51, max(0.24, _safe_float(silero_row.get("score"), 0.38)))
            row = {
                **silero_row,
                "id": f"stt_segment_seed_{len(consensus) + 1:04d}",
                "source": STT_WORK_SEGMENT_SOURCE,
                "vad_sources": ["silero"],
                "vad_confidence": round(score, 4),
                "vad_confidence_label": _confidence_label(score),
                "vad_decision": "silero_only_fallback",
                "candidate_refs": {"silero": silero_row},
                "text": "",
            }
            consensus.append(row)

    for t_idx, ten_row in enumerate(ten):
        if t_idx in used_ten:
            continue
        score = min(0.51, max(0.24, _safe_float(ten_row.get("score"), 0.36)))
        row = {
            **ten_row,
            "id": f"stt_segment_seed_{len(consensus) + 1:04d}",
            "source": STT_WORK_SEGMENT_SOURCE,
            "vad_sources": ["ten_vad"],
            "vad_confidence": round(score, 4),
            "vad_confidence_label": _confidence_label(score),
            "vad_decision": "ten_only_fallback",
            "candidate_refs": {"ten_vad": ten_row},
            "text": "",
        }
        consensus.append(row)

    consensus.sort(key=lambda row: _frames(row, timeline_fps))
    return build_stt_work_segments(
        consensus,
        cut_boundaries=cut_boundaries,
        media_duration=media_duration,
        fps=timeline_fps,
        settings=settings,
    )


def detect_stt_work_segments(
    media_path: str,
    *,
    fps: float | int | str | None = None,
    settings: dict[str, Any] | None = None,
    cut_boundaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run available providers and return STT work segments."""
    from core.stt_mode.vad_provider import detect_vad_candidates_from_wav, extract_vad_analysis_wav

    timeline_fps = normalize_fps(fps or 30.0)
    silero: list[dict[str, Any]] = []
    ten: list[dict[str, Any]] = []
    if not media_path or not os.path.exists(media_path):
        return []
    with tempfile.TemporaryDirectory(prefix="ai_subtitle_stt_vad_") as td:
        wav_path = os.path.join(td, "stt_vad.wav")
        try:
            extract_vad_analysis_wav(media_path, wav_path)
        except Exception:
            return []
        try:
            silero = detect_vad_candidates_from_wav(wav_path, provider="silero", settings=settings, fps=timeline_fps)
        except Exception:
            silero = []
        try:
            ten = detect_vad_candidates_from_wav(wav_path, provider="ten_vad", settings=settings, fps=timeline_fps)
        except Exception:
            ten = []
    return ensemble_vad_candidates(
        silero,
        ten,
        fps=timeline_fps,
        settings=settings,
        cut_boundaries=cut_boundaries,
    )


__all__ = [
    "detect_stt_work_segments",
    "ensemble_vad_candidates",
    "normalize_vad_candidate",
]
