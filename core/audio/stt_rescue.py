from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


DEFAULT_RECHECK_THRESHOLD = 50.0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _score(segment: dict[str, Any]) -> float:
    for key in ("stt_score", "score", "confidence", "avg_confidence"):
        if segment.get(key) is None:
            continue
        value = _as_float(segment.get(key), -1.0)
        if value <= 1.0:
            value *= 100.0
        return max(0.0, min(100.0, value))
    return 0.0


def _text(segment: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(segment.get("text", "") or "")).strip()


def _duration(segment: dict[str, Any]) -> float:
    return max(0.0, _as_float(segment.get("end")) - _as_float(segment.get("start")))


def _overlap_ratio(left: dict[str, Any], right: dict[str, Any]) -> float:
    start = max(_as_float(left.get("start")), _as_float(right.get("start")))
    end = min(_as_float(left.get("end")), _as_float(right.get("end")))
    overlap = max(0.0, end - start)
    span = max(_duration(left), _duration(right), 0.001)
    return overlap / span


@dataclass(frozen=True)
class SttRecheckRange:
    start: float
    end: float
    primary_score: float
    secondary_score: float
    primary_text: str
    secondary_text: str
    primary: dict[str, Any]
    secondary: dict[str, Any]

    @property
    def best_original_score(self) -> float:
        return max(self.primary_score, self.secondary_score)


def enabled(settings: dict[str, Any] | None) -> bool:
    settings = settings or {}
    return bool(settings.get("stt_low_score_recheck_enabled", False))


def threshold(settings: dict[str, Any] | None) -> float:
    settings = settings or {}
    return max(0.0, min(100.0, _as_float(settings.get("stt_low_score_recheck_threshold"), DEFAULT_RECHECK_THRESHOLD)))


def recheck_padding(settings: dict[str, Any] | None) -> float:
    settings = settings or {}
    return max(0.05, min(1.5, _as_float(settings.get("stt_low_score_recheck_padding_sec"), 0.45)))


def max_recheck_segments(settings: dict[str, Any] | None) -> int:
    settings = settings or {}
    return max(1, min(200, int(_as_float(settings.get("stt_low_score_recheck_max_segments"), 80))))


def max_recheck_audio_sec(settings: dict[str, Any] | None) -> float:
    settings = settings or {}
    value = _as_float(settings.get("stt_low_score_recheck_max_audio_sec"), 180.0)
    return max(10.0, min(1800.0, value))


def _range_duration(item: SttRecheckRange) -> float:
    return max(0.05, float(item.end or 0.0) - float(item.start or 0.0))


def budget_recheck_ranges(
    ranges: list[SttRecheckRange],
    settings: dict[str, Any] | None = None,
    *,
    max_segments: int | None = None,
    max_audio_sec: float | None = None,
) -> list[SttRecheckRange]:
    if not ranges:
        return []
    seg_limit = max_recheck_segments(settings) if max_segments is None else max(1, min(200, int(max_segments)))
    sec_limit = max_recheck_audio_sec(settings) if max_audio_sec is None else max(10.0, min(1800.0, float(max_audio_sec)))

    def _priority(item: SttRecheckRange) -> tuple[float, float, float]:
        missing_voice = not item.primary_text and not item.secondary_text
        best_score = item.best_original_score
        duration = _range_duration(item)
        return (0.0 if missing_voice else 1.0, best_score, -duration)

    selected: list[SttRecheckRange] = []
    selected_sec = 0.0
    for item in sorted(ranges, key=_priority):
        duration = _range_duration(item)
        if len(selected) >= seg_limit:
            break
        if selected and selected_sec + duration > sec_limit:
            continue
        selected.append(item)
        selected_sec += duration
    selected.sort(key=lambda item: (item.start, item.end))
    return selected


def find_low_score_recheck_ranges(
    primary_segments: list[dict[str, Any]],
    secondary_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    apply_budget: bool = True,
) -> list[SttRecheckRange]:
    """Find overlapping STT1/STT2 ranges where both candidates are below threshold."""
    limit = threshold(settings)
    candidates: list[SttRecheckRange] = []
    used_secondary: set[int] = set()

    for primary in primary_segments or []:
        if not _text(primary):
            continue
        p_score = _score(primary)
        if p_score > limit:
            continue

        best_idx = None
        best_overlap = 0.0
        for idx, secondary in enumerate(secondary_segments or []):
            if idx in used_secondary or not _text(secondary):
                continue
            overlap = _overlap_ratio(primary, secondary)
            if overlap > best_overlap:
                best_idx = idx
                best_overlap = overlap

        if best_idx is None or best_overlap < 0.18:
            continue
        secondary = secondary_segments[best_idx]
        s_score = _score(secondary)
        if s_score > limit:
            continue

        used_secondary.add(best_idx)
        start = max(0.0, min(_as_float(primary.get("start")), _as_float(secondary.get("start"))))
        end = max(_as_float(primary.get("end")), _as_float(secondary.get("end")), start + 0.1)
        candidates.append(
            SttRecheckRange(
                start=round(start, 3),
                end=round(end, 3),
                primary_score=round(p_score, 2),
                secondary_score=round(s_score, 2),
                primary_text=_text(primary),
                secondary_text=_text(secondary),
                primary=dict(primary),
                secondary=dict(secondary),
            )
        )
    if apply_budget:
        return budget_recheck_ranges(candidates, settings)
    candidates.sort(key=lambda item: (item.start, item.end))
    return candidates


