"""Subtitle style fingerprints learned from ground-truth rows."""
from __future__ import annotations

import re
from typing import Any

from core.personalization.lora_models import line_break_pattern_for_text

STYLE_PROFILE_SCHEMA = "ai_subtitle_studio.subtitle_style_profile.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _norm_lines(text: Any) -> list[str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [re.sub(r"\s+", " ", line).strip() for line in raw.split("\n") if re.sub(r"\s+", " ", line).strip()]


def _compact_len(text: Any) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _punctuation_counts(text: Any) -> dict[str, int]:
    raw = str(text or "")
    return {
        "period": raw.count("."),
        "comma": raw.count(","),
        "bang": raw.count("!"),
        "question": raw.count("?"),
        "wave": raw.count("~") + raw.count("～"),
        "ellipsis": raw.count("…") + raw.count("..."),
    }


def _punctuation_pattern(text: Any) -> str:
    return "".join(ch for ch in str(text or "") if ch in ".,!?~～…")


def _tone_label(text: Any) -> str:
    clean = re.sub(r"[\s.,!?~～…]+$", "", str(text or "").strip())
    if not clean:
        return "unknown"
    if re.search(r"(습니다|입니다|합니다|드립니다|됩니다)$", clean):
        return "formal_polite"
    if re.search(r"(요|죠|네요|예요|에요|어요|아요)$", clean):
        return "casual_polite"
    if re.search(r"(다|했다|한다|된다|였다)$", clean):
        return "plain_declarative"
    if re.search(r"(해|야|자|네|지|거든)$", clean):
        return "casual_spoken"
    return "fragment"


def _parenthetical_blocks(text: Any) -> list[str]:
    raw = str(text or "")
    patterns = [
        r"\([^)]*\)",
        r"\[[^\]]*\]",
        r"\{[^}]*\}",
        r"（[^）]*）",
        r"【[^】]*】",
    ]
    out: list[str] = []
    for pattern in patterns:
        out.extend(match.group(0).strip() for match in re.finditer(pattern, raw) if match.group(0).strip())
    return out


def _brand_tokens(*texts: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        raw = str(text or "")
        for token in re.findall(r"(?<![A-Za-z0-9])(?:[A-Z][A-Z0-9]{1,})(?:[- ][A-Z0-9]{1,})*", raw):
            clean = token.strip()
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                found.append(clean)
    return found[:12]


def _word_tokens(text: Any, *, limit: int = 8) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣_+-]*", str(text or "")):
        clean = token.strip(".,!?~～…")
        if clean:
            tokens.append(clean)
        if len(tokens) >= limit:
            break
    return tokens


def _line_word_boundaries(lines: list[str]) -> dict[str, Any]:
    line_tokens = [_word_tokens(line, limit=6) for line in lines]
    line_start_words = [tokens[0] for tokens in line_tokens if tokens]
    subtitle_start_word = line_start_words[0] if line_start_words else ""
    subtitle_start_bigram = " ".join(line_tokens[0][:2]) if line_tokens and line_tokens[0] else ""
    line_breaks: list[dict[str, Any]] = []
    for index in range(max(0, len(line_tokens) - 1)):
        previous = line_tokens[index]
        following = line_tokens[index + 1]
        if not previous or not following:
            continue
        before_word = previous[-1]
        after_word = following[0]
        line_breaks.append(
            {
                "line_index": index,
                "before_word": before_word,
                "after_word": after_word,
                "before_bigram": " ".join(previous[-2:]),
                "after_bigram": " ".join(following[:2]),
                "pair": f"{before_word}->{after_word}",
            }
        )
    return {
        "subtitle_start_word": subtitle_start_word,
        "subtitle_start_bigram": subtitle_start_bigram,
        "line_start_words": line_start_words[:8],
        "line_breaks": line_breaks[:8],
    }


