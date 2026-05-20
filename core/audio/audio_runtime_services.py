# Version: 04.00.10
# Phase: PHASE2
"""Durable audio runtime service helpers.

Keep worker-count and cleanup policy outside the large media processor mixins
so audio hot paths can share one conservative resource plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import performance as runtime_performance
from core.runtime.multi_process import runtime_parallel_worker_plan


@dataclass(frozen=True)
class AudioRouteWorkerPlan:
    max_workers: int
    scheduler: dict[str, Any]

    @property
    def reductions_label(self) -> str:
        return ",".join(str(item) for item in list(self.scheduler.get("reductions") or []) if item)


@dataclass(frozen=True)
class StageOwnedResourcePolicy:
    pressure_stage: str
    allow_stt_collect_worker_reuse: bool
    keep_stt_worker_warm: bool
    keep_llm_resident: bool
    include_gpu_on_release: bool
    warm_pool_label: str
    reason: str


def _int_setting(settings: dict[str, Any], key: str, fallback: int) -> int:
    try:
        return int(float(settings.get(key, fallback) or fallback))
    except (TypeError, ValueError):
        return fallback


def _float_setting(settings: dict[str, Any], key: str, fallback: float) -> float:
    try:
        value = settings.get(key, fallback)
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_memory_pressure_stage(value: Any) -> str:
    stage = str(value or "").strip().lower()
    return stage if stage in {"warning", "critical"} else "normal"


def memory_pressure_stage_from_snapshot(
    snapshot: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> str:
    settings = dict(settings or {})
    data = dict(snapshot or {})
    stage = normalize_memory_pressure_stage(data.get("memory_pressure_stage") or data.get("pressure_stage"))
    if stage != "normal":
        return stage
    native = data.get("native_memory")
    if isinstance(native, dict):
        stage = normalize_memory_pressure_stage(native.get("pressure_stage") or native.get("memory_pressure_stage"))
        if stage != "normal":
            return stage

    warning_ratio = _float_setting(
        settings,
        "runtime_memory_warning_ratio",
        _float_setting(settings, "macos_memory_warning_ratio", 0.20),
    )
    critical_ratio = _float_setting(
        settings,
        "runtime_memory_critical_ratio",
        _float_setting(settings, "macos_memory_critical_ratio", 0.12),
    )
    warning_reserve_gb = _float_setting(settings, "macos_memory_warning_reserve_gb", 3.0)
    critical_reserve_gb = _float_setting(settings, "macos_memory_critical_reserve_gb", 1.5)
    warning_compressed_ratio = _float_setting(
        settings,
        "runtime_memory_warning_compressed_ratio",
        _float_setting(settings, "macos_memory_warning_compressed_ratio", 0.22),
    )
    critical_compressed_ratio = _float_setting(
        settings,
        "runtime_memory_critical_compressed_ratio",
        _float_setting(settings, "macos_memory_critical_compressed_ratio", 0.30),
    )
    if warning_ratio <= critical_ratio:
        warning_ratio, critical_ratio = critical_ratio, warning_ratio
    if warning_reserve_gb <= critical_reserve_gb:
        warning_reserve_gb, critical_reserve_gb = critical_reserve_gb, warning_reserve_gb
    if warning_compressed_ratio <= critical_compressed_ratio:
        warning_compressed_ratio, critical_compressed_ratio = critical_compressed_ratio, warning_compressed_ratio

    available_ratio = _float_setting(data, "available_memory_ratio", 1.0)
    available_gb = _float_setting(data, "available_memory_bytes", 0.0) / float(1024 ** 3)
    compressed_ratio = _float_setting(data, "compressed_memory_ratio", 0.0)
    if available_ratio <= critical_ratio or (available_gb > 0.0 and available_gb <= critical_reserve_gb):
        return "critical"
    if compressed_ratio >= critical_compressed_ratio:
        return "critical"
    if compressed_ratio >= warning_compressed_ratio:
        return "warning"
    if available_ratio <= warning_ratio or (available_gb > 0.0 and available_gb <= warning_reserve_gb):
        return "warning"
    return "normal"


def current_memory_pressure_stage(settings: dict[str, Any] | None = None) -> str:
    try:
        snapshot = runtime_performance.current_resource_snapshot(dict(settings or {}))
    except Exception:
        return "normal"
    return memory_pressure_stage_from_snapshot(snapshot if isinstance(snapshot, dict) else {}, settings)


def stage_owned_resource_policy(
    settings: dict[str, Any] | None = None,
    *,
    pressure_stage: str | None = None,
) -> StageOwnedResourcePolicy:
    """Decide model residency from one pressure policy shared by STT and LLM."""

    stage = normalize_memory_pressure_stage(pressure_stage) if pressure_stage else current_memory_pressure_stage(settings)
    if stage == "critical":
        # Critical pressure is where warm workers become a repeated-run slowdown
        # source, so release model residency at the stage boundary.
        return StageOwnedResourcePolicy(
            pressure_stage="critical",
            allow_stt_collect_worker_reuse=False,
            keep_stt_worker_warm=False,
            keep_llm_resident=False,
            include_gpu_on_release=True,
            warm_pool_label="release",
            reason="critical_memory_pressure",
        )
    if stage == "warning":
        return StageOwnedResourcePolicy(
            pressure_stage="warning",
            allow_stt_collect_worker_reuse=True,
            keep_stt_worker_warm=True,
            keep_llm_resident=True,
            include_gpu_on_release=False,
            warm_pool_label="reduced",
            reason="warning_memory_pressure",
        )
    return StageOwnedResourcePolicy(
        pressure_stage="normal",
        allow_stt_collect_worker_reuse=True,
        keep_stt_worker_warm=True,
        keep_llm_resident=True,
        include_gpu_on_release=False,
        warm_pool_label="warm",
        reason="normal_memory_pressure",
    )


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
    "StageOwnedResourcePolicy",
    "current_memory_pressure_stage",
    "memory_pressure_stage_from_snapshot",
    "normalize_memory_pressure_stage",
    "plan_audio_route_workers",
    "stage_owned_resource_policy",
]
