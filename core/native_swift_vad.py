from __future__ import annotations

from typing import Any

from core.native_swift_subtitle import native_swift_runtime_enabled, request_native_core_task
from core.runtime.config import IS_MAC
from core.runtime.setting_utils import setting_bool


def _enabled(settings: dict[str, Any] | None = None) -> bool:
    if not IS_MAC:
        return False
    data = dict(settings or {})
    if not setting_bool(data.get("native_swift_vad_segments_enabled"), True):
        return False
    return native_swift_runtime_enabled("AI_SUBTITLE_STUDIO_SWIFT_VAD")


def vad_flags_to_segments_via_swift(
    flags: list[int],
    *,
    hop_sec: float,
    min_speech_sec: float,
    min_silence_sec: float,
    speech_pad_sec: float,
    source: str,
    for_post_stt_align: bool = False,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    if not flags or not _enabled(settings):
        return None
    decoded = request_native_core_task(
        "vad_flags_to_segments",
        {
            "flags": [1 if item else 0 for item in flags],
            "hop_sec": float(hop_sec or 0.0),
            "min_speech_sec": float(min_speech_sec or 0.0),
            "min_silence_sec": float(min_silence_sec or 0.0),
            "speech_pad_sec": float(speech_pad_sec or 0.0),
            "source": str(source or "vad"),
            "for_post_stt_align": bool(for_post_stt_align),
        },
    )
    if not isinstance(decoded, dict):
        return None
    rows = decoded.get("segments")
    if not isinstance(rows, list):
        return None
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        try:
            start = float(row.get("start", 0.0) or 0.0)
            end = float(row.get("end", start) or start)
        except (TypeError, ValueError):
            return None
        if end <= start:
            continue
        out.append(
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "source": str(row.get("source") or source or "vad"),
                "post_stt_align": bool(row.get("post_stt_align", for_post_stt_align)),
                "vad_word_filter": bool(row.get("vad_word_filter", not for_post_stt_align)),
                "speech_pad_sec": round(float(row.get("speech_pad_sec", speech_pad_sec) or 0.0), 3),
                "min_silence_sec": round(float(row.get("min_silence_sec", min_silence_sec) or 0.0), 3),
            }
        )
    return out


__all__ = ["vad_flags_to_segments_via_swift"]
