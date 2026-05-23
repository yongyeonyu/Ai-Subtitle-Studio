"""FFmpeg scene-change prepass for cut-boundary pioneer scans.

This detector is intentionally lightweight. FFmpeg's native ``scene`` filter
can skim decoded frames in C much faster than Python/OpenCV seeking for long
videos, then the existing strict follower can refine or reject the candidates.
"""
from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

from core.ffmpeg_acceleration import ffmpeg_video_decode_accel_args
from core.frame_time import normalize_fps, sec_to_frame
from core.platform_compat import ffmpeg_binary, hidden_subprocess_kwargs


FFMPEG_SCENE_SOURCE = "ffmpeg_scene_provisional"
FFMPEG_SCENE_DETECTOR = "ffmpeg-scene-prepass-v1"
FFMPEG_SCENE_LINE_COLOR = "#00D1FF"

_PTS_TIME_RE = re.compile(r"\bpts_time:\s*(-?\d+(?:\.\d+)?)")
_SCENE_SCORE_RE = re.compile(r"\b(?:lavfi\.)?scene_score[=:]\s*(-?\d+(?:\.\d+)?)")


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except Exception:
        return default
    if not math.isfinite(number):
        return default
    return number


def parse_ffmpeg_scene_showinfo(stderr: str, *, threshold: float = 0.35) -> list[tuple[float, float]]:
    """Parse ``showinfo`` stderr into ``(sec, score)`` scene candidates."""
    out: list[tuple[float, float]] = []
    fallback_score = max(0.0, float(threshold or 0.0))
    for line in str(stderr or "").splitlines():
        time_match = _PTS_TIME_RE.search(line)
        if not time_match:
            continue
        sec = _finite_float(time_match.group(1))
        if sec is None or sec <= 0.0:
            continue
        score_match = _SCENE_SCORE_RE.search(line)
        score = _finite_float(score_match.group(1), fallback_score) if score_match else fallback_score
        out.append((round(sec, 3), float(score if score is not None else fallback_score)))
    return out


def detect_ffmpeg_scene_boundaries(
    filepath: str,
    *,
    clip_offset: float = 0.0,
    clip_idx: int = 0,
    fps: float = 30.0,
    threshold: float = 0.35,
    min_gap_sec: float = 8.0,
    timeout_sec: float = 90.0,
    max_candidates: int = 300,
    progress_callback=None,
    visual_scan_source_path: str | None = None,
    visual_scan_proxy: bool = False,
) -> list[dict[str, Any]]:
    """Return fast provisional visual cut candidates from FFmpeg.

    The rows are not final decisions. They are marked ``refine_pending`` so the
    normal strict verifier can move/delete them after the fast C-side pass.
    """
    path = Path(str(filepath or ""))
    if not path.exists():
        return []

    fps_value = normalize_fps(fps or 30.0)
    scene_threshold = max(0.01, min(0.95, float(threshold or 0.35)))
    min_gap = max(0.0, float(min_gap_sec or 0.0))
    timeout = max(1.0, float(timeout_sec or 90.0))
    limit = max(1, int(max_candidates or 300))
    source_path = str(visual_scan_source_path or path)

    filter_expr = f"select='gt(scene,{scene_threshold:.4f})',showinfo"
    input_args = [
        *ffmpeg_video_decode_accel_args(),
        "-i",
        str(path),
    ]
    cmd = [
        ffmpeg_binary(),
        "-hide_banner",
        "-nostdin",
        "-threads",
        "1",
        *input_args,
        "-vf",
        filter_expr,
        "-an",
        "-f",
        "null",
        "-",
    ]

    proc = None
    for attempt, candidate in enumerate((cmd, [item for item in cmd if item not in {"-hwaccel", "videotoolbox"}])):
        if attempt > 0 and candidate == cmd:
            continue
        try:
            proc = subprocess.run(
                candidate,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                **hidden_subprocess_kwargs(strip_qt=True),
            )
        except Exception:
            proc = None
        if proc is not None and proc.returncode in (0, None):
            break
    if proc is None:
        return []

    stderr = str(proc.stderr or "")
    if proc.returncode not in (0, None) and not stderr:
        return []

    rows: list[dict[str, Any]] = []
    last_sec = -999999.0
    for sec, score in parse_ffmpeg_scene_showinfo(stderr, threshold=scene_threshold):
        if sec - last_sec < min_gap:
            continue
        timeline_sec = round(float(clip_offset or 0.0) + sec, 3)
        frame = sec_to_frame(timeline_sec, fps_value)
        row = {
            "time": timeline_sec,
            "timeline_sec": timeline_sec,
            "clip_idx": int(clip_idx or 0),
            "clip_local_sec": sec,
            "coarse_time": sec,
            "frame": frame,
            "timeline_frame": frame,
            "fps": fps_value,
            "source": FFMPEG_SCENE_SOURCE,
            "detector": FFMPEG_SCENE_DETECTOR,
            "reason": "ffmpeg_scene_change",
            "score": round(float(score), 4),
            "scene_threshold": scene_threshold,
            "min_gap_sec": min_gap,
            "line_color": FFMPEG_SCENE_LINE_COLOR,
            "refine_pending": True,
            "refine_backend": "strict_visual_verify",
            "source_path": source_path,
            "visual_scan_source_path": str(path),
            "visual_scan_proxy": bool(visual_scan_proxy),
        }
        rows.append(row)
        last_sec = sec
        if callable(progress_callback):
            try:
                progress_callback(
                    {
                        "clip_idx": int(clip_idx or 0),
                        "stage": "ffmpeg_scene_prepass",
                        "timestamp": timeline_sec,
                        "detected": len(rows),
                        "visual_scan_source_path": str(path),
                        "visual_scan_proxy": bool(visual_scan_proxy),
                    }
                )
            except Exception:
                pass
        if len(rows) >= limit:
            break
    return rows


__all__ = [
    "FFMPEG_SCENE_DETECTOR",
    "FFMPEG_SCENE_LINE_COLOR",
    "FFMPEG_SCENE_SOURCE",
    "detect_ffmpeg_scene_boundaries",
    "parse_ffmpeg_scene_showinfo",
]
