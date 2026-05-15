"""Shared small helpers for subtitle accuracy scoring."""

from __future__ import annotations

from typing import Any

from core.coerce import safe_float as _shared_safe_float, safe_round_int as _shared_safe_int
from core.text_utils import (
    clean_text as _shared_clean_text,
    compact_text as _shared_compact_text,
    line_count as _shared_line_count,
)


def safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "n", "끔", "아니오"}
    return bool(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    return float(_shared_safe_float(value, default))


def safe_int(value: Any, default: int = 0) -> int:
    return int(_shared_safe_int(value, default))


def compact_len(text: Any) -> int:
    return len(_shared_compact_text(text))


def compact_text(text: Any) -> str:
    return _shared_compact_text(text)


def clean_text(text: Any) -> str:
    return _shared_clean_text(text)


def line_count(text: Any) -> int:
    return _shared_line_count(text)
