# Version: 03.01.25
# Phase: PHASE2
"""Correction memory storage for subtitle quality review."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import config

CORRECTION_MEMORY_FILE = Path(config.DATASET_DIR) / "correction_memory.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def infer_correction_type(original: str, corrected: str) -> str:
    src = _normalize_text(original)
    dst = _normalize_text(corrected)
    if not src or not dst:
        return "typo"
    if re.sub(r"\s+", "", src) == re.sub(r"\s+", "", dst) and src != dst:
        return "spacing"
    if re.search(r"\d", src + dst):
        return "number"
    if len(dst) < max(1, len(src) * 0.55):
        return "hallucination_remove"
    if "\n" in corrected and "\n" not in original:
        return "split"
    if "\n" in original and "\n" not in corrected:
        return "merge"
    if any(ch.isupper() for ch in dst):
        return "proper_noun"
    return "typo"


def _empty_payload() -> dict[str, Any]:
    return {"schema": "ai_subtitle_studio.correction_memory.v1", "items": []}


def load_correction_memory(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else CORRECTION_MEMORY_FILE
    if not target.exists():
        return _empty_payload()
    try:
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty_payload()
    if isinstance(data, list):
        return {"schema": "ai_subtitle_studio.correction_memory.v1", "items": data}
    if not isinstance(data, dict):
        return _empty_payload()
    data.setdefault("schema", "ai_subtitle_studio.correction_memory.v1")
    data.setdefault("items", [])
    if not isinstance(data["items"], list):
        data["items"] = []
    return data


def save_correction_memory(memory: dict[str, Any], path: str | Path | None = None) -> None:
    target = Path(path) if path else CORRECTION_MEMORY_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(memory or _empty_payload())
    payload.setdefault("schema", "ai_subtitle_studio.correction_memory.v1")
    payload.setdefault("items", [])
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)


def add_correction_memory_item(
    original: str,
    corrected: str,
    *,
    correction_type: str | None = None,
    confidence: float = 0.75,
    source: str = "manual",
    context: str = "",
    path: str | Path | None = None,
) -> dict[str, Any]:
    src = _normalize_text(original)
    dst = _normalize_text(corrected)
    memory = load_correction_memory(path)
    if not src or not dst or src == dst:
        return memory

    correction_type = correction_type or infer_correction_type(src, dst)
    items = list(memory.get("items") or [])
    for item in items:
        if _normalize_text(item.get("original")) == src and _normalize_text(item.get("corrected")) == dst:
            item["count"] = int(item.get("count", 0) or 0) + 1
            item["confidence"] = max(float(item.get("confidence", 0.0) or 0.0), float(confidence or 0.0))
            item["updated_at"] = _now()
            item["source"] = source or item.get("source", "manual")
            if context:
                item["context"] = context[:500]
            save_correction_memory(memory, path)
            return memory

    items.append(
        {
            "original": src,
            "corrected": dst,
            "type": correction_type,
            "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
            "count": 1,
            "source": source,
            "context": context[:500],
            "updated_at": _now(),
        }
    )
    memory["items"] = items
    save_correction_memory(memory, path)
    return memory


def search_correction_memory(
    text: str,
    *,
    limit: int = 5,
    min_confidence: float = 0.5,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    haystack = _normalize_text(text)
    if not haystack:
        return []
    matches: list[dict[str, Any]] = []
    for item in load_correction_memory(path).get("items", []):
        if not isinstance(item, dict):
            continue
        original = _normalize_text(item.get("original"))
        corrected = _normalize_text(item.get("corrected"))
        confidence = float(item.get("confidence", 0.0) or 0.0)
        if not original or not corrected or confidence < min_confidence:
            continue
        if original in haystack:
            enriched = dict(item)
            enriched["match_length"] = len(original)
            matches.append(enriched)
    matches.sort(key=lambda item: (int(item.get("count", 0) or 0), float(item.get("confidence", 0.0) or 0.0), int(item.get("match_length", 0) or 0)), reverse=True)
    return matches[: max(0, int(limit or 0))]


def apply_correction_memory(text: str, items: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, Any]]]:
    out = str(text or "")
    applied: list[dict[str, Any]] = []
    candidates = list(items or search_correction_memory(out))
    candidates.sort(key=lambda item: len(str(item.get("original", "") or "")), reverse=True)
    for item in candidates:
        original = str(item.get("original", "") or "")
        corrected = str(item.get("corrected", "") or "")
        if original and corrected and original in out:
            out = out.replace(original, corrected)
            applied.append(dict(item))
    return out, applied


__all__ = [
    "CORRECTION_MEMORY_FILE",
    "add_correction_memory_item",
    "apply_correction_memory",
    "infer_correction_type",
    "load_correction_memory",
    "save_correction_memory",
    "search_correction_memory",
]
