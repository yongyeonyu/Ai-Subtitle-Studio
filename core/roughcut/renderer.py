# Version: 03.01.26
# Phase: PHASE2
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.platform_compat import ffmpeg_binary

from .models import EDLSegment
from .render_executor import RenderExecutionResult, run_render_plan
from .renderer_skeleton import build_concat_render_plan


def _edl_segment_from_any(item: EDLSegment | dict[str, Any], fallback_source: str) -> EDLSegment | None:
    if isinstance(item, EDLSegment):
        source_path = item.source_path or fallback_source
        if source_path == item.source_path:
            return item
        return EDLSegment(
            source_path=source_path,
            segment_id=item.segment_id,
            source_start=item.source_start,
            source_end=item.source_end,
            output_start=item.output_start,
            output_end=item.output_end,
            action=item.action,
            chapter_id=item.chapter_id,
            story_role=item.story_role,
            reason=item.reason,
            timeline_start=item.timeline_start,
            timeline_end=item.timeline_end,
            clip_index=item.clip_index,
        )
    if not isinstance(item, dict):
        return None
    source_path = str(item.get("source_path") or fallback_source or "")
    if not source_path:
        return None
    source_start = float(item.get("source_start", item.get("start", 0.0)) or 0.0)
    source_end = float(item.get("source_end", item.get("end", source_start)) or source_start)
    return EDLSegment(
        source_path=source_path,
        segment_id=str(item.get("segment_id") or item.get("chapter_id") or "segment"),
        source_start=source_start,
        source_end=max(source_start, source_end),
        output_start=float(item.get("output_start", 0.0) or 0.0),
        output_end=float(item.get("output_end", max(0.0, source_end - source_start)) or 0.0),
        action=str(item.get("action") or "keep"),
        chapter_id=item.get("chapter_id"),
        story_role=str(item.get("story_role") or ""),
        reason=str(item.get("reason") or ""),
        timeline_start=item.get("timeline_start"),
        timeline_end=item.get("timeline_end"),
        clip_index=item.get("clip_index"),
    )


def render_from_edl(
    input_path: str,
    edl: Iterable[EDLSegment | dict[str, Any]],
    output_path: str,
    temp_dir: str,
    *,
    dry_run: bool = False,
    ffmpeg_path: str | None = None,
    render_mode: str | None = None,
) -> RenderExecutionResult:
    """Render a roughcut from EDL data through the existing concat plan."""
    source = str(Path(input_path).expanduser()) if input_path else ""
    segments = [
        segment
        for segment in (_edl_segment_from_any(item, source) for item in edl or ())
        if segment is not None and segment.source_end > segment.source_start
    ]
    if not segments:
        raise ValueError("edl must contain at least one renderable segment")
    binary = ffmpeg_path or ffmpeg_binary()
    plan = build_concat_render_plan(
        segments,
        output_path=output_path,
        temp_dir=temp_dir,
        ffmpeg_binary=binary,
        render_mode=render_mode,
    )
    return run_render_plan(plan, dry_run=dry_run)


__all__ = ["render_from_edl"]
