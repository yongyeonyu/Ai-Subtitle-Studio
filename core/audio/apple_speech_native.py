from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from time import time
import re

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import setting_bool

APPLE_SPEECH_STT_BACKEND = "apple_speech"
APPLE_SPEECH_VAD_BACKEND = "apple_speech_detector"
APPLE_SPEECH_DEFAULT_LOCALE = "ko-KR"
_APPLE_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_APPLE_NUMERIC_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?")
_APPLE_CLAUSE_ENDINGS = ("고", "고요", "구요", "인데", "는데")
_APPLE_NUMERIC_FOLLOWERS = {"유지가", "유지", "인데", "점", "계속"}
_APPLE_GAP_FOLLOWERS = {"계속", "크루즈", "진짜", "너무"}


@dataclass(frozen=True, slots=True)
class AppleSpeechSupport:
    available: bool
    detector_available: bool
    reason: str
    locale: str


@dataclass(frozen=True, slots=True)
class AppleSpeechTranscription:
    ok: bool
    payload: dict[str, Any]
    reason: str
    locale: str


def _split_single_long_apple_segment(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    segments = list(data.get("segments") or [])
    if len(segments) != 1:
        return data
    seg = dict(segments[0] or {})
    text = str(seg.get("text") or "").strip()
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or start)
    duration = max(0.0, end - start)
    if not text or duration < 8.0:
        return data
    parts = [part.strip() for part in _APPLE_SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if len(parts) < 2:
        return data
    # Only split when the transcript already contains sentence-ending punctuation.
    punctuated_parts = [part for part in parts if part[-1:] in ".!?"]
    if len(punctuated_parts) < 2:
        return data
    weights = [max(1, len(part.replace(" ", ""))) for part in parts]
    total_weight = sum(weights) or len(parts)
    cursor = start
    rebuilt: list[dict[str, Any]] = []
    for idx, (part, weight) in enumerate(zip(parts, weights)):
        if idx == len(parts) - 1:
            part_start = cursor
            part_end = end
        else:
            share = duration * (float(weight) / float(total_weight))
            part_start = cursor
            part_end = min(end, max(part_start + 0.05, cursor + share))
        rebuilt.append(
            {
                **seg,
                "start": round(part_start, 6),
                "end": round(part_end, 6),
                "text": part,
            }
        )
        cursor = part_end
    data["segments"] = rebuilt
    data["text"] = " ".join(str(item.get("text") or "").strip() for item in rebuilt if str(item.get("text") or "").strip())
    data["synthetic_sentence_split"] = True
    return data


def _rebalance_segment_groups(seg: dict[str, Any], groups: list[list[str]]) -> list[dict[str, Any]]:
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or start)
    duration = max(0.0, end - start)
    flat_parts = [" ".join(part for part in group if part).strip() for group in groups]
    flat_parts = [part for part in flat_parts if part]
    if len(flat_parts) < 2 or duration <= 0.0:
        return [seg]
    weights = [max(1, len(part.replace(" ", ""))) for part in flat_parts]
    total_weight = sum(weights) or len(flat_parts)
    cursor = start
    rebuilt: list[dict[str, Any]] = []
    for idx, (part, weight) in enumerate(zip(flat_parts, weights)):
        if idx == len(flat_parts) - 1:
            part_start = cursor
            part_end = end
        else:
            share = duration * (float(weight) / float(total_weight))
            part_start = cursor
            part_end = min(end, max(part_start + 0.05, cursor + share))
        rebuilt.append(
            {
                **seg,
                "start": round(part_start, 6),
                "end": round(part_end, 6),
                "text": part,
            }
        )
        cursor = part_end
    return rebuilt


