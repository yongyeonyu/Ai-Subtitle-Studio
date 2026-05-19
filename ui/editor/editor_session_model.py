# Version: 04.00.10
# Phase: PHASE2
"""Canonical editor session state views.

The editor still feeds existing widgets with lists, but this model keeps the
session contract explicit and delays row copying until a caller asks for a view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


def _row_refs(rows: Iterable[dict] | None) -> tuple[dict, ...]:
    if rows is None:
        return ()
    return tuple(row for row in rows if isinstance(row, dict))


def _row_copies(rows: Sequence[dict]) -> list[dict]:
    return [dict(row) for row in rows if isinstance(row, dict)]


@dataclass(frozen=True)
class EditorSessionModel:
    final_segments: tuple[dict, ...] = field(default_factory=tuple)
    stt_preview_segments: tuple[dict, ...] = field(default_factory=tuple)
    voice_activity_segments: tuple[dict, ...] = field(default_factory=tuple)
    boundary_times: tuple[float | dict, ...] = field(default_factory=tuple)
    provisional_boundaries: tuple[dict | float, ...] = field(default_factory=tuple)
    stt_preview_subtitle_drafts: bool | None = None

    @classmethod
    def from_canvas_state(
        cls,
        *,
        final_segments: Iterable[dict] | None = None,
        stt_preview_segments: Iterable[dict] | None = None,
        voice_activity_segments: Iterable[dict] | None = None,
        boundary_times: Iterable[float | dict] | None = None,
        provisional_boundaries: Iterable[dict | float] | None = None,
        stt_preview_subtitle_drafts: bool | None = None,
    ) -> "EditorSessionModel":
        return cls(
            final_segments=_row_refs(final_segments),
            stt_preview_segments=_row_refs(stt_preview_segments),
            voice_activity_segments=_row_refs(voice_activity_segments),
            boundary_times=tuple(() if boundary_times is None else boundary_times),
            provisional_boundaries=tuple(() if provisional_boundaries is None else provisional_boundaries),
            stt_preview_subtitle_drafts=stt_preview_subtitle_drafts,
        )

    def final_subtitle_rows(self) -> list[dict]:
        return _row_copies(self.final_segments)

    def stt_preview_rows(self) -> list[dict]:
        return _row_copies(self.stt_preview_segments)

    def voice_activity_rows(self) -> list[dict]:
        return _row_copies(self.voice_activity_segments)

    def project_save_view(self) -> dict[str, list | bool | None]:
        return {
            "segments": self.final_subtitle_rows(),
            "stt_preview_segments": self.stt_preview_rows(),
            "voice_activity_segments": self.voice_activity_rows(),
            "boundary_times": list(self.boundary_times),
            "provisional_boundaries": [
                dict(row) if isinstance(row, Mapping) else row
                for row in self.provisional_boundaries
            ],
            "stt_preview_subtitle_drafts": self.stt_preview_subtitle_drafts,
        }


__all__ = ["EditorSessionModel"]
