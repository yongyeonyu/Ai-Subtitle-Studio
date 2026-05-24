# Version: 03.01.25
# Phase: PHASE2
"""Candidate generation surface for subtitle quality review."""

from __future__ import annotations

from typing import Any

from core.engine.subtitle_dictionary import (
    build_subtitle_dictionary_lookup_request,
    build_subtitle_dictionary_text_update,
    compact_subtitle_dictionary_text,
    remove_subtitle_dictionary_wrong_phrases,
)

from .correction_memory import apply_correction_memory, search_correction_memory
from .wrong_answer_memory import search_wrong_answer_memory


def _line_id(segment: dict[str, Any]) -> int:
    try:
        return int(segment.get("segment_index", segment.get("line", 0)) or 0)
    except (TypeError, ValueError):
        return 0


def _compact(text: Any) -> str:
    return compact_subtitle_dictionary_text(text)


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
    dictionary_request = build_subtitle_dictionary_lookup_request(
        text,
        settings=settings,
        context=context,
    )

    if dictionary_request.correction_enabled:
        memory_items = search_correction_memory(
            dictionary_request.text,
            limit=dictionary_request.limit,
            min_confidence=dictionary_request.min_confidence,
            path=dictionary_request.correction_memory_path or None,
        )
        corrected, applied = apply_correction_memory(text, memory_items)
        update = build_subtitle_dictionary_text_update(
            source="correction_memory",
            before_text=text,
            after_text=corrected,
            applied_items=applied,
        )
        if applied and update.changed:
            item = dict(base)
            item["text"] = corrected
            candidates.append(
                _candidate(
                    "correction_memory",
                    item,
                    "correction_memory",
                    "사용자 교정 memory 적용",
                    score_bonus=8.0,
                    metadata={"memory_items": applied, "dictionary_update": update.to_dict()},
                )
            )

    if dictionary_request.wrong_answer_enabled:
        wrong_items = search_wrong_answer_memory(
            dictionary_request.text,
            limit=dictionary_request.limit,
            path=dictionary_request.wrong_answer_memory_path or None,
        )
        cleaned, applied_wrong = remove_subtitle_dictionary_wrong_phrases(text, wrong_items)
        update = build_subtitle_dictionary_text_update(
            source="wrong_answer_memory",
            before_text=text,
            after_text=cleaned,
            applied_items=applied_wrong,
        )
        if applied_wrong and cleaned and update.changed:
            item = dict(base)
            item["text"] = cleaned
            candidates.append(
                _candidate(
                    "wrong_answer_memory_remove",
                    item,
                    "wrong_answer_memory",
                    "오답 memory phrase 제거",
                    score_bonus=6.0,
                    metadata={"wrong_answer_items": applied_wrong, "dictionary_update": update.to_dict()},
                )
            )

    stripped = " ".join(text.split())
    if stripped and stripped != text:
        item = dict(base)
        item["text"] = stripped
        candidates.append(_candidate("spacing_normalized", item, "normalizer", "공백 정규화", score_bonus=2.0))

    return candidates


__all__ = ["generate_quality_candidates"]
