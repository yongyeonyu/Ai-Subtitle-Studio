# Version: 04.00.10
# Phase: PHASE2
"""Testable planning and progress helpers for the single-file pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable


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


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


@dataclass(frozen=True)
class SinglePipelineIterationPlan:
    target_file: str
    queue_index: int
    total_files: int
    cut_boundaries: tuple[dict, ...]
    provisional_cut_boundaries: tuple[dict, ...]
    hard_cut_boundaries: tuple[float, ...]


def build_single_pipeline_iteration_plan(
    *,
    target_file: str,
    queue_index: int,
    total_files: int,
    cut_boundary_snapshot: dict | None,
) -> SinglePipelineIterationPlan:
    snapshot = dict(cut_boundary_snapshot or {})
    cut_rows = normalize_pipeline_rows(snapshot.get("cut_boundaries"))
    provisional_rows = normalize_pipeline_rows(snapshot.get("provisional_cut_boundaries"))
    return SinglePipelineIterationPlan(
        target_file=str(target_file or ""),
        queue_index=max(0, _safe_int(queue_index)),
        total_files=max(0, _safe_int(total_files)),
        cut_boundaries=tuple(cut_rows),
        provisional_cut_boundaries=tuple(provisional_rows),
        hard_cut_boundaries=tuple(hard_cut_seconds_from_rows(snapshot.get("cut_boundaries"))),
    )


class PipelineProgressCoordinator:
    """Small UI-signal adapter for pipeline progress events."""

    def __init__(self, emit: Callable[..., bool]):
        self._emit = emit

    def emit_stage(self, queue_index: int, status: str) -> bool:
        text = str(status or "")
        queue_ok = bool(self._emit("_sig_update_queue", queue_index, text, "", "", ""))
        editor_ok = bool(self._emit("_sig_editor_processing_stage", text))
        return queue_ok or editor_ok


__all__ = [
    "PipelineProgressCoordinator",
    "SinglePipelineIterationPlan",
    "build_single_pipeline_iteration_plan",
    "hard_cut_seconds_from_rows",
    "normalize_pipeline_rows",
]
