from __future__ import annotations

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


def lora_score_for_row(kind: str, row: dict[str, Any]) -> float:
    status = str((row or {}).get("status") or "").strip().lower()
    if status in {"failed", "error", "cancelled", "skipped"}:
        return 0.0

    explicit = _explicit_score(dict(row or {}))
    if explicit is not None:
        return explicit

    kind = str(kind or "")
    if kind in {"truth_table", "text_lora_corpus"}:
        return 82.0
    if kind == "excluded_parentheticals":
        return 90.0
    if kind == "text_lora_dataset":
        return 74.0
    if kind == "multimodal_lora_context":
        return 76.0
    if kind == "deep_policy_events":
        if bool((row or {}).get("hard_case")):
            return 58.0
        return 70.0
    if kind == "voice_lora_bridge":
        try:
            duration = float((row or {}).get("duration_sec", 0.0) or 0.0)
        except Exception:
            duration = 0.0
        return max(45.0, min(82.0, duration / 12.0 * 100.0))
    if kind == "stt1_whisper_adapter_dataset":
        return 78.0
    if kind.startswith("learned_") or kind == "audio_preset_lora":
        try:
            return max(0.0, min(100.0, float((row or {}).get("confidence", 0.0) or 0.0) * 100.0))
        except Exception:
            return 0.0
    if kind == "best_settings":
        return 78.0
    return 55.0


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


def lora_allowed_buckets_for_quality(settings_or_key: dict[str, Any] | str | None) -> frozenset[str]:
    key = normalize_stt_quality_key(
        str((settings_or_key or {}).get("stt_quality_preset") or "") if isinstance(settings_or_key, dict) else settings_or_key
    )
    if key == "precise":
        return frozenset(LORA_ALL_BUCKETS)
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
    "lora_allowed_buckets_for_quality",
    "lora_bucket_for_row",
    "lora_bucket_for_score",
    "lora_score_for_row",
]
