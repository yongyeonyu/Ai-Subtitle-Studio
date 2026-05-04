# Version: 03.13.07
# Phase: PHASE2
"""5x5 cut-boundary scan profile helpers."""

from __future__ import annotations


CUT_BOUNDARY_LEVEL_CHOICES = (
    ("off", "미사용"),
    ("low", "낮음 - 5×5 선택 9칸"),
    ("medium", "중간 - 5×5 선택 13칸"),
)

CUT_BOUNDARY_GRID_PROFILES = {
    "off": {
        "level": "off",
        "label": "미사용",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "off",
        "positions": (),
        "cell_count": 0,
    },
    "low": {
        "level": "low",
        "label": "중간 - 5×5 선택 9칸",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "custom9",
        "positions": (1, 3, 7, 10, 12, 14, 17, 21, 23),
        "cell_count": 9,
    },
    "medium": {
        "level": "medium",
        "label": "중간 - 5×5 선택 13칸",
        "grid": "5x5",
        "grid_size": 5,
        "mask": "custom13",
        "positions": (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24),
        "cell_count": 13,
    },
}


def _grid_cell_slices(width: int, height: int):
    """
    5×5 grid cell slices.
    index:
      0  1  2  3  4
      5  6  7  8  9
     10 11 12 13 14
     15 16 17 18 19
     20 21 22 23 24
    """
    xs = [
        0,
        width // 5,
        (width * 2) // 5,
        (width * 3) // 5,
        (width * 4) // 5,
        width,
    ]
    ys = [
        0,
        height // 5,
        (height * 2) // 5,
        (height * 3) // 5,
        (height * 4) // 5,
        height,
    ]

    cells = []
    for r in range(5):
        for c in range(5):
            cells.append((xs[c], ys[r], xs[c + 1], ys[r + 1]))
    return cells


def _auto_5x5_positions_for_level(level: str):
    level = str(level or "medium").lower()
    if level == "low":
        return (1, 3, 7, 10, 12, 14, 17, 21, 23)
    return (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24)


def _auto_level_positions(scan_profile=None, sample_positions=None):
    """
    strict color avg 검증에서 사용할 5×5 grid 위치.
    기존 3×3 sample_positions가 들어와도 level 기준 5×5로 재해석한다.
    """
    profile = scan_profile or {}
    level = ""
    if isinstance(profile, dict):
        level = str(profile.get("level", "") or "").lower()

    if isinstance(profile, dict) and int(profile.get("grid_size", 5) or 5) == 5:
        positions = profile.get("positions")
        if positions:
            try:
                return tuple(int(x) for x in positions)
            except Exception:
                pass

    return _auto_5x5_positions_for_level(level or "medium")


def _auto_grid_cells(width: int, height: int):
    """strict color avg 검증용 5×5 grid cells."""
    return _grid_cell_slices(width, height)


def build_auto_grid_profile_helpers(cut_boundary_level):
    def cut_boundary_scan_profile(settings: dict | None = None) -> dict:
        level = cut_boundary_level(settings or {})
        profile = dict(CUT_BOUNDARY_GRID_PROFILES.get(level, CUT_BOUNDARY_GRID_PROFILES["medium"]))
        profile["choices"] = CUT_BOUNDARY_LEVEL_CHOICES
        return profile

    return {
        "CUT_BOUNDARY_LEVEL_CHOICES": CUT_BOUNDARY_LEVEL_CHOICES,
        "CUT_BOUNDARY_GRID_PROFILES": CUT_BOUNDARY_GRID_PROFILES,
        "cut_boundary_scan_profile": cut_boundary_scan_profile,
        "_grid_cell_slices": _grid_cell_slices,
        "_auto_5x5_positions_for_level": _auto_5x5_positions_for_level,
        "_auto_level_positions": _auto_level_positions,
        "_auto_grid_cells": _auto_grid_cells,
    }
