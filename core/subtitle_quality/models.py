# Version: 03.01.23
# Phase: PHASE2
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

ASR_METADATA_FIELDS: tuple[str, ...] = (
    "avg_logprob",
    "compression_ratio",
    "no_speech_prob",
    "temperature",
    "tokens",
    "words",
    "word_confidence",
    "language_probability",
    "_clip_idx",
)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list_or_none(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return list(value)
    return None


def _dictable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple):
        return [_dictable(item) for item in value]
    if isinstance(value, list):
        return [_dictable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dictable(item) for key, item in value.items()}
    return value


def normalize_word_items(words: Any) -> list[dict[str, Any]]:
    """Return word timestamp items in the app's dict format."""
    normalized: list[dict[str, Any]] = []
    for item in words or ():
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", item.get("text", "")) or "").strip()
        if not word:
            continue
        out: dict[str, Any] = {"word": word}
        if item.get("start") is not None:
            out["start"] = _float_or_none(item.get("start"))
        if item.get("end") is not None:
            out["end"] = _float_or_none(item.get("end"))
        confidence = item.get("probability", item.get("confidence"))
        if confidence is not None:
            out["confidence"] = _float_or_none(confidence)
        if item.get("speaker") is not None:
            out["speaker"] = item.get("speaker")
        normalized.append(out)
    return normalized


def _average_word_confidence(words: list[dict[str, Any]]) -> float | None:
    values = [
        _float_or_none(item.get("confidence", item.get("probability")))
        for item in words
        if item.get("confidence", item.get("probability")) is not None
    ]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def normalize_asr_metadata(
    segment: dict[str, Any] | None,
    *,
    backend: str | None = None,
    language_probability: Any = None,
    chunk_path: str | None = None,
) -> dict[str, Any]:
    """Normalize backend-specific ASR metadata into stable segment metadata."""
    source = dict(segment or {})
    existing = dict(source.get("asr_metadata") or {})
    meta: dict[str, Any] = {key: existing.get(key) for key in ASR_METADATA_FIELDS}

    for key in ("avg_logprob", "compression_ratio", "no_speech_prob", "temperature"):
        if source.get(key) is not None:
            meta[key] = _float_or_none(source.get(key))

    if source.get("tokens") is not None:
        meta["tokens"] = _list_or_none(source.get("tokens"))

    words = normalize_word_items(source.get("words") or existing.get("words") or ())
    if words:
        meta["words"] = words
        meta["word_confidence"] = _first_not_none(
            _float_or_none(source.get("word_confidence")),
            _float_or_none(existing.get("word_confidence")),
            _average_word_confidence(words),
        )
    elif meta.get("words") is None:
        meta["words"] = None

    if language_probability is not None:
        meta["language_probability"] = _float_or_none(language_probability)
    elif source.get("language_probability") is not None:
        meta["language_probability"] = _float_or_none(source.get("language_probability"))
    elif source.get("language_prob") is not None:
        meta["language_probability"] = _float_or_none(source.get("language_prob"))

    if backend:
        meta["backend"] = backend
    elif existing.get("backend"):
        meta["backend"] = existing.get("backend")

    if chunk_path:
        meta["chunk_path"] = str(chunk_path)
    elif existing.get("chunk_path"):
        meta["chunk_path"] = existing.get("chunk_path")

    return meta


def attach_asr_metadata(
    segment: dict[str, Any],
    *,
    backend: str | None = None,
    language_probability: Any = None,
    chunk_path: str | None = None,
) -> dict[str, Any]:
    """Return a segment copy with normalized asr_metadata attached."""
    out = dict(segment or {})
    out["asr_metadata"] = normalize_asr_metadata(
        out,
        backend=backend,
        language_probability=language_probability,
        chunk_path=chunk_path,
    )
    return out


@dataclass(frozen=True, slots=True)
class SubtitleQualityMetrics:
    confidence_score: float | None = None
    confidence_label: str = "gray"
    confidence_reason: str = ""
    flags: tuple[str, ...] = field(default_factory=tuple)
    asr_metadata_score: float | None = None
    vad_alignment_score: float | None = None
    word_timestamp_score: float | None = None
    timing_score: float | None = None
    repetition_score: float | None = None
    context_score: float | None = None
    correction_memory_score: float | None = None
    hallucination_penalty: float | None = None


@dataclass(frozen=True, slots=True)
class SubtitleQualitySummary:
    overall_score: float | None = None
    green_count: int = 0
    yellow_count: int = 0
    red_count: int = 0
    gray_count: int = 0
    needs_review_count: int = 0
    auto_corrected_count: int = 0
    before_score: float | None = None
    after_score: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class QualityCandidate:
    candidate_id: str
    segment_index: int
    text: str
    start: float
    end: float
    source: str = "existing"
    score: float | None = None
    reason: str = ""
    safe_to_apply: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QualityPipelineResult:
    segments: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    summary: SubtitleQualitySummary = field(default_factory=SubtitleQualitySummary)
    candidates: tuple[QualityCandidate, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def metrics_to_dict(metrics: SubtitleQualityMetrics | dict[str, Any] | None) -> dict[str, Any]:
    if metrics is None:
        return {}
    return _dictable(metrics)


def metrics_from_dict(data: dict[str, Any] | None) -> SubtitleQualityMetrics:
    data = dict(data or {})
    if "flags" in data:
        data["flags"] = tuple(data.get("flags") or ())
    allowed = {field.name for field in SubtitleQualityMetrics.__dataclass_fields__.values()}
    return SubtitleQualityMetrics(**{key: data[key] for key in allowed if key in data})


def normalize_segment_quality(segment: dict[str, Any]) -> dict[str, Any]:
    """Normalize optional quality fields without changing segment text/timing."""
    out = dict(segment or {})
    if out.get("quality") is not None:
        out["quality"] = metrics_to_dict(metrics_from_dict(out.get("quality")))
    history = out.get("quality_history")
    if history is not None:
        out["quality_history"] = [metrics_to_dict(metrics_from_dict(item)) for item in history if isinstance(item, dict)]
    return out
