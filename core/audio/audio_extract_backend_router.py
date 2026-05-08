from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.optimization.backend_policy import normalize_backend_policy, profile_backend


@dataclass(frozen=True, slots=True)
class AudioExtractBackendChoice:
    backend: str
    reason: str
    direct_chunk_min_sec: float | None = None


def select_audio_extract_backend(
    settings: dict[str, Any] | None,
    *,
    audio_ai: str,
    span_sec: float,
) -> AudioExtractBackendChoice:
    data = dict(settings or {})
    policy = normalize_backend_policy(data.get("audio_extract_backend_policy", "auto"))
    prof = profile_backend("audio_extract", data)
    try:
        direct_min_sec = float(data.get("direct_ffmpeg_chunk_min_sec", 60.0) or 60.0)
    except (TypeError, ValueError):
        direct_min_sec = 60.0
    direct_min_sec = max(1.0, direct_min_sec)
    if prof and policy == "auto":
        return AudioExtractBackendChoice(prof, "autotuned_profile")
    if policy == "legacy":
        return AudioExtractBackendChoice("ffmpeg_cli", "legacy_policy")
    if policy == "native":
        return AudioExtractBackendChoice("native_libav_optional", "native_policy")
    if policy == "fast":
        # Direct chunk extraction is quality-safe only for filters that already
        # support one-pass FFmpeg preprocessing.
        if str(audio_ai or "").strip().lower() in {"none", "deepfilter"}:
            return AudioExtractBackendChoice("ffmpeg_direct_chunks", "fast_policy", direct_chunk_min_sec=direct_min_sec)
        return AudioExtractBackendChoice("ffmpeg_cli", "fast_policy_filter_preserved")
    if span_sec >= direct_min_sec and str(audio_ai or "").strip().lower() in {"none", "deepfilter"}:
        return AudioExtractBackendChoice("ffmpeg_direct_chunks", "auto_long_media", direct_chunk_min_sec=direct_min_sec)
    return AudioExtractBackendChoice("ffmpeg_cli", "auto")


__all__ = ["AudioExtractBackendChoice", "select_audio_extract_backend"]