def _split_clause_like_apple_segments(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    source_segments = list(data.get("segments") or [])
    if not source_segments:
        return data

    rebuilt: list[dict[str, Any]] = []
    changed = False
    for raw_seg in source_segments:
        seg = dict(raw_seg or {})
        text = str(seg.get("text") or "").strip()
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        duration = max(0.0, end - start)
        if not text or any(ch in text for ch in ".!?") or duration < 2.8:
            rebuilt.append(seg)
            continue
        tokens = [token.strip() for token in text.split() if token.strip()]
        if len(tokens) < 4:
            rebuilt.append(seg)
            continue

        split_points: list[int] = []
        for idx, token in enumerate(tokens[:-1]):
            next_token = tokens[idx + 1]
            if idx >= 1 and idx <= len(tokens) - 3 and token.endswith(_APPLE_CLAUSE_ENDINGS):
                split_points.append(idx + 1)
                continue
            if idx >= 1 and idx <= len(tokens) - 3 and token.endswith("가") and next_token in _APPLE_GAP_FOLLOWERS:
                split_points.append(idx + 1)
                continue
            if idx >= 0 and idx <= len(tokens) - 2 and _APPLE_NUMERIC_TOKEN_RE.match(token) and next_token in _APPLE_NUMERIC_FOLLOWERS:
                split_points.append(idx + 1)
                continue

        split_points = sorted(set(point for point in split_points if 1 <= point < len(tokens)))
        if not split_points:
            rebuilt.append(seg)
            continue

        groups: list[list[str]] = []
        cursor = 0
        for point in split_points:
            groups.append(tokens[cursor:point])
            cursor = point
        groups.append(tokens[cursor:])
        groups = [group for group in groups if group]
        if len(groups) < 2:
            rebuilt.append(seg)
            continue

        rebuilt.extend(_rebalance_segment_groups(seg, groups))
        changed = True

    if changed:
        data["segments"] = rebuilt
        data["text"] = " ".join(str(item.get("text") or "").strip() for item in rebuilt if str(item.get("text") or "").strip())
        data["synthetic_clause_split"] = True
    return data


def apple_speech_locale(settings: dict[str, Any] | None = None, default: str = APPLE_SPEECH_DEFAULT_LOCALE) -> str:
    data = dict(settings or {})
    locale = str(data.get("stt_apple_speech_locale") or default).strip()
    return locale or default


def apple_speech_model(locale: str | None = None) -> str:
    return f"{APPLE_SPEECH_STT_BACKEND}:{str(locale or APPLE_SPEECH_DEFAULT_LOCALE).strip() or APPLE_SPEECH_DEFAULT_LOCALE}"


def apple_speech_benchmark_only(settings: dict[str, Any] | None = None) -> bool:
    return setting_bool(dict(settings or {}).get("stt_apple_speech_benchmark_only"), True)


def apple_speech_challenger_enabled(settings: dict[str, Any] | None = None) -> bool:
    if not IS_MAC:
        return False
    data = dict(settings or {})
    if not setting_bool(data.get("stt_apple_speech_challenger_enabled"), False):
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CORE")


def apple_speech_vad_coupled_enabled(settings: dict[str, Any] | None = None) -> bool:
    if not apple_speech_challenger_enabled(settings):
        return False
    return setting_bool(dict(settings or {}).get("stt_apple_speech_vad_coupled_enabled"), True)


def apple_speech_support(
    settings: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
) -> AppleSpeechSupport:
    resolved_locale = apple_speech_locale(settings, default=str(locale or APPLE_SPEECH_DEFAULT_LOCALE))
    if not IS_MAC:
        return AppleSpeechSupport(False, False, "mac_only", resolved_locale)
    if not native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_CORE"):
        return AppleSpeechSupport(False, False, "native_swift_disabled", resolved_locale)
    decoded = request_native_core_task(
        "apple_speech_support",
        {"locale": resolved_locale},
    )
    if not isinstance(decoded, dict):
        return AppleSpeechSupport(False, False, "native_probe_unavailable", resolved_locale)
    return AppleSpeechSupport(
        bool(decoded.get("available")),
        bool(decoded.get("detector_available")),
        str(decoded.get("reason") or ("available" if decoded.get("available") else "unavailable")),
        str(decoded.get("locale") or resolved_locale),
    )


def apple_speech_probe_benchmark_row(
    settings: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
    elapsed_sec: float | None = None,
) -> dict[str, Any]:
    support = apple_speech_support(settings, locale=locale)
    return {
        "task": "stt",
        "backend": APPLE_SPEECH_STT_BACKEND,
        "model": apple_speech_model(support.locale),
        "available": bool(support.available),
        "detector_available": bool(support.detector_available),
        "reason": str(support.reason or ""),
        "elapsed_sec": float(elapsed_sec if elapsed_sec is not None else 0.0),
        "passed_quality_gate": False,
        "quality": {},
        "resources": {},
        "created_at": float(time()),
        "probe_only": True,
    }


def apple_speech_transcribe(
    audio_path: str,
    settings: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
    word_timestamps: bool = False,
) -> AppleSpeechTranscription:
    support = apple_speech_support(settings, locale=locale)
    if not support.available:
        return AppleSpeechTranscription(False, {}, str(support.reason or "unavailable"), support.locale)
    decoded = request_native_core_task(
        "apple_speech_transcribe",
        {
            "path": str(audio_path or ""),
            "locale": support.locale,
            "word_timestamps": bool(word_timestamps),
        },
    )
    if not isinstance(decoded, dict):
        return AppleSpeechTranscription(False, {}, "native_transcribe_unavailable", support.locale)
    if decoded.get("error"):
        return AppleSpeechTranscription(False, dict(decoded), str(decoded.get("error") or "native_transcribe_error"), support.locale)
    payload = _split_single_long_apple_segment(dict(decoded))
    payload = _split_clause_like_apple_segments(payload)
    payload.setdefault("backend", APPLE_SPEECH_STT_BACKEND)
    payload.setdefault("word_timestamps", bool(word_timestamps))
    payload.setdefault("language_probability", 1.0)
    payload.setdefault("chunk_path", str(audio_path or ""))
    return AppleSpeechTranscription(True, payload, str(payload.get("reason") or "ok"), support.locale)


def apple_speech_batch_transcribe(
    audio_paths: list[str],
    settings: dict[str, Any] | None = None,
    *,
    locale: str | None = None,
    word_timestamps: bool = False,
) -> list[AppleSpeechTranscription]:
    support = apple_speech_support(settings, locale=locale)
    if not support.available:
        return [
            AppleSpeechTranscription(False, {}, str(support.reason or "unavailable"), support.locale)
            for _ in audio_paths
        ]
    if not audio_paths:
        return []
    decoded = request_native_core_task(
        "apple_speech_batch_transcribe",
        {
            "paths": [str(p or "") for p in audio_paths],
            "locale": support.locale,
            "word_timestamps": bool(word_timestamps),
        },
    )
    if not isinstance(decoded, dict) or decoded.get("error") or "results" not in decoded:
        results = []
        for path in audio_paths:
            results.append(apple_speech_transcribe(path, settings, locale=locale, word_timestamps=word_timestamps))
        return results

    results = []
    decoded_results = decoded.get("results", [])
    for idx, item in enumerate(decoded_results):
        path = audio_paths[idx] if idx < len(audio_paths) else ""
        if not isinstance(item, dict) or item.get("error"):
            results.append(AppleSpeechTranscription(
                False,
                dict(item) if isinstance(item, dict) else {},
                str(item.get("error") if isinstance(item, dict) else "native_transcribe_error"),
                support.locale
            ))
        else:
            payload = dict(item)
            payload = _split_single_long_apple_segment(payload)
            payload = _split_clause_like_apple_segments(payload)
            payload.setdefault("backend", APPLE_SPEECH_STT_BACKEND)
            payload.setdefault("word_timestamps", bool(word_timestamps))
            payload.setdefault("language_probability", 1.0)
            payload.setdefault("chunk_path", str(path or ""))
            results.append(AppleSpeechTranscription(True, payload, str(payload.get("reason") or "ok"), support.locale))
    return results


__all__ = [
    "APPLE_SPEECH_DEFAULT_LOCALE",
    "APPLE_SPEECH_STT_BACKEND",
    "APPLE_SPEECH_VAD_BACKEND",
    "AppleSpeechSupport",
    "apple_speech_benchmark_only",
    "apple_speech_challenger_enabled",
    "apple_speech_locale",
    "apple_speech_model",
    "apple_speech_probe_benchmark_row",
    "apple_speech_support",
    "apple_speech_transcribe",
    "apple_speech_batch_transcribe",
    "apple_speech_vad_coupled_enabled",
    "AppleSpeechTranscription",
]
