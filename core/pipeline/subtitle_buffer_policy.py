from __future__ import annotations

from core.personalization.subtitle_bundle_policy import should_flush_subtitle_bundle


def should_flush_final_subtitle_buffer(
    current_duration: float,
    chunk_time_limit: int,
    *,
    stt_ensemble_enabled: bool,
    settings: dict | None = None,
    buffer_segments: list[dict] | None = None,
    cut_boundaries: list | None = None,
    provisional_cut_boundaries: list | None = None,
    media_duration_sec: float | None = None,
) -> bool:
    if settings is None and not buffer_segments and not cut_boundaries and not provisional_cut_boundaries:
        # Backward-compatible live-preview behavior for legacy callers/tests.
        try:
            return float(current_duration or 0.0) > 0.0
        except Exception:
            return False
    try:
        flush, _policy = should_flush_subtitle_bundle(
            current_duration,
            chunk_time_limit,
            settings=settings,
            segments=buffer_segments,
            cut_boundaries=cut_boundaries,
            provisional_cut_boundaries=provisional_cut_boundaries,
            media_duration_sec=media_duration_sec,
        )
        return bool(flush)
    except Exception:
        return False


def should_flush_live_subtitle_buffer(
    current_duration: float,
    chunk_time_limit: int,
    *,
    stt_ensemble_enabled: bool,
    individual_queue_mode: bool | None = None,
    settings: dict | None = None,
    buffer_segments: list[dict] | None = None,
    cut_boundaries: list | None = None,
    provisional_cut_boundaries: list | None = None,
    media_duration_sec: float | None = None,
) -> bool:
    if (
        individual_queue_mode is not None
        and settings is None
        and not buffer_segments
        and not cut_boundaries
        and not provisional_cut_boundaries
    ):
        try:
            return float(current_duration or 0.0) > 0.0
        except Exception:
            return False
    return should_flush_final_subtitle_buffer(
        current_duration,
        chunk_time_limit,
        stt_ensemble_enabled=stt_ensemble_enabled,
        settings=settings,
        buffer_segments=buffer_segments,
        cut_boundaries=cut_boundaries,
        provisional_cut_boundaries=provisional_cut_boundaries,
        media_duration_sec=media_duration_sec,
    )


__all__ = [
    "should_flush_final_subtitle_buffer",
    "should_flush_live_subtitle_buffer",
]
