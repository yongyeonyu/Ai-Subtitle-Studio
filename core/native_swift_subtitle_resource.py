from __future__ import annotations

from typing import Any

from core.runtime.hardware_profile import hardware_profile
from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


def _default_topology() -> dict[str, Any]:
    try:
        profile = dict(hardware_profile() or {})
    except Exception:
        return {}
    keys = (
        "logical_cores",
        "physical_cores",
        "performance_cores",
        "efficiency_cores",
        "gpu_cores",
        "neural_engine_cores",
        "memory_bytes",
    )
    return {key: int(profile.get(key, 0) or 0) for key in keys if int(profile.get(key, 0) or 0) > 0 or key == "efficiency_cores"}


def _cpp_resource_summary(swift_summary: dict[str, Any]) -> dict[str, Any] | None:
    routing = swift_summary.get("routing")
    if not isinstance(routing, list) or not routing:
        return None
    rows: list[dict[str, Any]] = []
    for row in routing:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "task": row.get("task"),
                "accelerator": {
                    "policy": row.get("policy"),
                    "gpu_lanes": row.get("gpu_lanes"),
                    "ane_lanes": row.get("ane_lanes"),
                },
            }
        )
    if not rows:
        return None
    try:
        from core.native_subtitle_resource import resource_lane_summary

        return resource_lane_summary(
            rows,
            gpu_lane_capacity=int(swift_summary.get("gpu_lane_capacity", 0) or 0),
            ane_model_lane_capacity=int(swift_summary.get("ane_model_lane_capacity", 0) or 0),
        )
    except Exception:
        return None


def _attach_cpp_parity(native: dict[str, Any]) -> dict[str, Any]:
    summary = native.get("accelerator_summary")
    if not isinstance(summary, dict):
        return native
    cpp = _cpp_resource_summary(summary)
    if not isinstance(cpp, dict):
        return native
    comparable_keys = (
        "gpu_task_count",
        "ane_task_count",
        "metal_task_count",
        "gpu_lanes_total",
        "ane_lanes_total",
        "max_gpu_lanes",
        "max_ane_lanes",
        "gpu_lane_capacity",
        "ane_model_lane_capacity",
        "gpu_lane_peak_ratio",
        "ane_model_lane_peak_ratio",
        "full_gpu_lane_task_count",
        "full_ane_model_lane_task_count",
        "gpu_lane_peak_saturated",
        "ane_model_lane_peak_saturated",
        "metal_claims_ane",
    )
    summary["cpp_backend"] = str(cpp.get("native_backend") or "cpp")
    summary["cpp_parity"] = all(summary.get(key) == cpp.get(key) for key in comparable_keys)
    summary["cpp_summary"] = {key: cpp.get(key) for key in comparable_keys}
    return native


def plan_subtitle_resource_via_swift(
    *,
    settings: dict[str, Any] | None = None,
    active_labels: list[str] | None = None,
    topology: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
    previous_allocation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "settings": dict(settings or {}),
        "active_labels": list(active_labels or ["pipeline", "stt", "subtitle_optimize"]),
    }
    if topology:
        payload["topology"] = dict(topology)
    else:
        resolved_topology = _default_topology()
        if resolved_topology:
            payload["topology"] = resolved_topology
    if memory:
        payload["memory"] = dict(memory)
    if previous_allocation:
        payload["previous_allocation"] = dict(previous_allocation)
    native = run_subtitle_core_operation_via_swift(
        "subtitle_resource_plan",
        payload,
        settings=settings,
        context={"bridge": "native_swift_subtitle_resource"},
    )
    if not isinstance(native, dict):
        return None
    if str(native.get("schema") or "") != "ai_subtitle_studio.subtitle_resource.plan.v1":
        return None
    return _attach_cpp_parity(native)


__all__ = ["plan_subtitle_resource_via_swift"]
