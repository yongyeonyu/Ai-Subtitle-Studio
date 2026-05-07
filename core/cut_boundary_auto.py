# Version: 03.13.07
# Phase: PHASE2
"""Auto grid cut-boundary scan installer orchestration."""

from __future__ import annotations

from core.cut_boundary_auto_profile import build_auto_grid_profile_helpers
from core.cut_boundary_auto_scan import build_auto_grid_scan_helpers
from core.cut_boundary_auto_utils import build_auto_grid_verify_utils
from core.cut_boundary_auto_verify import build_strict_verify_helpers


def install_auto_grid_v3(namespace: dict) -> None:
    normalize_fps = namespace["normalize_fps"]
    sec_to_frame = namespace["sec_to_frame"]
    normalize_cut_boundaries = namespace["normalize_cut_boundaries"]
    normalize_cut_boundary_level = namespace["normalize_cut_boundary_level"]
    cut_boundary_level = namespace["cut_boundary_level"]
    _selected_grid_delta = namespace["_selected_grid_delta"]
    _cb_level_interval_sec = namespace["_cb_level_interval_sec"]
    _cb_level_effective_threshold = namespace["_cb_level_effective_threshold"]
    _cb_level_min_gap_sec = namespace["_cb_level_min_gap_sec"]
    _cb_cuda_available = namespace["_cb_cuda_available"]

    profile_helpers = build_auto_grid_profile_helpers(cut_boundary_level)
    CUT_BOUNDARY_LEVEL_CHOICES = profile_helpers["CUT_BOUNDARY_LEVEL_CHOICES"]
    CUT_BOUNDARY_GRID_PROFILES = profile_helpers["CUT_BOUNDARY_GRID_PROFILES"]
    cut_boundary_scan_profile = profile_helpers["cut_boundary_scan_profile"]
    _auto_level_positions = profile_helpers["_auto_level_positions"]
    _auto_grid_cells = profile_helpers["_auto_grid_cells"]
    _grid_cell_slices = profile_helpers["_grid_cell_slices"]
    _auto_5x5_positions_for_level = profile_helpers["_auto_5x5_positions_for_level"]

    verify_utils = build_auto_grid_verify_utils(lambda width, height: _auto_grid_cells(width, height))
    _auto_gray_delta = verify_utils["_auto_gray_delta"]
    _auto_color_avg_delta = verify_utils["_auto_color_avg_delta"]
    _mps_available = verify_utils["_mps_available"]
    _auto_gray_delta_mps = verify_utils["_auto_gray_delta_mps"]
    _auto_color_avg_delta_mps = verify_utils["_auto_color_avg_delta_mps"]
    _auto_capture_verify_maps = verify_utils["_auto_capture_verify_maps"]
    _auto_downscale_frame_for_compare = verify_utils["_auto_downscale_frame_for_compare"]

    strict_helpers = build_strict_verify_helpers(
        {
            "normalize_cut_boundary_level": normalize_cut_boundary_level,
            "get_level_positions": _auto_level_positions,
            "_auto_capture_verify_maps": _auto_capture_verify_maps,
            "_auto_gray_delta": _auto_gray_delta,
            "_auto_color_avg_delta": _auto_color_avg_delta,
            "_auto_gray_delta_mps": _auto_gray_delta_mps,
            "_auto_color_avg_delta_mps": _auto_color_avg_delta_mps,
            "_mps_available": _mps_available,
        }
    )
    _auto_grid_v3_manual_verify_strict = strict_helpers["_auto_grid_v3_manual_verify_strict"]
    _auto_grid_v3_manual_verify_strict_mps = strict_helpers["_auto_grid_v3_manual_verify_strict_mps"]

    scan_helpers = build_auto_grid_scan_helpers(
        {
            "normalize_fps": normalize_fps,
            "sec_to_frame": sec_to_frame,
            "normalize_cut_boundaries": normalize_cut_boundaries,
            "normalize_cut_boundary_level": normalize_cut_boundary_level,
            "_selected_grid_delta": _selected_grid_delta,
            "_auto_downscale_frame_for_compare": _auto_downscale_frame_for_compare,
            "_cb_level_interval_sec": _cb_level_interval_sec,
            "_cb_level_effective_threshold": _cb_level_effective_threshold,
            "_cb_level_min_gap_sec": _cb_level_min_gap_sec,
            "_cb_cuda_available": _cb_cuda_available,
            "_auto_grid_v3_manual_verify_strict": _auto_grid_v3_manual_verify_strict,
            "_auto_grid_v3_manual_verify_strict_mps": _auto_grid_v3_manual_verify_strict_mps,
            "_mps_available": _mps_available,
            "original_detect_media_cut_boundaries": namespace["detect_media_cut_boundaries"],
        }
    )
    detect_media_cut_boundaries = scan_helpers["detect_media_cut_boundaries"]
    scan_media_cut_boundary_provisionals = scan_helpers["scan_media_cut_boundary_provisionals"]
    verify_media_cut_boundary_rows = scan_helpers["verify_media_cut_boundary_rows"]
    _auto_grid_v3_original_detect_media_cut_boundaries = scan_helpers[
        "_auto_grid_v3_original_detect_media_cut_boundaries"
    ]

    namespace.update({
        "CUT_BOUNDARY_LEVEL_CHOICES": CUT_BOUNDARY_LEVEL_CHOICES,
        "CUT_BOUNDARY_GRID_PROFILES": CUT_BOUNDARY_GRID_PROFILES,
        "cut_boundary_scan_profile": cut_boundary_scan_profile,
        "detect_media_cut_boundaries": detect_media_cut_boundaries,
        "scan_media_cut_boundary_provisionals": scan_media_cut_boundary_provisionals,
        "verify_media_cut_boundary_rows": verify_media_cut_boundary_rows,
        "_auto_level_positions": _auto_level_positions,
        "_auto_grid_cells": _auto_grid_cells,
        "_grid_cell_slices": _grid_cell_slices,
        "_auto_5x5_positions_for_level": _auto_5x5_positions_for_level,
        "_auto_grid_v3_manual_verify_strict": _auto_grid_v3_manual_verify_strict,
        "_auto_grid_v3_manual_verify_strict_mps": _auto_grid_v3_manual_verify_strict_mps,
        "_auto_downscale_frame_for_compare": _auto_downscale_frame_for_compare,
        "_auto_grid_v3_original_detect_media_cut_boundaries": _auto_grid_v3_original_detect_media_cut_boundaries,
    })
