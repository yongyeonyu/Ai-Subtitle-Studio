# Version: 04.00.10
# Phase: PHASE2
"""Strategy objects for cut-boundary startup helpers.

The pipeline mixin still owns orchestration, but deterministic row/key/prescan
decisions live here so they can be tested without starting the full pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.pipeline.cut_boundary_prescan_policy import (
    cut_boundary_adaptive_prescan_plan,
    fast_cut_boundary_prescan_settings,
)


def _list_rows(rows: Iterable | None) -> list:
    return [] if rows is None else list(rows)


@dataclass(frozen=True)
class CutBoundaryCandidateStrategy:
    """Normalize cut-boundary rows and update provisional follower state."""

    def sec_from_row(self, row) -> float | None:
        try:
            if isinstance(row, dict):
                return float(row.get("timeline_sec", row.get("time", row.get("start", 0.0))) or 0.0)
            return float(row)
        except (TypeError, ValueError):
            return None

    def candidate_key(self, row) -> str:
        sec = self.sec_from_row(row)
        if sec is None:
            sec = 0.0
        try:
            clip_idx = int(row.get("clip_idx", 0) or 0) if isinstance(row, dict) else 0
        except (TypeError, ValueError):
            clip_idx = 0
        return f"{clip_idx}:{float(sec):.3f}"

    def candidate_keys(self, rows: Iterable | None) -> set[str]:
        return {
            self.candidate_key(row)
            for row in _list_rows(rows)
            if isinstance(row, dict)
        }

    def hard_cut_seconds(self, rows: Iterable | None) -> list[float]:
        seconds: set[float] = set()
        for row in _list_rows(rows):
            sec = self.sec_from_row(row)
            if sec is not None and sec > 0.0:
                seconds.add(round(float(sec), 3))
        return sorted(seconds)

    def mark_following(self, provisional_rows: list[dict], rows: Iterable | None) -> bool:
        candidate_keys = self.candidate_keys(rows)
        if not candidate_keys:
            return False
        changed = False
        for idx, item in enumerate(_list_rows(provisional_rows)):
            if not isinstance(item, dict):
                continue
            key = str(item.get("candidate_key") or self.candidate_key(item))
            if key not in candidate_keys:
                continue
            marked = dict(item)
            marked["candidate_key"] = key
            marked["status"] = "verifying"
            marked["detector_stage"] = "follower"
            marked["follower_active"] = True
            marked["line_color"] = "#FFD60A"
            marked["line_style"] = "dash"
            marked["ui_label"] = "후발대 확인"
            provisional_rows[idx] = marked
            changed = True
        return changed

    def remove_checked(self, provisional_rows: list[dict], rows: Iterable | None) -> bool:
        candidate_keys = self.candidate_keys(rows)
        if not candidate_keys:
            return False
        kept: list[dict] = []
        changed = False
        for item in _list_rows(provisional_rows):
            if not isinstance(item, dict):
                kept.append(item)
                continue
            if bool(item.get("follower_relocated") or item.get("rollback_relocated")):
                kept.append(item)
                continue
            key = str(item.get("candidate_key") or self.candidate_key(item))
            if key in candidate_keys:
                changed = True
                continue
            kept.append(item)
        if changed:
            provisional_rows[:] = kept
        return changed


@dataclass(frozen=True)
class CutBoundaryPrescanStrategy:
    """Resolve startup prescan settings and follower scheduling."""

    def fast_settings(self, settings: dict | None) -> dict:
        return fast_cut_boundary_prescan_settings(settings)

    def adaptive_plan(self, settings: dict | None, files: list[str] | None) -> dict:
        return cut_boundary_adaptive_prescan_plan(settings, files)


__all__ = [
    "CutBoundaryCandidateStrategy",
    "CutBoundaryPrescanStrategy",
]
