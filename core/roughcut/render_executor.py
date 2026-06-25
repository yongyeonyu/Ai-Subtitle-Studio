# Version: 03.01.32
# Phase: PHASE2
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.platform_compat import hidden_subprocess_kwargs

from .renderer_skeleton import RenderCommandPlan


@dataclass(frozen=True, slots=True)
class RenderExecutionResult:
    output_path: str
    concat_file_path: str
    executed_commands: tuple[tuple[str, ...], ...]
    return_codes: tuple[int, ...]
    dry_run: bool = False
    segment_manifest: tuple[dict, ...] = ()
    stitched_cut_boundaries: tuple[dict, ...] = ()


def write_concat_file(plan: RenderCommandPlan) -> Path:
    target = Path(plan.concat_file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for command in plan.extract_commands:
        if not command:
            continue
        part_path = str(Path(command[-1]).expanduser().resolve(strict=False)).replace("'", "'\\''")
        lines.append(f"file '{part_path}'")
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def run_render_plan(
    plan: RenderCommandPlan,
    dry_run: bool = False,
    cleanup_temp_parts: bool = True,
    cleanup_concat_file: bool = True,
) -> RenderExecutionResult:
    """Execute an ffmpeg concat plan. Tests and UI can use dry_run to verify paths safely."""
    concat_path = write_concat_file(plan)
    commands = tuple(plan.extract_commands) + (plan.concat_command,)
    if dry_run:
        return RenderExecutionResult(
            output_path=plan.output_path,
            concat_file_path=str(concat_path),
            executed_commands=commands,
            return_codes=tuple(0 for _ in commands),
            dry_run=True,
            segment_manifest=tuple(getattr(plan, "segment_manifest", ()) or ()),
            stitched_cut_boundaries=tuple(getattr(plan, "stitched_cut_boundaries", ()) or ()),
        )

    return_codes: list[int] = []
    try:
        for command in plan.extract_commands:
            completed = subprocess.run(command, check=False, **hidden_subprocess_kwargs(strip_qt=True))
            return_codes.append(completed.returncode)
            if completed.returncode != 0:
                raise RuntimeError(f"ffmpeg extract failed: {completed.returncode}")
        completed = subprocess.run(plan.concat_command, check=False, **hidden_subprocess_kwargs(strip_qt=True))
        return_codes.append(completed.returncode)
        if completed.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {completed.returncode}")
    finally:
        if cleanup_temp_parts:
            for command in plan.extract_commands:
                if command:
                    Path(command[-1]).unlink(missing_ok=True)
        if cleanup_concat_file:
            concat_path.unlink(missing_ok=True)

    return RenderExecutionResult(
        output_path=plan.output_path,
        concat_file_path=str(concat_path),
        executed_commands=commands,
        return_codes=tuple(return_codes),
        dry_run=False,
        segment_manifest=tuple(getattr(plan, "segment_manifest", ()) or ()),
        stitched_cut_boundaries=tuple(getattr(plan, "stitched_cut_boundaries", ()) or ()),
    )
