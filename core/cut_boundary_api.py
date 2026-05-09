"""Stable public API for the cut-boundary detector.

This module is intentionally thin: it exposes a versioned library boundary
around the existing detector while keeping the detector implementation in
``core.cut_boundary``.  Callers should depend on this file when they need a
stable contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence


CUT_BOUNDARY_API_VERSION = "01.00"
CUT_BOUNDARY_ALGORITHM_VERSION = "01.00"
CUT_BOUNDARY_ALGORITHM_ID = "ai_subtitle_studio.cut_boundary.grid_v3_strict_color_avg"

ProgressCallback = Callable[[dict[str, Any]], None]
FoundCallback = Callable[[dict[str, Any], list[dict[str, Any]]], None]


@dataclass(frozen=True, slots=True)
class CutBoundaryRequest:
    media_path: str
    clip_offset: float = 0.0
    clip_idx: int = 0
    sample_step_sec: float | None = None
    threshold: float | None = None
    level: str | None = None
    settings: Mapping[str, Any] | None = None
    scan_profile: Mapping[str, Any] | None = None
    sample_positions: Sequence[int] | None = None
    sample_mask: str | None = None


@dataclass(frozen=True, slots=True)
class CutBoundaryResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.rows)


class CutBoundaryAPI:
    """Versioned facade for cut-boundary detection and row operations."""

    api_version = CUT_BOUNDARY_API_VERSION
    algorithm_version = CUT_BOUNDARY_ALGORITHM_VERSION
    algorithm_id = CUT_BOUNDARY_ALGORITHM_ID

    def info(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "algorithm_version": self.algorithm_version,
            "algorithm_id": self.algorithm_id,
        }

    def detect(
        self,
        request: CutBoundaryRequest,
        *,
        progress_callback: ProgressCallback | None = None,
        found_callback: FoundCallback | None = None,
    ) -> CutBoundaryResult:
        from core import cut_boundary as engine
        from core.cut_boundary_backend_router import select_cut_boundary_backend

        settings = dict(request.settings or {})
        settings.setdefault("cut_boundary_api_version", self.api_version)
        settings.setdefault("cut_boundary_algorithm_version", self.algorithm_version)
        settings.setdefault("cut_boundary_algorithm_id", self.algorithm_id)
        if request.level:
            settings["scan_cut_boundary_level"] = request.level
            settings.setdefault("cut_boundary_level", request.level)

        scan_profile = dict(request.scan_profile or {})
        if not scan_profile:
            scan_profile = dict(engine.cut_boundary_scan_profile(settings) or {})

        backend_meta: dict[str, Any] = {}
        try:
            choice = select_cut_boundary_backend(request.media_path, settings)
            backend_meta = {
                "backend": choice.backend,
                "scan_path": choice.scan_path,
                "backend_reason": choice.reason,
                "use_proxy": choice.use_proxy,
            }
        except Exception:
            backend_meta = {}

        rows = engine.detect_media_cut_boundaries(
            request.media_path,
            clip_offset=float(request.clip_offset or 0.0),
            clip_idx=int(request.clip_idx or 0),
            sample_step_sec=float(request.sample_step_sec or settings.get("scan_cut_auto_sample_step_sec", 2.0) or 2.0),
            threshold=float(request.threshold or settings.get("scan_cut_auto_threshold", 24.0) or 24.0),
            progress_callback=progress_callback,
            found_callback=found_callback,
            scan_profile=scan_profile,
            sample_positions=request.sample_positions,
            sample_mask=request.sample_mask,
            settings=settings,
            settings_preloaded=True,
        )
        normalized = self.normalize(rows)
        return CutBoundaryResult(
            rows=normalized,
            metadata={
                **self.info(),
                **backend_meta,
                "media_path": str(request.media_path or ""),
                "clip_idx": int(request.clip_idx or 0),
                "row_count": len(normalized),
            },
        )

    def normalize(
        self,
        rows: list[dict[str, Any]] | None,
        *,
        primary_fps: float = 30.0,
    ) -> list[dict[str, Any]]:
        from core import cut_boundary as engine

        normalized = engine.normalize_cut_boundaries(rows, primary_fps=primary_fps)
        return [self._stamp_row(row) for row in normalized]

    def split_segments(
        self,
        segments: list[dict[str, Any]] | None,
        boundaries: list[dict[str, Any]] | None,
        *,
        enabled: bool = True,
        primary_fps: float = 30.0,
    ) -> list[dict[str, Any]]:
        from core import cut_boundary as engine

        stamped = self.normalize(boundaries, primary_fps=primary_fps)
        return engine.split_segments_by_cut_boundaries(
            segments,
            stamped,
            enabled=enabled,
            primary_fps=primary_fps,
        )

    def _stamp_row(self, row: dict[str, Any]) -> dict[str, Any]:
        stamped = dict(row or {})
        stamped["cut_boundary_api_version"] = self.api_version
        stamped["cut_boundary_algorithm_version"] = self.algorithm_version
        stamped["cut_boundary_algorithm_id"] = self.algorithm_id
        return stamped


default_cut_boundary_api = CutBoundaryAPI()


def library_info() -> dict[str, Any]:
    return default_cut_boundary_api.info()


def detect_cut_boundaries(
    media_path: str,
    **kwargs,
) -> CutBoundaryResult:
    return default_cut_boundary_api.detect(CutBoundaryRequest(media_path=media_path, **kwargs))


def normalize_cut_boundary_rows(
    rows: list[dict[str, Any]] | None,
    *,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    return default_cut_boundary_api.normalize(rows, primary_fps=primary_fps)


def split_segments_by_cut_boundary_rows(
    segments: list[dict[str, Any]] | None,
    boundaries: list[dict[str, Any]] | None,
    *,
    enabled: bool = True,
    primary_fps: float = 30.0,
) -> list[dict[str, Any]]:
    return default_cut_boundary_api.split_segments(
        segments,
        boundaries,
        enabled=enabled,
        primary_fps=primary_fps,
    )


__all__ = [
    "CUT_BOUNDARY_ALGORITHM_ID",
    "CUT_BOUNDARY_ALGORITHM_VERSION",
    "CUT_BOUNDARY_API_VERSION",
    "CutBoundaryAPI",
    "CutBoundaryRequest",
    "CutBoundaryResult",
    "default_cut_boundary_api",
    "detect_cut_boundaries",
    "library_info",
    "normalize_cut_boundary_rows",
    "split_segments_by_cut_boundary_rows",
]
