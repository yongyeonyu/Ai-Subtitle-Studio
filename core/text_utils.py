"""Shared small text-normalization helpers."""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def compact_text(text: Any) -> str:
    return _WHITESPACE_RE.sub("", str(text or "")).strip().lower()


def line_count(text: Any) -> int:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return max(1, len(lines))
