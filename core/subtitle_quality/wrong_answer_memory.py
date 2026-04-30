# Version: 03.01.25
# Phase: PHASE2
"""Wrong-answer memory storage for subtitle quality review."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config

WRONG_ANSWER_MEMORY_FILE = Path(config.DATASET_DIR) / "wrong_answer_memory.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _empty_payload() -> dict[str, Any]:
    return {"schema": "ai_subtitle_studio.wrong_answer_memory.v1", "items": []}


def load_wrong_answer_memory(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else WRONG_ANSWER_MEMORY_FILE
    if not target.exists():
        return _empty_payload()
    try:
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty_payload()
    if isinstance(data, list):
        return {"schema": "ai_subtitle_studio.wrong_answer_memory.v1", "items": data}
    if not isinstance(data, dict):
        return _empty_payload()
    data.setdefault("schema", "ai_subtitle_studio.wrong_answer_memory.v1")
    data.setdefault("items", [])
    if not isinstance(data["items"], list):
        data["items"] = []
    return data


def save_wrong_answer_memory(memory: dict[str, Any], path: str | Path | None = None) -> None:
    target = Path(path) if path else WRONG_ANSWER_MEMORY_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(memory or _empty_payload())
    payload.setdefault("schema", "ai_subtitle_studio.wrong_answer_memory.v1")
    payload.setdefault("items", [])
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)


def add_wrong_answer_memory_item(
    phrase: str,
    *,
    context: str = "",
    evidence: dict[str, Any] | None = None,
    source: str = "quality_review",
    path: str | Path | None = None,
) -> dict[str, Any]:
    phrase = _normalize_text(phrase)
    memory = load_wrong_answer_memory(path)
    if not phrase:
        return memory
    items = list(memory.get("items") or [])
    for item in items:
        if _normalize_text(item.get("phrase")) == phrase:
            item["count"] = int(item.get("count", 0) or 0) + 1
            item["updated_at"] = _now()
            item["source"] = source or item.get("source", "quality_review")
            if context:
                item["context"] = context[:500]
            if evidence:
                item["evidence"] = dict(evidence)
            save_wrong_answer_memory(memory, path)
            return memory
    items.append(
        {
            "phrase": phrase,
            "context": context[:500],
            "evidence": dict(evidence or {}),
            "count": 1,
            "source": source,
            "updated_at": _now(),
        }
    )
    memory["items"] = items
    save_wrong_answer_memory(memory, path)
    return memory


def search_wrong_answer_memory(
    text: str,
    *,
    limit: int = 5,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    haystack = _normalize_text(text)
    if not haystack:
        return []
    matches: list[dict[str, Any]] = []
    for item in load_wrong_answer_memory(path).get("items", []):
        if not isinstance(item, dict):
            continue
        phrase = _normalize_text(item.get("phrase"))
        if phrase and phrase in haystack:
            enriched = dict(item)
            enriched["match_length"] = len(phrase)
            matches.append(enriched)
    matches.sort(key=lambda item: (int(item.get("count", 0) or 0), int(item.get("match_length", 0) or 0)), reverse=True)
    return matches[: max(0, int(limit or 0))]


__all__ = [
    "WRONG_ANSWER_MEMORY_FILE",
    "add_wrong_answer_memory_item",
    "load_wrong_answer_memory",
    "save_wrong_answer_memory",
    "search_wrong_answer_memory",
]
