# Version: 03.00.20
# Phase: PHASE2
from __future__ import annotations

import re
from typing import Any


_PUNCT_ENDINGS = tuple(",?!;:~…")


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _char_count(text: str) -> int:
    return len(str(text or "").replace(" ", "").replace("\n", ""))


def _clean_word(value: str) -> str:
    return re.sub(r"[^\w가-힣]", "", str(value or ""))


def _word_text(word: dict[str, Any]) -> str:
    return str(word.get("word", "") or "").strip()


def _segment_words(segment: dict[str, Any]) -> list[dict[str, Any]]:
    words = [dict(word) for word in (segment.get("words") or []) if _word_text(word)]
    if words:
        return sorted(words, key=lambda item: _as_float(item.get("start")))

    text = str(segment.get("text", "") or "").strip()
    tokens = [token for token in text.split() if token]
    if not tokens:
        return []
    start = _as_float(segment.get("start"))
    end = max(start + 0.1, _as_float(segment.get("end"), start + 0.1))
    step = max(0.05, (end - start) / max(1, len(tokens)))
    speaker = segment.get("speaker")
    return [
        {
            "word": token,
            "start": round(start + index * step, 3),
            "end": round(start + (index + 1) * step, 3),
            "speaker": speaker,
        }
        for index, token in enumerate(tokens)
    ]


def _is_rule_break(word: str, next_word: str, rules: dict[str, Any] | None) -> bool:
    rules = rules or {}
    current = _clean_word(word)
    nxt = _clean_word(next_word)
    end_words = [str(item) for item in rules.get("end_words", []) if item]
    start_words = [str(item) for item in rules.get("start_words", []) if item]
    if end_words and any(current.endswith(item) for item in end_words):
        return True
    if start_words and any(nxt.startswith(item) for item in start_words):
        return True
    return False


def _is_punctuation_break(word: str) -> bool:
    value = str(word or "").strip()
    return bool(value) and value.endswith(_PUNCT_ENDINGS)


def _build_segment(words: list[dict[str, Any]], fallback_speaker: str | None) -> dict[str, Any] | None:
    if not words:
        return None
    text = " ".join(_word_text(word) for word in words).strip()
    if not text:
        return None
    start = _as_float(words[0].get("start"))
    end = max(start + 0.05, _as_float(words[-1].get("end"), start + 0.05))
    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
        "speaker": words[0].get("speaker") or fallback_speaker,
        "words": words,
    }


def _should_flush(
    buf: list[dict[str, Any]],
    next_word: dict[str, Any] | None,
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    rules: dict[str, Any] | None,
) -> bool:
    if not buf:
        return False
    if next_word is None:
        return True

    start = _as_float(buf[0].get("start"))
    end = _as_float(buf[-1].get("end"), start)
    duration = max(0.05, end - start)
    if duration < min_duration:
        return False

    text = " ".join(_word_text(word) for word in buf)
    chars = _char_count(text)
    current_word = _word_text(buf[-1])
    following_word = _word_text(next_word)
    gap = _as_float(next_word.get("start"), end) - end
    cps = chars / duration if duration > 0 else chars
    natural = _is_punctuation_break(current_word) or _is_rule_break(current_word, following_word, rules)

    if gap >= gap_break_sec:
        return True
    if chars >= max_chars and natural:
        return True
    if duration >= max_duration and (natural or gap >= min(gap_break_sec * 0.5, 1.0) or chars >= int(max_chars * 0.5)):
        return True
    if cps > max_cps and chars >= max_chars and natural:
        return True
    if chars >= int(max_chars * 1.5):
        return True
    return False


def resegment_by_word_timestamps(
    segments: list[dict[str, Any]],
    *,
    max_chars: int,
    max_duration: float,
    max_cps: float,
    min_duration: float,
    gap_break_sec: float,
    rules: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Re-split subtitles using word timestamps after STT/LLM cleanup."""
    if not segments:
        return []

    max_chars = max(2, int(max_chars or 10))
    max_duration = max(0.5, float(max_duration or 6.0))
    max_cps = max(3.0, float(max_cps or 12.0))
    min_duration = max(0.0, float(min_duration or 0.0))
    gap_break_sec = max(0.05, float(gap_break_sec or 1.5))

    result: list[dict[str, Any]] = []
    for segment in sorted((dict(item) for item in segments), key=lambda item: _as_float(item.get("start"))):
        words = _segment_words(segment)
        if not words:
            continue
        fallback_speaker = segment.get("speaker")
        buf: list[dict[str, Any]] = []
        for index, word in enumerate(words):
            buf.append(word)
            next_word = words[index + 1] if index + 1 < len(words) else None
            if not _should_flush(
                buf,
                next_word,
                max_chars=max_chars,
                max_duration=max_duration,
                max_cps=max_cps,
                min_duration=min_duration,
                gap_break_sec=gap_break_sec,
                rules=rules,
            ):
                continue
            built = _build_segment(buf, fallback_speaker)
            if built is not None:
                result.append(built)
            buf = []

        if buf:
            built = _build_segment(buf, fallback_speaker)
            if built is not None:
                result.append(built)

    return result
