# Version: 03.00.17
# Phase: PHASE2
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import EDLSegment


@dataclass(frozen=True, slots=True)
class RenderCommandPlan:
    temp_dir: str
    extract_commands: tuple[tuple[str, ...], ...]
    concat_file_path: str
    concat_command: tuple[str, ...]
    output_path: str
    warnings: tuple[str, ...] = ()


def ffmpeg_available(binary: str = "ffmpeg") -> bool:
    return shutil.which(binary) is not None


def _safe_path(path: str | Path) -> str:
    return str(Path(path).expanduser())


def _validate_output_path(output_path: str | Path, source_paths: Iterable[str]) -> str:
    output = Path(output_path).expanduser()
    output_resolved = output.resolve(strict=False)
    for source in source_paths:
        if output_resolved == Path(source).expanduser().resolve(strict=False):
            raise ValueError("output_path must not overwrite the source media file")
    return str(output)


def _renderable_segments(edl_segments: Iterable[EDLSegment]) -> list[EDLSegment]:
    allowed = {"keep", "highlight", "trim", "move"}
    return [segment for segment in edl_segments if segment.action in allowed and segment.source_end > segment.source_start]


def build_ffmpeg_extract_command(
    segment: EDLSegment,
    output_path: str | Path,
    ffmpeg_binary: str = "ffmpeg",
) -> tuple[str, ...]:
    duration = max(0.0, segment.source_end - segment.source_start)
    return (
        ffmpeg_binary,
        "-y",
        "-ss",
        f"{segment.source_start:.3f}",
        "-i",
        segment.source_path,
        "-t",
        f"{duration:.3f}",
        "-c",
        "copy",
        _safe_path(output_path),
    )


def build_ffmpeg_concat_command(
    concat_file_path: str | Path,
    output_path: str | Path,
    ffmpeg_binary: str = "ffmpeg",
) -> tuple[str, ...]:
    return (
        ffmpeg_binary,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        _safe_path(concat_file_path),
        "-c",
        "copy",
        _safe_path(output_path),
    )


def _subtitle_filter_path(path: str | Path) -> str:
    raw = _safe_path(path)
    return raw.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def build_ffmpeg_subtitle_burnin_command(
    input_path: str | Path,
    subtitle_path: str | Path,
    output_path: str | Path,
    ffmpeg_binary: str = "ffmpeg",
) -> tuple[str, ...]:
    output = _validate_output_path(output_path, [str(input_path)])
    return (
        ffmpeg_binary,
        "-y",
        "-i",
        _safe_path(input_path),
        "-vf",
        f"subtitles='{_subtitle_filter_path(subtitle_path)}'",
        "-c:a",
        "copy",
        output,
    )


def build_concat_render_plan(
    edl_segments: Iterable[EDLSegment],
    output_path: str | Path,
    temp_dir: str | Path,
    ffmpeg_binary: str = "ffmpeg",
) -> RenderCommandPlan:
    """Build a no-execution ffmpeg concat plan for roughcut keep/highlight segments."""
    segments = _renderable_segments(edl_segments)
    source_paths = {segment.source_path for segment in segments}
    output = _validate_output_path(output_path, source_paths)
    temp = Path(temp_dir).expanduser()
    concat_file = temp / "roughcut_concat.txt"
    warnings: list[str] = []
    if not ffmpeg_available(ffmpeg_binary):
        warnings.append(f"{ffmpeg_binary} not found")

    extract_commands = []
    for index, segment in enumerate(segments, start=1):
        suffix = Path(segment.source_path).suffix or ".mp4"
        part_path = temp / f"roughcut_part_{index:04d}{suffix}"
        extract_commands.append(build_ffmpeg_extract_command(segment, part_path, ffmpeg_binary=ffmpeg_binary))

    return RenderCommandPlan(
        temp_dir=str(temp),
        extract_commands=tuple(extract_commands),
        concat_file_path=str(concat_file),
        concat_command=build_ffmpeg_concat_command(concat_file, output, ffmpeg_binary=ffmpeg_binary),
        output_path=output,
        warnings=tuple(warnings),
    )
