# Version: 04.00.10
# Phase: PHASE2
"""Testable planning and progress helpers for the single-file pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable

from core.pipeline.subtitle_parallel_manager import (
    SubtitleParallelIterationPlan as SinglePipelineIterationPlan,
    build_subtitle_parallel_iteration_plan,
    hard_cut_seconds_from_rows,
    normalize_pipeline_rows,
    pipeline_overall_progress_percent,
)


def build_single_pipeline_iteration_plan(
    *,
    target_file: str,
    queue_index: int,
    total_files: int,
    cut_boundary_snapshot: dict | None,
) -> SinglePipelineIterationPlan:
    return build_subtitle_parallel_iteration_plan(
        target_file=target_file,
        queue_index=queue_index,
        total_files=total_files,
        cut_boundary_snapshot=cut_boundary_snapshot,
    )


@dataclass
class SinglePipelineActionSession:
    """Pipeline editor callback state that stays compatible with legacy backend fields."""

    state_ref: list[str] = field(default_factory=lambda: ["wait"])
    final_segments: list[dict] = field(default_factory=list)
    edit_event: threading.Event = field(default_factory=threading.Event)
    start_event: threading.Event = field(default_factory=threading.Event)

    @property
    def action_state(self) -> str:
        return str(self.state_ref[0] or "wait")

    @action_state.setter
    def action_state(self, value: str) -> None:
        self.state_ref[0] = str(value or "wait")

    def callbacks(
        self,
        *,
        start_hook: Callable[[], None] | None = None,
        stop_hook: Callable[[], None] | None = None,
    ) -> tuple[Callable[[list[dict]], None], Callable[[], None], Callable[[], None], Callable[[list[dict]], None]]:
        def on_save(segments):
            self.final_segments = list(segments or [])
            self.action_state = "next"
            self.start_event.set()
            self.edit_event.set()

        def on_start():
            if callable(start_hook):
                start_hook()
            self.action_state = "start"
            self.start_event.set()

        def on_prev():
            self.action_state = "prev"
            self.start_event.set()
            self.edit_event.set()

        def on_exit(segments):
            self.final_segments = list(segments or [])
            self.action_state = "exit"
            if callable(stop_hook):
                stop_hook()
            self.start_event.set()
            self.edit_event.set()

        return on_save, on_start, on_prev, on_exit


class PipelineProgressCoordinator:
    """Small UI-signal adapter for pipeline progress events."""

    def __init__(self, emit: Callable[..., bool]):
        self._emit = emit

    def emit_queue_status(
        self,
        queue_index: int,
        status: str,
        time_txt: str = "",
        codec_txt: str = "",
        duration_txt: str = "",
    ) -> bool:
        return bool(
            self._emit(
                "_sig_update_queue",
                int(queue_index),
                str(status or ""),
                str(time_txt or ""),
                str(codec_txt or ""),
                str(duration_txt or ""),
            )
        )

    def emit_queue_header(
        self,
        current: int,
        total: int,
        pct: int,
        eta_txt: str = "",
    ) -> bool:
        return bool(
            self._emit(
                "_sig_update_queue_header",
                int(current),
                int(total),
                int(pct),
                str(eta_txt or ""),
            )
        )

    def emit_stage(self, queue_index: int, status: str) -> bool:
        text = str(status or "")
        queue_ok = self.emit_queue_status(queue_index, text)
        editor_ok = bool(self._emit("_sig_editor_processing_stage", text))
        return queue_ok or editor_ok

    def emit_queue_item_start(self, queue_index: int, total_files: int) -> bool:
        queue_ok = self.emit_queue_status(queue_index, "⏳ 오디오 추출 중")
        header_ok = self.emit_queue_header(int(queue_index) + 1, total_files, 0, "")
        return queue_ok or header_ok

    def emit_generation_started(self, queue_index: int, expected_time_txt: str) -> bool:
        return self.emit_queue_status(queue_index, "자막 생성 중", expected_time_txt)

    def emit_chunk_status(self, chunk_index: int, chunk_total: int) -> bool:
        return bool(self._emit("_sig_update_status", int(chunk_index), int(chunk_total)))

    def emit_chunk_progress(
        self,
        *,
        queue_index: int,
        total_files: int,
        chunk_index: int,
        chunk_total: int,
    ) -> int:
        self.emit_chunk_status(chunk_index, chunk_total)
        pct = pipeline_overall_progress_percent(
            queue_index=queue_index,
            total_files=total_files,
            chunk_index=chunk_index,
            chunk_total=chunk_total,
        )
        self.emit_queue_header(int(queue_index) + 1, total_files, pct, "")
        return int(pct)

    def emit_generation_completion_ready(self, queue_index: int, reason: str) -> bool:
        self.emit_queue_status(queue_index, "저장 준비 중")
        finalized = bool(self._emit("_sig_finalize_generation_complete", str(reason or "backend_done")))
        return finalized

    def emit_item_error(self, queue_index: int) -> bool:
        return self.emit_queue_status(queue_index, "❌ 오류")


__all__ = [
    "PipelineProgressCoordinator",
    "SinglePipelineActionSession",
    "SinglePipelineIterationPlan",
    "build_single_pipeline_iteration_plan",
    "hard_cut_seconds_from_rows",
    "normalize_pipeline_rows",
    "pipeline_overall_progress_percent",
]
