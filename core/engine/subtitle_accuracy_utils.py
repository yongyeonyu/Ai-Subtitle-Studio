"""Shared small helpers for subtitle accuracy scoring."""

from __future__ import annotations

import re
from typing import Any


def safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "off", "no", "n", "끔", "아니오"}
    return bool(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(round(float(value)))
    except Exception:
        return int(default)


def compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def line_count(text: Any) -> int:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return max(1, len(lines))
