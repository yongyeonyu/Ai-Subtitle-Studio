# Version: 03.24.01
# Phase: STT_MODE_DESKTOP_WITH_IPAD_COMPAT
"""Protected-term and light text quality helpers for STT Mode."""
from __future__ import annotations

import re
from typing import Any, Iterable


_SPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"([.!?。！？…]+|[。！？])")


def normalize_text(text: Any) -> str:
    return _SPACE_RE.sub(" ", str(text or "").replace("\u2028", " ")).strip()


def normalize_protected_terms(*sources: Any) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for source in sources:
        values: Iterable[Any]
        if isinstance(source, dict):
            values = source.get("protected_terms") or source.get("terms") or []
        elif isinstance(source, (list, tuple, set)):
            values = source
        else:
            values = [source]
        for value in values:
            term = normalize_text(value)
            if term and term not in seen:
                seen.add(term)
                terms.append(term)
    terms.sort(key=len, reverse=True)
    return terms


def _mask_terms(text: str, terms: list[str]) -> tuple[str, dict[str, str]]:
    masked = text
    table: dict[str, str] = {}
    for idx, term in enumerate(terms):
        if not term or term not in masked:
            continue
        token = f"__STTTERM{idx:04d}__"
        masked = masked.replace(term, token)
        table[token] = term
    return masked, table


def _unmask_terms(text: str, table: dict[str, str]) -> str:
    out = text
    for token, term in table.items():
        out = out.replace(token, term)
    return out


def split_sentences(text: Any, *, protected_terms: list[str] | None = None) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    masked, table = _mask_terms(normalized, normalize_protected_terms(protected_terms or []))
    parts = _SENTENCE_SPLIT_RE.split(masked)
    sentences: list[str] = []
    current = ""
    for part in parts:
        if not part:
            continue
        current += part
        if _SENTENCE_SPLIT_RE.fullmatch(part):
            restored = normalize_text(_unmask_terms(current, table))
            if restored:
                sentences.append(restored)
            current = ""
    if current.strip():
        sentences.append(normalize_text(_unmask_terms(current, table)))
    return sentences or [normalized]


def split_text_chunks(
    text: Any,
    *,
    target_chars: int = 24,
    protected_terms: list[str] | None = None,
) -> list[str]:
    """Split text into subtitle-sized chunks without splitting protected terms when possible."""
    normalized = normalize_text(text)
    if not normalized:
        return []
    target = max(6, int(target_chars or 24))
    terms = normalize_protected_terms(protected_terms or [])
    chunks: list[str] = []
    for sentence in split_sentences(normalized, protected_terms=terms):
        if len(sentence) <= target * 1.25:
            chunks.append(sentence)
            continue
        masked, table = _mask_terms(sentence, terms)
        tokens = masked.split(" ")
        if len(tokens) <= 1:
            # Korean often has no spaces. Prefer nearby particles/endings before hard length cuts.
            pieces = re.split(r"(?<=[은는이가을를에에서으로와과고다요죠까])", masked)
            tokens = [piece for piece in pieces if piece]
        current = ""
        for token in tokens:
            candidate = normalize_text(f"{current} {token}" if current else token)
            if current and len(_unmask_terms(candidate, table)) > target:
                restored = normalize_text(_unmask_terms(current, table))
                if restored:
                    chunks.append(restored)
                current = token
            else:
                current = candidate
        restored = normalize_text(_unmask_terms(current, table))
        if restored:
            chunks.append(restored)
    return [chunk for chunk in chunks if chunk]


def wrap_subtitle_lines(
    text: Any,
    *,
    target_chars_per_line: int = 12,
    max_lines: int = 2,
    protected_terms: list[str] | None = None,
) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    max_lines = max(1, int(max_lines or 1))
    target = max(6, int(target_chars_per_line or 12))
    if max_lines == 1 or len(normalized) <= target:
        return normalized
    chunks = split_text_chunks(
        normalized,
        target_chars=max(target, int(len(normalized) / max_lines + 0.5)),
        protected_terms=protected_terms,
    )
    if len(chunks) <= max_lines:
        return "\n".join(chunks)
    merged: list[str] = []
    for chunk in chunks:
        if len(merged) < max_lines:
            merged.append(chunk)
        else:
            merged[-1] = normalize_text(f"{merged[-1]} {chunk}")
    return "\n".join(merged)


def subtitle_line_violations(
    text: Any,
    *,
    max_lines: int = 2,
    max_chars_per_line: int = 18,
) -> list[str]:
    lines = [line for line in str(text or "").replace("\u2028", "\n").splitlines() if line.strip()]
    violations: list[str] = []
    if len(lines) > max(1, int(max_lines or 1)):
        violations.append("too_many_lines")
    if any(len(line.strip()) > max_chars_per_line for line in lines):
        violations.append("line_too_long")
    return violations


__all__ = [
    "normalize_protected_terms",
    "normalize_text",
    "split_sentences",
    "split_text_chunks",
    "subtitle_line_violations",
    "wrap_subtitle_lines",
]
