from __future__ import annotations

from typing import Any

from core.native_swift_subtitle_core import run_subtitle_core_operation_via_swift


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
    return native


__all__ = ["plan_subtitle_resource_via_swift"]
