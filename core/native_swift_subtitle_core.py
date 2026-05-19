from __future__ import annotations

from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.subtitle_core_contract import build_subtitle_core_request, subtitle_core_response_result


def _enabled() -> bool:
    if not IS_MAC:
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_SUBTITLE_CORE")


def run_subtitle_core_operation_via_swift(
    operation: Any,
    payload: dict[str, Any] | None = None,
    *,
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not _enabled():
        return None
    try:
        request = build_subtitle_core_request(
            operation,
            payload=dict(payload or {}),
            settings=dict(settings or {}),
            context=dict(context or {}),
        )
    except ValueError:
        return None
    decoded = request_native_core_task("subtitle_core_plan", request)
    return subtitle_core_response_result(decoded, operation=operation)


__all__ = ["run_subtitle_core_operation_via_swift"]
