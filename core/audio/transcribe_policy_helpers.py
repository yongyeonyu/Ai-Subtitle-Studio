from __future__ import annotations

import os
import re
import wave

from core.runtime import config


def stt_candidate_keep_score(settings: dict | None) -> float:
    try:
        score = float((settings or {}).get("stt_candidate_keep_score", 24.0) or 24.0)
    except Exception:
        score = 24.0
    return max(0.0, min(100.0, score))


def setting_bool(settings: dict | None, key: str, default: bool = False) -> bool:
    value = (settings or {}).get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "사용", "켜짐"}
    return bool(value)


def setting_float(settings: dict | None, key: str, default: float) -> float:
    try:
        return float((settings or {}).get(key, default))
    except Exception:
        return default


def stt_word_timestamps_for_pass(settings: dict | None) -> bool:
    settings = settings or {}
    if bool(settings.get("stt_word_timestamp_precision_pass", False)):
        return setting_bool(settings, "stt_word_timestamps_precision_enabled", True)
    mode = str(settings.get("stt_word_timestamps_mode") or "always").strip().lower()
    if mode in {"off", "false", "none", "disabled"}:
        return False
    if mode in {"always", "on", "true", "word", "words"}:
        return True
    return setting_bool(settings, "stt_word_timestamps_default_enabled", False)


def stt_selective_ensemble_enabled(settings: dict | None) -> bool:
    settings = settings or {}
    if setting_bool(settings, "stt_ensemble_parallel_enabled", False):
        return False
    return setting_bool(settings, "stt_ensemble_selective_enabled", False)


def stt_persistent_runtime_reuse_enabled(settings: dict | None) -> bool:
    if not bool(getattr(config, "IS_MAC", False)):
        return False
    return setting_bool(settings, "stt_persistent_runtime_reuse_enabled", True)


def mac_primary_fast_native_model(model: str, settings: dict | None, log_label: str = "STT") -> str:
    """Use the Mac-native turbo model for the first STT1 pass only."""
    if not bool(getattr(config, "IS_MAC", False)):
        return str(model or "").strip()
    if not setting_bool(settings, "stt_primary_fast_native_enabled", True):
        return str(model or "").strip()
    label = str(log_label or "STT").strip().upper()
    if label not in {"STT1"}:
        return str(model or "").strip()
    if setting_bool(settings, "stt_word_timestamp_precision_pass", False):
        return str(model or "").strip()

    raw = str(model or "").strip()
    lowered = raw.lower()
    if not raw:
        return str((settings or {}).get("stt_primary_fast_native_model") or config.WHISPERKIT_FAST_MODEL)
    if "large-v3" not in lowered and "whisper-large-v3" not in lowered:
        return raw
    return str(
        (settings or {}).get("stt_primary_fast_native_model")
        or getattr(config, "WHISPERKIT_FAST_MODEL", "")
        or raw
    ).strip()


def segment_score_100(segment: dict | None) -> float:
    segment = segment or {}
    for key in ("stt_score", "score", "confidence", "avg_confidence"):
        value = segment.get(key)
        if value is None:
            continue
        try:
            score = float(value)
        except Exception:
            continue
        if score <= 1.0:
            score *= 100.0
        return max(0.0, min(100.0, score))
    return 0.0


def segment_has_score(segment: dict | None) -> bool:
    segment = segment or {}
    return any(segment.get(key) is not None for key in ("stt_score", "score", "confidence", "avg_confidence"))


def segment_needs_word_precision(segment: dict, settings: dict | None) -> bool:
    if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
        return False
    if segment.get("words"):
        return False
    if any(bool(segment.get(key)) for key in ("editor_selected", "selected", "precision_review", "needs_review")):
        return True
    score_threshold = setting_float(settings, "stt_word_timestamps_precision_threshold", 72.0)
    if segment_has_score(segment) and segment_score_100(segment) <= score_threshold:
        return True
    quality = dict(segment.get("quality") or {})
    if str(quality.get("confidence_label") or "").strip().lower() in {"red", "yellow"}:
        return True
    flags = {str(flag) for flag in (quality.get("flags") or ())}
    if flags.intersection({"outside_vad_speech", "high_cps", "short_duration_long_text", "word_timestamps_missing"}):
        return True
    meta = dict(segment.get("asr_metadata") or {})
    hallucination = dict(meta.get("hallucination_risk") or {})
    try:
        if float(hallucination.get("risk", 0.0) or 0.0) >= 0.25:
            return True
    except Exception:
        pass
    vad = dict(meta.get("vad_alignment") or {})
    try:
        ratio = vad.get("vad_overlap_ratio")
        if ratio is not None and float(ratio) < 0.35:
            return True
    except Exception:
        pass
    return bool(segment.get("stt_ensemble_needs_llm_review"))


def segment_chunk_path(segment: dict) -> str:
    meta = dict(segment.get("asr_metadata") or {})
    return str(meta.get("chunk_path") or segment.get("chunk_path") or "")


def chunk_start_from_path(path: str) -> float:
    name = os.path.basename(str(path or ""))
    match = re.search(r"vad_\d+_([\d.]+)\.wav$", name)
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except Exception:
        return 0.0


def chunk_sort_key(path: str) -> tuple[float, str]:
    return (chunk_start_from_path(path), os.path.basename(str(path or "")))


def wav_duration(path: str) -> float:
    try:
        with wave.open(path, "r") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def segment_overlaps_range(segment: dict, start: float, end: float) -> bool:
    seg_start = float(segment.get("start", 0.0) or 0.0)
    seg_end = float(segment.get("end", seg_start) or seg_start)
    overlap = max(0.0, min(seg_end, end) - max(seg_start, start))
    span = max(0.001, min(max(seg_end - seg_start, 0.0), max(end - start, 0.0)))
    return overlap / span >= 0.35


__all__ = [
    "chunk_sort_key",
    "chunk_start_from_path",
    "mac_primary_fast_native_model",
    "segment_chunk_path",
    "segment_has_score",
    "segment_needs_word_precision",
    "segment_overlaps_range",
    "segment_score_100",
    "setting_bool",
    "setting_float",
    "stt_candidate_keep_score",
    "stt_persistent_runtime_reuse_enabled",
    "stt_selective_ensemble_enabled",
    "stt_word_timestamps_for_pass",
    "wav_duration",
]
