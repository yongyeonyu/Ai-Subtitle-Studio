from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SUBTITLE_CORE_REQUEST_SCHEMA = "ai_subtitle_studio.subtitle_core.request.v1"
SUBTITLE_CORE_RESPONSE_SCHEMA = "ai_subtitle_studio.subtitle_core.response.v1"
SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN = "common_split_plan"
SUBTITLE_CORE_SUPPORTED_OPERATIONS = frozenset({SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN})

_OPERATION_ALIASES = {
    "common-split-plan": SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
    "common_split": SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
    "common_split_plan": SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN,
}


def _copy_mapping(data: Mapping[str, Any] | None) -> dict[str, Any]:
    return {str(key): value for key, value in dict(data or {}).items()}


def normalize_subtitle_core_operation(value: Any) -> str:
    key = str(value or "").strip().lower()
    return _OPERATION_ALIASES.get(key, key)


def build_subtitle_core_request(
    operation: Any,
    *,
    payload: Mapping[str, Any] | None = None,
    settings: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_subtitle_core_operation(operation)
    if normalized not in SUBTITLE_CORE_SUPPORTED_OPERATIONS:
        supported = ", ".join(sorted(SUBTITLE_CORE_SUPPORTED_OPERATIONS))
        raise ValueError(f"Unsupported subtitle core operation: {operation!r}. Supported: {supported}")
    request = {
        "schema": SUBTITLE_CORE_REQUEST_SCHEMA,
        "operation": normalized,
        "payload": _copy_mapping(payload),
    }
    if settings:
        request["settings"] = _copy_mapping(settings)
    if context:
        request["context"] = _copy_mapping(context)
    return request


def is_subtitle_core_response(response: Any, *, operation: Any | None = None) -> bool:
    if not isinstance(response, dict):
        return False
    if str(response.get("schema") or "").strip() != SUBTITLE_CORE_RESPONSE_SCHEMA:
        return False
    if operation is None:
        return True
    expected = normalize_subtitle_core_operation(operation)
    return str(response.get("operation") or "").strip().lower() == expected


def subtitle_core_response_result(
    response: Any,
    *,
    operation: Any | None = None,
) -> dict[str, Any] | None:
    if not is_subtitle_core_response(response, operation=operation):
        return None
    result = response.get("result")
    return dict(result) if isinstance(result, dict) else None


__all__ = [
    "SUBTITLE_CORE_OPERATION_COMMON_SPLIT_PLAN",
    "SUBTITLE_CORE_REQUEST_SCHEMA",
    "SUBTITLE_CORE_RESPONSE_SCHEMA",
    "SUBTITLE_CORE_SUPPORTED_OPERATIONS",
    "build_subtitle_core_request",
    "is_subtitle_core_response",
    "normalize_subtitle_core_operation",
    "subtitle_core_response_result",
]
