# Version: 04.00.01
# Phase: MAC_NATIVE_REFACTOR
"""Shared subtitle text cleanup and final output policy.

This module keeps LLM/STT text sanitation out of the large subtitle engine so
generation, project asset export, and SRT save paths can share the same guard.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from core import correction_dictionary_db
from core import native_text_cleanup
from core.runtime.logger import get_logger
from core.text_utils import strip_subtitle_quote_marks

_TS_BRACKET = re.compile(r"\[\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s*\]\s*")
_TS_NO_BRACKET = re.compile(r"^\s*\d{1,3}[:.]\d{1,2}(?:[:.]\d+)?\s+")
_WHISPER_CONTROL_TOKEN = re.compile(r"<\|[^|]{1,80}\|>")
_JUNK_PATTERN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CLEAN_CACHE_MAX = 4096
_CLEAN_CACHE: "OrderedDict[tuple[str, int, str], tuple[str, tuple[tuple[str, str], ...]]]" = OrderedDict()
_CORRECTION_LOG_COUNTS: "OrderedDict[tuple[str, str], int]" = OrderedDict()
_CORRECTION_LOG_CACHE_MAX = 512


def strip_stt_control_tokens(text: str) -> str:
    return _WHISPER_CONTROL_TOKEN.sub(" ", str(text or "")).strip()


def strip_forbidden_sentence_periods(text: str) -> str:
    return str(text or "").replace(".", "")


def strip_forbidden_subtitle_quotes(text: str) -> str:
    # KEEP: user subtitles do not use decorative quote marks.
    # STT raw text, LLM rewrites, and LoRA prompt examples can still surface
    # wrapped "..." / ‘...’ fragments, so the final subtitle contract strips
    # them here for editor/save/render alike while preserving inner apostrophes.
    return strip_subtitle_quote_marks(text)


def normalize_subtitle_text_lines(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(text or "").split("\n")]
    return "\n".join(line for line in lines if line)


def split_visible_len(text: str) -> int:
    return len(strip_stt_control_tokens(text).replace(" ", "").replace("\n", ""))


def _log_applied_corrections(applied_pairs: list[tuple[str, str]] | None) -> None:
    for old, new in list(applied_pairs or []):
        key = (str(old), str(new))
        count = int(_CORRECTION_LOG_COUNTS.get(key, 0) or 0) + 1
        _CORRECTION_LOG_COUNTS[key] = count
        _CORRECTION_LOG_COUNTS.move_to_end(key)
        while len(_CORRECTION_LOG_COUNTS) > _CORRECTION_LOG_CACHE_MAX:
            _CORRECTION_LOG_COUNTS.popitem(last=False)
        if count == 1:
            get_logger().log(f"[정제-교정사전] 적용: '{old}' => '{new}'")
        elif count >= 8 and (count & (count - 1)) == 0:
            get_logger().log(f"[정제-교정사전] 누적적용 {count}회: '{old}' => '{new}'")


def _log_applied_corrections_batch(applied_batches: list[list[tuple[str, str]]] | None) -> None:
    counts: "OrderedDict[tuple[str, str], int]" = OrderedDict()
    for batch in list(applied_batches or []):
        for old, new in list(batch or []):
            key = (str(old), str(new))
            counts[key] = int(counts.get(key, 0) or 0) + 1
    for (old, new), count in counts.items():
        key = (str(old), str(new))
        previous = int(_CORRECTION_LOG_COUNTS.get(key, 0) or 0)
        total = previous + int(count)
        _CORRECTION_LOG_COUNTS[key] = total
        _CORRECTION_LOG_COUNTS.move_to_end(key)
        while len(_CORRECTION_LOG_COUNTS) > _CORRECTION_LOG_CACHE_MAX:
            _CORRECTION_LOG_COUNTS.popitem(last=False)
        if previous == 0:
            if count <= 1:
                get_logger().log(f"[정제-교정사전] 적용: '{old}' => '{new}'")
            else:
                get_logger().log(f"[정제-교정사전] 일괄적용 {count}회: '{old}' => '{new}'")
        elif total >= 8 and (total & (total - 1)) == 0:
            get_logger().log(f"[정제-교정사전] 누적적용 {total}회: '{old}' => '{new}'")


def _prepare_subtitle_text(text: str) -> str:
    original = text
    text = strip_stt_control_tokens(text)
    text = _TS_BRACKET.sub(" ", text)
    text = _TS_NO_BRACKET.sub(" ", text)
    if text != original:
        get_logger().log(f"[정제-시간태그] 삭제: '{str(original)[:15]}' => '{text[:15]}'")
    text = _JUNK_PATTERN.sub("", text)
    text = strip_forbidden_subtitle_quotes(strip_forbidden_sentence_periods(text)).replace("\r", "")
    return normalize_subtitle_text_lines(text)


def _finalize_subtitle_text(text: str) -> str:
    return normalize_subtitle_text_lines(strip_forbidden_subtitle_quotes(strip_forbidden_sentence_periods(text)))


def _multi_speaker_linebreak_allowed(item: dict[str, Any]) -> bool:
    speakers = [
        str(speaker).strip()
        for speaker in list(item.get("speaker_list") or [])
        if str(speaker).strip()
    ]
    return len(set(speakers)) >= 2


def _enforce_linebreak_policy(text: str, item: dict[str, Any]) -> str:
    if "\n" not in str(text or ""):
        return text
    if _multi_speaker_linebreak_allowed(item):
        return text
    return " ".join(
        line.strip()
        for line in str(text or "").splitlines()
        if line.strip()
    )


def _apply_corrections_with_tracking(text: str, corrections: dict | None = None) -> tuple[str, list[tuple[str, str]]]:
    if not corrections or not text:
        return text, []
    if len(corrections) >= correction_dictionary_db.INDEXED_QUERY_MIN_ENTRIES and not correction_dictionary_db.corrections_may_apply(text, corrections):
        return text, []
    native_out = native_text_cleanup.apply_corrections(text, corrections)
    if native_out is not None:
        updated, applied_pairs = native_out
        return str(updated), list(applied_pairs or [])
    applied_pairs: list[tuple[str, str]] = []
    for old, new in corrections.items():
        if old and old in text:
            text = text.replace(old, new)
            applied_pairs.append((str(old), str(new)))
    return text, applied_pairs


def _corrections_cache_token(corrections: dict | None) -> tuple[str, int]:
    if not isinstance(corrections, dict):
        return ("0", 0)
    return native_text_cleanup.correction_index_token(corrections)


def _clean_cache_get(cache_key: tuple[str, int, str]) -> tuple[str, list[tuple[str, str]]] | None:
    cached = _CLEAN_CACHE.get(cache_key)
    if cached is None:
        return None
    _CLEAN_CACHE.move_to_end(cache_key)
    text, pairs = cached
    return text, list(pairs or ())


def _clean_cache_put(cache_key: tuple[str, int, str], text: str, applied_pairs: list[tuple[str, str]]) -> None:
    _CLEAN_CACHE[cache_key] = (str(text), tuple((str(old), str(new)) for old, new in list(applied_pairs or [])))
    _CLEAN_CACHE.move_to_end(cache_key)
    while len(_CLEAN_CACHE) > _CLEAN_CACHE_MAX:
        _CLEAN_CACHE.popitem(last=False)


def clean_subtitle_text(text: str, corrections: dict | None = None) -> str:
    text = _prepare_subtitle_text(text)

    if corrections:
        cache_key = (*_corrections_cache_token(corrections), text)
        cached = _clean_cache_get(cache_key)
        if cached is not None:
            text, applied_pairs = cached
        else:
            text, applied_pairs = _apply_corrections_with_tracking(text, corrections)
            _clean_cache_put(cache_key, text, applied_pairs)
        _log_applied_corrections(applied_pairs)
    return _finalize_subtitle_text(text)


def enforce_final_subtitle_text_policy(
    segments: list[dict[str, Any]],
    corrections: dict | None = None,
) -> list[dict[str, Any]]:
    staged_items: list[dict[str, Any]] = []
    staged_texts: list[str] = []
    for seg in list(segments or []):
        if not isinstance(seg, dict):
            continue
        item = dict(seg)
        text = _prepare_subtitle_text(str(item.get("text", "") or ""))
        staged_items.append(item)
        staged_texts.append(text)

    applied_batches: list[list[tuple[str, str]]] = [[] for _ in range(len(staged_items))]
    if corrections and staged_texts:
        correction_token = _corrections_cache_token(corrections)
        unique_indices: dict[str, int] = {}
        unique_texts: list[str] = []
        row_to_unique: list[int] = []
        for text in staged_texts:
            mapped = unique_indices.get(text)
            if mapped is None:
                mapped = len(unique_texts)
                unique_indices[text] = mapped
                unique_texts.append(text)
            row_to_unique.append(mapped)

        unique_out_texts: list[str] = []
        unique_out_batches: list[list[tuple[str, str]]] = []
        gate_enabled = len(corrections) >= correction_dictionary_db.INDEXED_QUERY_MIN_ENTRIES
        maybe_flags = (
            [correction_dictionary_db.corrections_may_apply(text, corrections) for text in unique_texts]
            if gate_enabled
            else [True] * len(unique_texts)
        )
        native_batch = native_text_cleanup.apply_corrections_batch(unique_texts, corrections)
        use_native_batch = native_batch is not None
        if use_native_batch:
            use_native_batch = all(maybe_flags)
        if use_native_batch:
            unique_out_texts, unique_out_batches = native_batch or ([], [])
            for source_text, updated, applied_pairs in zip(unique_texts, unique_out_texts, unique_out_batches):
                _clean_cache_put((*correction_token, source_text), str(updated), list(applied_pairs or []))
        else:
            for text, maybe_apply in zip(unique_texts, maybe_flags):
                cache_key = (*correction_token, text)
                cached = _clean_cache_get(cache_key)
                if cached is not None:
                    updated, applied_pairs = cached
                elif not maybe_apply:
                    updated, applied_pairs = text, []
                    _clean_cache_put(cache_key, updated, applied_pairs)
                else:
                    updated, applied_pairs = _apply_corrections_with_tracking(text, corrections)
                    _clean_cache_put(cache_key, updated, applied_pairs)
                unique_out_texts.append(updated)
                unique_out_batches.append(applied_pairs)

        staged_texts = [str(unique_out_texts[idx]) for idx in row_to_unique]
        applied_batches = [list(unique_out_batches[idx] or []) for idx in row_to_unique]

    _log_applied_corrections_batch(applied_batches)
    result: list[dict[str, Any]] = []
    for item, text, applied_pairs in zip(staged_items, staged_texts, applied_batches):
        text = _finalize_subtitle_text(text)
        text = _enforce_linebreak_policy(text, item)
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
