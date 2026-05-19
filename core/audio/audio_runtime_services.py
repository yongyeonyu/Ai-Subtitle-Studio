# Version: 04.00.10
# Phase: PHASE2
"""Durable audio runtime service helpers.

Keep worker-count and cleanup policy outside the large media processor mixins
so audio hot paths can share one conservative resource plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.multi_process import runtime_parallel_worker_plan


@dataclass(frozen=True)
class AudioRouteWorkerPlan:
    max_workers: int
    scheduler: dict[str, Any]

    @property
    def reductions_label(self) -> str:
        return ",".join(str(item) for item in list(self.scheduler.get("reductions") or []) if item)


def _int_setting(settings: dict[str, Any], key: str, fallback: int) -> int:
    try:
        return int(float(settings.get(key, fallback) or fallback))
    except (TypeError, ValueError):
        return fallback


def plan_audio_route_workers(
    *,
    settings: dict[str, Any] | None,
    requested: int | None,
    workload: int,
) -> AudioRouteWorkerPlan:
    """Plan audio-route workers with a single shared cap policy."""

    settings = dict(settings or {})
    workload = max(1, int(workload or 1))
    max_workers, scheduler = runtime_parallel_worker_plan(
        settings=settings,
        task="io",
        requested=requested,
        workload=workload,
        minimum=1,
        maximum=workload,
        reserve_task="io",
    )
    scheduler = dict(scheduler or {})
    route_worker_cap = _int_setting(settings, "audio_chunk_route_max_workers", 2)
    if route_worker_cap > 0 and max_workers > route_worker_cap:
        max_workers = max(1, min(int(max_workers), route_worker_cap))
        reductions = list(scheduler.get("reductions") or [])
        reductions.append("audio_route_cap")
        scheduler["reductions"] = reductions
        scheduler["audio_chunk_route_max_workers"] = int(route_worker_cap)
    return AudioRouteWorkerPlan(max_workers=max(1, int(max_workers)), scheduler=scheduler)


__all__ = [
    "AudioRouteWorkerPlan",
    "plan_audio_route_workers",
]
