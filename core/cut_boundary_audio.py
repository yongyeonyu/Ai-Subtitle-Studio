"""Audio-gain provisional cut-boundary detection.

Audio changes are intentionally treated as rough pioneer hints. The visual
rollback follower must still verify, relocate, or delete these candidates.
"""
from __future__ import annotations

import array
import math
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from core.frame_time import normalize_fps, sec_to_frame
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs
from core.personalization.deep_subtitle_policy import score_cut_boundary


AUDIO_GAIN_BOUNDARY_SOURCE = "audio_gain_provisional"
AUDIO_GAIN_BOUNDARY_DETECTOR = "audio-gain-rms-v1"
AUDIO_GAIN_LINE_COLOR = "#39FF14"


def is_audio_gain_boundary(row: dict | None) -> bool:
    if not isinstance(row, dict):
        return False
    source = str(row.get("source", "") or "").strip().lower()
    detector = str(row.get("detector", "") or "").strip().lower()
    return source == AUDIO_GAIN_BOUNDARY_SOURCE or detector.startswith("audio-gain")


def _finite_float(value, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except Exception:
        return default
    if not math.isfinite(number):
        return default
    return number


def _avg(values: Iterable[float]) -> float | None:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return None
    return sum(finite) / float(len(finite))


def audio_gain_levels_from_pcm16le(
    pcm: bytes,
    *,
    sample_rate: int = 4000,
    window_sec: float = 2.0,
    floor_db: float = -90.0,
) -> list[tuple[float, float]]:
    """Return ``(window_center_sec, rms_dbfs)`` levels from signed 16-bit PCM."""
    if not pcm:
        return []
    sample_rate = max(1, int(sample_rate or 4000))
    window_samples = max(1, int(round(sample_rate * max(0.10, float(window_sec or 2.0)))))
    floor_db = float(floor_db)

    try:
        import numpy as np

        samples = np.frombuffer(pcm, dtype="<i2")
        if samples.size <= 0:
            return []
        levels: list[tuple[float, float]] = []
        full_count = int(samples.size // window_samples)
        if full_count > 0:
            usable = full_count * window_samples
            windows = samples[:usable].astype("float32").reshape(full_count, window_samples)
            rms = np.sqrt(np.mean(windows * windows, axis=1))
            with np.errstate(divide="ignore", invalid="ignore"):
                dbs = 20.0 * np.log10(rms / 32768.0)
            for idx, db in enumerate(dbs):
                center = (idx * window_samples + (window_samples * 0.5)) / float(sample_rate)
                value = float(db) if math.isfinite(float(db)) else floor_db
                levels.append((round(center, 3), max(floor_db, value)))
        remainder = samples[full_count * window_samples :]
        if remainder.size >= max(1, window_samples // 2):
            rem = remainder.astype("float32")
            rms = float(np.sqrt(np.mean(rem * rem)))
            db = 20.0 * math.log10(rms / 32768.0) if rms > 0.0 else floor_db
            start = full_count * window_samples
            center = (start + (remainder.size * 0.5)) / float(sample_rate)
            levels.append((round(center, 3), max(floor_db, db)))
        return levels
    except Exception:
        pass

    usable_bytes = len(pcm) - (len(pcm) % 2)
    if usable_bytes <= 0:
        return []
    samples = array.array("h")
    samples.frombytes(pcm[:usable_bytes])
    if sys.byteorder != "little":
        samples.byteswap()
    levels: list[tuple[float, float]] = []
    total_samples = len(samples)
    for start in range(0, total_samples, window_samples):
        end = min(total_samples, start + window_samples)
        count = end - start
        if count <= 0:
            continue
        if start > 0 and count < max(1, window_samples // 2):
            break
        total_sq = 0.0
        for sample in samples[start:end]:
            value = int(sample)
            total_sq += float(value * value)
        rms = math.sqrt(total_sq / float(count)) if count else 0.0
        db = 20.0 * math.log10(rms / 32768.0) if rms > 0.0 else floor_db
        center = (start + (count * 0.5)) / float(sample_rate)
        levels.append((round(center, 3), max(floor_db, db)))
    return levels


def extract_audio_gain_levels(
    filepath: str,
    *,
    sample_rate: int = 4000,
    window_sec: float = 2.0,
    timeout_sec: float = 45.0,
) -> list[tuple[float, float]]:
    """Decode a lightweight mono PCM stream and return RMS windows."""
    path = Path(str(filepath or ""))
    if not path.exists():
        return []
    sample_rate = max(1000, int(sample_rate or 4000))
    timeout_sec = max(1.0, float(timeout_sec or 45.0))
    cmd = [
        ffmpeg_binary(),
        "-nostdin",
        "-v",
        "error",
        "-threads",
        "1",
        "-i",
        str(path),
        "-map",
        "0:a:0?",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            **hidden_subprocess_kwargs(strip_qt=True),
        )
    except Exception:
        return []
    if not completed.stdout:
        return []
    return audio_gain_levels_from_pcm16le(
        completed.stdout,
        sample_rate=sample_rate,
        window_sec=window_sec,
    )


def detect_audio_gain_changes(
    levels: list[tuple[float, float]],
    *,
    threshold_db: float = 10.0,
    min_gap_sec: float = 8.0,
    context_windows: int = 2,
    duration_sec: float | None = None,
    edge_guard_sec: float = 1.0,
    max_candidates: int = 240,
) -> list[dict]:
    """Find sustained RMS-level shifts suitable for rough cut-boundary hints."""
    cleaned: list[tuple[float, float]] = []
    for sec, db in levels or []:
        sec_value = _finite_float(sec)
        db_value = _finite_float(db)
        if sec_value is None or db_value is None:
            continue
        cleaned.append((sec_value, db_value))
    cleaned.sort(key=lambda item: item[0])
    if len(cleaned) < 3:
        return []

    threshold_db = max(1.0, float(threshold_db or 10.0))
    min_gap_sec = max(0.0, float(min_gap_sec or 0.0))
    context_windows = max(1, int(context_windows or 2))
    edge_guard_sec = max(0.0, float(edge_guard_sec or 0.0))
    duration_value = _finite_float(duration_sec)
    max_candidates = max(1, int(max_candidates or 240))
    candidates: list[dict] = []

    for idx in range(1, len(cleaned)):
        before = _avg(db for _sec, db in cleaned[max(0, idx - context_windows) : idx])
        after = _avg(db for _sec, db in cleaned[idx : min(len(cleaned), idx + context_windows)])
        if before is None or after is None:
            continue
        prev_sec = cleaned[idx - 1][0]
        next_sec = cleaned[idx][0]
        boundary_sec = (prev_sec + next_sec) * 0.5
        if boundary_sec <= edge_guard_sec:
            continue
        if duration_value is not None and boundary_sec >= max(0.0, duration_value - edge_guard_sec):
            continue
        delta = after - before
        score = abs(delta)
        if score < threshold_db:
            continue
        candidate = {
            "local_sec": round(boundary_sec, 3),
            "score": round(score, 3),
            "before_db": round(before, 3),
            "after_db": round(after, 3),
            "delta_db": round(delta, 3),
            "window_index": idx,
        }
        if candidates and (boundary_sec - float(candidates[-1]["local_sec"])) < min_gap_sec:
            if score > float(candidates[-1]["score"]):
                candidates[-1] = candidate
            continue
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            break
    return candidates


def build_audio_gain_boundary_rows(
    candidates: list[dict],
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    fps: float = 30.0,
    source_path: str = "",
    threshold_db: float = 10.0,
    window_sec: float = 2.0,
    sample_rate: int = 4000,
) -> list[dict]:
    rows: list[dict] = []
    fps_value = normalize_fps(fps or 30.0)
    offset = float(clip_offset or 0.0)
    for idx, candidate in enumerate(candidates or [], start=1):
        local_sec = _finite_float(candidate.get("local_sec"))
        if local_sec is None or local_sec <= 0.0:
            continue
        timeline_sec = round(offset + local_sec, 3)
        timeline_frame = sec_to_frame(timeline_sec, fps_value)
        row = {
            "schema": "cut_boundary.v1",
            "id": f"audio_cut_{int(clip_idx or 0):02d}_{timeline_frame:08d}",
            "time": timeline_sec,
            "timeline_sec": timeline_sec,
            "frame": timeline_frame,
            "timeline_frame": timeline_frame,
            "fps": fps_value,
            "frame_rate": fps_value,
            "timeline_frame_rate": fps_value,
            "clip_idx": int(clip_idx or 0),
            "clip_local_sec": round(local_sec, 3),
            "source_path": str(source_path or ""),
            "source": AUDIO_GAIN_BOUNDARY_SOURCE,
            "detector": AUDIO_GAIN_BOUNDARY_DETECTOR,
            "detector_stage": "audio_pioneer",
            "reason": "audio_gain_shift",
            "status": "provisional",
            "verified": False,
            "locked": False,
            "absolute": True,
            "refine_pending": True,
            "refine_backend": "visual_rollback",
            "provisional_type": "audio_gain",
            "line_color": AUDIO_GAIN_LINE_COLOR,
            "line_style": "dash",
            "score": float(candidate.get("score", 0.0) or 0.0),
            "audio_gain_db_before": float(candidate.get("before_db", 0.0) or 0.0),
            "audio_gain_db_after": float(candidate.get("after_db", 0.0) or 0.0),
            "audio_gain_db_delta": float(candidate.get("delta_db", 0.0) or 0.0),
            "audio_gain_threshold_db": float(threshold_db or 0.0),
            "audio_gain_window_sec": float(window_sec or 0.0),
            "audio_gain_sample_rate": int(sample_rate or 0),
            "audio_gain_candidate_index": idx,
        }
        deep_score = score_cut_boundary(row, {"scan_cut_audio_gain_threshold_db": threshold_db})
        row["deep_boundary_score"] = deep_score.get("score", 0.0)
        row["deep_boundary_decision"] = deep_score.get("decision", "")
        row["deep_boundary_model"] = deep_score.get("model", "")
        rows.append(row)
    return rows


def detect_audio_gain_boundary_rows(
    filepath: str,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    fps: float = 30.0,
    duration_sec: float | None = None,
    threshold_db: float = 10.0,
    min_gap_sec: float = 8.0,
    window_sec: float = 2.0,
    sample_rate: int = 4000,
    context_windows: int = 2,
    timeout_sec: float = 45.0,
    max_candidates: int = 240,
) -> list[dict]:
    levels = extract_audio_gain_levels(
        filepath,
        sample_rate=sample_rate,
        window_sec=window_sec,
        timeout_sec=timeout_sec,
    )
    candidates = detect_audio_gain_changes(
        levels,
        threshold_db=threshold_db,
        min_gap_sec=min_gap_sec,
        context_windows=context_windows,
        duration_sec=duration_sec,
        max_candidates=max_candidates,
    )
    return build_audio_gain_boundary_rows(
        candidates,
        clip_offset=clip_offset,
        clip_idx=clip_idx,
        fps=fps,
        source_path=str(filepath or ""),
        threshold_db=threshold_db,
        window_sec=window_sec,
        sample_rate=sample_rate,
    )


__all__ = [
    "AUDIO_GAIN_BOUNDARY_DETECTOR",
    "AUDIO_GAIN_BOUNDARY_SOURCE",
    "AUDIO_GAIN_LINE_COLOR",
    "audio_gain_levels_from_pcm16le",
    "build_audio_gain_boundary_rows",
    "detect_audio_gain_boundary_rows",
    "detect_audio_gain_changes",
    "extract_audio_gain_levels",
    "is_audio_gain_boundary",
]