def build_subtitle_style_profile(
    *,
    raw_text: Any,
    speech_text: Any | None = None,
    input_text: Any = "",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    previous_end_sec: float | None = None,
    next_start_sec: float | None = None,
) -> dict[str, Any]:
    """Extract reusable style signals from a final ground-truth subtitle."""
    raw = str(raw_text or "").strip()
    speech = str(speech_text if speech_text is not None else raw).strip()
    lines = _norm_lines(speech)
    line_lengths = [_compact_len(line) for line in lines]
    start = _safe_float(start_sec, 0.0)
    end = _safe_float(end_sec, start)
    duration = max(0.0, end - start)
    compact_chars = _compact_len(speech)
    previous_gap = None
    next_gap = None
    if previous_end_sec is not None:
        previous_gap = round(max(0.0, start - _safe_float(previous_end_sec, start)), 3)
    if next_start_sec is not None:
        next_gap = round(max(0.0, _safe_float(next_start_sec, end) - end), 3)
    parentheticals = _parenthetical_blocks(raw)
    brand_tokens = _brand_tokens(raw, speech, input_text)
    punctuation = _punctuation_counts(raw)
    word_boundaries = _line_word_boundaries(lines)

    return {
        "schema": STYLE_PROFILE_SCHEMA,
        "line_break": {
            "pattern": line_break_pattern_for_text(speech),
            "line_count": len(lines),
            "line_lengths": line_lengths,
            "max_line_chars": max(line_lengths) if line_lengths else 0,
            "prefers_multiline": len(lines) >= 2,
        },
        "word_boundaries": word_boundaries,
        "tone": {
            "label": _tone_label(speech),
            "has_honorific": bool(re.search(r"(요|습니다|입니다|합니다|드립니다)", speech)),
            "has_laughter": bool(re.search(r"(ㅋ{2,}|ㅎ{2,})", raw)),
        },
        "parenthetical_policy": {
            "raw_has_parenthetical": bool(parentheticals),
            "removed_from_speech": bool(parentheticals and re.sub(r"\s+", "", raw) != re.sub(r"\s+", "", speech)),
            "excluded_count": len(parentheticals),
            "policy": "drop_editorial_parentheticals" if parentheticals else "none",
        },
        "punctuation": {
            "pattern": _punctuation_pattern(raw),
            "counts": punctuation,
            "uses_period": punctuation["period"] > 0,
            "uses_comma": punctuation["comma"] > 0,
            "uses_bang": punctuation["bang"] > 0,
            "uses_question": punctuation["question"] > 0,
        },
        "wave_marks": {
            "count": punctuation["wave"],
            "uses_wave": punctuation["wave"] > 0,
        },
        "brand_name_policy": {
            "tokens": brand_tokens,
            "preserve_case": bool(brand_tokens),
        },
        "timing_padding": {
            "duration_sec": round(duration, 3),
            "cps": round(compact_chars / duration, 3) if compact_chars and duration > 0 else 0.0,
            "previous_gap_sec": previous_gap,
            "next_gap_sec": next_gap,
            "padding_style": "tight" if (previous_gap is not None and previous_gap <= 0.25 and (next_gap is None or next_gap <= 0.25)) else "natural",
        },
    }


def subtitle_style_search_terms(profile: dict[str, Any] | None) -> list[str]:
    """Flatten a style profile into retrieval-friendly terms."""
    data = dict(profile or {})
    line = dict(data.get("line_break") or {})
    tone = dict(data.get("tone") or {})
    parenthetical = dict(data.get("parenthetical_policy") or {})
    punctuation = dict(data.get("punctuation") or {})
    wave = dict(data.get("wave_marks") or {})
    brand = dict(data.get("brand_name_policy") or {})
    timing = dict(data.get("timing_padding") or {})
    terms = [
        "subtitle style clone",
        f"line_pattern={line.get('pattern', '')}",
        f"line_count={line.get('line_count', 0)}",
        f"tone={tone.get('label', '')}",
        f"parenthetical={parenthetical.get('policy', '')}",
        f"punctuation={punctuation.get('pattern', '')}",
        f"wave={bool(wave.get('uses_wave'))}",
        f"padding={timing.get('padding_style', '')}",
    ]
    terms.extend(str(token) for token in list(brand.get("tokens") or []) if str(token or "").strip())
    return [term for term in terms if str(term or "").strip()]


__all__ = [
    "STYLE_PROFILE_SCHEMA",
    "build_subtitle_style_profile",
    "subtitle_style_search_terms",
]
