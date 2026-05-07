from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from core.audio.stt_quality_presets import normalize_stt_quality_key


LORA_BUCKET_HIGH = "high"
LORA_BUCKET_MEDIUM = "medium"
LORA_BUCKET_LOW = "low"
LORA_BUCKET_PENDING_DELETE = "pending_delete"
LORA_ACTIVE_BUCKETS = (LORA_BUCKET_HIGH, LORA_BUCKET_MEDIUM, LORA_BUCKET_LOW)
LORA_ALL_BUCKETS = (*LORA_ACTIVE_BUCKETS, LORA_BUCKET_PENDING_DELETE)
LORA_BUCKET_LABELS = {
    LORA_BUCKET_HIGH: "상",
    LORA_BUCKET_MEDIUM: "중",
    LORA_BUCKET_LOW: "하",
    LORA_BUCKET_PENDING_DELETE: "삭제예정",
}
LORA_BUCKET_FILENAMES = {
    LORA_BUCKET_HIGH: "lora_data_high.zip",
    LORA_BUCKET_MEDIUM: "lora_data_medium.zip",
    LORA_BUCKET_LOW: "lora_data_low.zip",
    LORA_BUCKET_PENDING_DELETE: "lora_data_pending_delete.zip",
}
LORA_BUCKET_PRIORITY = {
    LORA_BUCKET_HIGH: 0,
    LORA_BUCKET_MEDIUM: 1,
    LORA_BUCKET_LOW: 2,
    LORA_BUCKET_PENDING_DELETE: 3,
}
LORA_QUALITY_METADATA_KEYS = frozenset(
    {
        "lora_value_score",
        "lora_quality_bucket",
        "lora_retention_reason",
    }
)

_TEXT_SIGNAL_KEYS_BY_KIND: dict[str, tuple[str, ...]] = {
    "truth_table": (
        "speech_training_text",
        "line_break_pattern",
        "punctuation_pattern",
        "detected_split_rule",
        "style_profile",
        "subtitle_style_profile",
    ),
    "excluded_parentheticals": ("excluded_text", "kept_text", "reason_code"),
    "setting_trials": ("config", "metrics", "reason"),
    "prompt_trials": ("config", "prompt_text", "prompt_template_id", "metrics", "reason"),
    "text_lora_dataset": ("input", "output", "meta.patterns", "metadata.patterns", "style_profile"),
    "text_lora_corpus": ("input", "output", "meta.patterns", "metadata.patterns", "style_profile"),
    "multimodal_lora_context": (
        "context_classification",
        "media_profile",
        "subtitle_profile",
        "subtitle_style_profile",
        "candidate_context",
        "generation_targets",
    ),
    "deep_policy_events": ("event_type", "text", "decision", "features", "applied_settings"),
    "audio_preset_lora": ("audio_strategy", "features", "audio_profile", "audio_tune_settings", "settings"),
    "voice_lora_bridge": ("text", "duration_sec", "clip_path"),
    "stt1_whisper_adapter_dataset": (
        "transcript_text",
        "weak_input_text",
        "classification_summary",
        "candidate_context_summary",
        "training_tags",
    ),
}
_PATTERN_SIGNAL_KEYS = (
    "line_break_pattern",
    "punctuation_pattern",
    "detected_split_rule",
    "style_profile",
    "subtitle_style_profile",
    "meta.style_profile",
    "metadata.style_profile",
    "meta.patterns",
    "metadata.patterns",
    "features",
    "generation_targets",
    "decision",
    "applied_settings",
)


def _nested_value(payload: dict[str, Any], dotted_key: str) -> Any:
    current: Any = payload
    for part in dotted_key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except Exception:
        return None
    return score * 100.0 if 0.0 <= score <= 1.0 else score


def _explicit_score(row: dict[str, Any]) -> float | None:
    for key in (
        "lora_score",
        "score",
        "quality_score",
        "confidence_score",
        "stt_score",
        "train_weight",
        "metrics.final_score",
        "metrics.quality_score",
        "metadata.score",
    ):
        score = _float_or_none(_nested_value(row, key))
        if score is not None:
            return max(0.0, min(100.0, score))
    return None


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _created_timestamp(row: dict[str, Any], fallback_index: int = 0) -> float:
    for key in ("last_used_at", "updated_at", "captured_at", "created_at"):
        text = str(row.get(key) or "").strip()
        if not text:
            continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
    return float(fallback_index)


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    if isinstance(value, (int, float)):
        try:
            return float(value) > 0.0
        except Exception:
            return False
    return bool(value)


def _has_training_signal(kind: str, row: dict[str, Any]) -> bool:
    keys = _TEXT_SIGNAL_KEYS_BY_KIND.get(kind)
    if not keys:
        return True
    return any(_has_content(_nested_value(row, key)) for key in keys)


def _pattern_signal_boost(row: dict[str, Any]) -> float:
    matches = sum(1 for key in _PATTERN_SIGNAL_KEYS if _has_content(_nested_value(row, key)))
    return min(10.0, float(matches) * 2.0)


def _usage_boost(row: dict[str, Any]) -> float:
    usage = max(
        _coerce_int(row.get("usage_count"), 0),
        _coerce_int(row.get("frequency"), 0),
        _coerce_int(_nested_value(row, "metadata.usage_count"), 0),
    )
    return min(12.0, math.log1p(max(0, usage)) * 3.0)


def strip_lora_quality_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in dict(row or {}).items() if key not in LORA_QUALITY_METADATA_KEYS}


