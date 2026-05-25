# Version: 03.14.29
# Phase: PHASE1-B
"""Saved cut-boundary segment split and magnetize helpers."""

from core.runtime.logger import get_logger
from core.settings import load_settings


class PipelineCutBoundarySegmentOpsMixin:
    def _split_by_saved_cut_boundaries(self, segments, *, offset: float = 0.0, context: str = "자막") -> list[dict]:
        """Split subtitle/STT rows so no row crosses a saved visual cut."""
        try:
            from core.cut_boundary import cut_boundary_enabled, split_segments_by_cut_boundaries

            settings = load_settings()
            boundaries = self._project_cut_boundaries_for_pipeline()
            if offset:
                boundaries = self._shift_cut_boundary_rows_for_offset(boundaries, float(offset or 0.0))
            if not boundaries:
                return [dict(seg) for seg in (segments or [])]
            result = split_segments_by_cut_boundaries(
                segments,
                boundaries,
                enabled=cut_boundary_enabled(settings),
            )
            if len(result) != len(segments or []):
                get_logger().log(f"  ✂️ [컷 경계] {context} {len(segments or [])}개 → {len(result)}개 절대 분할")
            return result
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 분할 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]

    def _magnetize_by_saved_cut_boundaries(
        self,
        segments,
        *,
        offset: float = 0.0,
        context: str = "자막",
        include_confirmed: bool = True,
        include_provisional: bool = True,
        provisional_window_sec: float = 0.32,
        confirmed_window_sec: float = 0.60,
    ) -> list[dict]:
        """Snap subtitle/STT rows to both provisional and confirmed saved cuts."""
        try:
            from core.cut_boundary import (
                cut_boundary_enabled,
                magnetize_segments_to_cut_boundaries,
            )

            settings = load_settings()
            confirmed = self._project_cut_boundaries_for_pipeline() if include_confirmed else []
            provisional = self._project_cut_provisional_boundaries_for_pipeline() if include_provisional else []
            if offset:
                offset = float(offset or 0.0)
                confirmed = self._shift_cut_boundary_rows_for_offset(confirmed, offset)
                provisional = self._shift_cut_boundary_rows_for_offset(provisional, offset)
            if not confirmed and not provisional:
                return [dict(seg) for seg in (segments or [])]
            return magnetize_segments_to_cut_boundaries(
                segments,
                confirmed_boundaries=confirmed,
                provisional_boundaries=provisional,
                enabled=cut_boundary_enabled(settings),
                provisional_window_sec=provisional_window_sec,
                confirmed_window_sec=confirmed_window_sec,
                min_duration_sec=0.05,
            )
        except Exception as exc:
            get_logger().log(f"  ⚠️ [컷 경계] {context} 스냅 실패, 기존 세그먼트 유지: {exc}")
            return [dict(seg) for seg in (segments or [])]
