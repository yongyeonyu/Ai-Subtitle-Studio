# Version: 03.01.25
# Phase: PHASE2
"""Candidate generation surface for subtitle quality review."""

from __future__ import annotations

import re
from typing import Any

from .correction_memory import apply_correction_memory, search_correction_memory
from .wrong_answer_memory import search_wrong_answer_memory


def _line_id(segment: dict[str, Any]) -> int:
    try:
        return int(segment.get("segment_index", segment.get("line", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _compact(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _candidate(candidate_id: str, segment: dict[str, Any], source: str, reason: str, *, score_bonus: float = 0.0, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "segment_index": _line_id(segment),
        "segment": dict(segment),
        "text": str(segment.get("text", "") or ""),
        "start": float(segment.get("start", 0.0) or 0.0),
        "end": float(segment.get("end", segment.get("start", 0.0)) or 0.0),
        "source": source,
        "reason": reason,
        "score_bonus": float(score_bonus or 0.0),
        "metadata": dict(metadata or {}),
    }


def _remove_wrong_phrases(text: str, wrong_items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    out = str(text or "")
    applied: list[dict[str, Any]] = []
    for item in sorted(wrong_items, key=lambda x: len(str(x.get("phrase", "") or "")), reverse=True):
        phrase = str(item.get("phrase", "") or "")
        if phrase and phrase in out:
            out = out.replace(phrase, "").strip()
            applied.append(dict(item))
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, applied


def generate_quality_candidates(
    segment: dict[str, Any],
    *,
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = settings or {}
    context = context or {}
    base = dict(segment or {})
    candidates: list[dict[str, Any]] = [_candidate("existing", base, "existing", "기존 자막 유지")]
    text = str(base.get("text", "") or "")

    if settings.get("correction_memory_enabled", True):
        memory_path = context.get("correction_memory_path")
        memory_items = search_correction_memory(text, path=memory_path)
        corrected, applied = apply_correction_memory(text, memory_items)
        if applied and _compact(corrected) != _compact(text):
            item = dict(base)
            item["text"] = corrected
            candidates.append(
                _candidate(
                    "correction_memory",
                    item,
                    "correction_memory",
                    "사용자 교정 memory 적용",
                    score_bonus=8.0,
                    metadata={"memory_items": applied},
                )
            )

    if settings.get("wrong_answer_memory_enabled", True):
        wrong_path = context.get("wrong_answer_memory_path")
        wrong_items = search_wrong_answer_memory(text, path=wrong_path)
        cleaned, applied_wrong = _remove_wrong_phrases(text, wrong_items)
        if applied_wrong and cleaned and _compact(cleaned) != _compact(text):
            item = dict(base)
            item["text"] = cleaned
            candidates.append(
                _candidate(
                    "wrong_answer_memory_remove",
                    item,
                    "wrong_answer_memory",
                    "오답 memory phrase 제거",
                    score_bonus=6.0,
                    metadata={"wrong_answer_items": applied_wrong},
                )
            )

    stripped = re.sub(r"\s+", " ", text).strip()
    if stripped and stripped != text:
        item = dict(base)
        item["text"] = stripped
        candidates.append(_candidate("spacing_normalized", item, "normalizer", "공백 정규화", score_bonus=2.0))

    return candidates


__all__ = ["generate_quality_candidates"]