def lora_score_for_row(kind: str, row: dict[str, Any]) -> float:
    row = strip_lora_quality_metadata(dict(row or {}))
    status = str(row.get("status") or "").strip().lower()
    if status in {"failed", "error", "cancelled", "skipped"}:
        return 0.0

    explicit = _explicit_score(row)
    if explicit is not None:
        score = explicit
    else:
        kind = str(kind or "")
        if kind in {"truth_table", "text_lora_corpus"}:
            score = 82.0
        elif kind == "excluded_parentheticals":
            score = 90.0
        elif kind == "text_lora_dataset":
            score = 74.0
        elif kind == "multimodal_lora_context":
            score = 76.0
        elif kind == "deep_policy_events":
            score = 58.0 if bool(row.get("hard_case")) else 70.0
        elif kind == "voice_lora_bridge":
            try:
                duration = float(row.get("duration_sec", 0.0) or 0.0)
            except Exception:
                duration = 0.0
            score = max(45.0, min(82.0, duration / 12.0 * 100.0))
        elif kind == "stt1_whisper_adapter_dataset":
            score = 78.0
        elif kind.startswith("learned_") or kind == "audio_preset_lora":
            try:
                score = max(0.0, min(100.0, float(row.get("confidence", 0.0) or 0.0) * 100.0))
            except Exception:
                score = 0.0
        elif kind == "best_settings":
            score = 78.0
        else:
            score = 55.0

    kind = str(kind or "")
    if not _has_training_signal(kind, row):
        score = min(score, 20.0)
    else:
        score += _pattern_signal_boost(row)
    if status in {"complete", "reviewed"}:
        score += 3.0
    score += _usage_boost(row)
    if bool(row.get("pinned") or _nested_value(row, "metadata.pinned")):
        score = max(score, 95.0)
    return max(0.0, min(100.0, score))


def lora_bucket_for_score(score: Any) -> str:
    try:
        value = float(score)
    except Exception:
        value = 0.0
    if value >= 80.0:
        return LORA_BUCKET_HIGH
    if value >= 60.0:
        return LORA_BUCKET_MEDIUM
    if value >= 35.0:
        return LORA_BUCKET_LOW
    return LORA_BUCKET_PENDING_DELETE


def lora_bucket_for_row(kind: str, row: dict[str, Any]) -> str:
    return lora_bucket_for_score(lora_score_for_row(kind, row))


def lora_bucket_priority(bucket: str) -> int:
    return int(LORA_BUCKET_PRIORITY.get(str(bucket or ""), LORA_BUCKET_PRIORITY[LORA_BUCKET_PENDING_DELETE]))


def annotate_lora_row_quality(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row or {})
    score = lora_score_for_row(kind, out)
    bucket = lora_bucket_for_score(score)
    out["lora_value_score"] = round(float(score), 3)
    out["lora_quality_bucket"] = bucket
    if bucket == LORA_BUCKET_PENDING_DELETE:
        out["lora_retention_reason"] = "pending_delete_low_value_or_missing_pattern_signal"
    elif "lora_retention_reason" in out:
        out.pop("lora_retention_reason", None)
    return out


def lora_row_sort_key(kind: str, row: dict[str, Any], index: int = 0) -> tuple[int, float, float, float, int]:
    score = lora_score_for_row(kind, row)
    bucket = lora_bucket_for_score(score)
    usage = max(
        _coerce_int((row or {}).get("usage_count"), 0),
        _coerce_int((row or {}).get("frequency"), 0),
        _coerce_int(_nested_value(dict(row or {}), "metadata.usage_count"), 0),
    )
    return (
        lora_bucket_priority(bucket),
        -float(score),
        -float(usage),
        -_created_timestamp(dict(row or {}), index),
        int(index),
    )


def ranked_lora_rows(
    kind: str,
    rows: list[dict[str, Any]],
    *,
    bucket: str | None = None,
    annotate: bool = True,
) -> list[dict[str, Any]]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for index, row in enumerate(list(rows or [])):
        if not isinstance(row, dict):
            continue
        if bucket and lora_bucket_for_row(kind, row) != bucket:
            continue
        candidates.append((index, annotate_lora_row_quality(kind, row) if annotate else dict(row)))
    candidates.sort(key=lambda pair: lora_row_sort_key(kind, pair[1], pair[0]))
    return [row for _index, row in candidates]


def lora_allowed_buckets_for_quality(settings_or_key: dict[str, Any] | str | None) -> frozenset[str]:
    key = normalize_stt_quality_key(
        str((settings_or_key or {}).get("stt_quality_preset") or "") if isinstance(settings_or_key, dict) else settings_or_key
    )
    if key == "precise":
        return frozenset(LORA_ACTIVE_BUCKETS)
    if key == "balanced":
        return frozenset({LORA_BUCKET_HIGH})
    return frozenset()


__all__ = [
    "LORA_ACTIVE_BUCKETS",
    "LORA_ALL_BUCKETS",
    "LORA_BUCKET_FILENAMES",
    "LORA_BUCKET_HIGH",
    "LORA_BUCKET_LABELS",
    "LORA_BUCKET_LOW",
    "LORA_BUCKET_MEDIUM",
    "LORA_BUCKET_PENDING_DELETE",
    "LORA_BUCKET_PRIORITY",
    "LORA_QUALITY_METADATA_KEYS",
    "annotate_lora_row_quality",
    "lora_bucket_priority",
    "lora_allowed_buckets_for_quality",
    "lora_bucket_for_row",
    "lora_bucket_for_score",
    "lora_row_sort_key",
    "lora_score_for_row",
    "ranked_lora_rows",
    "strip_lora_quality_metadata",
]
