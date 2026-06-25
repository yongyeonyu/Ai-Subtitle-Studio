# Version: 03.01.32
# Phase: PHASE2
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.video_codec import ffmpeg_hwdecode_args, hevc_encode_args, lossless_video_encode_args, roughcut_render_mode

from .edl_generator import build_stitched_cut_boundaries
from .models import EDLSegment


@dataclass(frozen=True, slots=True)
class RenderCommandPlan:
    temp_dir: str
    extract_commands: tuple[tuple[str, ...], ...]
    concat_file_path: str
    concat_command: tuple[str, ...]
    output_path: str
    render_mode: str = "copy"
    warnings: tuple[str, ...] = ()
    segment_manifest: tuple[dict, ...] = ()
    stitched_cut_boundaries: tuple[dict, ...] = ()


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


def _faststart_args(output_path: str | Path) -> tuple[str, ...]:
    suffix = Path(output_path).suffix.lower()
    return ("-movflags", "+faststart") if suffix in {".mp4", ".m4v", ".mov"} else ()


def build_ffmpeg_extract_command(
    segment: EDLSegment,
    output_path: str | Path,
    ffmpeg_binary: str = "ffmpeg",
    render_mode: str | None = None,
) -> tuple[str, ...]:
    duration = max(0.0, segment.source_end - segment.source_start)
    mode = roughcut_render_mode(render_mode)
    if mode == "copy":
        return (
            ffmpeg_binary,
            "-y",
            "-ss",
            f"{segment.source_start:.3f}",
            "-i",
            segment.source_path,
            "-t",
            f"{duration:.3f}",
            "-map",
            "0",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            _safe_path(output_path),
        )
    if mode == "lossless":
        return (
            ffmpeg_binary,
            "-y",
            *ffmpeg_hwdecode_args(),
            "-i",
            segment.source_path,
            "-ss",
            f"{segment.source_start:.3f}",
            "-t",
            f"{duration:.3f}",
            *lossless_video_encode_args(output_path),
            _safe_path(output_path),
        )
    return (
        ffmpeg_binary,
        "-y",
        "-ss",
        f"{segment.source_start:.3f}",
        *ffmpeg_hwdecode_args(),
        "-i",
        segment.source_path,
        "-t",
        f"{duration:.3f}",
        *hevc_encode_args(quality="fast"),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        _safe_path(output_path),
    )


def build_ffmpeg_concat_command(
    concat_file_path: str | Path,
    output_path: str | Path,
    ffmpeg_binary: str = "ffmpeg",
    render_mode: str | None = None,
) -> tuple[str, ...]:
    mode = roughcut_render_mode(render_mode)
    if mode in {"copy", "lossless"}:
        return (
            ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            _safe_path(concat_file_path),
            "-map",
            "0",
            "-c",
            "copy",
            *_faststart_args(output_path),
            _safe_path(output_path),
        )
    return (
        ffmpeg_binary,
        "-y",
        *ffmpeg_hwdecode_args(),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        _safe_path(concat_file_path),
        *hevc_encode_args(quality="balanced"),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        *_faststart_args(output_path),
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
    render_mode: str | None = "lossless",
) -> tuple[str, ...]:
    output = _validate_output_path(output_path, [str(input_path)])
    mode = roughcut_render_mode(render_mode)
    encode_args = hevc_encode_args(quality="balanced") if mode == "preview_hevc" else lossless_video_encode_args(output_path)
    return (
        ffmpeg_binary,
        "-y",
        *ffmpeg_hwdecode_args(),
        "-i",
        _safe_path(input_path),
        "-vf",
        f"subtitles='{_subtitle_filter_path(subtitle_path)}'",
        *encode_args,
        *_faststart_args(output_path),
        output,
    )


def build_concat_render_plan(
    edl_segments: Iterable[EDLSegment],
    output_path: str | Path,
    temp_dir: str | Path,
    ffmpeg_binary: str = "ffmpeg",
    render_mode: str | None = None,
) -> RenderCommandPlan:
    """Build a no-execution ffmpeg concat plan for roughcut keep/highlight segments."""
    mode = roughcut_render_mode(render_mode)
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
        if mode == "lossless":
            suffix = Path(output).suffix or ".mkv"
        part_path = temp / f"roughcut_part_{index:04d}{suffix}"
        extract_commands.append(
            build_ffmpeg_extract_command(
                segment,
                part_path,
                ffmpeg_binary=ffmpeg_binary,
                render_mode=mode,
            )
        )

    return RenderCommandPlan(
        temp_dir=str(temp),
        extract_commands=tuple(extract_commands),
        concat_file_path=str(concat_file),
        concat_command=build_ffmpeg_concat_command(concat_file, output, ffmpeg_binary=ffmpeg_binary, render_mode=mode),
        output_path=output,
        render_mode=mode,
        warnings=tuple(warnings),
        segment_manifest=tuple(_render_segment_manifest(segments)),
        stitched_cut_boundaries=tuple(build_stitched_cut_boundaries(segments)),
    )


def _render_segment_manifest(segments: Iterable[EDLSegment]) -> list[dict]:
    return [
        {
            "segment_id": segment.segment_id,
            "chapter_id": segment.chapter_id,
            "action": segment.action,
            "story_role": segment.story_role,
            "source_path": segment.source_path,
            "source_start": segment.source_start,
            "source_end": segment.source_end,
            "timeline_start": segment.timeline_start,
            "timeline_end": segment.timeline_end,
            "clip_index": segment.clip_index,
        }
        for segment in segments
    ]
