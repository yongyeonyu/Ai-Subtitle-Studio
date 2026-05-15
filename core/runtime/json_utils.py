"""Shared helpers for JSON-safe payload shaping."""

from __future__ import annotations

from typing import Any


def json_safe(value: Any, *, max_depth: int = 8) -> Any:
    if max_depth <= 0:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): json_safe(item, max_depth=max_depth - 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item, max_depth=max_depth - 1) for item in value]
    return str(value)
