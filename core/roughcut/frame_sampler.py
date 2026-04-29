# Version: 03.00.00
# Phase: PHASE2
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable


def sample_timestamps(start: float, end: float, max_frames: int = 5, avoid_edges: float = 0.2) -> list[float]:
    """Choose stable frame timestamps while avoiding hard cut edges."""
    start_sec = max(0.0, float(start))
    end_sec = max(start_sec, float(end))
    count = max(1, int(max_frames))
    edge = max(0.0, float(avoid_edges))

    if end_sec - start_sec <= edge * 2:
        return [round((start_sec + end_sec) / 2, 3)]

    inner_start = start_sec + edge
    inner_end = end_sec - edge
    if count == 1:
        return [round((inner_start + inner_end) / 2, 3)]

    step = (inner_end - inner_start) / (count - 1)
    return [round(inner_start + step * index, 3) for index in range(count)]


def build_ffmpeg_frame_command(
    input_path: str,
    timestamp: float,
    output_path: str,
    width: int = 320,
    quality: int = 5,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    width_value = max(64, int(width))
    quality_value = max(2, min(31, int(quality)))
    return [
        ffmpeg_bin,
        "-y",
        "-ss",
        f"{max(0.0, float(timestamp)):.3f}",
        "-i",
        input_path,
        "-frames:v",
        "1",
        "-vf",
        f"scale={width_value}:-2",
        "-q:v",
        str(quality_value),
        output_path,
    ]


def extract_frames(
    input_path: str,
    timestamps: Iterable[float],
    output_dir: str,
    width: int = 320,
    quality: int = 5,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Extract low-resolution frames for roughcut thumbnails.

    This helper is optional and never writes over the source media. It is kept
    small so UI/workers can decide when to call it.
    """
    source = os.path.abspath(input_path)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    for index, timestamp in enumerate(timestamps):
        frame_name = f"frame_{index:03d}_{int(max(0.0, float(timestamp)) * 1000):09d}.jpg"
        output_path = str(target_dir / frame_name)
        command = build_ffmpeg_frame_command(
            source,
            timestamp,
            output_path,
            width=width,
            quality=quality,
            ffmpeg_bin=ffmpeg_bin,
        )
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        outputs.append(output_path)
    return outputs
