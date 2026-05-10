# Version: 04.00.01
# Phase: MAC_NATIVE_REFACTOR
"""Shared subtitle text cleanup and final output policy.

This module keeps LLM/STT text sanitation out of the large subtitle engine so
generation, project asset export, and SRT save paths can share the same guard.
"""

from __future__ import annotations

import re
from typing import Any

from core.runtime.logger import get_logger

_TS_BRACKET = re.compile(r"\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]\s*")
_TS_NO_BRACKET = re.compile(r"^\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s+")
_WHISPER_CONTROL_TOKEN = re.compile(r"<\|[^|]{1,80}\|>")
_JUNK_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def strip_stt_control_tokens(text: str) -> str:
    return _WHISPER_CONTROL_TOKEN.sub(" ", str(text or "")).strip()


def strip_forbidden_sentence_periods(text: str) -> str:
    return str(text or "").replace(".", "")


def normalize_subtitle_text_lines(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(text or "").split("\n")]
    return "\n".join(line for line in lines if line)


def split_visible_len(text: str) -> int:
    return len(strip_stt_control_tokens(text).replace(" ", "").replace("\n", ""))


def clean_subtitle_text(text: str, corrections: dict | None = None) -> str:
    original = text
    text = strip_stt_control_tokens(text)
    text = _TS_BRACKET.sub(" ", text)
    text = _TS_NO_BRACKET.sub(" ", text)

    if text != original:
        get_logger().log(f"[정제-시간태그] 삭제: '{str(original)[:15]}' => '{text[:15]}'")

    text = _JUNK_PATTERN.sub("", text)
    text = strip_forbidden_sentence_periods(text).replace("\r", "")
    text = normalize_subtitle_text_lines(text)

    if corrections:
        for old, new in corrections.items():
            if old and old in text:
                text = text.replace(old, new)
                get_logger().log(f"[정제-교정사전] 적용: '{old}' => '{new}'")
    return normalize_subtitle_text_lines(strip_forbidden_sentence_periods(text))


def enforce_final_subtitle_text_policy(
    segments: list[dict[str, Any]],
    corrections: dict | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        item = dict(seg)
        text = clean_subtitle_text(str(item.get("text", "") or ""), corrections)
        if text:
            item["text"] = text
            result.append(item)
        elif item.get("is_gap") or item.get("gap_type"):
            item["text"] = text
            result.append(item)
    return result


__all__ = [
    "clean_subtitle_text",
    "enforce_final_subtitle_text_policy",
    "normalize_subtitle_text_lines",
    "split_visible_len",
    "strip_forbidden_sentence_periods",
    "strip_stt_control_tokens",
]