def find_primary_low_score_recheck_ranges(
    primary_segments: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    *,
    apply_budget: bool = True,
) -> list[SttRecheckRange]:
    """Find STT1-only low-score ranges for selective secondary recheck.

    Fast mode should not pay the cost of full STT1/STT2 ensemble. This finder
    lets the caller run STT2 only for the short primary spans that are already
    below the configured rescue threshold.
    """
    limit = threshold(settings)
    candidates: list[SttRecheckRange] = []
    for primary in primary_segments or []:
        if not _text(primary):
            continue
        p_score = _score(primary)
        if p_score > limit:
            continue
        start = max(0.0, _as_float(primary.get("start")))
        end = max(_as_float(primary.get("end")), start + 0.1)
        candidates.append(
            SttRecheckRange(
                start=round(start, 3),
                end=round(end, 3),
                primary_score=round(p_score, 2),
                secondary_score=0.0,
                primary_text=_text(primary),
                secondary_text="",
                primary=dict(primary),
                secondary={},
            )
        )
    if apply_budget:
        return budget_recheck_ranges(candidates, settings)
    candidates.sort(key=lambda item: (item.start, item.end))
    return candidates


def rescue_audio_filter(settings: dict[str, Any] | None = None) -> str:
    """Speech-focused ffmpeg chain for short recheck clips."""
    settings = settings or {}
    if bool(settings.get("stt_recheck_native_fast_audio_filter_enabled", True)):
        return (
            "highpass=f=80,"
            "lowpass=f=7600,"
            "acompressor=threshold=-24dB:ratio=3:attack=5:release=55,"
            "volume=2.5,"
            "alimiter=limit=0.93"
        )
    return (
        "highpass=f=80,"
        "lowpass=f=7600,"
        "afftdn=nf=-25,"
        "dynaudnorm=f=150:g=15:p=0.95,"
        "loudnorm=I=-18:TP=-1.5:LRA=11"
    )


def replacement_is_better(
    rescue_segments: list[dict[str, Any]],
    item: SttRecheckRange,
    settings: dict[str, Any] | None = None,
) -> bool:
    if not rescue_segments:
        return False
    scores = [_score(seg) for seg in rescue_segments if _text(seg)]
    if not scores:
        return False
    rescue_score = max(scores)
    min_improvement = max(0.0, _as_float((settings or {}).get("stt_low_score_recheck_min_improvement"), 3.0))
    return rescue_score >= threshold(settings) or rescue_score >= item.best_original_score + min_improvement


def mark_rescue_segments(
    rescue_segments: list[dict[str, Any]],
    item: SttRecheckRange,
) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for seg in rescue_segments or []:
        if not _text(seg):
            continue
        out = dict(seg)
        meta = dict(out.get("asr_metadata") or {})
        meta["stt_low_score_recheck"] = {
            "enabled": True,
            "range_start": item.start,
            "range_end": item.end,
            "primary_score": item.primary_score,
            "secondary_score": item.secondary_score,
            "primary_text": item.primary_text[:120],
            "secondary_text": item.secondary_text[:120],
        }
        out["asr_metadata"] = meta
        out["stt_recheck_applied"] = True
        out["stt_recheck_original_scores"] = {
            "STT1": item.primary_score,
            "STT2": item.secondary_score,
        }
        marked.append(out)
    return marked


__all__ = [
    "DEFAULT_RECHECK_THRESHOLD",
    "SttRecheckRange",
    "budget_recheck_ranges",
    "enabled",
    "find_primary_low_score_recheck_ranges",
    "find_low_score_recheck_ranges",
    "mark_rescue_segments",
    "max_recheck_segments",
    "max_recheck_audio_sec",
    "recheck_padding",
    "replacement_is_better",
    "rescue_audio_filter",
    "threshold",
]
