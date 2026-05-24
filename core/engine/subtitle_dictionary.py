from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUBTITLE_DICTIONARY_LOOKUP_SCHEMA = "ai_subtitle_studio.subtitle_dictionary.lookup.v1"
SUBTITLE_DICTIONARY_UPDATE_SCHEMA = "ai_subtitle_studio.subtitle_dictionary.update.v1"


def _bool_setting(settings: dict[str, Any], key: str, default: bool) -> bool:
    value = settings.get(key)
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable", "사용", "켜기", "켬"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable", "미사용", "끄기", "끔"}:
        return False
    return bool(default)


def _int_setting(settings: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(settings.get(key, default) or default)
    except Exception:
        return int(default)


def _float_setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default) or default)
    except Exception:
        return float(default)


def compact_subtitle_dictionary_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or ""))


@dataclass(frozen=True)
class SubtitleDictionaryLookupRequest:
    schema: str
    text: str
    correction_enabled: bool
    wrong_answer_enabled: bool
    correction_memory_path: str
    wrong_answer_memory_path: str
    limit: int
    min_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "text": self.text,
            "correction_enabled": self.correction_enabled,
            "wrong_answer_enabled": self.wrong_answer_enabled,
            "correction_memory_path": self.correction_memory_path,
            "wrong_answer_memory_path": self.wrong_answer_memory_path,
            "limit": self.limit,
            "min_confidence": self.min_confidence,
        }


@dataclass(frozen=True)
class SubtitleDictionaryTextUpdate:
    schema: str
    source: str
    before_text: str
    after_text: str
    applied_items: tuple[dict[str, Any], ...]

    @property
    def changed(self) -> bool:
        return compact_subtitle_dictionary_text(self.before_text) != compact_subtitle_dictionary_text(self.after_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source": self.source,
            "before_text": self.before_text,
            "after_text": self.after_text,
            "changed": self.changed,
            "applied_items": [dict(item) for item in self.applied_items],
        }


def build_subtitle_dictionary_lookup_request(
    text: Any,
    *,
    settings: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> SubtitleDictionaryLookupRequest:
    settings = dict(settings or {})
    context = dict(context or {})
    limit = max(0, _int_setting(settings, "dictionary_memory_lookup_limit", 5))
    min_confidence = max(0.0, min(1.0, _float_setting(settings, "correction_memory_min_confidence", 0.5)))
    return SubtitleDictionaryLookupRequest(
        schema=SUBTITLE_DICTIONARY_LOOKUP_SCHEMA,
        text=str(text or ""),
        correction_enabled=_bool_setting(settings, "correction_memory_enabled", True),
        wrong_answer_enabled=_bool_setting(settings, "wrong_answer_memory_enabled", True),
        correction_memory_path=str(context.get("correction_memory_path") or ""),
        wrong_answer_memory_path=str(context.get("wrong_answer_memory_path") or ""),
        limit=limit,
        min_confidence=min_confidence,
    )


def build_subtitle_dictionary_text_update(
    *,
    source: str,
    before_text: Any,
    after_text: Any,
    applied_items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> SubtitleDictionaryTextUpdate:
    return SubtitleDictionaryTextUpdate(
        schema=SUBTITLE_DICTIONARY_UPDATE_SCHEMA,
        source=str(source or ""),
        before_text=str(before_text or ""),
        after_text=str(after_text or ""),
        applied_items=tuple(dict(item) for item in list(applied_items or []) if isinstance(item, dict)),
    )


def remove_subtitle_dictionary_wrong_phrases(
    text: Any,
    wrong_items: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[str, list[dict[str, Any]]]:
    out = str(text or "")
    applied: list[dict[str, Any]] = []
    for item in sorted(
        [dict(row) for row in list(wrong_items or []) if isinstance(row, dict)],
        key=lambda row: len(str(row.get("phrase", "") or "")),
        reverse=True,
    ):
        phrase = str(item.get("phrase", "") or "")
        if phrase and phrase in out:
            out = out.replace(phrase, "").strip()
            applied.append(item)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, applied


__all__ = [
    "SUBTITLE_DICTIONARY_LOOKUP_SCHEMA",
    "SUBTITLE_DICTIONARY_UPDATE_SCHEMA",
    "SubtitleDictionaryLookupRequest",
    "SubtitleDictionaryTextUpdate",
    "build_subtitle_dictionary_lookup_request",
    "build_subtitle_dictionary_text_update",
    "compact_subtitle_dictionary_text",
    "remove_subtitle_dictionary_wrong_phrases",
]
