"""Shared small text-normalization helpers."""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")
_DOUBLE_QUOTE_RE = re.compile(r'["“”]+')
_EDGE_SINGLE_QUOTE_RE = re.compile(r"(?<![A-Za-z0-9])['‘’]+|['‘’]+(?![A-Za-z0-9])")


def clean_text(text: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(text or "")).strip()


def compact_text(text: Any) -> str:
    return _WHITESPACE_RE.sub("", str(text or "")).strip().lower()


def strip_subtitle_quote_marks(text: Any) -> str:
    value = str(text or "")
    value = _DOUBLE_QUOTE_RE.sub("", value)
    return _EDGE_SINGLE_QUOTE_RE.sub("", value)


def line_count(text: Any) -> int:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    return max(1, len(lines))
