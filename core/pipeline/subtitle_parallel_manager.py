"""Pure subtitle pipeline planning contracts for queue and stage orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


STAGE_DAG_SCHEMA = "ai_subtitle_studio.subtitle_stage_dag.v1"


def _list_rows(rows: Iterable | None) -> list:
    return [] if rows is None else list(rows)


def normalize_pipeline_rows(rows: Iterable | None) -> list[dict]:
    return [dict(row) for row in _list_rows(rows) if isinstance(row, dict)]


def hard_cut_seconds_from_rows(rows: Iterable | None) -> list[float]:
    seconds: set[float] = set()
    for row in _list_rows(rows):
        try:
            if isinstance(row, dict):
                sec = float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
            else:
                sec = float(row)
        except (TypeError, ValueError):
            continue
        if sec > 0.0:
            seconds.add(round(float(sec), 3))
    return sorted(seconds)


def safe_pipeline_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def pipeline_overall_progress_percent(
    *,
    queue_index: int,
    total_files: int,
    chunk_index: int,
    chunk_total: int,
) -> int:
    total = max(1, safe_pipeline_int(total_files, 1))
    index = max(0, safe_pipeline_int(queue_index))
    current = max(0, safe_pipeline_int(chunk_index))
    chunk_count = max(0, safe_pipeline_int(chunk_total))
    if chunk_count > 0:
        return int(((index + (current / chunk_count)) / total) * 100)
    return int((index / total) * 100)


@dataclass(frozen=True)
class SubtitleStageNode:
    stage: str
    depends_on: tuple[str, ...] = ()
    lane: str = "serial"


DEFAULT_SUBTITLE_STAGE_DAG: tuple[SubtitleStageNode, ...] = (
    SubtitleStageNode("audio_extract"),
    SubtitleStageNode("cut_boundary", ("audio_extract",), "cpu"),
    SubtitleStageNode("stt", ("audio_extract", "cut_boundary"), "ane_gpu"),
    SubtitleStageNode("stt_preview", ("stt",), "cpu"),
    SubtitleStageNode("subtitle_llm", ("stt",), "llm"),
    SubtitleStageNode("subtitle_timing", ("subtitle_llm",), "cpu"),
    SubtitleStageNode("subtitle_segments", ("subtitle_timing",), "cpu"),
    SubtitleStageNode("editor_feed", ("subtitle_segments",), "ui"),
)


def build_subtitle_stage_dag(enabled_stages: Iterable[str] | None = None) -> tuple[SubtitleStageNode, ...]:
    enabled = None
    if enabled_stages is not None:
        enabled = {str(stage or "").strip() for stage in enabled_stages if str(stage or "").strip()}
    if enabled is None:
        return DEFAULT_SUBTITLE_STAGE_DAG
    return tuple(node for node in DEFAULT_SUBTITLE_STAGE_DAG if node.stage in enabled)


@dataclass(frozen=True)
class SubtitleParallelIterationPlan:
    target_file: str
    queue_index: int
    total_files: int
    cut_boundaries: tuple[dict, ...]
    provisional_cut_boundaries: tuple[dict, ...]
    hard_cut_boundaries: tuple[float, ...]
    stage_schema: str = STAGE_DAG_SCHEMA
    stage_dag: tuple[SubtitleStageNode, ...] = DEFAULT_SUBTITLE_STAGE_DAG


def build_subtitle_parallel_iteration_plan(
    *,
    target_file: str,
    queue_index: int,
    total_files: int,
    cut_boundary_snapshot: dict | None,
) -> SubtitleParallelIterationPlan:
    snapshot = dict(cut_boundary_snapshot or {})
    cut_rows = normalize_pipeline_rows(snapshot.get("cut_boundaries"))
    provisional_rows = normalize_pipeline_rows(snapshot.get("provisional_cut_boundaries"))
    return SubtitleParallelIterationPlan(
        target_file=str(target_file or ""),
        queue_index=max(0, safe_pipeline_int(queue_index)),
        total_files=max(0, safe_pipeline_int(total_files)),
        cut_boundaries=tuple(cut_rows),
        provisional_cut_boundaries=tuple(provisional_rows),
        hard_cut_boundaries=tuple(hard_cut_seconds_from_rows(snapshot.get("cut_boundaries"))),
    )


__all__ = [
    "DEFAULT_SUBTITLE_STAGE_DAG",
    "STAGE_DAG_SCHEMA",
    "SubtitleParallelIterationPlan",
    "SubtitleStageNode",
    "build_subtitle_parallel_iteration_plan",
    "build_subtitle_stage_dag",
    "hard_cut_seconds_from_rows",
    "normalize_pipeline_rows",
    "pipeline_overall_progress_percent",
    "safe_pipeline_int",
]
